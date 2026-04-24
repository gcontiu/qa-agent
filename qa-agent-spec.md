# QA Agent — Specificație

**Status:** Design finalizat, pre-implementare
**Autor:** Gelu
**Ultimă actualizare:** 2026-04-24

## 1. Context și motivație

Punct de plecare: jocul React **German Brawl** (https://german-brawl.vercel.app/), pentru care există nevoie de testare automată bazată pe specificații.

Obiectivul mai larg: construirea unui **agent de testare automată agnostic** care poate testa orice produs software (aplicație web, CLI, REST API), primind ca input un director cu specificații și producând un raport consumabil de un agent separat de remediere (fix-agent).

Utilizatorul țintă primar nu e testerul manual, ci **un alt agent** din pipeline-ul de dezvoltare asistată (fix-agent citește raportul, propune patch-uri, qa-agent re-rulează).

## 2. Principii de design

1. **Agnosticism.** Același binar testează produse complet diferite prin schimbarea directorului de spec-uri. Zero modificări de cod între produse.
2. **Contract stabil de I/O.** Output-ul agentului (JSON + markdown) respectă o schemă versionată, consumabilă programatic.
3. **Determinism unde se poate, LLM unde e necesar.** Parsarea, validarea, execuția browserului, gestionarea stării — deterministe. Interpretarea pașilor în limbaj natural, evaluarea aserțiilor fuzzy, raportarea — LLM.
4. **Cost controlabil.** Model mixing per subagent, prompt caching, `--only-failing`, snapshot parsimony. Suport pentru LLM local ca alternativă la API.
5. **Portabilitate.** Rulabil pe laptop dev, în CI, în Docker, fără divergențe de comportament.
6. **Compozabilitate prin CLI.** Invocare uniformă prin linie de comandă cu exit codes stabile și output JSON/markdown pe disk. Orice consumator (Claude Code via Bash, shell script, CI, agent scris în alt limbaj) cheamă identic, fără dependențe de protocol.

## 3. Decizii arhitecturale

### 3.1 Runtime agentic

**Claude Agent SDK (Python)** ca runtime principal. Motivație: evităm să scriem de la zero loop-ul de tool use, gestionarea conversației, subagents, hooks. Scade codul de la ~2000 LOC (opțiunea custom) la ~500 LOC.

### 3.2 Abstractizarea providerului LLM

**LiteLLM** ca strat uniform peste providers. Permite per-subagent alegerea între Anthropic API, Ollama local, vLLM, OpenAI-compatible, etc., fără schimbări de cod.

```yaml
subagents:
  planner:   { provider: anthropic, model: claude-opus-4-7 }
  executor:  { provider: ollama,    model: qwen2.5:32b, fallback: {provider: anthropic, model: claude-sonnet-4-6, after_failures: 3} }
  reporter:  { provider: anthropic, model: claude-haiku-4-5-20251001 }
  judge:     { provider: anthropic, model: claude-haiku-4-5-20251001 }
```

Default pentru toate subagents: Anthropic API. Local e opt-in.

### 3.3 Layer browser

**Playwright MCP oficial Microsoft** (`@playwright/mcp`), rulat ca subproces Node via `npx`. Consumat prin protocolul MCP de Agent SDK.

Avantaje decisive: accessibility tree (nu screenshots) → ieftin, determinist, rapid. ~25 tools pre-definite (`browser_navigate`, `browser_click`, `browser_snapshot`, etc.).

Flags obligatorii în CI: `--headless --isolated`. Dev local: `--headed` pentru vizibilitate.

### 3.4 Tools custom (non-browser)

**MCP server propriu** (Python, `mcp` SDK) expune tools pentru:
- `seed_database(payload)` — state setup pentru fixtures imperative
- `call_api(endpoint, method, body)` — testare REST directă fără browser
- `read_artifact(path)` — citire fișiere produse de SUT
- `compare_snapshots(a, b)` — diff determinist DOM/screenshot

~100 LOC. Se lansează tot ca subproces din Agent SDK.

### 3.5 Formate de specificații (dual)

**Gherkin (`.feature`)** pentru scenarios comportamentale end-to-end. Parsat cu `gherkin-official` (doar parser, **nu** `behave`/`pytest-bdd` — nu vrem step definitions Python, LLM-ul interpretează pașii direct).

**YAML (`.yaml`)** pentru:
- Config țintă (`meta.target.url`, environments, browser settings)
- Fixtures declarative
- Teste API structurate cu payload-uri complexe

Loader-ul detectează tipul după extensie și normalizează în `SpecBundle` Pydantic.

### 3.6 Fixtures

Trei niveluri:

1. **Declarative YAML** — pași setup/teardown ca acțiuni predefinite (navigate, click, wait_for, seed_via_api). Default.
2. **Imperative Python** — modul `.py` în `specs/<product>/fixtures/` cu decorator `@fixture`. Escape hatch pentru logică complexă (JWT generation, Docker spin-up).
3. **Scopes** (după modelul pytest): `function` / `scenario` / `feature` / `session`.

Fixtures `scope=session` sunt **cache-uite** pe disk (`reports/.state/fixtures/<name>.json`) pentru a evita re-executare între rulări. Referire din Gherkin via tag `@fixture:<name>`.

### 3.7 State store

**SQLite** în `reports/.state/runs.db`. Schemă minimală:
- `runs(run_id, spec_path, started_at, summary_json)`
- `results(run_id, requirement_id, status, duration_ms, evidence_dir)`
- `flake_tracking(requirement_id, last_n_results)`

Powers `--only-failing`, `--previous`, detectare flake.

### 3.8 Modelul de execuție

**CLI one-shot** ca mod unic de invocare. Proces scurt: pornește, orchestrează subprocese (Playwright MCP, Chromium, custom MCP), face apeluri LLM, scrie rapoarte pe disk, iese. Exit codes stabile: `0` = all pass, `1` = failures, `2` = eroare internă.

Motivație explicită a alegerii CLI peste MCP server persistent:
- Orice consumator cheamă uniform (Claude Code via Bash, shell, CI, alt agent non-Claude) — zero overhead de protocol
- Zero state între rulări în memorie — toată starea persistă pe disk (SQLite + `reports/`) → reproducibil, debuggable cu tool-uri standard
- Fără lifecycle de server (start/stop/restart), fără porturi, fără config `.mcp.json` la consumator
- Cold start 2-5s per rulare acceptabil; amortizat de `--only-failing` în loop-urile fix-agent

MCP server wrapper rămâne **opțiune viitoare** (vezi secțiunea 11) dacă apare un use case concret (integrare Claude Desktop, ecosistem MCP-native, streaming progress cerut de consumator). Va fi un thin wrapper de ~80 LOC peste CLI-ul existent, nu un mod paralel de funcționare.

URL-ul țintă trăiește în spec-uri (`meta.target.url` / environments), **nu** pe linia de comandă. Override pentru dev disponibil: `--override target.url=...`.

### 3.9 Deployment

**Docker image** peste `mcr.microsoft.com/playwright:v1.xx-jammy` (are Node + Chromium + dependențe sistem). Adaugă Python + qa-agent. Runtime:

```bash
docker run \
  -v $(pwd)/specs:/specs \
  -v $(pwd)/reports:/reports \
  -e ANTHROPIC_API_KEY=$KEY \
  qa-agent run --spec /specs/german-brawl/
```

Portabilitate laptop → laptop și laptop → CI fără reconfigurare.

## 4. Format spec-uri

### 4.1 Structură director

```
specs/<product>/
├── config.yaml           # meta, target, environments
├── fixtures.yaml         # fixtures declarative
├── fixtures/             # (opțional) fixtures imperative Python
│   └── authenticated_user.py
├── *.feature             # scenarios Gherkin
└── *.yaml                # teste API și structurate
```

### 4.2 `config.yaml`

```yaml
meta:
  name: "German Brawl"
  version: "1.0"
  target:
    type: web                   # web | api | cli
    environments:
      local:   { url: http://localhost:3000 }
      staging: { url: https://staging.example.com }
      prod:    { url: https://german-brawl.vercel.app/ }
    default_environment: prod
    browser: chromium           # chromium | firefox | webkit
    viewport: { width: 1280, height: 720 }
  env_vars:
    API_KEY: "${GERMAN_BRAWL_API_KEY}"

context: |
  Descriere a produsului în limbaj natural.
  LLM-ul o primește ca context de planificare.
```

### 4.3 Gherkin scenarios

```gherkin
Feature: Core gameplay

  Background:
    Given jocul este încărcat

  @priority:high @id:GP-001 @fixture:game_started
  Scenario: Răspuns corect crește scorul
    Given un cuvânt german este afișat
    When jucătorul alege traducerea corectă
    Then scorul crește cu 10
    And apare un cuvânt nou
```

Tag-uri suportate: `@id:<ID>` (obligatoriu, stabil), `@priority:high|medium|low`, `@fixture:<name>`, `@tag:<anything>` (filtrare CLI), `@env:<name>` (limitare la un environment), `@skip` (temporar).

`Scenario Outline + Examples` generează automat N requirements parametrice cu ID-uri derivate (`GP-002-01`, `GP-002-02`).

### 4.4 Fixtures declarative

```yaml
fixtures:
  - name: game_started
    scope: scenario
    setup:
      - { action: navigate, url: "{{target.url}}" }
      - { action: click, target: "button[name='Start']" }
      - { action: wait_for, target: ".game-board" }
    teardown:
      - { action: reload }

  - name: authenticated_user
    scope: session
    depends_on: []
    setup:
      - { action: seed_via_api, endpoint: /api/test/session, body: { role: player } }
```

## 5. Subagents

| Subagent | Rol | Model default | Input | Output |
|---|---|---|---|---|
| **Planner** | Traduce requirement complex în plan pași JSON | `claude-opus-4-7` | Requirement + context spec | Lista de pași structurată |
| **Executor** | Execută planul pe browser via tools MCP | `claude-sonnet-4-6` (sau `qwen2.5:32b` local) | Plan + acces tools | `{status, actual, actions_log}` |
| **Judge** | Evaluează aserții fuzzy (`then` ambiguu) | `claude-haiku-4-5-20251001` | Expected + actual | `{verdict, rationale}` |
| **Reporter** | Agregă rezultate în markdown uman | `claude-haiku-4-5-20251001` | JSON rezultate | `report.md` |

Planner-ul e **opțional** — activat doar pentru scenarios marcate complexe sau prin config. Scenarios simple trec direct la Executor.

## 6. Contract CLI

### 6.1 Comenzi principale

```bash
# Rulare standard
qa-agent run --spec <dir> [--env <name>] [--output <dir>]

# Filtrare
qa-agent run --spec <dir> --tag smoke --priority high
qa-agent run --spec <dir> --only-failing [--previous <run-id>]
qa-agent run --spec <dir> --id GP-001,GP-002

# Dev
qa-agent run --spec <dir> --headed --debug --pause-on-failure
qa-agent run --spec <dir> --override target.url=http://localhost:3000
qa-agent run --spec <dir> --format jsonl   # streaming output pentru consumatori live

# Utilitare
qa-agent validate --spec <dir>       # validează schema spec-urilor
qa-agent list-runs [--spec <dir>]
qa-agent show-report <run-id> [--format md|json]
qa-agent --help                      # self-descriptive, citibil de agent consumator
```

### 6.2 Exit codes

- `0` — toate scenarios PASS
- `1` — cel puțin un FAIL
- `2` — eroare de configurare sau runtime (spec invalid, Playwright MCP indisponibil, fără API key, target inaccesibil)

### 6.3 Configurare

Ordine priorități (de jos în sus):
1. Defaults în cod
2. `~/.qa-agent/config.yaml` (user global)
3. `<spec-dir>/config.yaml`
4. Variabile de mediu
5. Flaguri CLI

## 7. Contract raport (output)

### 7.1 Structură director run

```
reports/run-2026-04-24T14-30-00Z/
├── report.json              # contract machine-readable (schema versionată)
├── report.md                # raport uman
├── telemetry.json           # tokens, cost, latency, cache hits
├── evidence/
│   ├── GP-001-before.png
│   ├── GP-001-after.png
│   ├── GP-001-dom.html
│   └── GP-001-actions.jsonl
└── logs/
    ├── executor.jsonl       # tool calls brute
    └── llm.jsonl            # prompts + responses (opțional, flag)
```

### 7.2 Schema `report.json`

```json
{
  "schema_version": "1.0",
  "run_id": "2026-04-24T14-30-00Z",
  "spec_path": "specs/german-brawl/",
  "environment": "prod",
  "target": "https://german-brawl.vercel.app/",
  "started_at": "2026-04-24T14:30:00Z",
  "duration_ms": 125340,
  "summary": {
    "total": 12, "passed": 9, "failed": 2, "skipped": 1, "flaky": 0
  },
  "results": [
    {
      "requirement_id": "GP-002",
      "title": "Correct answer increases score",
      "status": "failed",
      "priority": "high",
      "duration_ms": 5120,
      "expected": "Score increases by 10",
      "actual": "Score did not change after correct answer",
      "evidence": {
        "screenshots": ["evidence/GP-002-before.png", "evidence/GP-002-after.png"],
        "dom_snapshot": "evidence/GP-002-dom.html",
        "actions_log": "evidence/GP-002-actions.jsonl",
        "console_errors": ["TypeError: cannot read property 'score' of undefined"]
      },
      "code_hints": null
    }
  ],
  "report_markdown": "report.md"
}
```

`code_hints` populat doar dacă se rulează cu `--source-path <repo>` — păstrează agnosticismul default.

### 7.3 `telemetry.json`

```json
{
  "run_id": "...",
  "llm_calls": {
    "total": 87,
    "by_subagent": { "executor": 72, "reporter": 1, "judge": 14 },
    "by_provider": { "anthropic": 87, "ollama": 0 }
  },
  "tokens": { "input": 245320, "output": 18450, "cached_read": 180000 },
  "cost_estimated_usd": 0.42,
  "cache_hit_rate": 0.73
}
```

## 8. Integrare cu fix-agent (și alți consumatori)

Consumator tipic (fix-agent ca Claude Code instance):

```
fix-agent → Bash: qa-agent run --spec specs/X/ --output reports/run-N/
         ← exit code + report.json pe disk
fix-agent → Read: reports/run-N/report.json
         ← înțelege failures, propune patch
         → aplică patch pe SUT
fix-agent → Bash: qa-agent run --spec specs/X/ --only-failing --previous run-N
         ← verifică remedierea
```

**Ghid pentru integrator** (livrat ca `docs/agent-integration.md`):
- Exemple concrete de invocare din Claude Code, shell, Python, GitHub Actions
- Schema `report.json` explicată per câmp
- Convenții de tratare a exit codes
- Pattern-uri recomandate pentru loop-uri fix→test→fix

**Consumator non-Claude:** orice runtime care poate executa un proces și citi un fișier JSON. Nu există dependență de protocol MCP la consumator.

**Streaming progress opțional** pentru UI-uri care vor feedback live:
```bash
qa-agent run --spec X --format jsonl | consumator
# fiecare linie = event: {"type":"scenario_start","id":"GP-001"} / "scenario_end" / "summary"
```

## 9. Stack tehnic

### 9.1 Runtime

- Python 3.11+
- Node 20+ (pentru Playwright MCP)
- Chromium (via `npx playwright install`)

### 9.2 Dependențe Python principale

- `claude-agent-sdk` — orchestrare agentică
- `litellm` — abstractizare provider LLM
- `mcp` — client MCP (consum Playwright MCP și custom tools MCP intern)
- `gherkin-official` — parser Gherkin
- `pydantic` — schema validation
- `pyyaml` — YAML loader
- `typer` — CLI
- `sqlite3` (stdlib) — state store
- `rich` — formatare terminal

### 9.3 LLM providers suportați

- **Anthropic API** (default)
- **Ollama** (local; recomandat: Qwen 3 32B+)
- **vLLM** (local/remote, OpenAI-compatible)
- Orice alt provider suportat de LiteLLM (OpenAI, Bedrock, Azure, Gemini — via config)

## 10. Structură director repo

```
qa-agent/
├── CLAUDE.md
├── README.md
├── qa-agent-spec.md                    # acest document
├── pyproject.toml
├── Dockerfile
├── .env.example
│
├── src/qa_agent/
│   ├── cli.py                          # Typer entrypoint (unicul mod de invocare)
│   ├── agent.py                        # orchestrare Agent SDK
│   ├── config.py                       # config loading (ierarhic)
│   ├── llm/
│   │   ├── router.py                   # dispatch per subagent
│   │   └── providers.py                # wrappers LiteLLM
│   ├── specs/
│   │   ├── loader.py                   # Gherkin + YAML → SpecBundle
│   │   ├── schema.py                   # Pydantic models
│   │   └── validator.py
│   ├── fixtures/
│   │   ├── runtime.py                  # execuție setup/teardown + scopes
│   │   └── cache.py                    # persistență session fixtures
│   ├── executor/
│   │   ├── planner.py
│   │   ├── executor.py
│   │   ├── judge.py
│   │   └── reporter.py
│   ├── tools/
│   │   └── custom_mcp.py               # MCP server intern: seed_database, call_api, etc. (consumat de Agent SDK, NU expus extern)
│   ├── evidence/
│   │   └── collector.py                # hooks pentru screenshots, DOM, logs
│   ├── state/
│   │   └── store.py                    # SQLite
│   ├── telemetry.py
│   └── prompts/
│       ├── planner.md
│       ├── executor.md
│       ├── judge.md
│       └── reporter.md
│
├── specs/                              # user-provided (gitignored structural)
│   └── german-brawl/
│       ├── config.yaml
│       ├── fixtures.yaml
│       └── gameplay.feature
│
├── reports/                            # gitignored
│   └── .state/
│
├── tests/
│   ├── unit/
│   └── integration/
│
└── scripts/
    ├── install.sh
    └── smoke.py
```

## 11. Plan de implementare (iterații)

| # | Titlu | Durată | Exit criteria | Demo |
|---|---|---|---|---|
| 0 | Scaffold & smoke | 0.5-1 zi | Agent SDK + Playwright MCP deschid German Brawl, returnează titlu | `python -m qa_agent.smoke <URL>` |
| 1 | Un requirement hardcodat | 2-3 zile | LLM găsește și apasă Start fără selector explicit, detectează game board, PASS/FAIL | Run pe un requirement text-liber, log acțiuni |
| 2 | Spec loader + CLI | 2 zile | Gherkin + YAML parsate, CLI rulează 5 scenarios, output terminal cu ✓/✗ | `qa-agent run --spec specs/german-brawl/` |
| 3 | Subagents + raport + evidence | 2-3 zile | Planner/Executor/Reporter separate, `report.md` + `report.json` + screenshots per failure | Deschizi `reports/run-XXX/report.md` uman-citibil |
| 4 | Fixtures + state store + `--only-failing` | 3 zile | Session fixtures cache-uite, `--only-failing` taie >70% din timp, telemetrie completă | Workflow fix-loop simulat pe 2 rulări |
| **4.5** | **LiteLLM + Ollama opțional** | 2-3 zile | Flag `--provider`, Executor rulat pe Qwen 3 32B, comparație paritate | Același spec, două providers, diff rezultate |
| 5 | Validare agnosticism | 2 zile | Al doilea produs (diferit de German Brawl) testat fără modificări în `src/` | Două `qa-agent run` pe două target-uri |
| 6 | Integrare fix-agent + docs | 1-2 zile | `docs/agent-integration.md` complet, exemplu fix-agent real care loop-uiește fix→test | Claude Code extern rulează qa-agent via Bash, citește raport, propune patch |
| 7 | Docker image | 1-2 zile | `docker run qa-agent ...` funcționează pe un laptop curat | Clonezi pe alt laptop, rulezi prin Docker |
| 8+ | Robustețe ongoing | continuu | Retry, timeouts, flake detection, paralelizare, cross-browser | — |

**Total MVP:** ~14-18 zile lucrătoare (~3-4 săptămâni calendar cu buffer).

**Checkpoint-uri critice cu utilizatorul:** după iter 1 (viabilitate tehnică), iter 5 (agnosticism confirmat), iter 7 (portabilitate Docker).

**MCP server wrapper — opțiune amânată.** Dacă post-MVP apare nevoia (integrare Claude Desktop, streaming structurat cerut de consumator, ecosistem MCP standardizat), se adaugă ca iterație separată: ~80 LOC thin wrapper `qa-agent serve` care reapelează intern CLI-ul și expune 6 tools MCP (`run_spec`, `list_runs`, `get_report`, `get_evidence`, `rerun_failing`, `validate_spec`). Nu face parte din MVP.

## 12. Decizii explicite de evitat

- **Fără ZeroStep** (proiect arhivat din 2024).
- **Fără `behave` / `pytest-bdd`** — vrem interpretare LLM a pașilor, nu step definitions.
- **Fără `suggested_fix_hints` care referă path-uri din SUT** fără `--source-path` explicit — ar rupe agnosticismul.
- **Fără snapshot după fiecare acțiune** — cost exploziv; doar după navigate / state change / la cerere LLM.
- **Fără logică business hardcodată pentru German Brawl** în `src/` — totul merge prin spec-uri.
- **Fără modele locale <14B** pentru Executor — tool use failure rate inacceptabil.

## 13. Glosar

- **SUT** — System Under Test (produsul testat).
- **Requirement** — unitate atomică de test; un `Scenario` Gherkin sau o intrare YAML cu `id`.
- **Run** — o execuție completă a agentului peste un spec bundle. Identificat prin `run_id` ISO timestamp.
- **Evidence** — artifacts produse în timpul unui run (screenshots, DOM, logs) pentru inspecție post-mortem.
- **Subagent** — un rol LLM specializat (Planner/Executor/Judge/Reporter), fiecare cu prompt și model propriu.
- **Fix-agent** — consumator extern al rapoartelor qa-agent, responsabil cu propunerea de patches.
