-- Auth migration: Supabase Auth -> Clerk (MIGRATION_PLAN.md §2).
--
-- WHY THIS FILE EXISTS AT ALL
-- The plan assumed the 19 RLS policies could stay untouched because Supabase
-- accepts Clerk as a third-party JWT issuer. That is only half true. `auth.uid()`
-- casts the JWT subject to uuid, and a Clerk subject is not a uuid:
--
--   select 'user_2abcDEF456ghiJKL'::uuid
--   ERROR 22P02: invalid input syntax for type uuid
--
-- So every policy keyed on auth.uid() has to change. The question was only how.
--
-- WHY A MAPPING TABLE RATHER THAN text COLUMNS
-- The documented Supabase+Clerk pattern is to store the Clerk subject directly
-- in a text column and compare against auth.jwt()->>'sub'. That would mean
-- dropping the FK to auth.users, and with it `on delete cascade` — the guarantee
-- that deleting a user destroys their biometric rows. That cascade is a
-- compliance control (BIPA/GDPR erasure), not a convenience, so it is not
-- something to reimplement in application code.
--
-- Instead the Clerk subject is mapped to an internal uuid exactly once, here.
-- Every biometric table keeps `owner_user_id uuid` and keeps cascading deletes;
-- only the FK target moves from auth.users to public.users. Application code and
-- all 15 rest() call sites are unaffected, because verify_user() keeps returning
-- an internal uuid.
--
-- IDEMPOTENT and REVERSIBLE (see 0004_clerk_auth_rollback.sql).
-- Apply during a maintenance window: policies are dropped and recreated, so a
-- request racing this migration could see a table with RLS enabled and no
-- matching policy — which fails closed (no rows), never open.

begin;

-- ── 1. Identity mapping ──────────────────────────────────────────────────────
-- One row per human. `id` is the internal identifier every other table already
-- references; `clerk_user_id` is the external subject Clerk puts in the JWT.
create table if not exists public.users (
  id            uuid primary key default gen_random_uuid(),
  -- Nullable on purpose: rows backfilled from auth.users below have no Clerk id
  -- until that person signs in through Clerk for the first time, at which point
  -- the backend links them by email. Unique so a Clerk account cannot be
  -- attached to two internal users.
  clerk_user_id text unique,
  email         text,
  created_at    timestamptz not null default now()
);

create index if not exists users_clerk_idx on public.users (clerk_user_id);
create index if not exists users_email_idx on public.users (lower(email));

-- Preserve existing ids so every biometric row keeps pointing at the same
-- person. This is what makes the migration non-destructive.
insert into public.users (id, email)
select id, email from auth.users
on conflict (id) do nothing;

-- ── 2. The uuid that policies compare against ────────────────────────────────
-- Resolves the Clerk subject in the request JWT to an internal user id.
--
-- `stable` lets the planner call this once per statement rather than per row.
-- `security definer` with a pinned search_path so the lookup works regardless of
-- the caller's own read permissions on public.users, and cannot be hijacked by a
-- search_path shadowing attack.
create or replace function public.current_user_id()
returns uuid
language sql
stable
security definer
set search_path = public
as $$
  select u.id
  from public.users u
  where u.clerk_user_id = (select auth.jwt() ->> 'sub')
$$;

revoke all on function public.current_user_id() from public;
grant execute on function public.current_user_id() to authenticated;

-- Resolve the caller to an internal uuid, creating or linking the row on first
-- sign-in. Called once per session by the backend.
--
-- The Clerk subject is read from the verified JWT *inside* this function rather
-- than passed in, so a caller cannot claim someone else's identity. That is what
-- lets this be `security definer` — and what lets the backend keep holding no
-- service-role key.
create or replace function public.link_current_user(p_email text default null)
returns uuid
language plpgsql
security definer
set search_path = public
as $$
declare
  v_subject text := (select auth.jwt() ->> 'sub');
  v_id      uuid;
begin
  if v_subject is null or v_subject = '' then
    raise exception 'no authenticated subject' using errcode = '28000';
  end if;

  select id into v_id from public.users where clerk_user_id = v_subject;
  if v_id is not null then
    return v_id;
  end if;

  -- Account that predates the migration: attach the Clerk subject to it so the
  -- person keeps their enrolled voice profiles instead of silently starting
  -- empty. Matched case-insensitively; only rows not already claimed.
  if p_email is not null and p_email <> '' then
    update public.users
      set clerk_user_id = v_subject
      where clerk_user_id is null and lower(email) = lower(p_email)
      returning id into v_id;
    if v_id is not null then
      return v_id;
    end if;
  end if;

  -- New account. ON CONFLICT makes concurrent first requests idempotent rather
  -- than letting one of them fail on the unique index.
  insert into public.users (clerk_user_id, email)
  values (v_subject, nullif(p_email, ''))
  on conflict (clerk_user_id)
    do update set email = coalesce(excluded.email, public.users.email)
  returning id into v_id;

  return v_id;
end;
$$;

revoke all on function public.link_current_user(text) from public;
grant execute on function public.link_current_user(text) to authenticated;

-- Users may read and update only their own mapping row. No insert or delete
-- policy: rows are created by the backend and removed only by account deletion,
-- so the client can never mint or drop an identity.
alter table public.users enable row level security;

drop policy if exists "own user row select" on public.users;
create policy "own user row select" on public.users
  for select to authenticated
  using (id = (select public.current_user_id()));

drop policy if exists "own user row update" on public.users;
create policy "own user row update" on public.users
  for update to authenticated
  using (id = (select public.current_user_id()))
  with check (id = (select public.current_user_id()));

