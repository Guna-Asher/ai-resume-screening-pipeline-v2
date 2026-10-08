"""File discovery and text extraction. Pure functions; no batch state."""

import io
import logging
from pathlib import Path

from pypdf import PdfReader

from app.errors import FileTooLargeError, ResumeParseError, UnsupportedFormatError

logger = logging.getLogger(__name__)

PDF_SUFFIX = ".pdf"
TEXT_SUFFIXES = {".txt", ".md"}  # convenience formats for local testing
SUPPORTED_SUFFIXES = {PDF_SUFFIX, *TEXT_SUFFIXES}
MAX_FILE_BYTES = 20 * 1024 * 1024


def discover_resume_files(input_dir: Path) -> list[Path]:
    """All regular, non-hidden files under ``input_dir``, in sorted order.

    Unsupported types are returned too, so the batch can report them as
    failures instead of silently ignoring them.
    """
    if not input_dir.is_dir():
        raise NotADirectoryError(f"Input directory not found: {input_dir}")
    files = [
        p
        for p in input_dir.rglob("*")
        if p.is_file() and not any(part.startswith(".") for part in p.relative_to(input_dir).parts)
    ]
    return sorted(files, key=lambda p: p.relative_to(input_dir).as_posix())


def extract_text(filename: str, data: bytes) -> str:
    """Turn raw file bytes into resume text, based on the file suffix."""
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise UnsupportedFormatError(
            f"Unsupported file type '{suffix or '(none)'}'; supported: "
            f"{', '.join(sorted(SUPPORTED_SUFFIXES))}"
        )
    if len(data) > MAX_FILE_BYTES:
        raise FileTooLargeError(f"File is {len(data)} bytes; limit is {MAX_FILE_BYTES}")

    text = _pdf_text(data) if suffix == PDF_SUFFIX else data.decode("utf-8", errors="replace")
    if not text.strip():
        raise ResumeParseError(
            "No extractable text found (empty file, or a scanned/image-only document)"
        )
    return text


def _pdf_text(data: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise ResumeParseError("PDF is encrypted")
        pages = [page.extract_text() or "" for page in reader.pages]
        links = _pdf_link_targets(reader)
    except ResumeParseError:
        raise
    except Exception as exc:  # pypdf raises many types for malformed files
        raise ResumeParseError(f"Could not parse PDF: {type(exc).__name__}: {exc}") from exc
    text = "\n".join(pages)
    if links and text.strip():
        text += "\n" + "\n".join(links)
    return text


def _pdf_link_targets(reader: PdfReader) -> list[str]:
    """Hyperlink targets (e.g. a 'GitHub' label linking to the profile).

    Best effort: failing here must not fail the resume, but it is logged.
    """
    targets: list[str] = []
    try:
        for page in reader.pages:
            for annot in page.get("/Annots") or []:
                action = annot.get_object().get("/A")
                uri = action.get("/URI") if action else None
                if isinstance(uri, str) and uri not in targets:
                    targets.append(uri)
    except Exception as exc:
        logger.warning("Could not read PDF link annotations: %s: %s", type(exc).__name__, exc)
    return targets
