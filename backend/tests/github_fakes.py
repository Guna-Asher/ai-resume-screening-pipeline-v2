"""Fake GitHub REST API (httpx.MockTransport). No network, no real accounts."""

import asyncio
from datetime import UTC, datetime, timedelta

import httpx

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


def iso(days_ago: float) -> str:
    return (NOW - timedelta(days=days_ago)).isoformat().replace("+00:00", "Z")


def repo(name, *, language="Python", description="A useful project for testing things", days=10,
         fork=False, archived=False, size=100, topics=(), stars=0):
    return {
        "name": name, "html_url": f"https://github.com/u/{name}", "description": description,
        "language": language, "topics": list(topics), "fork": fork, "archived": archived,
        "size": size, "pushed_at": iso(days), "updated_at": iso(days), "stargazers_count": stars,
    }


def event(type_="PushEvent", days=1.0, repo_name="u/proj"):
    return {"type": type_, "created_at": iso(days), "repo": {"name": repo_name}, "actor": {"login": "private-ish"}}


def events(n, *, spread_days=1, type_="PushEvent"):
    """n events spread over ``spread_days`` distinct days."""
    return [event(type_, days=1 + (i % spread_days)) for i in range(n)]


STRONG_USER = {
    "repos": [
        repo("rag-service", description="RAG service with embeddings and FastAPI", days=5,
             topics=("llm", "rag")),
        repo("agent-toolkit", description="LangGraph agents for research workflows", days=20),
        repo("dotfiles", language="Shell", description="my dotfiles and shell setup scripts", days=40),
    ],
    "events": events(30, spread_days=6),
}


def rate_limited_response() -> httpx.Response:
    return httpx.Response(403, headers={"x-ratelimit-remaining": "0"}, json={"message": "API rate limit exceeded"})


class FakeGitHub:
    """users: {lower-case username: {"repos": [...], "events": [...], optional overrides}}."""

    def __init__(self, users: dict[str, dict] | None = None, *, delay: float = 0.0):
        self.users = users or {}
        self.delay = delay
        self.requests: list[httpx.Request] = []
        self.in_flight = 0
        self.max_in_flight = 0
        self.transport = httpx.MockTransport(self._handle)

    @property
    def paths(self) -> list[str]:
        return [r.url.path for r in self.requests]

    def usernames_requested(self) -> set[str]:
        return {p.split("/")[2] for p in self.paths}

    async def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            _, _, user, *rest = request.url.path.split("/")
            spec = self.users.get(user.lower())
            if spec is None:
                return httpx.Response(404, json={"message": "Not Found"})
            kind = "events" if rest and rest[0] == "events" else "repos"
            if "raise" in spec:
                raise spec["raise"]
            if "response" in spec:
                return spec["response"]
            return httpx.Response(200, json=spec.get(kind, []))
        finally:
            self.in_flight -= 1
