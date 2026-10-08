# AI Resume Screening & Ranking

Screens a batch of PDF resumes for Python + AI/LLM/RAG/agentic engineering ability: a hard eligibility
filter first, then an explainable 100-point score for eligible candidates only. The output is a
machine-readable `results.json`.

## Current status: Step 1 (deterministic engine)

| Implemented | Not implemented yet |
|---|---|
| PDF (and `.txt`/`.md`) ingestion, hashing, duplicate detection | LLM semantic extraction / project-quality judgment |
| Field extraction: name, email, skills, projects, GitHub URL | GitHub API enrichment (score is `0`, status `not_evaluated`) |
| Hard eligibility rules (Python AND AI evidence) | Upload UI / frontend dashboard |
| Deterministic 100-point scoring + shallow-project penalty | API endpoints beyond `/health` |
| Ranking, `results.json` contract, CLI, tests | Deployment |

No database, queue, auth or vector store is used or needed.

## Running it (Docker only)

The host needs only Docker and Docker Compose. No local Python, pip or virtualenv.

```bash
cp .env.example .env          # optional in Step 1; every value may stay empty
docker compose build

# run the test suite
docker compose run --rm backend pytest

# screen resumes: reads ./resumes, writes ./output/results.json on the host
docker compose run --rm backend python main.py \
  --input /app/resumes \
  --output /app/output/results.json

# API server (health check only for now) with auto-reload
docker compose up           # then: curl localhost:8000/health
```

How the pieces line up:

```
host ./resumes  ->  /app/resumes   (container, read)
host ./output   <-  /app/output    (container, write)
host ./backend/{app,tests,main.py,pytest.ini} -> /app/...   (mounted: edit code, no rebuild)
```

Rebuild (`docker compose build`) is only needed when `backend/requirements.txt` changes.
The image runs as a non-root user (uid 1000); on Linux hosts make `./output` writable by that uid.
Secrets are read from the environment at run time and are never baked into the image.
`resumes/*` and `output/*` are git-ignored because real resumes contain personal data.

## Project structure

```
docker-compose.yml        backend service only
.env.example              documented configuration (all optional)
resumes/  output/         mounted data folders
frontend/                 placeholder (later step)
backend/
  Dockerfile  requirements.txt  pytest.ini
  main.py                 CLI entry point
  app/
    api.py                minimal FastAPI app (/health)
    errors.py             structured pipeline errors (stage-tagged)
    config/               env settings (pydantic-settings), category weights
    models/               Pydantic contracts: Candidate, Evidence, EligibilityResult,
                          ScoreBreakdown, CandidateResult, BatchSummary, ScreeningResults
    ingestion/            file discovery, PDF/text reading, hashing
    extraction/           normalise text -> sections -> fields/projects -> Candidate
    screening/
      rules.py            ALL keyword/regex/point tables (the place to extend)
      context.py          how much can this line prove? (project vs skills vs tutorial)
      python_evidence.py  ai_evidence.py   eligibility.py
      ai_depth.py         AI depth score + shallow penalty
      signals.py scoring.py   backend / cloud / engineering scoring, total
      explain.py          strengths, concerns, project summaries
      ranking.py          engine.py   batch.py
  tests/                  synthetic resumes only; no network
```

Data flow: `file bytes -> text -> Candidate (sections, lines, projects) -> eligibility -> score (eligible only) -> rank -> ScreeningResults`.
Every detector works on `ResumeLine`s that carry their section, so each decision cites the line and section behind it.

## Deterministic eligibility rules

A candidate is eligible only if **both** hold:

1. **Genuine Python evidence.** Each line is graded by context (`context.py`):
   - project or work/internship entry -> strong
   - elsewhere but phrased as usage ("Python developer", "built X in Python") or in a skills list -> moderate
   - tutorial / course / "learning" / coursework / bare keyword -> **weak, does not count**
     (an action verb such as *built* overrides a tutorial mention: "Built a RAG app after a tutorial" counts)
   - Python-only libraries (FastAPI, Django, pandas, ...) count when used in a project/job, not from a skills list.
2. **Meaningful AI/LLM/RAG/agentic evidence** from `rules.AI_TERMS`:
   - named frameworks (LangChain, LangGraph, Google ADK, LlamaIndex, ...) and techniques (RAG, embeddings, vector
     search, tool/function calling, agentic workflows, multi-agent, orchestration, evaluation pipeline, ...) are
     strong inside a project/work entry;
   - generic LLM usage (OpenAI API, chatbot, "LLM") is moderate in a project/work entry;
   - a bare "AI" or "agent" is never a term; "agents" needs a qualifier ("AI agent", "multi-agent", "agentic");
   - a named *framework* in a skills list passes the gate (the "framework" route) but earns almost no score;
     techniques or generic terms listed only as skills do not pass.

Java, JavaScript, React, Next.js, etc. never cause rejection. Missing GitHub never affects eligibility.
Rejections state which side failed and why (e.g. `Only weak Python mentions found ... learning/tutorial context`).

## Scoring model (100 points, integers)

Rejected candidates are not scored. Every point appears in `score_evidence` with the resume line behind it.

