-- Phase 5.1: slang knowledge base (curated dictionary) + gap log.
-- Unlike speaker data (private biometric, per-user RLS in 0001), the slang KB is
-- a SHARED, public-read reference. Writes are limited to authenticated admins;
-- the gap log records searched-but-missing terms to guide curation (Step 5.5).
-- Embeddings are 256-dim (services/genz/base.py EMBED_DIM); the `vector`
-- extension is already installed by migration 0001.

create table public.slang_terms (
  id uuid primary key default gen_random_uuid(),
  term text not null unique check (char_length(term) between 1 and 120),
  meaning text not null default '',
  origin text not null default '',
  region text not null default '',
  first_seen text not null default '',
  example text not null default '',
  adult_friendly_explanation text not null default '',
  embedding extensions.vector(256),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Searched terms that had no confident KB match — the curation backlog.
create table public.slang_gap_log (
  id uuid primary key default gen_random_uuid(),
  query text not null check (char_length(query) between 1 and 200),
  created_at timestamptz not null default now()
);

-- Cosine ANN index for vector search (pgvector HNSW).
create index slang_terms_embedding_idx on public.slang_terms
  using hnsw (embedding extensions.vector_cosine_ops);
create index slang_gap_log_created_idx on public.slang_gap_log (created_at desc);

alter table public.slang_terms enable row level security;
alter table public.slang_gap_log enable row level security;

-- The dictionary is public to read (anon + authenticated).
create policy "slang read" on public.slang_terms
  for select to anon, authenticated using (true);

-- Only signed-in users (admins in practice) may curate entries.
create policy "slang insert" on public.slang_terms
  for insert to authenticated with check (true);
create policy "slang update" on public.slang_terms
  for update to authenticated using (true) with check (true);

-- Anyone can contribute a gap (a missing-term search); reads are admin-only.
create policy "gap insert" on public.slang_gap_log
  for insert to anon, authenticated with check (true);
create policy "gap read" on public.slang_gap_log
  for select to authenticated using (true);

-- Vector similarity search callable by anon (the runtime reads with the anon key).
-- Returns cosine similarity in [0,1]; higher = closer.
create or replace function public.match_slang_terms(
  query_embedding extensions.vector(256),
  match_count int default 3
)
returns table (
  id uuid,
  term text,
  meaning text,
  origin text,
  region text,
  first_seen text,
  example text,
  adult_friendly_explanation text,
  similarity float
)
language sql stable security definer set search_path = public, extensions as $$
  select s.id, s.term, s.meaning, s.origin, s.region, s.first_seen, s.example,
         s.adult_friendly_explanation,
         1 - (s.embedding <=> query_embedding) as similarity
  from public.slang_terms s
  where s.embedding is not null
  order by s.embedding <=> query_embedding
  limit greatest(1, least(match_count, 20));
$$;
