"""GitHub enrichment service: dedupe + cache + bounded concurrency + failure isolation.

Mirrors the LLM analyzer: the cache lives on the instance (one run), calls are bounded by an
``asyncio.Semaphore``, and nothing here ever raises for a GitHub problem.
"""

import asyncio
import logging
from collections.abc import Callable, Sequence
from datetime import UTC, datetime

import httpx

from app.config import Settings
from app.github.client import GitHubClient
from app.github.errors import GitHubError
from app.github.scoring import DEFAULT_RULES, GitHubRules, build_enrichment
from app.github.urls import parse_github_url
from app.models import GitHubEnrichment, GitHubStatus

logger = logging.getLogger(__name__)

_EXPLANATIONS = {
    GitHubStatus.MISSING: "no GitHub link on the resume",
    GitHubStatus.INVALID_URL: "the GitHub link is not a usable profile URL",
    GitHubStatus.NOT_FOUND: "GitHub profile not found",
    GitHubStatus.RATE_LIMITED: "GitHub API rate limited",
    GitHubStatus.TIMEOUT: "GitHub API timed out",
    GitHubStatus.API_ERROR: "GitHub API error",
}


def failure(
    status: GitHubStatus,
    reason: str | None = None,
    *,
    username: str | None = None,
    profile_url: str | None = None,
) -> GitHubEnrichment:
    """A zero-point result that explains why. The candidate is never penalised further."""
    return GitHubEnrichment(
        status=status,
        reason=reason,
        username=username,
        profile_url=profile_url or (f"https://github.com/{username}" if username else None),
        summary=f"GitHub: 0 points - {_EXPLANATIONS.get(status, status.value)}.",
    )


class GitHubEnricher:
    def __init__(
        self,
        client: GitHubClient,
        *,
        max_concurrency: int = 3,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        rules: GitHubRules = DEFAULT_RULES,
    ) -> None:
        self._client = client
        self._max_concurrency = max(1, max_concurrency)
        self._clock = clock
        self._rules = rules
        self._cache: dict[str, GitHubEnrichment] = {}  # lower-case username -> result
        self._rate_limited = False  # once hit, stop calling GitHub for the rest of the run

    @classmethod
    def from_settings(cls, settings: Settings) -> "GitHubEnricher":
        return cls(GitHubClient.from_settings(settings), max_concurrency=settings.github_max_concurrency)

    @property
    def authenticated(self) -> bool:
        return self._client.authenticated

    async def enrich_many_async(
        self, items: Sequence[tuple[str, str | None]]
    ) -> dict[str, GitHubEnrichment]:
        """``items`` are (key, github_url). Returns one result per key, whatever happens."""
        results: dict[str, GitHubEnrichment] = {}
        wanted: dict[str, list[str]] = {}  # username key -> candidate keys
        display: dict[str, str] = {}
        for key, url in items:
            parsed = parse_github_url(url)
            if parsed.cache_key is None:
                results[key] = failure(parsed.status, parsed.reason, profile_url=url if url else None)
                continue
            wanted.setdefault(parsed.cache_key, []).append(key)
            display.setdefault(parsed.cache_key, parsed.username or parsed.cache_key)

        to_fetch = [u for u in wanted if u not in self._cache]  # each username at most once
        if to_fetch:
            semaphore = asyncio.Semaphore(self._max_concurrency)
            async with self._client.open() as http:
                await asyncio.gather(*(self._fetch_user(http, semaphore, u, display[u]) for u in to_fetch))
        for user, keys in wanted.items():
            for key in keys:
                results[key] = self._cache[user]
        return results

    def enrich_many(self, items: Sequence[tuple[str, str | None]]) -> dict[str, GitHubEnrichment]:
        """Sync entry point (must not be called from a running event loop)."""
        return asyncio.run(self.enrich_many_async(items))

    async def _fetch_user(
        self, http: httpx.AsyncClient, semaphore: asyncio.Semaphore, key: str, username: str
    ) -> None:
        async with semaphore:
            if self._rate_limited:  # a previous call was rate limited: do not hammer the API
                self._cache[key] = failure(GitHubStatus.RATE_LIMITED, "skipped after earlier rate limit", username=username)
                return
            try:
                repos = await self._client.fetch_repos(http, username)  # 404 here => not found
                events = await self._client.fetch_events(http, username)
                self._cache[key] = build_enrichment(username, repos, events, self._clock(), self._rules)
            except GitHubError as exc:
                if exc.status == GitHubStatus.RATE_LIMITED:
                    self._rate_limited = True
                logger.warning("GitHub enrichment for %s failed: %s", username, exc.status.value)
                self._cache[key] = failure(exc.status, exc.detail or None, username=username)
            except Exception as exc:  # last resort: never break the batch
                logger.exception("Unexpected GitHub enrichment failure for %s", username)
                self._cache[key] = failure(
                    GitHubStatus.API_ERROR, f"unexpected: {type(exc).__name__}", username=username
                )
