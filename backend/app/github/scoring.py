"""Deterministic GitHub score (0-10). Pure functions; no I/O.

GitHub is an *approximate public signal*, not a measure of engineering ability: private work,
company repos and non-GitHub hosting are invisible, and the public Events API only exposes
recent activity (we read one page of up to 100 events). Followers and stars are deliberately
NOT used.

Recent activity (0-5) - engineering events in the last ``window_days`` (90)
    Counted event types: push, pull request / review / review comment, issues, issue comments,
    create (branch/tag/repo), release. Stars, watches, forks and membership events are ignored.
    N = counted events, D = distinct active days.
        5: N >= 25 and D >= 4        4: N >= 12 and D >= 3        3: N >= 6 and D >= 2
        2: N >= 3                    1: N >= 1                    0: none
    The highest tier whose conditions are all met applies.

Repositories (0-5) - the first 100 public repos owned by the user, sorted by last push
    A repo is *maintained* if it is not a fork, not archived, not empty, and was pushed to
    within ``maintained_days`` (365).
        maintained count:  0 -> 0,  1 -> 1,  >= 2 -> 2
        +1  a maintained repo has a meaningful description (>= 20 chars) or topics
        +1  a maintained repo is Python-relevant (language Python, or Python terms in name /
            description / topics)
        +1  a maintained repo is AI-relevant (LLM / RAG / agents / embeddings ... terms)

total = activity + repositories  (<= 10)
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.config.scoring import GITHUB_MAX
from app.github.schemas import EventInfo, RepoInfo
from app.models import GitHubEnrichment, GitHubStatus, RelevantRepository


def _term_regex(terms: tuple[str, ...]) -> re.Pattern[str]:
    parts = [re.escape(t).replace(r"\ ", r"[ -]") for t in terms]
    return re.compile(r"(?<![a-z0-9])(" + "|".join(parts) + r")(?![a-z0-9])")


# plural -> singular so "agent" / "agents" are reported as one tag
_CANONICAL_TAGS = {"agents": "agent", "embeddings": "embedding", "llms": "llm"}


@dataclass(frozen=True)
class GitHubRules:
    window_days: int = 90
    maintained_days: int = 365
    description_min_chars: int = 20
    max_relevant_shown: int = 5
    # (points, min events, min distinct days), highest first
    activity_tiers: tuple[tuple[int, int, int], ...] = (
        (5, 25, 4), (4, 12, 3), (3, 6, 2), (2, 3, 1), (1, 1, 1),
    )
    engineering_events: frozenset[str] = frozenset(
        {
            "PushEvent", "PullRequestEvent", "PullRequestReviewEvent",
            "PullRequestReviewCommentEvent", "IssuesEvent", "IssueCommentEvent",
            "CreateEvent", "ReleaseEvent",
        }
    )
    python_terms: tuple[str, ...] = (
        "python", "fastapi", "django", "flask", "asyncio", "pydantic", "pytest", "pandas",
    )
    ai_terms: tuple[str, ...] = (
        "ai", "llm", "llms", "rag", "langchain", "langgraph", "agent", "agents", "agentic",
        "multi-agent", "embedding", "embeddings", "vector search", "machine learning",
        "openai", "gpt", "chatbot", "generative", "semantic search", "retrieval",
        "deep learning", "transformers",
    )
    _python_rx: re.Pattern[str] = field(init=False, repr=False, compare=False)
    _ai_rx: re.Pattern[str] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_python_rx", _term_regex(self.python_terms))
        object.__setattr__(self, "_ai_rx", _term_regex(self.ai_terms))

    def relevance(self, repo: RepoInfo) -> list[str]:
        """Relevance tags from name, description, topics and primary language."""
        text = " ".join([repo.name, repo.description, *repo.topics]).lower().replace("_", " ")
        tags: list[str] = []
        if (repo.language or "").lower() == "python" or self._python_rx.search(text):
            tags.append("python")
        for match in self._ai_rx.findall(text):
            tag = _CANONICAL_TAGS.get(match, match).replace(" ", "-")
            if tag not in tags:
                tags.append(tag)
        return tags[:5]


DEFAULT_RULES = GitHubRules()


def is_ai_relevant(tags: list[str]) -> bool:
    return any(t != "python" for t in tags)


def score_activity(
    events: list[EventInfo], now: datetime, rules: GitHubRules = DEFAULT_RULES
) -> tuple[int, int, int]:
    """(points, counted events, distinct active days)."""
    cutoff = now - timedelta(days=rules.window_days)
    counted = [e for e in events if e.type in rules.engineering_events and e.created_at >= cutoff]
    days = {e.created_at.date() for e in counted}
    n, d = len(counted), len(days)
    for points, min_events, min_days in rules.activity_tiers:
        if n >= min_events and d >= min_days:
            return points, n, d
    return 0, n, d


def _is_maintained(repo: RepoInfo, now: datetime, rules: GitHubRules) -> bool:
    return (
        not repo.fork
        and not repo.archived
        and repo.size > 0
        and repo.pushed_at is not None
        and repo.pushed_at >= now - timedelta(days=rules.maintained_days)
    )


def score_repositories(
    repos: list[RepoInfo], now: datetime, rules: GitHubRules = DEFAULT_RULES
) -> tuple[int, list[RepoInfo], dict[str, list[str]], dict[str, bool]]:
    """(points, maintained repos newest first, relevance tags by repo name, achieved bonuses)."""
    maintained = sorted(
        (r for r in repos if _is_maintained(r, now, rules)),
        key=lambda r: (r.pushed_at, r.name),
        reverse=True,
    )
    tags = {r.name: rules.relevance(r) for r in maintained}
    bonuses = {
        "documented": any(
            len(r.description.strip()) >= rules.description_min_chars or r.topics for r in maintained
        ),
        "python": any("python" in t for t in tags.values()),
        "ai": any(is_ai_relevant(t) for t in tags.values()),
    }
    points = min(2, len(maintained)) + sum(bonuses.values())
    return points, maintained, tags, bonuses


def build_enrichment(
    username: str,
    repos: list[RepoInfo],
    events: list[EventInfo],
    now: datetime,
    rules: GitHubRules = DEFAULT_RULES,
) -> GitHubEnrichment:
    activity_pts, n_events, n_days = score_activity(events, now, rules)
    repo_pts, maintained, tags, bonuses = score_repositories(repos, now, rules)

    relevant = [r for r in maintained if tags[r.name]]
    shown = [
        RelevantRepository(
            name=r.name,
            language=r.language,
            relevance=tags[r.name],
            updated_at=r.pushed_at.isoformat() if r.pushed_at else None,
            html_url=r.html_url,
        )
        for r in relevant[: rules.max_relevant_shown]
    ]
    n_py = sum("python" in tags[r.name] for r in relevant)
    n_ai = sum(is_ai_relevant(tags[r.name]) for r in relevant)

    evidence = [
        f"{n_events} engineering-related public events in the last {rules.window_days} days "
        f"on {n_days} active day(s) -> {activity_pts}/5",
        f"{len(maintained)} maintained public repositories (non-fork, non-archived, pushed in the "
        f"last {rules.maintained_days} days) of {len(repos)} fetched",
        f"repository signals -> {repo_pts}/5: maintained {min(2, len(maintained))}/2, "
        f"description {int(bonuses['documented'])}/1, Python {int(bonuses['python'])}/1, "
        f"AI {int(bonuses['ai'])}/1",
    ]
    if relevant:
        evidence.append(
            f"{len(relevant)} relevant repositories ({n_py} Python, {n_ai} AI): "
            + ", ".join(r.name for r in relevant[:3])
        )

    if n_events:
        activity_phrase = f"{n_events} recent public engineering events"
    else:
        activity_phrase = "no recent public engineering activity"
    summary = (
        f"{activity_phrase.capitalize()}; {len(maintained)} maintained public repositories"
        + (f", {n_py} Python and {n_ai} AI-relevant" if relevant else "")
        + ". Approximate public signal only."
    )

    return GitHubEnrichment(
        status=GitHubStatus.OK,
        profile_url=f"https://github.com/{username}",
        username=username,
        recent_activity_points=activity_pts,
        repository_points=repo_pts,
        total_points=min(GITHUB_MAX, activity_pts + repo_pts),
        public_repositories=len(repos),
        maintained_repositories=len(maintained),
        recent_engineering_events=n_events,
        relevant_repositories=shown,
        summary=summary,
        evidence=evidence,
        reason=None,
    )
