"""Batch processing: one resume's failure never stops the batch."""

import logging
from collections import Counter
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from app.errors import ProcessingStage, ResumeProcessingError
from app.extraction import extract_candidate
from app.llm import SemanticAnalyzer, SemanticOutcome
from app.ingestion import discover_resume_files, extract_text, sha256_bytes, text_fingerprint
from app.models import (
    BatchSummary,
    Candidate,
    CandidateResult,
    DuplicateRecord,
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
Screener = Callable[..., CandidateResult]  # (candidate[, semantic=SemanticOutcome])


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

    Phases: (1) read/parse/extract every file, (2) hard eligibility, then LLM semantic
    analysis for the *eligible* candidates only (bounded concurrency, optional),
    (3) deterministic scoring + ranking. Each resume is isolated at every phase.
    """

    def __init__(
        self,
        read_text: TextReader = extract_text,
        extract: Extractor = extract_candidate,
        screen: Screener = screen_candidate,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        analyzer: SemanticAnalyzer | None = None,
    ) -> None:
        self._read_text = read_text
        self._extract = extract
        self._screen = screen
        self._clock = clock
        self._analyzer = analyzer

    def process_directory(self, input_dir: Path) -> ScreeningResults:
        paths = discover_resume_files(input_dir)
        items: list[tuple[str, Callable[[], bytes]]] = [
            (p.relative_to(input_dir).as_posix(), p.read_bytes) for p in paths
        ]
        return self.process(items)

    def process(self, items: Sequence[tuple[str, Callable[[], bytes]]]) -> ScreeningResults:
        """``items`` are (filename, lazy byte reader) pairs, processed in the given order."""
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

        outcomes = self._semantic_outcomes(prepared)
        eligible: list[CandidateResult] = []
        rejected: list[CandidateResult] = []
        for candidate in prepared:
            try:
                outcome = outcomes.get(candidate.resume_hash)
                result = (
                    self._screen(candidate, semantic=outcome) if outcome else self._screen(candidate)
                )
                (eligible if result.eligible else rejected).append(result)
            except Exception as exc:
                logger.exception(
                    "Unexpected failure on %s at %s", candidate.resume_filename, ProcessingStage.SCREEN
                )
                failed.append(
                    failed_result(candidate.resume_filename, candidate.resume_hash, ProcessingStage.SCREEN, exc)
                )

        failed.sort(key=lambda r: r.resume_filename.casefold())
        ranked = rank_candidates(eligible)
        rejected.sort(key=lambda r: (r.resume_filename.casefold(), r.resume_hash or ""))
        summary = BatchSummary(
            total_resumes=len(items),
            successfully_parsed=len(ranked) + len(rejected),
            eligible=len(ranked),
            rejected=len(rejected),
            failed=len(failed),
            duplicates=len(duplicates),
            llm_status_counts=dict(
                sorted(Counter(r.llm_enrichment.status for r in [*ranked, *rejected]).items())
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

    def _semantic_outcomes(self, candidates: Sequence[Candidate]) -> dict[str, SemanticOutcome]:
        """LLM analysis for eligible candidates only. Never raises."""
        if self._analyzer is None:
            return {}
        eligible: list[Candidate] = []
        for candidate in candidates:
            try:
                if check_eligibility(candidate).eligible:
                    eligible.append(candidate)
            except Exception:
                # the screening phase will hit the same error and record the failure
                logger.exception("Eligibility check failed for %s", candidate.resume_filename)
        if not eligible:
            return {}
        try:
            return self._analyzer.analyze_many(eligible)
        except Exception as exc:  # analyzer already isolates model errors; this is a last resort
            logger.exception("LLM batch analysis failed unexpectedly")
            failure = SemanticOutcome("failed", reason=f"unexpected:{type(exc).__name__}")
            return {c.resume_hash: failure for c in eligible}
