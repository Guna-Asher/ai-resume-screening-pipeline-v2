"""Safe handling of uploaded resumes (filenames are untrusted input).

Uploaded files are streamed into an isolated temporary directory under *generated* names
(``0000.pdf``, ``0001.pdf``...). The client's filename is never used as a filesystem path;
it is only sanitised for reporting. The directory is removed when the request finishes.
"""

import hashlib
import re
import tempfile
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from fastapi import UploadFile

from app.ingestion.loader import MAX_FILE_BYTES

_CHUNK = 1024 * 1024
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_DRIVE = re.compile(r"^[A-Za-z]:$")
_SAFE_SUFFIX = re.compile(r"^\.[a-z0-9]{1,8}$")
MAX_DISPLAY_NAME = 255


class UploadError(Exception):
    """The request itself is unacceptable (maps to an HTTP error, never a per-file failure)."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True)
class StoredUpload:
    original_filename: str  # exactly what the client sent (for logs / diagnostics only)
    display_name: str  # sanitised name used in results (unique within the request)
    safe_name: str  # generated on-disk name
    path: Path
    size: int
    content_hash: str  # sha256 of the stored bytes (same value the pipeline reports as resume_hash)


def sanitize_display_name(raw: str | None, index: int) -> str:
    """Client filename -> safe relative display name.

    Backslashes become '/', control characters, empty / '.' / '..' segments and drive letters
    are dropped, so ``../../etc/passwd.pdf`` -> ``etc/passwd.pdf`` and
    ``C:\\Users\\me\\cv.pdf`` -> ``Users/me/cv.pdf``. A folder-relative path from a folder upload
    keeps its folders (so two ``cv.pdf`` in different folders stay distinguishable).
    """
    name = _CONTROL.sub("", (raw or "").replace("\\", "/"))
    parts = [p.strip() for p in name.split("/")]
    parts = [p for p in parts if p not in ("", ".", "..") and not _DRIVE.match(p)]
    display = "/".join(parts)[-MAX_DISPLAY_NAME:].strip("/")
    return display or f"upload_{index}"


def _safe_suffix(display_name: str) -> str:
    suffix = PurePosixPath(display_name).suffix.lower()
    return suffix if _SAFE_SUFFIX.match(suffix) else ""


def _unique(display: str, taken: set[str]) -> str:
    if display.casefold() not in taken:
        return display
    path = PurePosixPath(display)
    for n in range(2, 10_000):
        candidate = str(path.with_name(f"{path.stem} ({n}){path.suffix}"))
        if candidate.casefold() not in taken:
            return candidate
    raise UploadError(400, "Too many files share the same name")


def _is_hidden(display: str) -> bool:
    return any(part.startswith(".") for part in display.split("/"))


@asynccontextmanager
async def stored_uploads(
    uploads: Sequence[UploadFile],
    *,
    max_files: int,
    max_total_bytes: int,
    max_file_bytes: int = MAX_FILE_BYTES,
) -> AsyncIterator[list[StoredUpload]]:
    """Write uploads to an isolated temp dir; yield them sorted by display name; clean up after.

    Hidden files (``.DS_Store`` and friends, common in folder uploads) are skipped, matching the
    CLI's folder discovery. Oversized files are truncated to ``max_file_bytes + 1`` bytes so the
    pipeline records them as a per-file failure without buffering them.
    """
    named = [u for u in uploads if (u.filename or "").strip()]  # browsers send blank parts
    if not named:
        raise UploadError(400, "No files uploaded. Send one or more resumes as multipart field 'files'.")
    if len(named) > max_files:
        raise UploadError(413, f"Too many files: {len(named)} uploaded, the limit is {max_files}.")

    with tempfile.TemporaryDirectory(prefix="resume-screening-") as tmp:
        root = Path(tmp)
        stored: list[StoredUpload] = []
        taken: set[str] = set()
        total = 0
        for index, upload in enumerate(named):
            display = sanitize_display_name(upload.filename, index)
            if _is_hidden(display):
                continue
            display = _unique(display, taken)
            taken.add(display.casefold())

            safe_name = f"{index:04d}{_safe_suffix(display)}"
            path = root / safe_name
            assert path.resolve().parent == root.resolve()  # generated name cannot escape

            digest = hashlib.sha256()
            size = 0
            with path.open("wb") as handle:
                while size <= max_file_bytes:
                    chunk = await upload.read(min(_CHUNK, max_file_bytes + 1 - size))
                    if not chunk:
                        break
                    handle.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
            total += size
            if total > max_total_bytes:
                raise UploadError(413, f"Upload too large: the limit is {max_total_bytes // (1024 * 1024)} MB in total.")
            stored.append(
                StoredUpload(upload.filename or "", display, safe_name, path, size, digest.hexdigest())
            )

        if not stored:
            raise UploadError(400, "No resume files found: only hidden files were uploaded.")
        stored.sort(key=lambda s: (s.display_name.casefold(), s.safe_name))
        yield stored
