"""results.json is the source of truth for the latest completed run (no database).

Writes are atomic: the JSON is written to a temp file in the same directory, flushed to disk,
then renamed over ``results.json``. A failure at any point leaves the previous file untouched.
"""

import contextlib
import os
import tempfile
from pathlib import Path

from pydantic import ValidationError

from app.models import ScreeningResults


class ResultsNotFoundError(Exception):
    """No completed run has written results yet."""


class ResultsCorruptError(Exception):
    """results.json exists but is not a valid ScreeningResults document."""


def write_results_atomic(results: ScreeningResults, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = results.model_dump_json(indent=2)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f"{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_name, 0o644)  # mkstemp creates 0600; keep the file readable on the host mount
        os.replace(tmp_name, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp_name)
        raise


def read_results(path: Path) -> ScreeningResults:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ResultsNotFoundError(str(path)) from exc
    try:
        return ScreeningResults.model_validate_json(raw)
    except ValidationError as exc:
        raise ResultsCorruptError(f"{path} is not a valid results document") from exc
