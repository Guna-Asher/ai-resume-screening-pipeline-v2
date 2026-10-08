"""Thin async HTTP client for the public GitHub REST API (only the two endpoints we need).

Every failure becomes a ``GitHubError`` with a normalised status; messages never contain the
token or response bodies. Auth is optional and sent via the Authorization header only.
"""

import logging
from typing import Any

import httpx

from app.config import Settings
from app.github.errors import GitHubError
from app.github.schemas import EventInfo, RepoInfo, parse_events, parse_repos
from app.models import GitHubStatus

logger = logging.getLogger(__name__)

PER_PAGE = 100  # one page per endpoint keeps a user to two requests


class GitHubClient:
    def __init__(
        self,
        *,
        base_url: str = "https://api.github.com",
        token: str | None = None,
        timeout_seconds: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token or None
        self._timeout = timeout_seconds
        self._transport = transport  # injectable for tests

    @classmethod
    def from_settings(cls, settings: Settings) -> "GitHubClient":
        token = settings.github_token.get_secret_value().strip() if settings.github_token else None
        return cls(
            base_url=settings.github_api_base_url,
            token=token,
            timeout_seconds=settings.github_timeout_seconds,
        )

    @property
    def authenticated(self) -> bool:
        return self._token is not None

    def __repr__(self) -> str:  # never expose the token
        return f"GitHubClient(base_url={self._base_url!r}, authenticated={self.authenticated})"

    def open(self) -> httpx.AsyncClient:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "ai-resume-screening",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return httpx.AsyncClient(
            base_url=self._base_url,
            headers=headers,
            timeout=self._timeout,
            transport=self._transport,
            follow_redirects=True,
        )

    async def _get_list(self, http: httpx.AsyncClient, path: str, params: dict[str, Any]) -> list[Any]:
        try:
            response = await http.get(path, params=params)
        except httpx.TimeoutException as exc:
            raise GitHubError(GitHubStatus.TIMEOUT, type(exc).__name__) from exc
        except httpx.HTTPError as exc:
            raise GitHubError(GitHubStatus.API_ERROR, f"connection error ({type(exc).__name__})") from exc

        status = response.status_code
        if status == 404:
            raise GitHubError(GitHubStatus.NOT_FOUND, "HTTP 404")
        if status == 429 or (status == 403 and _looks_rate_limited(response)):
            raise GitHubError(GitHubStatus.RATE_LIMITED, f"HTTP {status}")
        if status == 401:
            raise GitHubError(GitHubStatus.API_ERROR, "HTTP 401 (token rejected)")
        if status >= 400:
            raise GitHubError(GitHubStatus.API_ERROR, f"HTTP {status}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise GitHubError(GitHubStatus.API_ERROR, "response was not JSON") from exc
        if not isinstance(payload, list):
            raise GitHubError(GitHubStatus.API_ERROR, "unexpected response shape")
        return payload

    async def fetch_repos(self, http: httpx.AsyncClient, username: str) -> list[RepoInfo]:
        payload = await self._get_list(
            http,
            f"/users/{username}/repos",
            {"type": "owner", "sort": "pushed", "direction": "desc", "per_page": PER_PAGE},
        )
        return parse_repos(payload)

    async def fetch_events(self, http: httpx.AsyncClient, username: str) -> list[EventInfo]:
        payload = await self._get_list(http, f"/users/{username}/events/public", {"per_page": PER_PAGE})
        return parse_events(payload)


def _looks_rate_limited(response: httpx.Response) -> bool:
    if response.headers.get("x-ratelimit-remaining") == "0" or "retry-after" in response.headers:
        return True
    try:
        message = str(response.json().get("message", ""))
    except (ValueError, AttributeError):
        return False
    return "rate limit" in message.lower()
