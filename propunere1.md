Agent de testare automată agnostic — propuneri și plan
Salut Gelu! E o idee bună și foarte „pe val” — genul de tooling care se construiește acum peste Claude Code / MCP. Îți dau mai jos trei arhitecturi posibile, o recomandare clară, și un plan concret de implementare cu structură de directoare și contract de apelare pentru alți agenți (cum ar fi fix-agent-ul tău).
Cele trei opțiuni arhitecturale
Opțiunea A — Claude Code ca runtime, Playwright MCP ca „mâini și ochi"
Agentul este de fapt o instanță de Claude Code rulată headless (claude -p "..." sau prin SDK) cu un CLAUDE.md care îi explică rolul de QA agent. Pentru interacțiunea cu browser-ul folosește Playwright MCP (oficial Microsoft) — dă lui Claude acces la accessibility tree, nu screenshots, deci e rapid și determinist. Specificațiile sunt markdown/YAML în directorul specs/. Claude citește spec-ul, generează un plan de test, execută pașii prin MCP, scrie raportul.
Avantaje: zero cod de scris pentru „creierul" agentului, beneficiezi direct de model selection (Opus pentru planificare, Sonnet pentru execuție), e agnostic by design.
Dezavantaje: costuri variabile, dependent de disponibilitatea modelului, mai greu de rulat în CI fără config.
Opțiunea B — Agent custom Python cu Anthropic SDK + Playwright
Scrii tu loop-ul agentic: un script Python care cheamă API-ul Claude cu tool use, tools-urile sunt wrapper-e peste Playwright (navigate, click, type, assert_text, screenshot). Tu controlezi exact prompt-urile, bugetul de tokens, retry logic, persistența stării. Spec-urile le parsezi cum vrei.
Avantaje: control total, ușor de rulat în CI, costuri predictibile, poți adăuga caching agresiv pe spec-uri.
Dezavantaje: scrii și menții tu orchestrarea, ~500–800 linii de cod inițial.
Opțiunea C — Hibrid: framework existent + layer LLM pentru generare teste
Folosești ceva ca Auto Playwright sau ZeroStep care deja leagă LLM de Playwright, și pui LLM-ul doar în partea de „citește spec → generează plan → interpretează eșecuri". Execuția rămâne deterministă.
Avantaje: cel mai robust pentru CI, teste reproducibile, cost mic per rulare după prima generare.
Dezavantaje: mai puțin „agent" și mai mult „generator de teste", ai pierdut flexibilitatea când spec-ul e vag.
Recomandarea mea
Opțiunea B, cu o ieșire ușoară către A pentru dev loop.
Motivul: tu vrei un agent care să fie apelabil de alți agenți (fix-agent) cu un contract clar de I/O. Asta înseamnă că ai nevoie de un CLI determinist cu exit codes, output JSON structurat, și control fin asupra a ce rulează. Claude Code e excelent când tu stai la tastatură, dar pentru orchestrare între agenți vrei ceva mai „programabil". În plus, tu deja ai experiență cu FastAPI/Python din proiectul PSD2, deci stack-ul îți e familiar.
Pentru explorare și debugging interactiv pe jocul tău German Brawl, deschizi Claude Code cu Playwright MCP și te joci — dar produsul final (agentul reutilizabil) e Python.
Structura de directoare propusă
qa-agent/
├── README.md
├── pyproject.toml
├── .env.example
│
├── src/qa_agent/
│   ├── __init__.py
│   ├── cli.py                    # entry point: qa-agent run --spec ...
│   ├── agent.py                  # loop-ul principal agentic
│   ├── planner.py                # spec → test plan (LLM call)
│   ├── executor.py               # test plan → rezultate (tool use loop)
│   ├── reporter.py               # rezultate → raport markdown/JSON
│   │
│   ├── specs/
│   │   ├── loader.py             # citește YAML/MD/JSON din directorul de spec-uri
│   │   ├── schema.py             # Pydantic models pentru spec format
│   │   └── validator.py          # validează că spec-ul e bine format
│   │
│   ├── tools/
│   │   ├── base.py               # interfață Tool abstractă
│   │   ├── browser.py            # Playwright tools (navigate, click, assert)
│   │   ├── api.py                # HTTP tools pentru testare API
│   │   └── registry.py           # înregistrează tool-urile disponibile
│   │
│   ├── adapters/
│   │   ├── web.py                # adapter pentru aplicații web (default)
│   │   ├── cli.py                # adapter pentru tool-uri CLI
│   │   └── api.py                # adapter pentru REST APIs
│   │
│   └── prompts/
│       ├── planner_system.md
│       ├── executor_system.md
│       └── reporter_system.md
│
├── specs/                        # exemple și spec-uri user-provided
│   ├── german-brawl/
│   │   ├── gameplay.yaml
│   │   ├── ui.yaml
│   │   └── config.yaml           # URL, credentials, etc.
│   └── README.md                 # format documentation
│
├── reports/                      # output dir (gitignored)
│   └── .gitkeep
│
├── tests/                        # testele agentului însuși
│   ├── unit/
│   └── integration/
│
└── scripts/
    ├── install.sh
    └── run-example.sh
