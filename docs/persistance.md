## Persistence

qa-agent uses three persistence layers. Each layer has a distinct scope and lifetime.

---

### Layers at a glance

| Layer | Technology | Mount / URL | Survives restart? | Survives redeploy? |
|-------|-----------|-------------|-------------------|--------------------|
| **Postgres** | Supabase (asyncpg) | `DATABASE_URL` env var | ✓ | ✓ |
| **Volume** | Fly.io persistent disk | `/app/reports` | ✓ | ✓ |
| **In-memory** | Python dicts | process RAM | ✗ | ✗ |

Graceful degradation: if `DATABASE_URL` is unset, all DB calls are no-ops and the app falls back to in-memory + volume state transparently.

---

### What lives where

| Entity | Postgres table | Volume path | In-memory |
|--------|---------------|-------------|-----------|
| Products | `products` | — | — |
| Specs (feature files) | `specs` | `reports/analyses/<task_id>/` (temp copy) | — |
| Jobs / run status | `jobs` | `reports/run-<id>/run_status.json` | `_runs` dict |
| Run reports | — | `reports/run-<id>/report.json` | — |
| Analysis tasks | — | `reports/analyses/<task_id>/` | `_analyses` dict |
| SQLite state store | — | `reports/.state/runs.db` | — |

---

### Postgres (Supabase)

Connection via asyncpg pool, initialized at FastAPI startup. Pool size: min 1, max 5. SSL required (Supabase pooler enforces it).

**Tables:**

- `products` — one row per target website. FK anchor for specs and jobs.
- `specs` — raw Gherkin `.feature` and `config.yaml` content stored as TEXT. `UNIQUE(product_id, filename)` prevents duplicates. `approved` flag gates which specs the executor picks up.
- `jobs` — one row per run. Dual-written alongside the in-memory `_runs` dict so run history survives server restarts. `status` transitions: `pending → running → done | failed | cancelled`.
- `users` — stub; populated by auth layer (future).

**Connection pool (`db/__init__.py`):**

```python
await db.init()    # called at FastAPI startup; no-op if DATABASE_URL is unset
pool = db.get_pool()   # None when no DB
await db.close()   # called at FastAPI shutdown
```

**CRUD modules:**

| Module | Table | Key functions |
|--------|-------|---------------|
| `db/products.py` | `products` | `create`, `get`, `list_all` |
| `db/specs.py` | `specs` | `upsert`, `list_by_product`, `get_by_filename`, `update_content`, `set_approved`, `delete`, `get_files_dict` |
| `db/jobs.py` | `jobs` | `create`, `update`, `get`, `list_all`, `mark_interrupted` |

---

### Fly.io volume

Mounted at `/app/reports` inside the container. Single-machine only (current setup).

```toml
# fly.toml
[[mounts]]
  source      = "qa_agent_reports"
  destination = "/app/reports"
```

Contents:

```
reports/
├── .state/
│   └── runs.db              # SQLite — last status per spec path, flakiness
├── run-<id>/
│   ├── run_status.json      # mirrors _runs[run_id] dict
│   ├── report.json          # structured output consumed by fix-agent
│   ├── .specs/              # temp dir — specs materialized from DB at run start
│   │   ├── config.yaml
│   │   └── *.feature
│   └── evidence/            # screenshots, DOM snapshots (per scenario)
└── analyses/
    └── <task_id>/           # analyst output — also saved to specs table in DB
        ├── config.yaml
        ├── *.feature
        └── analyst_telemetry.json
```

The `.specs/` temp dir is created at run start when `product_id` is used and deleted after the run completes.

---

### Spec persistence flow

```
Local CLI (no product_id):
  analyst writes → specs/ on local filesystem only

API with product_id:
  POST /products/{id}/analyze
    → analyst writes to reports/analyses/<task_id>/  (volume, temp)
    → analyst upserts each file to specs table (Postgres)

POST /runs { product_id }:
  → SELECT filename, content FROM specs WHERE product_id = ?
  → write to reports/run-<id>/.specs/  (volume, temp dir)
  → load_spec(temp_dir) — existing loader, no changes
  → executor runs
```

---

### Job persistence flow

```
POST /runs:
  → INSERT INTO jobs (id, spec_dir, status='pending', ...)
  → _runs[run_id] = { status: 'pending', ... }
  → asyncio.create_task(_execute_job)

During run:
  → UPDATE jobs SET status='running'
  → write run_status.json to volume

On complete/fail:
  → UPDATE jobs SET status='done|failed', summary, report_path
  → write run_status.json to volume

On server restart:
  → mark_interrupted() sets all pending/running jobs to failed
  → in-memory _runs rebuilt lazily from run_status.json on GET /runs
```

---

### Schema migrations

Managed with Supabase CLI. Migration files live in `supabase/migrations/` and are version-controlled in git.

**Workflow for schema changes:**

```bash
# 1. Create a new migration file
supabase migration new <descriptive_name>
# → creates supabase/migrations/<timestamp>_<name>.sql

# 2. Edit the generated SQL file

# 3. Apply locally to test
export SUPABASE_ACCESS_TOKEN=<token>
supabase db push

# 4. Commit and push — GitHub Action applies it automatically
git add supabase/migrations/
git commit -m "feat: <description>"
git push
```

GitHub Action (`db-migrate.yml`) triggers only when files under `supabase/migrations/**` change. Supabase CLI tracks applied migrations in `supabase_migrations.schema_migrations` — never applies the same file twice.

---

### Fly.io secrets (production)

Secrets are injected as environment variables at container startup. Never stored in the image or in `.env`.

```bash
# View current secrets (names only)
fly secrets list --app qa-agent-sp

# Set / update
fly secrets set DATABASE_URL="postgresql://..." --app qa-agent-sp

# Remove
fly secrets unset OLD_KEY --app qa-agent-sp
```

See `docs/secrets-handling.md` for the full secrets inventory.

---

### Local development

`.env` file (gitignored) is loaded by `python-dotenv`. If `DATABASE_URL` is omitted, all DB calls are no-ops — the app runs entirely on in-memory + local filesystem.

```bash
# With DB (full mode)
DATABASE_URL=postgresql://... uv run qa-agent run --spec specs/alconind-smoke

# Without DB (local fallback mode)
uv run qa-agent run --spec specs/alconind-smoke
```

---

### References

- `supabase/migrations/` — full schema history
- `src/qa_agent/db/schema.sql` — reference snapshot (not executed directly)
- `docs/secrets-handling.md` — secrets inventory and flows
- `.github/workflows/db-migrate.yml` — CI migration workflow
