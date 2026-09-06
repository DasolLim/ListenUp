-- Subscriptions: who is entitled to the paid features (docs/product/SUBSCRIPTION.md).
--
-- One row per user, mirroring Stripe. Stripe is the system of record for money;
-- this table is the system of record for *access*, so the backend can answer
-- "is this person paid?" without a network call on every request.
--
-- The webhook writes this table, not the checkout redirect: a user can close the
-- tab before returning, and the subscription still exists. Anything that trusts
-- the redirect will eventually hand out free access.

begin;

create table if not exists public.subscriptions (
  user_id                uuid primary key references public.users (id) on delete cascade,
  stripe_customer_id     text unique,
  stripe_subscription_id text unique,
  -- Mirrors Stripe's subscription status verbatim (trialing, active, past_due,
  -- canceled, incomplete, ...). Stored raw rather than mapped to a boolean so a
  -- billing question can be answered from our own data.
  status                 text not null default 'none',
  -- When the paid period ends. Access continues to this instant even after a
  -- cancellation, because the user already paid for it.
  current_period_end     timestamptz,
  trial_ends_at          timestamptz,
  -- Guards against out-of-order webhooks: Stripe retries and does not promise
  -- ordering, so an older event must never overwrite a newer state.
  updated_at             timestamptz not null default now()
);

create index if not exists subscriptions_customer_idx
  on public.subscriptions (stripe_customer_id);

alter table public.subscriptions enable row level security;

-- Read-only to the owner. There is deliberately no insert/update/delete policy:
-- only the webhook (service context) may write, or a user could grant themselves
-- a subscription by PATCHing their own row.
drop policy if exists "own subscription select" on public.subscriptions;
create policy "own subscription select" on public.subscriptions
  for select to authenticated
  using (user_id = (select public.current_user_id()));

-- Entitlement in one place, so the API and the database agree on what "paid"
-- means. Trialing counts as paid — that is the whole point of a trial — and a
-- cancelled subscription keeps access until the period it paid for runs out.
create or replace function public.has_paid_access(p_user_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select coalesce(
    (select
       (s.status in ('trialing', 'active'))
       or (s.status = 'canceled' and s.current_period_end > now())
     from public.subscriptions s
     where s.user_id = p_user_id),
    false
  )
$$;

revoke all on function public.has_paid_access(uuid) from public;
revoke execute on function public.has_paid_access(uuid) from anon;
grant execute on function public.has_paid_access(uuid) to authenticated;

commit;
