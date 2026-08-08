-- Three tiers + metered usage (SUBSCRIPTION.md §10).
--
-- Two things are added here:
--
--   1. `subscriptions.tier` — which plan the Stripe price maps to. Entitlement
--      was previously boolean ("paid or not"); with Basic and Pro it has to say
--      *which*, because they differ in allowance rather than in feature list.
--
--   2. `usage` — one aggregated row per user per billing period. Aggregated,
--      not an event log: this is read on every gated request, so it must be a
--      single indexed lookup, not a sum over a growing table.
--
-- The interesting decision is how usage is *written*. The obvious route is the
-- service role, but that key bypasses RLS on every table including the biometric
-- ones, and its blast radius is already deliberately capped (app/supa.py). So
-- instead the user's own token calls a security-definer function that can only
-- ever *add* to their own row. A user cannot zero their meter, cannot touch
-- anyone else's, and the service-role allowlist stays at one table.

begin;

-- ── 1. Which plan a subscription is on ───────────────────────────────────────
alter table public.subscriptions
  add column if not exists tier text not null default 'free';

-- Cancelled/expired rows keep their tier for history; entitlement is decided by
-- status + current_period_end, exactly as before.
comment on column public.subscriptions.tier is
  'free | basic | pro — resolved from the Stripe price id by the webhook.';

-- ── 2. Metered usage, one row per user per billing period ────────────────────
create table if not exists public.usage (
  user_id           uuid not null references public.users (id) on delete cascade,
  -- The start of the billing period this row counts. Rows are never deleted or
  -- reset; a new period simply gets a new row, which leaves the previous period
  -- intact for support questions ("what did I actually use last month?").
  period_start      timestamptz not null,
  caption_seconds   bigint not null default 0,
  translated_chars  bigint not null default 0,
  explain_lookups   bigint not null default 0,
  cloud_tts_seconds bigint not null default 0,
  updated_at        timestamptz not null default now(),
  primary key (user_id, period_start)
);

alter table public.usage enable row level security;

-- Read-only to the owner, and only via this policy. There is no insert/update
-- policy at all: every write goes through record_usage() below, so there is no
-- path by which a user can set their own counters to zero.
drop policy if exists "own usage select" on public.usage;
create policy "own usage select" on public.usage
  for select to authenticated
  using (user_id = (select public.current_user_id()));

-- ── 3. When the current period started ───────────────────────────────────────
-- Anchored on the Stripe billing anniversary, never the 1st of the month: the
-- allowance should renew when the payment does. Free users have no Stripe
-- period, so they anchor on their signup day instead — still an anniversary,
-- still not the 1st, and it means a free user who signs up on the 28th doesn't
-- get a three-day month.
create or replace function public.usage_period_start(p_user_id uuid)
returns timestamptz
language plpgsql
stable
security definer
set search_path = public
as $$
declare
  v_period_end timestamptz;
  v_anchor     timestamptz;
  v_months     int;
begin
  select s.current_period_end into v_period_end
    from public.subscriptions s
   where s.user_id = p_user_id
     and s.current_period_end is not null
     and s.current_period_end > now();

  if v_period_end is not null then
    -- Stripe periods are monthly for every plan we sell.
    return v_period_end - interval '1 month';
  end if;

  select u.created_at into v_anchor from public.users u where u.id = p_user_id;
  if v_anchor is null then
    return date_trunc('month', now());
  end if;

  -- Most recent monthly anniversary of the anchor, at or before now. Postgres
  -- clamps overflow correctly (Jan 31 + 1 month = Feb 28), which is why this is
  -- month arithmetic rather than a 30-day interval.
  v_months := (extract(year from age(now(), v_anchor)) * 12
               + extract(month from age(now(), v_anchor)))::int;
  return v_anchor + (v_months || ' months')::interval;
end;
$$;

-- ── 4. The only way usage is written ─────────────────────────────────────────
-- Increment-only, own-row-only, positive-only. The metric name is matched
-- against a fixed set rather than interpolated into SQL — a dynamic column name
-- here would be an injection point reachable by any signed-in user.
create or replace function public.record_usage(p_metric text, p_amount bigint)
returns void
language plpgsql
volatile
security definer
set search_path = public
as $$
declare
  v_user   uuid;
  v_start  timestamptz;
begin
  if p_amount is null or p_amount <= 0 then
    return;  -- nothing to add; never a way to subtract
  end if;

  v_user := public.current_user_id();
  if v_user is null then
    raise exception 'record_usage requires an authenticated caller';
  end if;

  if p_metric not in ('captions', 'translated', 'explain', 'cloud_tts') then
    raise exception 'unknown usage metric: %', p_metric;
  end if;

  v_start := public.usage_period_start(v_user);

  insert into public.usage as u (
    user_id, period_start,
    caption_seconds, translated_chars, explain_lookups, cloud_tts_seconds
  )
  values (
    v_user, v_start,
    case when p_metric = 'captions'   then p_amount else 0 end,
    case when p_metric = 'translated' then p_amount else 0 end,
    case when p_metric = 'explain'    then p_amount else 0 end,
    case when p_metric = 'cloud_tts'  then p_amount else 0 end
  )
  on conflict (user_id, period_start) do update set
    caption_seconds   = u.caption_seconds
                        + case when p_metric = 'captions'   then p_amount else 0 end,
    translated_chars  = u.translated_chars
                        + case when p_metric = 'translated' then p_amount else 0 end,
    explain_lookups   = u.explain_lookups
                        + case when p_metric = 'explain'    then p_amount else 0 end,
    cloud_tts_seconds = u.cloud_tts_seconds
                        + case when p_metric = 'cloud_tts'  then p_amount else 0 end,
    updated_at        = now();
end;
$$;

-- ── 5. Reading the meters ────────────────────────────────────────────────────
-- One call returns the current period's totals plus its boundaries, so a gated
-- request is a single round trip rather than "work out the period, then query".
create or replace function public.current_usage()
returns table (
  period_start      timestamptz,
  period_end        timestamptz,
  caption_seconds   bigint,
  translated_chars  bigint,
  explain_lookups   bigint,
  cloud_tts_seconds bigint
)
language plpgsql
stable
security definer
set search_path = public
as $$
declare
  v_user  uuid;
  v_start timestamptz;
begin
  v_user := public.current_user_id();
  if v_user is null then
    raise exception 'current_usage requires an authenticated caller';
  end if;

  v_start := public.usage_period_start(v_user);

  return query
    select
      v_start,
      v_start + interval '1 month',
      coalesce(u.caption_seconds, 0),
      coalesce(u.translated_chars, 0),
      coalesce(u.explain_lookups, 0),
      coalesce(u.cloud_tts_seconds, 0)
    from (select 1) _
    left join public.usage u
      on u.user_id = v_user and u.period_start = v_start;
end;
$$;

-- Security-definer functions are executable by `public` (and therefore `anon`)
-- by default in Supabase — the lesson from migration 0004b. Anonymous callers
-- have no current_user_id(), so these would raise rather than leak, but an
-- endpoint that raises for anon is still an endpoint anon can reach.
revoke all on function public.usage_period_start(uuid) from public;
revoke all on function public.record_usage(text, bigint) from public;
revoke all on function public.current_usage() from public;
revoke execute on function public.usage_period_start(uuid) from anon;
revoke execute on function public.record_usage(text, bigint) from anon;
revoke execute on function public.current_usage() from anon;
grant execute on function public.usage_period_start(uuid) to authenticated;
grant execute on function public.record_usage(text, bigint) to authenticated;
grant execute on function public.current_usage() to authenticated;

commit;
