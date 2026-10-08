"""Batch processing: one resume's failure never stops the batch.

The core is ``BatchProcessor.process_async`` / ``process_directory_async``. They are
plain coroutines (no ``asyncio.run`` inside), so they can be awaited from the FastAPI
event loop and from the CLI's single top-level ``asyncio.run``. The sync ``process`` /
``process_directory`` wrappers exist only for synchronous callers such as unit tests.
"""

import asyncio
import logging
from collections import Counter
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from app.errors import ProcessingStage, ResumeProcessingError
from app.extraction import extract_candidate
from app.github import GitHubEnricher, failure
from app.ingestion import discover_resume_files, extract_text, sha256_bytes, text_fingerprint
from app.llm import SemanticAnalyzer, SemanticOutcome
from app.models import (
    BatchSummary,
    Candidate,
    CandidateResult,
    DuplicateRecord,
    GitHubEnrichment,
    GitHubStatus,
    ProcessingError,
    ProcessingStatus,
    ScreeningResults,
)
from app.screening.eligibility import check_eligibility
from app.screening.engine import screen_candidate
from app.screening.ranking import rank_candidates

logger = logging.getLogger(__name__)

TextReader = Callable[[str, bytes], str]
Extractor = Callable[[str, str, str], Candidate]
Screener = Callable[..., CandidateResult]  # (candidate[, semantic=..., github=...])
ResumeItem = tuple[str, Callable[[], bytes]]  # (reported filename, lazy byte reader)


def failed_result(
    filename: str, resume_hash: str | None, stage: ProcessingStage, exc: Exception
) -> CandidateResult:
    return CandidateResult(
        resume_filename=filename,
        resume_hash=resume_hash,
        status=ProcessingStatus.FAILED,
        error=ProcessingError(stage=stage.value, error_type=type(exc).__name__, message=str(exc)),
        eligible=False,
        concerns=[f"Processing failed at '{stage.value}' stage: {exc}"],
    )


