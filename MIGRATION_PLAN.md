# MIGRATION_PLAN — Infrastructure Decisions & Future Migrations

**Purpose:** record what we run, what we plan to migrate to, and — equally important — the tools we evaluated and rejected, with the reasoning. Decisions here are revisited only when a stated **trigger** fires, not on preference.

| Layer | Today | Target | Status |
|---|---|---|---|
| Database | Supabase Postgres | AWS RDS Postgres → Aurora | **Deferred** (trigger-based) |
| Auth | Supabase Auth | **Clerk** | **Code done; cutover pending keys** |
| LLM routing | OpenRouter | Direct provider w/ DPA | Pending |
| Payments | — | Stripe (+ RevenueCat for iOS) | Pending |
| Backend host | Railway/Render | Cloud Run or Fly.io | Pending |

---

## 1. Database — stay on Supabase

### Decision

Keep Supabase Postgres. Do **not** migrate now.

### Why

- It is plain Postgres. There is no proprietary query layer to unwind later — the exit is `pg_dump`.
- Migrating produces **zero user-visible benefit** and consumes the time that should go to product and revenue.
- The migration is not "move the data" (see coupling below). Doing it early means rewriting our security model before we have customers who need it.

### What couples us to Supabase (measured, not estimated)

| Coupling | Extent | Migration cost |
|---|---|---|
| `auth.uid()` in RLS policies | **17 references across 19 policies** in 3 migrations | High — the real work |
| FK → `auth.users(id)` | `speaker_profiles`, `custom_voices` | Low — becomes a local `users` table |
| `extensions.vector(192 / 256)` | `0001`, `0002` | Low — pgvector lives in `public` on RDS |
| HNSW index `extensions.vector_cosine_ops` | `0002` | Low — but **rebuild, don't restore** |
| `match_slang_terms()` RPC (`security definer`, pinned `search_path`) | `0002` | Medium — becomes an app-side query or a plain SQL function |
| PostgREST `rest()` data layer | **15 call sites** in `backend/app` | Medium — rewrite to asyncpg/SQLAlchemy |
| `verify_user()` HTTP hop to `/auth/v1/user` | `app/supa.py` | Removed by the Clerk migration (latency win) |

### The thing we must not break

`backend/app/supa.py` holds **no service-role key**; every profile query runs with the caller's own JWT so **RLS is the enforcement layer**. A bug in application code cannot read another user's biometric rows. That property is the security model, and it is what a naive migration destroys.

Plain Postgres has no `auth.uid()`. On RDS the equivalent is a transaction-scoped session variable:

```sql
-- set by the app on connection acquire, inside the transaction
SET LOCAL app.user_id = '<uuid>';

-- policy becomes
using (owner_user_id = current_setting('app.user_id', true)::uuid)
```

This is the standard pattern, but it is a **downgrade in guarantee**: enforcement moves from "the database validates a JWT" to "the app remembered to set a variable."

Non-negotiable if we do this:
- The variable is set in **one** connection-acquire helper that no query path can bypass.
- A test asserts that a **missing** `app.user_id` returns **zero rows**, never all rows. (`current_setting(..., true)` returns NULL, and `col = NULL` is false — verify this rather than assume it.)

### Migration triggers — move only when one fires

- A customer contractually requires a **BAA covering the database**, VPC peering, or data residency.
- **Procurement** mandates AWS specifically.
- We outgrow Supabase's operational ceiling (connection limits, read replicas, storage).

### Target: RDS Postgres first — not Aurora

| | RDS Postgres | Aurora PostgreSQL |
|---|---|---|
| Cost floor | Lower, predictable | Higher (Serverless v2 still has a minimum) |
| Read replicas | Up to 5 | Up to 15, faster |
| Failover | Minutes | ~30s |
| Storage | Provisioned | Auto-scaling |
| pgvector + HNSW | ✅ | ✅ |
| HIPAA under AWS BAA | ✅ | ✅ |

**Aurora's advantages are read-scaling and HA we will not need for a long time, and its cost floor is real.** Go RDS first; move to Aurora when read replicas are demonstrably the bottleneck — not before.

### Phased plan (when triggered)

1. **Decouple auth first** (see §2). Removes 17 `auth.uid()` references from the critical path of *this* migration.
2. Replace the PostgREST `rest()` layer with asyncpg/SQLAlchemy behind the same function signatures; tests stay green.
3. Stand up RDS; port migrations with `extensions.` → `public.` and `auth.users` → local `users`.
4. Rewrite RLS to `current_setting('app.user_id')` + add the zero-rows guard test.
5. Data copy: `pg_dump`/`pg_restore` while small; **AWS DMS** for near-zero-downtime later.
6. **Rebuild HNSW indexes** post-restore rather than carrying them over.
7. Re-run the two-user RLS isolation test against RDS before cutover.

### Rejected alternatives

- **Neon** — excellent (branching, scale-to-zero, cheaper than Aurora). Rejected only because if we are moving at all, the trigger is an enterprise/compliance requirement that names AWS. Neon would be the pick if the trigger were cost or DX.
- **PlanetScale** — strong operationally, but our workload is Postgres-native (`pgvector`, HNSW, `security definer` functions). No reason to port.
- **Any non-relational store** — speaker embeddings, consent records, and RLS-enforced ownership are relational with hard integrity requirements. Never appropriate here.

