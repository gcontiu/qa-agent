## Secrets handling

Secrets are never committed to git. There are three environments, each with its own injection mechanism.

---

### Full secrets inventory

| Variable | Purpose | Required in |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | LLM executor/reporter (Anthropic) | local, Fly.io |
| `TOGETHER_AI_API_KEY` | Alternative LLM executor (Together.ai) | local, Fly.io |
| `DATABASE_URL` | PostgreSQL connection (asyncpg) | local, Fly.io |
| `SUPABASE_ACCESS_TOKEN` | Supabase CLI auth (`supabase db push`) | local, GitHub Actions |
| `SUPABASE_PROJECT_REF` | Supabase project ID (e.g. `zjkucovapyjbyzxqgbrb`) | local, GitHub Actions |

---

### Environment 1 — local development (`.env`)

The `.env` file is listed in `.gitignore` and never reaches the repo.  
Loaded automatically by `python-dotenv` at agent startup.

```
ANTHROPIC_API_KEY=sk-ant-...
TOGETHER_AI_API_KEY=tgp_v1_...
DATABASE_URL=postgresql://postgres:p%40ssword@db.<REF>.supabase.co:5432/postgres
SUPABASE_PROJECT_REF=zjkucovapyjbyzxqgbrb
SUPABASE_ACCESS_TOKEN=sbp_...
```

**Special characters in `DATABASE_URL` passwords** must be URL-encoded:

| Character | Encoded |
|-----------|---------|
| `#` | `%23` |
| `@` | `%40` |
| `[` | `%5B` |
| `]` | `%5D` |

`asyncpg` URL-decodes the password automatically when parsing the connection string — no extra code needed.

The template (without values) lives in `.env.example`.

---

### Environment 2 — Fly.io production

The Docker container does **not** read `.env`. Secrets are set via the Fly CLI and injected as environment variables when the container starts.

**Add / update a secret:**
```bash
fly secrets set \
  ANTHROPIC_API_KEY="sk-ant-..." \
  DATABASE_URL="postgresql://postgres:p%23ssword@db.<REF>.supabase.co:5432/postgres" \
  --app qa-agent-sp
```

**List existing secrets (names only, no values):**
```bash
fly secrets list --app qa-agent-sp
```

**Remove a secret:**
```bash
fly secrets unset OLD_KEY --app qa-agent-sp
```

`fly secrets set` triggers a rolling restart by default. To stage secrets without an immediate restart, append `--stage`.

---

### Environment 3 — GitHub Actions (CI/CD)

The `db-migrate.yml` workflow runs on GitHub's servers and has no access to the local `.env`.  
Secrets are stored under **repo → Settings → Secrets and variables → Actions**.

Secrets required for migrations:

| GitHub Secret | Value |
|---------------|-------|
| `SUPABASE_ACCESS_TOKEN` | personal token from supabase.com → Account → Access tokens |
| `SUPABASE_PROJECT_REF` | project ID only, not the full URL (e.g. `zjkucovapyjbyzxqgbrb`) |

**Set via CLI:**
```bash
gh secret set SUPABASE_ACCESS_TOKEN --body "sbp_..."
gh secret set SUPABASE_PROJECT_REF  --body "zjkucovapyjbyzxqgbrb"
```

---

### Schema migration flow (Supabase CLI)

```
local development
│
│  1. supabase migration new <name>
│     → creates supabase/migrations/<timestamp>_<name>.sql
│
│  2. edit the SQL file with schema changes
│
│  3. test locally (optional):
│     export SUPABASE_ACCESS_TOKEN=sbp_...
│     supabase db push
│
│  4. git add supabase/migrations/ && git commit && git push
│
GitHub Actions (db-migrate.yml)
│
│  5. detects change under supabase/migrations/**
│  6. reads SUPABASE_ACCESS_TOKEN and SUPABASE_PROJECT_REF from Secrets
│  7. runs: supabase db push --project-ref <REF>
│  8. migration is applied to the remote Supabase instance
▼
Supabase PostgreSQL (remote)
```

The Supabase CLI tracks applied migrations in the internal table `supabase_migrations.schema_migrations` — it never applies the same file twice.

---

### Where secrets must NOT appear

- Hardcoded in source code
- In commit messages or PR descriptions
- In log files or reports under `reports/`
- In `CLAUDE.md` or any other committed documentation file

---

### References

- `.env.example` — local template with all parameters
- `.github/workflows/db-migrate.yml` — CI workflow for migrations
- `supabase/migrations/` — full schema history
- `src/qa_agent/db/schema.sql` — reference snapshot (no longer executed directly)
