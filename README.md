# AI Resume Screening & Ranking

Screens a batch of PDF resumes for Python + AI/LLM/RAG/agentic engineering ability: a hard eligibility
filter first, then an explainable 100-point score for eligible candidates only. The output is a
machine-readable `results.json`.

## Current status: Step 2 (deterministic engine + advisory LLM semantic layer)

| Implemented | Not implemented yet |
|---|---|
| PDF (and `.txt`/`.md`) ingestion, hashing, duplicate detection | GitHub API enrichment and activity scoring (score is `0`, status `not_evaluated`) |
| Field extraction: name, email, skills, projects, GitHub URL | OCR for scanned PDFs, `.docx` |
| Hard eligibility rules (Python AND AI evidence) | Upload UI / frontend dashboard |
| Deterministic 100-point scoring + shallow-project penalty | API endpoints beyond `/health` |
| Ranking, `results.json` contract, CLI, tests | Deployment |
| Optional LLM semantic analysis behind a provider adapter (advisory evidence only) | |

No database, queue, auth or vector store is used or needed.

## Running it (Docker only)

The host needs only Docker and Docker Compose. No local Python, pip or virtualenv.

```bash
cp .env.example .env          # optional; leave LLM_* empty for a deterministic-only run
docker compose build

# run the test suite
docker compose run --rm backend pytest

# screen resumes: reads ./resumes, writes ./output/results.json on the host
docker compose run --rm backend python main.py \
  --input /app/resumes \
  --output /app/output/results.json

# deterministic-only run (never calls an LLM)
docker compose run --rm backend python main.py \
  --input /app/resumes --output /app/output/results.json --no-llm

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
    llm/                  adapter.py (provider boundary), client.py (analyzer: cache, concurrency,
                          failure isolation), schemas.py, prompts.py (versioned), errors.py
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
      semantic.py         grounds LLM output in resume text and maps it to scoring targets
      explain.py          strengths, concerns, project summaries
      ranking.py          engine.py   batch.py
  tests/                  synthetic resumes, fake adapters, a local stub LLM server; no external network
```

Data flow: `file bytes -> text -> Candidate -> hard eligibility -> [eligible only: LLM semantic evidence -> grounding] -> deterministic score -> rank -> ScreeningResults`.
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

## LLM Architecture

**Why it exists.** Keyword rules miss paraphrases ("compares dense vectors", "wrote checks that run on every commit")
and cannot summarise a project. The LLM reads the sectioned resume and reports *which engineering signals the text
supports*, each with a verbatim quote, plus a short factual summary, a depth assessment and a shallow-wrapper flag.

**What it may do:** supply structured *evidence* for eligible candidates, add project summaries/concerns, and corroborate
shallow-wrapper findings. **What it may not do:** decide eligibility, assign any number, set a penalty, change ranking,
remove anything the rules found, or be required for a batch to finish. Fields such as `score` or `penalty` in a reply are
ignored by the schema.

**Flow.** Rejected candidates are never sent to the model. For each eligible candidate:
`prompt (header/contact block excluded) -> adapter -> JSON -> Pydantic validation -> grounding -> deterministic scoring`.

