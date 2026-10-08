"""Minimal typed views of the GitHub payloads. Only the fields scoring needs are kept."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class RepoInfo:
    name: str
    html_url: str | None
    description: str
    language: str | None
    topics: tuple[str, ...]
    fork: bool
    archived: bool
    size: int
    pushed_at: datetime | None


@dataclass(frozen=True)
class EventInfo:
    type: str
    created_at: datetime
    repo: str | None


def parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def parse_repos(payload: list[Any]) -> list[RepoInfo]:
    repos: list[RepoInfo] = []
    for item in payload:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            continue
        topics = item.get("topics")
        repos.append(
            RepoInfo(
                name=item["name"],
                html_url=item.get("html_url") if isinstance(item.get("html_url"), str) else None,
                description=item.get("description") or "",
                language=item.get("language") if isinstance(item.get("language"), str) else None,
                topics=tuple(t for t in topics if isinstance(t, str)) if isinstance(topics, list) else (),
                fork=bool(item.get("fork")),
                archived=bool(item.get("archived")),
                size=item.get("size") if isinstance(item.get("size"), int) else 0,
                pushed_at=parse_datetime(item.get("pushed_at")) or parse_datetime(item.get("updated_at")),
            )
        )
    return repos


def parse_events(payload: list[Any]) -> list[EventInfo]:
    events: list[EventInfo] = []
    for item in payload:
        if not isinstance(item, dict) or not isinstance(item.get("type"), str):
            continue
        created = parse_datetime(item.get("created_at"))
        if created is None:
            continue
        repo = item.get("repo")
        events.append(
            EventInfo(
                type=item["type"],
                created_at=created,
                repo=repo.get("name") if isinstance(repo, dict) and isinstance(repo.get("name"), str) else None,
            )
        )
    return events
