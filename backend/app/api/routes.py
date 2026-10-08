"""Thin HTTP layer: validate -> store uploads safely -> run the core pipeline -> return results."""

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile

from app.api.schemas import ErrorResponse, HealthResponse
from app.api.uploads import UploadError, stored_uploads
from app.config import Settings, load_settings
from app.models import ScreeningResults
from app.pipeline import (
    PipelineOptions,
    ResultsCorruptError,
    ResultsNotFoundError,
    build_processor,
    read_results,
    write_results_atomic,
)
from app.screening.batch import BatchProcessor

logger = logging.getLogger(__name__)
router = APIRouter()

ProcessorFactory = Callable[[PipelineOptions], BatchProcessor]


# --- dependencies (overridden in tests) -------------------------------------------------

def get_settings() -> Settings:
    return load_settings()


def get_processor_factory(settings: Annotated[Settings, Depends(get_settings)]) -> ProcessorFactory:
    """A new processor per request: run-level caches are never shared between requests."""
    return lambda options: build_processor(settings, options)


def get_results_path(settings: Annotated[Settings, Depends(get_settings)]) -> Path:
    return settings.results_path


# --- endpoints --------------------------------------------------------------------------

@router.get("/health", response_model=HealthResponse, summary="Liveness check")
async def health() -> HealthResponse:
    return HealthResponse()


@router.post(
    "/screen",
    response_model=ScreeningResults,
    summary="Screen and rank a batch of resumes",
    description=(
        "Send one or many resume files as repeated multipart fields named `files` (PDF is the "
        "intended format; `.txt`/`.md` are accepted for testing). Selecting a whole folder in a "
        "browser simply means sending all of its files in one request: they are screened as a "
        "single batch. Eligibility and scoring are deterministic; the optional LLM and GitHub "
        "steps only add evidence. A bad file is recorded under `failed_candidates` and never "
        "fails the batch. The result is returned and also written to `results.json`."
    ),
    responses={
        400: {"model": ErrorResponse, "description": "No usable files in the request"},
        409: {"model": ErrorResponse, "description": "Another screening run is in progress"},
        413: {"model": ErrorResponse, "description": "Too many files or upload too large"},
        500: {"model": ErrorResponse, "description": "The pipeline failed unexpectedly"},
    },
)
async def screen(
    request: Request,
    files: Annotated[
        list[UploadFile],
        File(description="Resume files (PDF). Repeat the field once per file."),
    ],
    use_llm: Annotated[bool, Query(description="Run LLM semantic analysis (if configured).")] = True,
    use_github: Annotated[bool, Query(description="Run GitHub enrichment.")] = True,
    factory: ProcessorFactory = Depends(get_processor_factory),
    results_path: Path = Depends(get_results_path),
    settings: Settings = Depends(get_settings),
) -> ScreeningResults:
    lock: asyncio.Lock = request.app.state.screen_lock
    if lock.locked():
        raise HTTPException(409, "A screening run is already in progress. Try again shortly.")

    async with lock:
        try:
            async with stored_uploads(
                files,
                max_files=settings.max_upload_files,
                max_total_bytes=settings.max_upload_total_mb * 1024 * 1024,
            ) as stored:
                processor = factory(PipelineOptions(use_llm=use_llm, use_github=use_github))
                items = [(s.display_name, s.path.read_bytes) for s in stored]
                results = await processor.process_async(items)
            # temp upload directory is gone here; persist only the (secret-free) results
            await asyncio.to_thread(write_results_atomic, results, results_path)
        except UploadError as exc:
            raise HTTPException(exc.status_code, exc.detail) from None
        except Exception:
            logger.exception("Screening run failed")  # details stay in the server log
            raise HTTPException(500, "The screening run failed. See server logs for details.") from None
    return results


@router.get(
    "/results",
    response_model=ScreeningResults,
    summary="Latest completed screening results",
    responses={
        404: {"model": ErrorResponse, "description": "No screening has completed yet"},
        500: {"model": ErrorResponse, "description": "Stored results could not be read"},
    },
)
async def results(results_path: Path = Depends(get_results_path)) -> ScreeningResults:
    try:
        return await asyncio.to_thread(read_results, results_path)
    except ResultsNotFoundError:
        raise HTTPException(404, "No results yet. POST resumes to /screen first.") from None
    except ResultsCorruptError:
        logger.exception("Stored results.json is unreadable")
        raise HTTPException(500, "Stored results could not be read.") from None
