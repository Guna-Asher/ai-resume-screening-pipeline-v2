"""Test doubles for the LLM layer. No network."""

import asyncio
import json
from collections.abc import Callable

from app.llm import LLMError


def analysis_json(*projects: dict, **extra) -> str:
    return json.dumps({"projects": list(projects), **extra})


def project(name: str, *signals: tuple[str, str], shallow: bool = False, depth: str = "unclear", **extra) -> dict:
    return {
        "project_name": name,
        "summary": f"{name} summary",
        "signals": [{"signal": s, "evidence": e} for s, e in signals],
        "depth_assessment": depth,
        "shallow_wrapper": shallow,
        "concerns": [],
        **extra,
    }


class FakeAdapter:
    """Replies with a fixed string, a callable(user_prompt) -> str, or raises."""

    provider = "fake"

    def __init__(
        self,
        reply: str | Callable[[str], str] | None = None,
        *,
        error: Exception | None = None,
        delay: float = 0.0,
        model: str = "fake-model",
    ) -> None:
        self.reply = reply
        self.error = error
        self.delay = delay
        self.model = model
        self.prompts: list[str] = []
        self.in_flight = 0
        self.max_in_flight = 0

    @property
    def calls(self) -> int:
        return len(self.prompts)

    async def complete(self, *, system: str, user: str) -> str:
        self.prompts.append(user)
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            if self.error:
                raise self.error
            return self.reply(user) if callable(self.reply) else (self.reply or "")
        finally:
            self.in_flight -= 1


def failing(category) -> FakeAdapter:
    return FakeAdapter(error=LLMError(category, "simulated"))
