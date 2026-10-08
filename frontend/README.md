# Frontend (React + TypeScript + Vite)

The screening dashboard. It is a client of the FastAPI service in `../backend` and contains **no screening logic**:
it uploads resumes to `POST /screen`, renders the returned `ScreeningResults`, and lets the user download that JSON.
Eligibility, scoring, GitHub enrichment, LLM analysis and ranking all happen in the backend.

## Run (Docker only; no host Node needed)

```bash
docker compose up --build                       # from the repo root: http://localhost:3000 (+ API on :8000)
docker compose run --rm --no-deps frontend npm test          # Vitest
docker compose run --rm --no-deps frontend npm run typecheck
docker compose run --rm --no-deps frontend npm run build     # tsc + production bundle
docker build --target prod -t resume-screening-frontend:prod ./frontend   # nginx + static files
```

In development `src/`, `public/`, `index.html`, `vite.config.ts` and `tsconfig.json` are bind-mounted, so edits hot-reload
without a rebuild. `node_modules` lives in the image; rebuild after changing `package.json` (the lockfile was generated
inside Docker).

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `VITE_API_BASE_URL` | `http://localhost:8000` | URL the **browser** uses to reach the backend (build-time for the prod image via `--build-arg`; set by Compose in dev). Public: never put secrets here. |
| `FRONTEND_PORT` / `BACKEND_PORT` | `3000` / `8000` | Host ports (root `docker-compose.yml`). The backend's `CORS_ORIGINS` must allow the frontend origin; Compose derives it from `FRONTEND_PORT`. |

## Structure

```text
src/
  api/client.ts          the only module that calls fetch(): /health, /screen, /results, errors, timeouts
  types/results.ts       TypeScript mirror of the backend result schema (display types only)
  lib/                   formatting helpers, file-selection validation
  hooks/useDialog.ts     Escape / focus-trap / scroll-lock for the details panel
  components/            UploadPanel, ProcessingState, BatchSummary, CandidateTable/Card, CandidateDetails,
                         ScoreBreakdown, OtherResults (rejected / failed / duplicates), ResultsView, Header, ...
  styles/                design tokens (light + dark), base, components (responsive, reduced-motion aware)
  test/                  Vitest + Testing Library tests with mocked API responses
```

## Behaviour notes

- Uploads: PDF only in the UI (the API also accepts `.txt`/`.md` for testing). Folder selection uses the browser's
  directory picker and keeps folder-relative names. Drag and drop handles files; for folders use "Choose Folder".
- `/screen` is one synchronous request with no progress reporting, so the processing view is indeterminate and offers
  "Stop waiting" (the server may still finish the batch; the result then appears under "View latest results").
- Errors from the API are mapped to short messages (409 busy, 413 too large, 422/400 invalid upload, 5xx generic);
  raw server text and stack traces are never shown.
- Candidate data is kept in memory only (no localStorage / sessionStorage).