---

## 2. Authentication — Clerk

### Decision

Migrate Supabase Auth → **Clerk**.

### Why Clerk

- **Fastest path to shipping paid web.** Native Next.js App Router support, prebuilt flows, and middleware — measured against a solo-founder time budget, this is the dominant factor right now.
- **B2B organizations, roles, and invitations are built in.** Schools and clinics are the plausible second market; hand-rolling orgs is weeks of work we would otherwise pay later.
- **Supabase supports Clerk as a third-party JWT issuer**, so the session token is accepted directly. ~~All 19 RLS policies stay untouched.~~ **Corrected — see below.**
- SOC 2, and a BAA available on higher tiers — required eventually because we store biometric data.
- Has an iOS SDK, so the Swift app is not blocked.

### Why not Auth0

- **Priced for companies with an enterprise sales motion.** Costs escalate sharply at the tiers where B2B features live — the wrong shape for a pre-revenue solo product.
- Its genuine advantage is **breadth of enterprise SSO/SAML/OIDC**, which we will not use for years. We would be paying for unused capability.
- Heavier integration and more configuration surface than Clerk for the same near-term outcome.
- **Reconsider if:** enterprise deals arrive demanding exotic SSO/SAML federation that Clerk's add-on cannot serve.

### Why not Firebase Auth (the close call)

Firebase was the strongest alternative and wins on three axes worth stating plainly:

- **Far more widely used** — more documentation, community answers, integrations, and longevity confidence.
- **Cheaper**, by a wide margin, particularly for free-tier users.
- **Better iOS SDK**, which matters for the planned Swift app.

**Chosen against because:** it has **no organization model** — orgs, roles, and invitations would be built by hand — and its Next.js web DX is materially slower to build against. We optimised for time-to-paid-web plus a ready B2B path.

**This is an accepted trade, not a free win.** See the tripwire below.

### Why not stay on Supabase Auth

- Weakest B2B story of the options: no first-class orgs/roles, limited enterprise SSO.
- Keeps auth and database coupled, so a future database migration would force an auth migration at the same time — on the system holding biometric data. Decoupling now is the point.

### Accepted risk + tripwire

**Clerk prices per monthly active user.** For paying subscribers this is a rounding error against subscription revenue. For a **large free tier** — plausible for an accessibility product — it scales badly.

> **Tripwire:** if free MAU materially outgrows paid, or the roadmap turns iOS-first before B2B materialises, re-evaluate Firebase. Both integrate with Supabase as third-party issuers, so the second migration is the same shape as the first.

Define the free-tier policy **before** committing to a paid Clerk plan — the free-tier decision, not the SDK, is what governs this cost.

### ⚠️ Correction — the RLS claim above was wrong

Verified against the live database before implementing:

```
auth.uid() type: uuid   owner_user_id type: uuid   public policies: 19
select 'user_2abcDEF456ghiJKL'::uuid
  → ERROR 22P02: invalid input syntax for type uuid
```

`auth.uid()` casts the JWT subject to `uuid`, and a Clerk subject (`user_2abc…`) is not one. **Every policy keyed on `auth.uid()` must change.** This makes the migration a schema change on the biometric tables, not the policy-free swap the plan assumed.

**Chosen fix: a mapping table, not text columns.** The documented Supabase+Clerk pattern is to store the Clerk subject in a `text` column and compare against `auth.jwt()->>'sub'` — but that means dropping the FK to `auth.users` and with it `on delete cascade`, which is an erasure control (BIPA/GDPR), not a convenience. Instead `public.users` maps the Clerk subject to an internal uuid once; every biometric table keeps `uuid` columns and cascading deletes, and only the FK target moves.

### Implementation status

| Piece | State |
|---|---|
| `0004_clerk_auth.sql` — mapping table, `current_user_id()`, `link_current_user()` RPC, FK repoint, 14 policies rewritten | **✅ Applied 2026-08-06** — verified below |
| `0004b_revoke_anon_execute` — closes anon EXECUTE the linter caught | **✅ Applied 2026-08-06** |
| `0004c_fix_fallback_uuid_cast` — makes the fallback total (QA-4 bug) | **✅ Applied 2026-08-06** |
| `0004_clerk_auth_rollback.sql` — restores `auth.uid()` policies | Written |
| `app/auth.py` — provider abstraction; Clerk verified locally against JWKS | **Done**, 11 tests |
| `verify_user()` delegates; still returns an internal uuid | **Done** — all 4 routes and 15 `rest()` sites unchanged |
| `lib/auth/token.ts` — provider-agnostic token/header helper | **Done**, 4 call sites migrated |
| `AUTH_PROVIDER` defaults to `supabase` | **Done** — deploying this changes nothing |
| Clerk sign-in UI (`AuthForm`, `Navbar`), `proxy.ts` guards | **Not done** — needs real keys |

