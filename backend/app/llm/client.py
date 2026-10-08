"""Semantic analysis service: prompt -> adapter -> parse -> validate, with failure isolation.

It returns a ``SemanticOutcome`` for every candidate and never raises for a
model/provider problem, so one bad call can never stop a batch.
"""

import asyncio
import json
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from pydantic import ValidationError

from app.config import Settings
from app.llm.adapter import LLMAdapter, build_adapter
from app.llm.errors import CONFIG_FAILURES, LLMError, LLMFailure
from app.llm.prompts import PROMPT_VERSION, SYSTEM_PROMPT, build_user_prompt
from app.llm.schemas import SemanticAnalysis
from app.models import Candidate

logger = logging.getLogger(__name__)

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


@dataclass(frozen=True)
class SemanticOutcome:
    status: Literal["ok", "failed", "unavailable"]
    analysis: SemanticAnalysis | None = None
    reason: str | None = None  # LLMFailure value when not ok
    model: str | None = None


def parse_analysis(raw: str) -> SemanticAnalysis:
    """Raw model text -> validated ``SemanticAnalysis`` or ``LLMError`` (no raw text in errors)."""
    text = _FENCE.sub("", raw.strip())
    try:
        data = json.loads(text)
    except ValueError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise LLMError(LLMFailure.INVALID_JSON, "no JSON object in reply") from None
        try:
            data = json.loads(text[start : end + 1])
        except ValueError:
            raise LLMError(LLMFailure.INVALID_JSON, "reply is not valid JSON") from None
    try:
        return SemanticAnalysis.model_validate(data)
    except ValidationError as exc:
        first = exc.errors()[0]
        where = ".".join(str(p) for p in first["loc"])
        raise LLMError(
            LLMFailure.SCHEMA_VALIDATION, f"{exc.error_count()} error(s), first at '{where}'"
        ) from None


class SemanticAnalyzer:
    """Wraps one adapter (or a recorded configuration problem) plus a per-run cache.

    The cache lives on the instance (no global state) and is keyed by resume hash,
    prompt version and model, so a candidate is sent to the model at most once per run.
    """

    def __init__(
        self,
        adapter: LLMAdapter | None,
        *,
        unavailable: LLMError | None = None,
        max_concurrency: int = 3,
        timeout_seconds: float = 30.0,
    ) -> None:
        if adapter is None and unavailable is None:
            unavailable = LLMError(LLMFailure.NOT_CONFIGURED, "no adapter supplied")
        self._adapter = adapter
        self._unavailable = unavailable
        self._max_concurrency = max(1, max_concurrency)
        self._timeout = timeout_seconds
        self._cache: dict[tuple[str, str, str], SemanticOutcome] = {}

    @classmethod
    def from_settings(cls, settings: Settings) -> "SemanticAnalyzer":
        try:
            adapter = build_adapter(settings)
        except LLMError as exc:
            return cls(None, unavailable=exc, max_concurrency=settings.llm_max_concurrency)
        return cls(
            adapter,
            max_concurrency=settings.llm_max_concurrency,
            timeout_seconds=settings.llm_timeout_seconds,
        )

    @property
    def unavailable_reason(self) -> LLMError | None:
        return self._unavailable

    async def analyze_async(self, candidate: Candidate) -> SemanticOutcome:
        if self._adapter is None:
            assert self._unavailable is not None
            return SemanticOutcome("unavailable", reason=self._unavailable.category.value)

        key = (candidate.resume_hash, PROMPT_VERSION, self._adapter.model)
        if key in self._cache:
            return self._cache[key]

        outcome = await self._call(candidate)
        self._cache[key] = outcome
        return outcome

    async def _call(self, candidate: Candidate) -> SemanticOutcome:
        assert self._adapter is not None
        model = self._adapter.model
        try:
            raw = await asyncio.wait_for(
                self._adapter.complete(system=SYSTEM_PROMPT, user=build_user_prompt(candidate)),
                timeout=self._timeout,
            )
            return SemanticOutcome("ok", analysis=parse_analysis(raw), model=model)
        except TimeoutError:
            error = LLMError(LLMFailure.TIMEOUT, f"no reply within {self._timeout:g}s")
        except LLMError as exc:
            error = exc
        except Exception as exc:  # a misbehaving adapter must not stop the batch
            logger.exception("Unexpected LLM failure for %s", candidate.resume_filename)
            error = LLMError(LLMFailure.UNEXPECTED, type(exc).__name__)
        logger.warning(
            "LLM analysis failed for %s: %s", candidate.resume_filename, error.category.value
        )
        status = "unavailable" if error.category in CONFIG_FAILURES else "failed"
        return SemanticOutcome(status, reason=error.category.value, model=model)

    async def analyze_many_async(
        self, candidates: Sequence[Candidate]
    ) -> dict[str, SemanticOutcome]:
        """Analyse candidates with at most ``max_concurrency`` calls in flight."""
        semaphore = asyncio.Semaphore(self._max_concurrency)

        async def one(candidate: Candidate) -> tuple[str, SemanticOutcome]:
            async with semaphore:
                return candidate.resume_hash, await self.analyze_async(candidate)

        pairs = await asyncio.gather(*(one(c) for c in candidates))
        return dict(pairs)

    def analyze_many(self, candidates: Sequence[Candidate]) -> dict[str, SemanticOutcome]:
        """Sync entry point for the batch (must not be called from a running event loop)."""
        return asyncio.run(self.analyze_many_async(candidates))
