# AI Resume Screening & Ranking

Pipeline: `extract -> hard eligibility -> [eligible only: LLM semantic evidence, GitHub enrichment] -> deterministic score -> rank -> results.json`.

Screens a batch of PDF resumes for Python + AI/LLM/RAG/agentic engineering ability: a hard eligibility
filter first, then an explainable 100-point score for eligible candidates only. The output is a
machine-readable `results.json`.

## Current status: Step 4 (deterministic engine + LLM layer + GitHub enrichment + HTTP API)

| Implemented | Not implemented yet |
|---|---|
| PDF (and `.txt`/`.md`) ingestion, hashing, duplicate detection | Frontend dashboard, browser upload UI |
| Field extraction: name, email, skills, projects, GitHub URL | OCR for scanned PDFs, `.docx` |
| Hard eligibility rules (Python AND AI evidence) | Authentication |
| Deterministic 100-point scoring + shallow-project penalty | Background jobs, queues, WebSockets |
| Ranking, `results.json` contract, CLI, tests | Deployment |
| Optional LLM semantic analysis behind a provider adapter (advisory evidence only) | |
| FastAPI interface (`/health`, `/screen`, `/results`) over the same pipeline as the CLI | |
| Lightweight public GitHub enrichment, 0-10 points (never affects eligibility) | |

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

# deterministic-only run (no LLM calls, no GitHub calls)
docker compose run --rm backend python main.py \
  --input /app/resumes --output /app/output/results.json --no-llm --no-github

# API server on http://localhost:8000 (auto-reload; docs at /docs)
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
frontend/                 placeholder (later step; no UI exists yet)
backend/
  Dockerfile  requirements.txt  pytest.ini
  main.py                 CLI entry point
  app/
    api/                  FastAPI app: routes.py (thin handlers), uploads.py (safe upload storage),
                          schemas.py, main.py (app factory, CORS, error handler)
    pipeline/             factory.py (builds the processor: used by CLI and API), results_store.py (atomic results.json)
    errors.py             structured pipeline errors (stage-tagged)
    github/               client.py (HTTP), service.py (cache, concurrency, failure isolation),
                          scoring.py (pure 0-10 rules), urls.py (link -> username), schemas.py, errors.py
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

Java, JavaScript, React, Next.js, etc. never cause rejection. Missing, private or unreachable GitHub never affects eligibility.
Rejections state which side failed and why (e.g. `Only weak Python mentions found ... learning/tutorial context`).

## Scoring model (100 points, integers)

Rejected candidates are not scored. Every point appears in `score_evidence` with the resume line behind it.

| Category | Max | Formula |
|---|---|---|
| AI / Agentic / RAG depth | 40 | Per project / work entry that mentions AI: 5 baseline + retrieval 7 + embeddings/vector store/chunking 4 + tool calling 5 + agents 6 + orchestration/state 5 + evaluation 5 + data/product logic 4 + backend integration 3. Result = best unit + 2 per *other* AI unit scoring >= 10 (cap 6) + 1 per AI framework/technique present only in skills (cap 3), capped at 40. AI mentions outside project/work sections are capped at 10. |
| Python & backend | 30 | Python 12 (4 any qualifying evidence + 5 in a project + 3 in work) + web framework 5 + database 4 + async 3 + Redis 3 + backend implementation 3. A keyword only in a skills list earns reduced points (2/2/1/1/1 respectively). |
| Cloud / deployment / full stack | 15 | cloud provider 4 + containers 3 + deployment/CI-CD 4 + frontend framework 2 + end-to-end system 2 (skills-list-only keywords earn 2/1/1/1/0). |
| GitHub | 10 | Recent activity 0-5 + repositories 0-5 from public GitHub data (see **GitHub Enrichment**). `0` when the link is missing/invalid or the API fails. |
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

## API

The API is a thin interface over the **same** pipeline the CLI uses (`app/pipeline/factory.py` builds the processor;
`BatchProcessor.process_async` runs it). Route handlers only validate input, store uploads safely, call the pipeline and
return the canonical `ScreeningResults` model: there is no screening logic in the API layer.

