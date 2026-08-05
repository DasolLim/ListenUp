-- Rollback for 0004_clerk_auth.sql — restores Supabase Auth as the RLS source.
--
-- Safe to run as long as auth.users still contains the accounts (Clerk migration
-- does not delete them). public.users is left in place: dropping it would cascade
-- to every biometric row via the FK. Removing it is a separate, deliberate step
-- once Clerk is confirmed permanent.

begin;

-- Point foreign keys back at Supabase Auth.
alter table public.speaker_profiles
  drop constraint if exists speaker_profiles_owner_user_id_fkey;
alter table public.speaker_profiles
  add constraint speaker_profiles_owner_user_id_fkey
  foreign key (owner_user_id) references auth.users (id) on delete cascade;

alter table public.custom_voices
  drop constraint if exists custom_voices_owner_user_id_fkey;
alter table public.custom_voices
  add constraint custom_voices_owner_user_id_fkey
  foreign key (owner_user_id) references auth.users (id) on delete cascade;

-- Restore the original auth.uid() policies.
drop policy if exists "own profiles select" on public.speaker_profiles;
create policy "own profiles select" on public.speaker_profiles
  for select to authenticated using ((select auth.uid()) = owner_user_id);

drop policy if exists "own profiles insert" on public.speaker_profiles;
create policy "own profiles insert" on public.speaker_profiles
  for insert to authenticated with check ((select auth.uid()) = owner_user_id);

drop policy if exists "own profiles update" on public.speaker_profiles;
create policy "own profiles update" on public.speaker_profiles
  for update to authenticated
  using ((select auth.uid()) = owner_user_id)
  with check ((select auth.uid()) = owner_user_id);

drop policy if exists "own profiles delete" on public.speaker_profiles;
create policy "own profiles delete" on public.speaker_profiles
  for delete to authenticated using ((select auth.uid()) = owner_user_id);

drop policy if exists "own embeddings select" on public.speaker_embeddings;
create policy "own embeddings select" on public.speaker_embeddings
  for select to authenticated using (exists (
    select 1 from public.speaker_profiles p
    where p.id = profile_id and p.owner_user_id = (select auth.uid())));

drop policy if exists "own embeddings insert" on public.speaker_embeddings;
create policy "own embeddings insert" on public.speaker_embeddings
  for insert to authenticated with check (exists (
    select 1 from public.speaker_profiles p
    where p.id = profile_id and p.owner_user_id = (select auth.uid())));

drop policy if exists "own embeddings delete" on public.speaker_embeddings;
create policy "own embeddings delete" on public.speaker_embeddings
  for delete to authenticated using (exists (
    select 1 from public.speaker_profiles p
    where p.id = profile_id and p.owner_user_id = (select auth.uid())));

drop policy if exists "own consent select" on public.consent_records;
create policy "own consent select" on public.consent_records
  for select to authenticated using (exists (
    select 1 from public.speaker_profiles p
    where p.id = profile_id and p.owner_user_id = (select auth.uid())));

drop policy if exists "own consent insert" on public.consent_records;
create policy "own consent insert" on public.consent_records
  for insert to authenticated with check (exists (
    select 1 from public.speaker_profiles p
    where p.id = profile_id and p.owner_user_id = (select auth.uid())));

drop policy if exists "own consent update" on public.consent_records;
create policy "own consent update" on public.consent_records
  for update to authenticated
  using (exists (
    select 1 from public.speaker_profiles p
    where p.id = profile_id and p.owner_user_id = (select auth.uid())))
  with check (exists (
    select 1 from public.speaker_profiles p
    where p.id = profile_id and p.owner_user_id = (select auth.uid())));

drop policy if exists "own voices select" on public.custom_voices;
create policy "own voices select" on public.custom_voices
  for select to authenticated using ((select auth.uid()) = owner_user_id);

drop policy if exists "own voices insert" on public.custom_voices;
create policy "own voices insert" on public.custom_voices
  for insert to authenticated with check ((select auth.uid()) = owner_user_id);

drop policy if exists "own voices update" on public.custom_voices;
create policy "own voices update" on public.custom_voices
  for update to authenticated
  using ((select auth.uid()) = owner_user_id)
  with check ((select auth.uid()) = owner_user_id);

drop policy if exists "own voices delete" on public.custom_voices;
create policy "own voices delete" on public.custom_voices
  for delete to authenticated using ((select auth.uid()) = owner_user_id);

commit;
