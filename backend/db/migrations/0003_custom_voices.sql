-- Custom (cloned) TTS voices.
--
-- A cloned voice can say words the person never said, so it is biometric data
-- with the same obligations as speaker_profiles in 0001: owner-only RLS,
-- recorded consent from the person being cloned, and a hard delete path.
--
-- The audio SAMPLE is deliberately not stored. The provider holds the voice
-- model; we keep only the handle plus the consent record. That matches the
-- "no audio stored by default" privacy default (INTRODUCTION §6) and means a
-- breach of our database cannot leak someone's voice recording.

create table if not exists public.custom_voices (
  id                    uuid primary key default gen_random_uuid(),
  owner_user_id         uuid not null references auth.users (id) on delete cascade,
  display_name          text not null,
  -- Voice id at the TTS provider (e.g. ElevenLabs). Not a secret, but useless
  -- without our API key.
  provider_voice_id     text not null,
  provider              text not null default 'elevenlabs',
  language              text not null default 'en',
  -- Consent, inlined rather than in a separate table: a voice clone has exactly
  -- one consenting person, unlike a profile which can gain samples over time.
  consented_by          text not null,
  consent_text_version  text not null,
  consented_at          timestamptz not null default now(),
  created_at            timestamptz not null default now(),
  constraint custom_voices_consent_present check (length(trim(consented_by)) > 0)
);

create index if not exists custom_voices_owner_idx
  on public.custom_voices (owner_user_id);

-- One provider voice belongs to one row, so deletes can't orphan a clone.
create unique index if not exists custom_voices_provider_voice_idx
  on public.custom_voices (provider_voice_id);

alter table public.custom_voices enable row level security;

create policy "own voices select" on public.custom_voices
  for select to authenticated
  using ((select auth.uid()) = owner_user_id);

create policy "own voices insert" on public.custom_voices
  for insert to authenticated
  with check ((select auth.uid()) = owner_user_id);

create policy "own voices update" on public.custom_voices
  for update to authenticated
  using ((select auth.uid()) = owner_user_id)
  with check ((select auth.uid()) = owner_user_id);

create policy "own voices delete" on public.custom_voices
  for delete to authenticated
  using ((select auth.uid()) = owner_user_id);