**No service-role key was introduced.** `link_current_user()` is `security definer` and reads the subject from the verified JWT *inside Postgres*, so a caller cannot claim another identity, and the backend keeps holding no privileged key.

### Post-apply verification (2026-08-06, live project)

| Check | Result |
|---|---|
| Policies still on `auth.uid()` | **0** (was 14) |
| Policies on `current_user_id()` | **16** (14 biometric + 2 on `public.users`) |
| **Fail-closed:** identity without a JWT | **NULL** ✅ |
| Orphaned biometric rows | **0** |
| Accounts mapped into `public.users` | **4 / 4** |
| Voice profiles / embeddings intact | **3 / 3** |
| FK target + delete rule | `public.users`, **CASCADE preserved** ✅ |
| `anon` can execute the new functions | **No** (after `0004b`) |

Remaining linter warnings are pre-existing and not from this migration: `match_slang_terms` (from `0002`) is anon-executable, and Supabase Auth's leaked-password protection is off — a one-click dashboard toggle worth enabling.

### QA against the live database (simulated JWT claims, all rolled back)

| # | Scenario | Result |
|---|---|---|
| QA-1 | Anonymous — no JWT | identity NULL, **0 rows** ✅ |
| QA-2 | Supabase Auth session (dual-mode fallback) | identity resolves, sees own 3 profiles ✅ |
| QA-3 | **Two-user isolation** — a different account | **0 profiles / 0 embeddings / 0 consent** ✅ |
| QA-4 | Clerk subject with no mapping yet | **FAILED → fixed by `0004c`**, now NULL + 0 rows ✅ |
| QA-5 | Existing account's first Clerk sign-in | linked by email, keeps all 3 profiles ✅ |
| QA-6 | Erasure: delete identity row | cascades to profiles, embeddings, consent, voices ✅ |

**QA-4 was a real bug, found by testing rather than review.** The fallback called `auth.uid()`, which casts the JWT subject to uuid unconditionally. For a Clerk user's very first request — before `link_current_user()` creates their mapping — that raised `22P02`, turning every RLS-protected query into a 500 precisely where a new user starts. `0004c` casts only a uuid-shaped subject, so the fallback can no longer raise.

Post-QA state confirmed unchanged: 4 users, 4 accounts, 3 profiles, 3 embeddings, 3 consent records, 0 Clerk links.

**Still unverified:** end-to-end sign-in with a real Clerk token. The dual-mode fallback means existing Supabase logins are unaffected either way.

### Cutover runbook

Everything below the line is manual — it needs a Clerk account and dashboard access.

1. Create the Clerk application; enable **Sign in with Apple** now if iOS is planned (App Store Guideline 4.8).
2. In Supabase → Authentication → **Third-Party Auth**, add Clerk. In Clerk, add Supabase as an integration.
3. Apply `0004_clerk_auth.sql`, then run the three verification queries at the bottom of that file. **Do not skip #2** — it proves the policies fail closed.
4. Set `CLERK_ISSUER` and `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`; leave `AUTH_PROVIDER` unset for now.
5. Import users from Supabase into Clerk **with password hashes** (bcrypt) so nobody is forced through a reset. Match on email — `link_current_user()` links returning accounts to their existing profiles by email on first sign-in.
6. Replace the sign-in UI: `<ClerkProvider>` in `app/layout.tsx`, Clerk components in `AuthForm.tsx`/`Navbar.tsx`, and `clerkMiddleware` in `proxy.ts` guarding `/voice-to-text/*` and `/translate/*`.
7. Flip `AUTH_PROVIDER=clerk`. **Verify before announcing:** two-user isolation (user B cannot see A's profiles), enrollment, consent, export, and delete all work under a Clerk session, and a pre-existing account still sees its voice profiles.
8. Rollback if needed: unset `AUTH_PROVIDER`, run `0004_clerk_auth_rollback.sql`.

**Do this while the user count is small.** Every auth migration gets harder with scale, and this one touches the biometric-data access path.

---

## 3. Other decisions

### OpenRouter → direct provider (pending, compliance-driven)

Not a preference — a **gap**. Routing through OpenRouter means inheriting whichever underlying provider serves the request: data-handling terms vary per model, and a DPA or BAA is not realistically obtainable. Before paying customers exist, move to **one provider under a commercial agreement** with a DPA and zero-retention / no-training terms.

Cheap to do: `services/openrouter/` already has the base/real/mock split, so this is one module swap.

### Deliberately keeping

- **AssemblyAI** — SOC 2, DPA, BAA available. Already correct.
- **Self-hosted ECAPA-TDNN** — biometric embeddings never leave our infrastructure. This removes a subprocessor from the highest-risk data category and is a genuine competitive and compliance asset. **Do not outsource this.**
- **Sentry / PostHog** — standard. Audit that transcript content is never attached to events.

---

## 4. Sequencing rule

**Auth first, database second, never both at once.**

Both migrations touch the RLS-enforced biometric access path. Done together, we would be rewriting the security model and the data-access layer simultaneously on the most sensitive data we hold. Done in order, the Clerk migration leaves RLS entirely untouched, and the database migration inherits an auth layer that is already independent.