| Category | Max | Formula |
|---|---|---|
| AI / Agentic / RAG depth | 40 | Per project / work entry that mentions AI: 5 baseline + retrieval 7 + embeddings/vector store/chunking 4 + tool calling 5 + agents 6 + orchestration/state 5 + evaluation 5 + data/product logic 4 + backend integration 3. Result = best unit + 2 per *other* AI unit scoring >= 10 (cap 6) + 1 per AI framework/technique present only in skills (cap 3), capped at 40. AI mentions outside project/work sections are capped at 10. |
| Python & backend | 30 | Python 12 (4 any qualifying evidence + 5 in a project + 3 in work) + web framework 5 + database 4 + async 3 + Redis 3 + backend implementation 3. A keyword only in a skills list earns reduced points (2/2/1/1/1 respectively). |
| Cloud / deployment / full stack | 15 | cloud provider 4 + containers 3 + deployment/CI-CD 4 + frontend framework 2 + end-to-end system 2 (skills-list-only keywords earn 2/1/1/1/0). |
| GitHub | 10 | `0`, `github_status: not_evaluated` (Step 1) |
| Engineering depth | 5 | 1 each: testing, architecture, caching/queues, concurrency, logging/observability/failure handling (project/work evidence only). |

`total_score = sum(categories) - penalty`, clamped to 0..100. All tables are in `rules.py`.

### Shallow-project penalty (5-15)

If the candidate has AI work but **no** project/work entry contains a strong signal (retrieval, embeddings, tool
calling, agents, orchestration/state, evaluation), it is judged a thin LLM/API wrapper. The penalty depends on how
much supporting logic (data/product logic, backend integration) the best such entry has: none -> 15, one -> 10,
two -> 5. A candidate with at least one non-shallow AI project is never penalised, so a side chatbot next to a real
RAG project costs nothing. The penalty records `amount`, `reason` and `evidence`.

Example: "created a chatbot using OpenAI API" -> 5 AI points and a 15-point penalty;
"RAG pipeline with chunking, embeddings, vector retrieval and citations" -> 20 AI points;
"stateful agentic workflow with retrieval, tools, orchestration and evaluation" -> 30+ AI points.

### Ranking

Eligible candidates sort by `total_score` descending. Ties break by candidate name (A-Z, case-insensitive,
missing names last), then resume filename, then resume hash. Ranks are sequential (1..N).

## Output (`results.json`)

`ScreeningResults` (schema version `1.0`): `generated_at`, `batch_summary`, `eligible_candidates` (ranked),
`rejected_candidates` (with reasons, matched skills, no rank/score), `failed_candidates`, `duplicates`.
Each candidate has `matched_skills`, `project_summary`, `score_breakdown`, `github_enrichment`, `strengths`,
`concerns` and `status`/`error`. The frontend will consume this contract; it must not duplicate screening logic.

`batch_summary`: `total_resumes = successfully_parsed + failed + duplicates`, and
`successfully_parsed = eligible + rejected` (read, extracted and screened without error).

## Error handling

- Each resume runs inside its own `try/except`; a failure becomes a `failed_candidates` entry with `stage`
  (`read`/`parse`/`extract`/`screen`), `error_type` and `message`, and the batch continues.
- Expected failures (corrupt/encrypted/scanned PDF, unsupported type, oversized file) are logged as warnings;
  unexpected exceptions are logged with a traceback. Nothing is silently swallowed.
- Duplicates are detected by file hash and by normalised-text hash; the first file (sorted path order) is kept.
- Missing name/email/GitHub/projects are warnings surfaced in `concerns`, not errors.
- Optional PDF hyperlink extraction failures are logged and ignored, never fatal.

## Tests

```bash
docker compose run --rm backend pytest
```

Synthetic resumes only; no network or API keys. Covers eligibility (Python+AI, no Python, no AI, Java/React,
tutorial mentions), scoring (skills-list frameworks, thin wrapper penalty, strong RAG/agentic), GitHub default,
deterministic ranking and tie-breaks, per-resume failure isolation (corrupt PDF, unreadable file, exception in
scoring), duplicates, PDF ingestion, and the JSON contract round trip.

## Design Decisions

- **Filtering strategy.** Eligibility is a two-part gate (Python AND AI) evaluated on section- and
  context-aware lines, not on whole-document keyword search. Weak mentions are kept as evidence, labelled weak, so a
  rejection can explain exactly what was seen and why it did not count.
- **Scoring strategy.** Small additive tables with fixed integer points and caps, documented here and in code.
  A reviewer can recompute any score by hand from `score_evidence`.
- **Why hard filtering is outside the LLM.** An eligibility decision must be reproducible, auditable and free of
  prompt/model drift, and must still work when an API is down. The LLM will only add semantic signals later.
- **Why deterministic scoring.** Same input, same output, unit-testable, no cost or latency. The future LLM may
  supply extra project-quality *evidence*, but the arithmetic and the penalty stay in code.
- **Project-quality evidence.** Depth comes from what a project/work entry says it does (retrieval, tools, state,
  evaluation, data logic), not from framework names. Skills-list keywords earn little; project/work evidence earns
  full credit. Thin wrappers are penalised, but only when *no* AI project shows depth.
- **GitHub later.** An enrichment adapter will fill `github_enrichment` and the 10-point category from the extracted
  `github_url`; failures will yield a status (not an exception) and never affect eligibility.

## If I Had More Time

- Calibrate the keyword tables and point weights against ~50 real, labelled resumes and add a regression fixture set.
- Better PDF layout handling (multi-column resumes, OCR for scanned PDFs) and `.docx` support.
- A pluggable LLM adapter to *propose* extra project-quality evidence (with a recorded confidence), kept out of the
  eligibility decision and the arithmetic.
- Decide how to treat classic ML/NLP/CV projects (currently not AI evidence) with the hiring team.

## Known limitations (Step 1)

- Section and project detection is heuristic; resumes that lose bullet markers collapse a project section into one project.
- Classic machine-learning projects (scikit-learn, etc.) are deliberately not counted as AI/LLM evidence.
- A very sparse resume can floor at a total of 0 after the shallow-project penalty.
