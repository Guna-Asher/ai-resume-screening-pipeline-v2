"""Batch processing: one resume's failure never stops the batch."""

import logging
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from app.errors import ProcessingStage, ResumeProcessingError
from app.extraction import extract_candidate
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
from app.screening.engine import screen_candidate
from app.screening.ranking import rank_candidates

logger = logging.getLogger(__name__)

TextReader = Callable[[str, bytes], str]
Extractor = Callable[[str, str, str], Candidate]
Screener = Callable[[Candidate], CandidateResult]


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
    """Collaborators are injectable so failures can be simulated in tests."""

    def __init__(
        self,
        read_text: TextReader = extract_text,
        extract: Extractor = extract_candidate,
        screen: Screener = screen_candidate,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._read_text = read_text
        self._extract = extract
        self._screen = screen
        self._clock = clock

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
        eligible: list[CandidateResult] = []
        rejected: list[CandidateResult] = []
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
                candidate = self._extract(text, filename, resume_hash)
                stage = ProcessingStage.SCREEN
                result = self._screen(candidate)
                (eligible if result.eligible else rejected).append(result)
            except Exception as exc:
                if isinstance(exc, ResumeProcessingError):
                    stage = exc.stage
                    logger.warning("Resume %s failed at %s: %s", filename, stage.value, exc)
                else:  # unexpected: keep the traceback
                    logger.exception("Unexpected failure on %s at %s", filename, stage.value)
                failed.append(failed_result(filename, resume_hash, stage, exc))

        ranked = rank_candidates(eligible)
        rejected.sort(key=lambda r: (r.resume_filename.casefold(), r.resume_hash or ""))
        summary = BatchSummary(
            total_resumes=len(items),
            successfully_parsed=len(ranked) + len(rejected),
            eligible=len(ranked),
            rejected=len(rejected),
            failed=len(failed),
            duplicates=len(duplicates),
        )
        return ScreeningResults(
            generated_at=self._clock(),
            batch_summary=summary,
            eligible_candidates=ranked,
            rejected_candidates=rejected,
            failed_candidates=failed,
            duplicates=duplicates,
        )
