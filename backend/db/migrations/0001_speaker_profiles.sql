-- Phase 3.1: speaker profiles (biometric voice embeddings) + consent records.
-- Voice embeddings are biometric data (BIPA/GDPR/Quebec Law 25): consent is a
-- first-class record, deletion cascades, and RLS isolates every user's data.

create extension if not exists vector with schema extensions;

-- Who the user has enrolled (e.g. "Mom") — owned by the enrolling account.
create table public.speaker_profiles (
  id uuid primary key default gen_random_uuid(),
  owner_user_id uuid not null references auth.users (id) on delete cascade,
  display_name text not null check (char_length(display_name) between 1 and 60),
  created_at timestamptz not null default now()
);

-- 192-dim ECAPA-TDNN embeddings; several per profile (enrollment + corrections).
create table public.speaker_embeddings (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references public.speaker_profiles (id) on delete cascade,
  embedding extensions.vector(192) not null,
  source text not null default 'enrollment' check (source in ('enrollment', 'correction')),
  created_at timestamptz not null default now()
);

-- Consent of the ENROLLED PERSON (not just the account holder).
create table public.consent_records (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references public.speaker_profiles (id) on delete cascade,
  consented_by text not null check (char_length(consented_by) between 1 and 120),
  consent_text_version text not null,
  consented_at timestamptz not null default now(),
  revoked_at timestamptz
);

create index speaker_profiles_owner_idx on public.speaker_profiles (owner_user_id);
create index speaker_embeddings_profile_idx on public.speaker_embeddings (profile_id);
create index consent_records_profile_idx on public.consent_records (profile_id);

alter table public.speaker_profiles enable row level security;
alter table public.speaker_embeddings enable row level security;
alter table public.consent_records enable row level security;

-- Profiles: owner-only, full lifecycle.
create policy "own profiles select" on public.speaker_profiles
  for select to authenticated
  using ((select auth.uid()) = owner_user_id);

create policy "own profiles insert" on public.speaker_profiles
  for insert to authenticated
  with check ((select auth.uid()) = owner_user_id);

create policy "own profiles update" on public.speaker_profiles
  for update to authenticated
  using ((select auth.uid()) = owner_user_id)
  with check ((select auth.uid()) = owner_user_id);

create policy "own profiles delete" on public.speaker_profiles
  for delete to authenticated
  using ((select auth.uid()) = owner_user_id);

-- Embeddings + consent: access only through an owned profile.
create policy "own embeddings select" on public.speaker_embeddings
  for select to authenticated
  using (exists (
    select 1 from public.speaker_profiles p
    where p.id = profile_id and p.owner_user_id = (select auth.uid())
  ));

create policy "own embeddings insert" on public.speaker_embeddings
  for insert to authenticated
  with check (exists (
    select 1 from public.speaker_profiles p
    where p.id = profile_id and p.owner_user_id = (select auth.uid())
  ));

create policy "own embeddings delete" on public.speaker_embeddings
  for delete to authenticated
  using (exists (
    select 1 from public.speaker_profiles p
    where p.id = profile_id and p.owner_user_id = (select auth.uid())
  ));

create policy "own consent select" on public.consent_records
  for select to authenticated
  using (exists (
    select 1 from public.speaker_profiles p
    where p.id = profile_id and p.owner_user_id = (select auth.uid())
  ));

create policy "own consent insert" on public.consent_records
  for insert to authenticated
  with check (exists (
    select 1 from public.speaker_profiles p
    where p.id = profile_id and p.owner_user_id = (select auth.uid())
  ));

create policy "own consent update" on public.consent_records
  for update to authenticated
  using (exists (
    select 1 from public.speaker_profiles p
    where p.id = profile_id and p.owner_user_id = (select auth.uid())
  ))
  with check (exists (
    select 1 from public.speaker_profiles p
    where p.id = profile_id and p.owner_user_id = (select auth.uid())
  ));
