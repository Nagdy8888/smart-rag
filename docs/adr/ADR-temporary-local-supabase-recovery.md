# Temporary local Supabase during hosted recovery

Status: accepted for development, 2026-10-22.

Authorization: the user requested open-source Supabase to continue agent
development while the hosted project is unavailable. This temporarily supersedes
the development-only restriction in ADR-cloud-only-supabase-no-local-fixture.

The hosted project, its configuration, and the verified checkpoint archive remain
intact. Local development uses a separate Docker project and persistent volumes.
Do not link, push migrations to, reset, or restore over the hosted project.

Use the Supabase CLI Docker stack with Postgres 17, Auth, PostgREST, Kong, and
Storage. Disable optional services to limit laptop disk and memory use. Bind
published ports to loopback using the dedicated Docker network. Never publish
this development stack through Vercel, tunnels, or a public interface.

Apply the repository migrations to the fresh local database. Use separate runtime
login wrappers and existing NOLOGIN application roles; keep RLS, budgets, and
asymmetric JWT verification enabled. Store signing keys and local credentials in
gitignored files. Keep local overrides separate from hosted environment files.

The checkpoint archive is not a full application backup. Do not restore orphaned
hosted checkpoints as if their users, documents, and evidence exist locally.
Provision local development identities and ingest the original local PDFs again.
Any local evaluation score must identify this new corpus and environment.

Before reporting the environment ready, verify migration completion, Auth login,
asymmetric JWKS validation, authorized API writes, checkpoint persistence, and a
user-visible question/answer flow. Record limitations explicitly.

Returning to hosted Supabase is an explicit configuration switch, not a database
merge. Preserve local work; review any data export or migration separately.