```text
                 CLI (main.py)        API (app/api)
                        \               /
                   app.pipeline.build_processor
                              |
                     BatchProcessor (async)
        extraction -> eligibility -> LLM / GitHub (eligible only) -> deterministic scoring -> ranking
                              |
                       ScreeningResults -> results.json
```

Start it with `docker compose up` (port 8000). Interactive docs: `http://localhost:8000/docs`; schema: `/openapi.json`.

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | `{"status": "ok"}`. No configuration is exposed. |
| `POST` | `/screen` | Multipart upload of one or many resumes; returns `ScreeningResults` and writes `output/results.json`. |
| `GET` | `/results` | The latest completed `ScreeningResults` read from `results.json`; `404` if no run has completed yet. |

**`POST /screen`**: repeat the multipart field `files` once per resume (PDF is the intended format; `.txt`/`.md` are also
accepted for testing). Query options (default `true`, equivalent to the CLI's `--no-llm` / `--no-github`):
`use_llm`, `use_github`. Scoring rules and weights cannot be changed through the API.

```bash
curl -X POST "http://localhost:8000/screen" \
  -F "files=@resumes/candidate_01.pdf" \
  -F "files=@resumes/candidate_02.pdf" \
  -F "files=@resumes/candidate_03.pdf"

# deterministic only, no model or GitHub calls
curl -X POST "http://localhost:8000/screen?use_llm=false&use_github=false" -F "files=@resumes/candidate_01.pdf"

curl http://localhost:8000/results
```

- **Folder uploads need no special endpoint.** A browser directory picker just sends every selected file as a `files`
  part; one request is one batch. Folder-relative names such as `team_a/cv.pdf` are kept for display; `.`-prefixed files
  (`.DS_Store`) are skipped, matching the CLI.
- **Upload safety.** Uploaded filenames are untrusted. Each file is streamed into an isolated temporary directory under a
  generated name (`0000.pdf`, `0001.pdf`, ...); the client name is only sanitised for reporting (backslashes become `/`,
  control characters, empty, `.` and `..` segments and drive letters are dropped, so `../../etc/passwd.pdf` is reported as
  `etc/passwd.pdf`). Two files with the same name are reported as `cv.pdf` and `cv (2).pdf`. The temporary directory is
  removed when the request ends (also on errors); the project's `resumes/` folder is never touched.
- **Per-file problems stay per-file.** Unsupported types, empty files and corrupt PDFs appear under `failed_candidates`
  with HTTP 200, exactly like the CLI. Duplicates (identical bytes or text) appear under `duplicates`.
- **Request errors.** `422` no `files` field; `400` no usable files (blank or only hidden files); `413` more than
  `MAX_UPLOAD_FILES` files or more than `MAX_UPLOAD_TOTAL_MB` in total; `409` another run is in progress (runs are
  serialised, not queued); `500` the pipeline failed unexpectedly (a generic message; details only in the server log, never
  API keys, headers or provider responses). A failed request never modifies the previous `results.json`.
- **Isolation.** Each request builds a fresh processor, so LLM/GitHub caches and rate-limit state are never shared between
  requests. Within a request the LLM and GitHub semaphores and caches work as before.
- **Output.** `results.json` is written atomically (temp file in the same folder, `fsync`, rename), so `/results` and
  readers on the host never see a half-written file. It is visible on the host as `./output/results.json`. It contains
  no raw model output, provider responses or tokens.

**CORS.** `CORS_ORIGINS` is a comma-separated list of allowed browser origins (default `http://localhost:3000`). Only
`GET`/`POST` and the `Content-Type` header are allowed. Set it to an empty string to disable CORS. `*` is accepted but
logs a warning; it is not the default. There is no authentication.

| Variable | Default | Meaning |
|---|---|---|
| `CORS_ORIGINS` | `http://localhost:3000` | Allowed browser origins, comma-separated. |
| `RESULTS_PATH` | `output/results.json` | Where `/screen` writes and `/results` reads (`/app/output/results.json` in Docker). |
| `MAX_UPLOAD_FILES` | `200` | Maximum files per `/screen` request. |
| `MAX_UPLOAD_TOTAL_MB` | `200` | Maximum total upload size per request. |

A single file larger than 20 MB is recorded as a per-file failure rather than rejecting the request.

## GitHub Enrichment

**Why it is additional, not mandatory.** The assignment treats GitHub as a lightweight positive signal worth at most
10 of 100 points. Many strong candidates have private work, company repos or no public account, so a missing link,
a private/unknown profile or an API failure scores `0` GitHub points and changes nothing else: eligibility is decided
*before* GitHub is consulted, and a candidate can never be rejected, dropped or made eligible by it.

**Honest limits.** GitHub activity is an *approximate public signal*, not a measure of engineering ability. The public
Events API only exposes recent activity (we read one page of up to 100 events) and is not a complete contribution
history. Followers and stars are deliberately **not used**. No LLM is involved in GitHub scoring.

**Flow.** Only *eligible* candidates are enriched (rejected candidates make no GitHub calls). Usernames are de-duplicated
and cached for the run; each unique account costs at most two requests:
`GET /users/{u}/repos?type=owner&sort=pushed&per_page=100` and `GET /users/{u}/events/public?per_page=100`.

**Link normalisation** (`github/urls.py`). `https://github.com/u`, `https://www.github.com/u/`, `github.com/u` all
become the username `u`. Repository links (`github.com/u/repo`) are not accepted as profiles by the normaliser. During
resume extraction a repo-only link yields its owner only if *all* GitHub links on the resume share one owner; links to
several owners (e.g. a framework's org) are ambiguous and no profile is inferred. A username is never guessed from a
person's name.

**Recent activity, 0-5** (`github/scoring.py`). Counted events in the last 90 days: pushes, pull requests, PR reviews and
review comments, issues, issue comments, branch/tag/repo creation, releases. Stars, watches and forks are ignored.
N = counted events, D = distinct active days; the highest satisfied tier applies:

| Points | Condition |
|---|---|
| 5 | N >= 25 and D >= 4 |
| 4 | N >= 12 and D >= 3 |
| 3 | N >= 6 and D >= 2 |
| 2 | N >= 3 |
| 1 | N >= 1 |
| 0 | no recent engineering events |

**Repositories, 0-5.** Among the first 100 public repos owned by the user (most recently pushed first), a repo is
*maintained* if it is not a fork, not archived, not empty and was pushed in the last 365 days.

| Points | Condition |
|---|---|
| 0-2 | number of maintained repos (0 -> 0, 1 -> 1, 2 or more -> 2) |
| +1 | a maintained repo has a description of >= 20 characters or topics |
| +1 | a maintained repo is Python-relevant |
| +1 | a maintained repo is AI-relevant |

**Relevance** is detected on repo name, description, topics and primary language (no LLM). Python: language `Python`
or terms such as python, fastapi, django, flask, asyncio, pydantic, pytest, pandas. AI: ai, llm, rag, langchain,
langgraph, agent(s), agentic, embedding(s), vector search, machine learning, openai, gpt, chatbot, retrieval, ... The
sets are the `python_terms` / `ai_terms` fields of `GitHubRules` and are matched on whole words. Up to 5 relevant repos
are listed in the output.

`github points = activity + repositories` (max 10). The score ledger shows `+N GitHub: recent public engineering activity`
and `+N GitHub: maintained/relevant public repositories`, or `GitHub: 0 points - <reason>`.

**Statuses** (`github_enrichment.status`): `ok`, `missing` (no link), `invalid_url`, `not_found` (404),
`rate_limited` (429, or 403 with rate-limit signals), `timeout`, `api_error` (other HTTP errors, malformed responses,
connection errors, rejected token), and `not_evaluated` (rejected candidate, or `--no-github`). Failures carry a short
`reason` (e.g. `HTTP 500`); responses, tokens and payloads are never stored. `batch_summary.github_status_counts`
aggregates them, and a non-`ok` status adds an informational note to `concerns`.

**Rate limits and cost.** No automatic retries. After the first rate-limited response the enricher stops calling GitHub for
the rest of the run (remaining accounts are reported `rate_limited` without a request), so a 50-resume batch cannot turn
into hundreds of failing calls. Unauthenticated requests are limited to roughly 60 per hour per IP, i.e. about 30
distinct accounts per hour at two requests each: set `GITHUB_TOKEN` for larger batches.

**Caching and concurrency.** Results (including failures) are cached in memory per run by lower-cased username, so two
resumes naming the same account cause one enrichment. Accounts are processed with an `asyncio.Semaphore`
(`GITHUB_MAX_CONCURRENCY`, default 3; a user's two requests run sequentially, so at most that many requests are in
flight). Enrichment is awaited on the caller's event loop after the LLM phase; nothing in the pipeline calls
`asyncio.run`.

**Configuration.**

| Variable | Default | Meaning |
|---|---|---|
| `GITHUB_TOKEN` | empty | Optional. Sent as `Authorization: Bearer ...` only; never logged or serialised. Without it requests are unauthenticated. A fine-grained token with no permissions is enough. |
| `GITHUB_API_BASE_URL` | `https://api.github.com` | Override for GitHub Enterprise or a test stub. |
| `GITHUB_TIMEOUT_SECONDS` | `10` | Per-request timeout. |
| `GITHUB_MAX_CONCURRENCY` | `3` | Simultaneous GitHub requests. |

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
- GitHub failures (`not_found`, `rate_limited`, `timeout`, `api_error`, ...) are recorded per candidate with 0 GitHub points;
  the candidate stays eligible and ranked on its other categories.
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
scoring), duplicates, PDF ingestion, and the JSON contract round trip. API tests (`TestClient`, fake LLM and GitHub, temporary results file) cover health, single/multiple/mixed/corrupt/duplicate uploads, no files, unsupported types, option flags, `/results` before and after a run, schema equality, atomic writes and failure preservation, hostile filenames and temp-dir cleanup, per-request isolation, no nested `asyncio.run`, 409/413 limits, CORS, OpenAPI, and CLI/API parity. GitHub tests (fake transport, no live GitHub) cover URL normalisation, activity/repository scoring and relevance, 404 / rate limit / timeout / API errors, token handling, caching, bounded concurrency, score caps, rejected candidates making no calls, failure preservation and stable ranking. LLM tests cover: valid / fenced / malformed / schema-invalid replies, timeout and API
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
- **GitHub.** An isolated adapter fills `github_enrichment` and the 10-point category for eligible candidates only, after
  the gate. Pure deterministic rules turn public metadata into points (no stars/followers, no LLM); failures yield a
  status, never an exception or a rejection.

## If I Had More Time

- Calibrate the keyword tables and point weights against ~50 real, labelled resumes and add a regression fixture set.
- Better PDF layout handling (multi-column resumes, OCR for scanned PDFs) and `.docx` support.
- Let semantic analysis also *veto* keyword-only false positives (currently it can only add evidence), and add a retry/backoff
  policy for rate limits plus a native Anthropic adapter.
- Use GitHub GraphQL contribution counts (needs a token) for a fuller activity picture, and weigh repo content (README/tests) rather than metadata alone.
- Decide how to treat classic ML/NLP/CV projects (currently not AI evidence) with the hiring team.

## Known limitations

- Section and project detection is heuristic; resumes that lose bullet markers collapse a project section into one project.
- Classic machine-learning projects (scikit-learn, etc.) are deliberately not counted as AI/LLM evidence.
- A very sparse resume can floor at a total of 0 after the shallow-project penalty.
- Semantic grounding checks that a quote exists in the resume, not that it truly supports the claimed signal; a resume
  containing prompt-injection text can still present misleading (but real) lines. Only the LLM-added share of the score is exposed to this.
- The sync wrappers `BatchProcessor.process()` / `process_directory()` (used by unit tests) call `asyncio.run` and must not be used inside a running loop; the CLI and API use the async methods.
- Only one `/screen` run executes at a time (a second concurrent request gets HTTP 409). Runs are synchronous HTTP requests: a large batch with a slow LLM can take long, and there is no progress reporting or job queue.
- `GET /results` returns only the latest run; there is no history.
- GitHub sees only one page (100) of public events and repos, so very prolific accounts are slightly under-counted, and `public_repositories` counts at most 100. Repo-name/description keyword relevance can mislabel repos.
- A single repository link on a resume is trusted to belong to the candidate when it is the only owner mentioned.