class BatchProcessor:
    """Collaborators are injectable so failures can be simulated in tests.

    Phases: (1) read/parse/extract every file, (2) hard eligibility, then - for the *eligible*
    candidates only - LLM semantic analysis and GitHub enrichment (both optional, bounded
    concurrency, cached per run), (3) deterministic scoring (GitHub points included) and
    ranking. Each resume is isolated at every phase.

    One instance is meant for one run: the analyzer / enricher carry run-level caches.
    """

    def __init__(
        self,
        read_text: TextReader = extract_text,
        extract: Extractor = extract_candidate,
        screen: Screener = screen_candidate,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        analyzer: SemanticAnalyzer | None = None,
        github: GitHubEnricher | None = None,
    ) -> None:
        self._read_text = read_text
        self._extract = extract
        self._screen = screen
        self._clock = clock
        self._analyzer = analyzer
        self._github = github

    # ------------------------------------------------------------------ async API

    async def process_directory_async(self, input_dir: Path) -> ScreeningResults:
        paths = discover_resume_files(input_dir)
        items: list[ResumeItem] = [
            (p.relative_to(input_dir).as_posix(), p.read_bytes) for p in paths
        ]
        return await self.process_async(items)

    async def process_async(self, items: Sequence[ResumeItem]) -> ScreeningResults:
        """``items`` are (filename, lazy byte reader) pairs, processed in the given order.

        CPU/file-bound phases run in worker threads so the event loop (and, in the API,
        health checks) stay responsive; the LLM and GitHub phases are awaited directly.
        """
        prepared, failed, duplicates = await asyncio.to_thread(self._prepare, items)
        eligible = await asyncio.to_thread(self._eligible, prepared)
        outcomes = await self._semantic_outcomes(eligible)
        github_results = await self._github_enrichments(eligible)
        return await asyncio.to_thread(
            self._finish, len(items), prepared, failed, duplicates, outcomes, github_results
        )

    # ------------------------------------------------------- sync wrappers (tests)

    def process_directory(self, input_dir: Path) -> ScreeningResults:
        """Synchronous convenience wrapper. Do not call from a running event loop."""
        return asyncio.run(self.process_directory_async(input_dir))

    def process(self, items: Sequence[ResumeItem]) -> ScreeningResults:
        """Synchronous convenience wrapper. Do not call from a running event loop."""
        return asyncio.run(self.process_async(items))

    # ------------------------------------------------------------------- phases

    def _prepare(
        self, items: Sequence[ResumeItem]
    ) -> tuple[list[Candidate], list[CandidateResult], list[DuplicateRecord]]:
        """Phase 1: read, de-duplicate, parse and extract. Failures become records."""
        seen_bytes: dict[str, str] = {}
        seen_text: dict[str, str] = {}
        prepared: list[Candidate] = []
        failed: list[CandidateResult] = []
        duplicates: list[DuplicateRecord] = []

        for filename, read_bytes in items:
            stage = ProcessingStage.READ
            resume_hash: str | None = None
            try:
                data = read_bytes()
                resume_hash = sha256_bytes(data)
                if resume_hash in seen_bytes:
                    duplicates.append(
                        DuplicateRecord(
                            resume_filename=filename,
                            duplicate_of=seen_bytes[resume_hash],
                            reason="identical_file",
                        )
                    )
                    continue
                seen_bytes[resume_hash] = filename

                stage = ProcessingStage.PARSE
                text = self._read_text(filename, data)
                fingerprint = text_fingerprint(text)
                if fingerprint in seen_text:
                    duplicates.append(
                        DuplicateRecord(
                            resume_filename=filename,
                            duplicate_of=seen_text[fingerprint],
                            reason="identical_text",
                        )
                    )
                    continue
                seen_text[fingerprint] = filename

                stage = ProcessingStage.EXTRACT
                prepared.append(self._extract(text, filename, resume_hash))
            except Exception as exc:
                if isinstance(exc, ResumeProcessingError):
                    stage = exc.stage
                    logger.warning("Resume %s failed at %s: %s", filename, stage.value, exc)
                else:  # unexpected: keep the traceback
                    logger.exception("Unexpected failure on %s at %s", filename, stage.value)
                failed.append(failed_result(filename, resume_hash, stage, exc))
        return prepared, failed, duplicates

    def _finish(
        self,
        total: int,
        prepared: list[Candidate],
        failed: list[CandidateResult],
        duplicates: list[DuplicateRecord],
        outcomes: dict[str, SemanticOutcome],
        github_results: dict[str, GitHubEnrichment],
    ) -> ScreeningResults:
        """Phase 3: deterministic scoring, ranking and the batch summary."""
        eligible: list[CandidateResult] = []
        rejected: list[CandidateResult] = []
        for candidate in prepared:
            try:
                kwargs = {}
                if candidate.resume_hash in outcomes:
                    kwargs["semantic"] = outcomes[candidate.resume_hash]
                if candidate.resume_hash in github_results:
                    kwargs["github"] = github_results[candidate.resume_hash]
                result = self._screen(candidate, **kwargs)
                (eligible if result.eligible else rejected).append(result)
            except Exception as exc:
                logger.exception(
                    "Unexpected failure on %s at %s",
                    candidate.resume_filename,
                    ProcessingStage.SCREEN.value,
                )
                failed.append(
                    failed_result(
                        candidate.resume_filename, candidate.resume_hash, ProcessingStage.SCREEN, exc
                    )
                )

        failed.sort(key=lambda r: r.resume_filename.casefold())
        ranked = rank_candidates(eligible)
        rejected.sort(key=lambda r: (r.resume_filename.casefold(), r.resume_hash or ""))
        screened = [*ranked, *rejected]
        summary = BatchSummary(
            total_resumes=total,
            successfully_parsed=len(ranked) + len(rejected),
            eligible=len(ranked),
            rejected=len(rejected),
            failed=len(failed),
            duplicates=len(duplicates),
            llm_status_counts=dict(sorted(Counter(r.llm_enrichment.status for r in screened).items())),
            github_status_counts=dict(
                sorted(Counter(r.github_enrichment.status.value for r in screened).items())
            ),
        )
        return ScreeningResults(
            generated_at=self._clock(),
            batch_summary=summary,
            eligible_candidates=ranked,
            rejected_candidates=rejected,
            failed_candidates=failed,
            duplicates=duplicates,
        )

    @staticmethod
    def _eligible(candidates: Sequence[Candidate]) -> list[Candidate]:
        """Candidates passing the deterministic gate: the only ones LLM/GitHub work is spent on."""
        eligible: list[Candidate] = []
        for candidate in candidates:
            try:
                if check_eligibility(candidate).eligible:
                    eligible.append(candidate)
            except Exception:
                # the screening phase will hit the same error and record the failure
                logger.exception("Eligibility check failed for %s", candidate.resume_filename)
        return eligible

    async def _semantic_outcomes(
        self, eligible: Sequence[Candidate]
    ) -> dict[str, SemanticOutcome]:
        """LLM analysis for eligible candidates only. Never raises."""
        if self._analyzer is None or not eligible:
            return {}
        try:
            return await self._analyzer.analyze_many_async(list(eligible))
        except Exception as exc:  # analyzer already isolates model errors; this is a last resort
            logger.exception("LLM batch analysis failed unexpectedly")
            failure_outcome = SemanticOutcome("failed", reason=f"unexpected:{type(exc).__name__}")
            return {c.resume_hash: failure_outcome for c in eligible}

    async def _github_enrichments(
        self, eligible: Sequence[Candidate]
    ) -> dict[str, GitHubEnrichment]:
        """Public-GitHub signal for eligible candidates only. Never raises."""
        if self._github is None or not eligible:
            return {}
        try:
            return await self._github.enrich_many_async(
                [(c.resume_hash, c.github_url) for c in eligible]
            )
        except Exception as exc:  # enricher already isolates API errors; this is a last resort
            logger.exception("GitHub batch enrichment failed unexpectedly")
            return {
                c.resume_hash: failure(GitHubStatus.API_ERROR, f"unexpected: {type(exc).__name__}")
                for c in eligible
            }