**Grounding and scoring policy** (`screening/semantic.py`):
- A signal counts only if its quote is found in a real resume line (>= 80% of the quote's words). Invented quotes are
  discarded and counted in `llm_enrichment.rejected_signals`.
- The grounded line must be project/work evidence. Skills-list and tutorial/coursework lines earn nothing from the LLM.
- Every signal maps to exactly one scoring target, and each target counts once per project: `rag`/`vector_search` ->
  retrieval (7), `embeddings` -> embeddings/vector store (4), `tool_calling`, `agents`/`multi_agent`,
  `state_management`/`orchestration`, `evaluation`, `data_processing`/`product_logic`, `backend_logic`, `llm_usage`
  (baseline); `fastapi`/`async`/`postgresql`/`redis` -> Python & backend rules; `gcp`/`docker`/`deployment`/`react`/
  `nextjs` -> cloud rules; `testing`/`architecture`/`caching`/`queues`/`concurrency`/`observability`/`failure_handling` ->
  engineering rules. `python` is ignored (Python evidence is already decided deterministically).
  Aliases, repeated quotes and keyword-stuffed sentences therefore cannot stack points; all category caps still apply.
- Additive only: semantic signals are *added* to rule-detected ones. With the LLM off, failed or unavailable, the score is
  exactly the deterministic score.
- Shallow penalty: still 5-15, chosen by the same deterministic tiers. Grounded semantic signals can remove the penalty
  (real retrieval/tools/state/evaluation found); the model's `shallow_wrapper` flag only adds a note to the penalty reason.

**Provider abstraction.** `app/llm/adapter.py` defines `LLMAdapter` (`async complete(system, user) -> str`).
`OpenAICompatibleAdapter` covers OpenRouter, OpenAI and any OpenAI-style endpoint. Another protocol (e.g. native
Anthropic) means one new adapter class and one line in `build_adapter`; screening/scoring code does not change.

**Failure behaviour.** Timeout, rate limit (HTTP 429), auth/API errors, connection errors, non-JSON replies, schema
violations, unexpected exceptions and missing configuration each become a candidate-level
`llm_enrichment: {"status": "failed" | "unavailable", "reason": "<category>"}`. Categories: `timeout`, `rate_limit`,
`auth_error`, `api_error`, `connection_error`, `invalid_json`, `schema_validation`, `unexpected`, and (unavailable)
`not_configured`, `missing_api_key`, `missing_model`, `missing_base_url`. The candidate keeps its deterministic
extraction, eligibility and score. Failures are logged as warnings. Raw prompts, raw replies, provider response bodies
and keys never reach `results.json`.

**Caching and concurrency.** Results (successes and failures) are cached in memory per analyzer instance, keyed by resume
hash + prompt version + model, so a candidate is sent at most once per run. Calls run through an `asyncio.Semaphore`
(`LLM_MAX_CONCURRENCY`, default 3; 1 = sequential). No queue, Redis or database.

**Configuration** (environment / `.env`; see `.env.example`):

| Variable | Default | Meaning |
|---|---|---|
| `LLM_PROVIDER` | empty | `openrouter`, `openai` or `openai_compatible`. Empty = LLM step reported `unavailable`. |
| `LLM_MODEL` | empty | Required model name (no default). |
| `LLM_API_KEY` | empty | Required key. Held as a secret; never logged or serialised. |
| `LLM_BASE_URL` | provider default | Overrides the endpoint; required for `openai_compatible`. |
| `LLM_TIMEOUT_SECONDS` | `30` | Per-call timeout. |
| `LLM_MAX_CONCURRENCY` | `3` | Simultaneous model calls. |

Run with the LLM (put the values in `.env`, then):

```bash
docker compose run --rm backend python main.py --input /app/resumes --output /app/output/results.json
```

Each candidate's `llm_enrichment` reports `status` (`ok` / `failed` / `unavailable` / `skipped`), `reason`, `model`,
`signals_accepted`, `rejected_signals`, `overall_evidence` and `confidence_notes`; `batch_summary.llm_status_counts`
aggregates them. LLM-detected evidence carries `origin: "llm"` and quotes the real resume line.

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

Synthetic resumes only; no live LLM, no external network, no API keys. Step 2 adds fake adapters, `httpx.MockTransport`
adapter tests and a local OpenAI-style stub server (`tests/stub_llm_server.py`) that drives the real adapter end to end.
Covers eligibility (Python+AI, no Python, no AI, Java/React,
tutorial mentions), scoring (skills-list frameworks, thin wrapper penalty, strong RAG/agentic), GitHub default,
deterministic ranking and tie-breaks, per-resume failure isolation (corrupt PDF, unreadable file, exception in
scoring), duplicates, PDF ingestion, and the JSON contract round trip. LLM tests cover: valid / fenced / malformed / schema-invalid replies, timeout and API
errors, missing key or model, caching, bounded concurrency, shallow-chatbot / RAG / stateful-agent responses,
grounding, no double counting, failure preserving the deterministic score, and rejected candidates never reaching the model.

## Design Decisions

- **Filtering strategy.** Eligibility is a two-part gate (Python AND AI) evaluated on section- and
  context-aware lines, not on whole-document keyword search. Weak mentions are kept as evidence, labelled weak, so a
  rejection can explain exactly what was seen and why it did not count.
- **Scoring strategy.** Small additive tables with fixed integer points and caps, documented here and in code.
  A reviewer can recompute any score by hand from `score_evidence`.
- **Why hard filtering is outside the LLM.** An eligibility decision must be reproducible, auditable and free of
  prompt/model drift, and must still work when an API is down. The LLM will only add semantic signals later.
- **Why deterministic scoring.** Same input, same output, unit-testable, no cost or latency. The LLM supplies
  normalised, grounded semantic *evidence*; the arithmetic, caps and the penalty tier stay in code. A model failure
  never terminates screening and never changes a candidate's deterministic score.
- **Project-quality evidence.** Depth comes from what a project/work entry says it does (retrieval, tools, state,
  evaluation, data logic), not from framework names. Skills-list keywords earn little; project/work evidence earns
  full credit. Thin wrappers are penalised, but only when *no* AI project shows depth.
- **LLM placement.** Hard eligibility and the final score stay deterministic. The LLM runs only after the eligibility gate,
  its output is untrusted until grounded in the resume text, and it can only add evidence.
- **GitHub later.** An enrichment adapter will fill `github_enrichment` and the 10-point category from the extracted
  `github_url`; failures will yield a status (not an exception) and never affect eligibility.

## If I Had More Time

- Calibrate the keyword tables and point weights against ~50 real, labelled resumes and add a regression fixture set.
- Better PDF layout handling (multi-column resumes, OCR for scanned PDFs) and `.docx` support.
- Let semantic analysis also *veto* keyword-only false positives (currently it can only add evidence), and add a retry/backoff
  policy for rate limits plus a native Anthropic adapter.
- Decide how to treat classic ML/NLP/CV projects (currently not AI evidence) with the hiring team.

## Known limitations

- Section and project detection is heuristic; resumes that lose bullet markers collapse a project section into one project.
- Classic machine-learning projects (scikit-learn, etc.) are deliberately not counted as AI/LLM evidence.
- A very sparse resume can floor at a total of 0 after the shallow-project penalty.
- Semantic grounding checks that a quote exists in the resume, not that it truly supports the claimed signal; a resume
  containing prompt-injection text can still present misleading (but real) lines. Only the LLM-added share of the score is exposed to this.
- The LLM step uses `asyncio.run` and must not be called from inside a running event loop (relevant when API endpoints are added).