Formatul spec-ului (agnostic)
Acesta e contractul crucial — dacă îl faci bine, agentul devine cu adevărat agnostic. Propun YAML pentru că e ușor de citit și de generat de alte LLM-uri:
yaml# specs/german-brawl/gameplay.yaml
meta:
  name: "German Brawl - Core Gameplay"
  version: "1.0"
  target:
    type: web
    url: https://german-brawl.vercel.app/
  
context: |
  German Brawl is a word-learning game where players match 
  German words to English translations under time pressure.

requirements:
  - id: GP-001
    title: "Game starts when player clicks Start"
    priority: high
    given: "Player is on landing page"
    when: "Player clicks the Start button"
    then: "Game board becomes visible and timer starts counting down"
    
  - id: GP-002
    title: "Correct answer increases score"
    priority: high
    given: "Game is in progress with a word prompt visible"
    when: "Player selects the correct translation"
    then: "Score increases by 10 and next word appears"
Agentul tratează fiecare requirement ca un test case independent. Câmpurile given/when/then sunt hint-uri — LLM-ul are libertatea să decidă cum le traduce în acțiuni pe browser.
Contractul de apelare pentru alți agenți
Aici e partea importantă pentru integrarea cu fix-agent-ul tău:
bash# Invocare simplă
qa-agent run --spec specs/german-brawl/ --output reports/run-001/

# Invocare de către alt agent (fix-agent)
qa-agent run \
  --spec specs/german-brawl/ \
  --output reports/run-001/ \
  --format json \
  --only-failing \        # re-rulează doar ce a eșuat data trecută
  --previous reports/run-000/
Output-ul JSON trebuie să fie stabil și auto-descriptiv:
json{
  "run_id": "2026-04-22T14-30-00Z",
  "spec_path": "specs/german-brawl/",
  "target": "https://german-brawl.vercel.app/",
  "summary": { "total": 12, "passed": 9, "failed": 2, "skipped": 1 },
  "results": [
    {
      "requirement_id": "GP-002",
      "status": "failed",
      "actual": "Score did not increase after correct answer",
      "expected": "Score increases by 10",
      "evidence": {
        "screenshots": ["reports/run-001/GP-002-before.png", "..."],
        "dom_snapshot": "reports/run-001/GP-002-dom.html",
        "actions_log": ["click #start", "click .option-2", ...]
      },
      "suggested_fix_hints": [
        "Check score update logic in src/game/scoring.ts",
        "Verify event handler on answer selection"
      ]
    }
  ],
  "report_markdown": "reports/run-001/report.md"
}
suggested_fix_hints e câmpul prin care agentul de QA îi dă fix-agent-ului un punct de plecare — nu ghicește soluția, dar identifică zonele suspecte pe baza log-urilor de acțiuni și a mesajelor de eroare.
Loop-ul agentic (simplificat)
1. Load spec files → validate → parse în Requirement objects
2. Pentru fiecare requirement:
   a. Planner LLM: „dat fiind spec-ul și capabilitățile tool-urilor, 
      generează un plan pas-cu-pas"
   b. Executor LLM cu tool use: execută planul, primește feedback 
      de la fiecare tool call, decide următorul pas
   c. La final: evaluează dacă „then" a fost satisfăcut
3. Reporter LLM: agregă rezultatele într-un raport uman-friendly
4. Scrie JSON structurat + markdown report + evidence
Pentru step 2, folosești Anthropic's tool use cu un model ca claude-sonnet-4-6 (bun raport cost/calitate pentru execuție) și claude-opus-4-7 pentru planner dacă spec-urile sunt complexe.
Plan de implementare, în etape
Săptămâna 1 — Scheletul
Setup pyproject, CLI cu Click/Typer, schema Pydantic pentru spec-uri, loader YAML, un Playwright wrapper minimal (4-5 tools: navigate, click, type, get_text, screenshot). Test manual că poți deschide German Brawl și da click pe Start.
Săptămâna 2 — Bucla agentică
Implementează planner + executor cu tool use. Focus pe un singur requirement end-to-end (GP-001). Aici vei simți unde e greu — probabil selectarea elementelor pe pagină fără selectori explicit declarați.
Săptămâna 3 — Raportare și robustețe
Reporter, JSON schema stabil, retry logic, timeouts, evidence collection (screenshots + DOM). Adaugă modul --only-failing și comparație cu run-ul anterior.
Săptămâna 4 — Agnosticism real
Scrie un al doilea set de spec-uri pentru o aplicație complet diferită (poate alconind.ro sau landing page-ul streamline-saas). Dacă agentul rulează pe ambele fără modificări de cod, ai reușit.
Câteva recomandări finale
Nu băga LLM-ul în fiecare decizie. Când e un click clar specificat, dă-i agentului posibilitatea să execute determinist prin matcheri de text/role. LLM-ul intervine doar când spec-ul e ambiguu sau când ceva eșuează neașteptat — asta reduce costurile drastic.
Folosește Playwright MCP-ul Microsoft ca referință pentru ce tools să expui — au făcut deja munca de a găsi setul minim util (cred că sunt ~25 de tools). Nu trebuie să le implementezi pe toate de la început.
Pentru contractul cu fix-agent, gândește-te la rapoarte ca la „issues" — fiecare failure e un GitHub issue structurat cu reproducere, evidence, și hint-uri. Fix-agent-ul citește issue-ul, nu tot raportul.