-- ── 3. Repoint foreign keys: auth.users -> public.users ──────────────────────
-- The column type and the cascade are unchanged; only the referenced table moves.
alter table public.speaker_profiles
  drop constraint if exists speaker_profiles_owner_user_id_fkey;
alter table public.speaker_profiles
  add constraint speaker_profiles_owner_user_id_fkey
  foreign key (owner_user_id) references public.users (id) on delete cascade;

alter table public.custom_voices
  drop constraint if exists custom_voices_owner_user_id_fkey;
alter table public.custom_voices
  add constraint custom_voices_owner_user_id_fkey
  foreign key (owner_user_id) references public.users (id) on delete cascade;

-- ── 4. Rewrite every policy that used auth.uid() ─────────────────────────────
-- Same logic, same shape; only the source of the caller's uuid changes.

-- speaker_profiles
drop policy if exists "own profiles select" on public.speaker_profiles;
create policy "own profiles select" on public.speaker_profiles
  for select to authenticated
  using ((select public.current_user_id()) = owner_user_id);

drop policy if exists "own profiles insert" on public.speaker_profiles;
create policy "own profiles insert" on public.speaker_profiles
  for insert to authenticated
  with check ((select public.current_user_id()) = owner_user_id);

drop policy if exists "own profiles update" on public.speaker_profiles;
create policy "own profiles update" on public.speaker_profiles
  for update to authenticated
  using ((select public.current_user_id()) = owner_user_id)
  with check ((select public.current_user_id()) = owner_user_id);

drop policy if exists "own profiles delete" on public.speaker_profiles;
create policy "own profiles delete" on public.speaker_profiles
  for delete to authenticated
  using ((select public.current_user_id()) = owner_user_id);

-- speaker_embeddings (reached only through an owned profile)
drop policy if exists "own embeddings select" on public.speaker_embeddings;
create policy "own embeddings select" on public.speaker_embeddings
  for select to authenticated
  using (exists (
    select 1 from public.speaker_profiles p
    where p.id = profile_id and p.owner_user_id = (select public.current_user_id())
  ));

drop policy if exists "own embeddings insert" on public.speaker_embeddings;
create policy "own embeddings insert" on public.speaker_embeddings
  for insert to authenticated
  with check (exists (
    select 1 from public.speaker_profiles p
    where p.id = profile_id and p.owner_user_id = (select public.current_user_id())
  ));

drop policy if exists "own embeddings delete" on public.speaker_embeddings;
create policy "own embeddings delete" on public.speaker_embeddings
  for delete to authenticated
  using (exists (
    select 1 from public.speaker_profiles p
    where p.id = profile_id and p.owner_user_id = (select public.current_user_id())
  ));

-- consent_records
drop policy if exists "own consent select" on public.consent_records;
create policy "own consent select" on public.consent_records
  for select to authenticated
  using (exists (
    select 1 from public.speaker_profiles p
    where p.id = profile_id and p.owner_user_id = (select public.current_user_id())
  ));

drop policy if exists "own consent insert" on public.consent_records;
create policy "own consent insert" on public.consent_records
  for insert to authenticated
  with check (exists (
    select 1 from public.speaker_profiles p
    where p.id = profile_id and p.owner_user_id = (select public.current_user_id())
  ));

drop policy if exists "own consent update" on public.consent_records;
create policy "own consent update" on public.consent_records
  for update to authenticated
  using (exists (
    select 1 from public.speaker_profiles p
    where p.id = profile_id and p.owner_user_id = (select public.current_user_id())
  ))
  with check (exists (
    select 1 from public.speaker_profiles p
    where p.id = profile_id and p.owner_user_id = (select public.current_user_id())
  ));

-- custom_voices
drop policy if exists "own voices select" on public.custom_voices;
create policy "own voices select" on public.custom_voices
  for select to authenticated
  using ((select public.current_user_id()) = owner_user_id);

drop policy if exists "own voices insert" on public.custom_voices;
create policy "own voices insert" on public.custom_voices
  for insert to authenticated
  with check ((select public.current_user_id()) = owner_user_id);

drop policy if exists "own voices update" on public.custom_voices;
create policy "own voices update" on public.custom_voices
  for update to authenticated
  using ((select public.current_user_id()) = owner_user_id)
  with check ((select public.current_user_id()) = owner_user_id);

drop policy if exists "own voices delete" on public.custom_voices;
create policy "own voices delete" on public.custom_voices
  for delete to authenticated
  using ((select public.current_user_id()) = owner_user_id);

commit;

-- ── Post-apply verification (run these, don't assume) ────────────────────────
-- 1. No policy still depends on auth.uid(). Check BOTH columns: an INSERT
--    policy's condition lives in `with_check`, not `qual`, so querying `qual`
--    alone reports success while insert policies are still on the old identity
--    (on this database, `qual` alone finds 10 of the 14 affected policies).
--      select policyname, tablename from pg_policies
--      where schemaname='public'
--        and (coalesce(qual::text,'') || coalesce(with_check::text,'')) like '%auth.uid%';
--    -> expect 0 rows
--
-- 2. An unauthenticated caller sees nothing rather than everything.
--    current_user_id() returns NULL with no JWT, and `col = NULL` is false,
--    so every policy fails closed:
--      select public.current_user_id();          -> NULL
--      select count(*) from public.speaker_profiles;  -> 0 as anon
--
-- 3. Every biometric row still resolves to a person:
--      select count(*) from public.speaker_profiles p
--      left join public.users u on u.id = p.owner_user_id where u.id is null;
--    -> expect 0 rows
