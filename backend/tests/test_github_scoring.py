import pytest
from github_fakes import NOW, event, events, repo

from app.github import GitHubRules, build_enrichment
from app.github.schemas import parse_events, parse_repos
from app.github.scoring import score_activity, score_repositories


def act(raw_events):
    return score_activity(parse_events(raw_events), NOW)


def repos(*raw):
    return parse_repos(list(raw))


@pytest.mark.parametrize(
    ("n", "days", "points"),
    [(0, 1, 0), (1, 1, 1), (2, 1, 1), (3, 1, 2), (5, 3, 2), (6, 1, 2), (6, 2, 3), (11, 2, 3),
     (12, 2, 3), (12, 3, 4), (24, 3, 4), (25, 3, 4), (25, 4, 5), (100, 10, 5)],
)
def test_recent_activity_tiers(n, days, points):
    assert act(events(n, spread_days=days))[0] == points


def test_only_engineering_events_in_the_window_count():
    raw = [event("WatchEvent"), event("ForkEvent"), event("PushEvent", days=120), event("PushEvent", days=89)]
    points, counted, active_days = act(raw)
    assert (points, counted, active_days) == (1, 1, 1)
    assert act([event("WatchEvent", days=d) for d in range(1, 40)])[0] == 0  # starring is not engineering


def test_repository_points_breakdown():
    pts, maintained, tags, bonuses = score_repositories(
        repos(
            repo("rag-service", description="RAG service with embeddings", days=5),
            repo("notes", language="Shell", description="short", days=30),
        ),
        NOW,
    )
    assert len(maintained) == 2 and bonuses == {"documented": True, "python": True, "ai": True}
    assert pts == 2 + 3 == 5


def test_repository_filters_forks_archived_empty_and_stale():
    pts, maintained, *_ = score_repositories(
        repos(
            repo("forked", fork=True), repo("old-archive", archived=True),
            repo("empty", size=0), repo("stale", days=400), repo("real", days=100),
        ),
        NOW,
    )
    assert [r.name for r in maintained] == ["real"]
    assert pts == 1 + 1 + 1  # one maintained + description + python (language); no AI


def test_no_maintained_repos_scores_zero():
    assert score_repositories(repos(repo("stale", days=800), repo("fork", fork=True)), NOW)[0] == 0
    assert score_repositories([], NOW)[0] == 0


def test_python_and_ai_relevance_detection():
    rules = GitHubRules()
    r = lambda **kw: parse_repos([repo(**kw)])[0]  # noqa: E731
    assert rules.relevance(r(name="svc", language="Python", description="x")) == ["python"]
    assert "python" in rules.relevance(r(name="api", language="Shell", description="FastAPI backend"))
    ai = rules.relevance(r(name="rag-service", language="TypeScript", description="LangChain agents with embeddings"))
    assert "python" not in ai and {"rag", "langchain", "agent", "embedding"} <= set(ai) and "agents" not in ai
    assert rules.relevance(r(name="ai-resume-tool", language="Go", description="")) == ["ai"]
    assert rules.relevance(r(name="garage-mail", language="Go", description="Email painting daily")) == []
    assert "llm" in rules.relevance(r(name="x", language="Go", description="", topics=("LLM",)))


def test_keyword_sets_are_configurable():
    rules = GitHubRules(ai_terms=("quantum",), python_terms=("cobol",))
    r = parse_repos([repo("quantum-lab", language="Go", description="quantum stuff for cobol users")])[0]
    assert rules.relevance(r) == ["python", "quantum"]


def test_stars_and_followers_do_not_matter():
    base = score_repositories(repos(repo("a", stars=0)), NOW)[0]
    assert score_repositories(repos(repo("a", stars=50_000)), NOW)[0] == base


def test_full_marks_cap_at_ten_and_relevant_list_is_capped():
    many = [repo(f"rag-{i}", description="RAG service with FastAPI embeddings", days=i + 1) for i in range(12)]
    gh = build_enrichment("alice", parse_repos(many), parse_events(events(40, spread_days=8)), NOW)
    assert (gh.recent_activity_points, gh.repository_points, gh.total_points) == (5, 5, 10)
    assert gh.public_repositories == 12 and gh.maintained_repositories == 12
    assert len(gh.relevant_repositories) == 5
    assert gh.relevant_repositories[0].name == "rag-0" and "rag" in gh.relevant_repositories[0].relevance


def test_enrichment_is_explainable_and_has_no_raw_payload():
    gh = build_enrichment("alice", parse_repos([repo("rag-service", description="RAG with FastAPI", days=3)]),
                          parse_events(events(7, spread_days=2)), NOW)
    assert gh.status == "ok" and gh.profile_url == "https://github.com/alice"
    assert any("7 engineering-related public events" in e for e in gh.evidence)
    assert "Approximate public signal only" in gh.summary
    dumped = gh.model_dump_json()
    assert "private-ish" not in dumped and "actor" not in dumped
