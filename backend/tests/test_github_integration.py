import json
from datetime import UTC, datetime

import httpx
from conftest import make_candidate
from github_fakes import NOW, STRONG_USER, FakeGitHub, event, events, repo
from samples import NO_PYTHON, RAG_PIPELINE, STRONG_AGENTIC, THIN_WRAPPER

from app.github import GitHubClient, GitHubEnricher
from app.models import GitHubEnrichment, GitHubStatus, ScoreBreakdown, ScreeningResults
from app.screening.batch import BatchProcessor
from app.screening.engine import screen_candidate

CLOCK = lambda: datetime(2026, 1, 1, tzinfo=UTC)  # noqa: E731


def with_gh(text: str, username: str | None, name: str | None = None) -> str:
    text = text.replace("ravi@example.com", f"ravi@example.com | github.com/{username}") if username else text
    return text.replace("Ravi Kumar", name) if name else text


def items(files):
    return [(n, (lambda d=d: d.encode())) for n, d in files.items()]


def batch(fake, files, **kw):
    client = GitHubClient(base_url="http://gh.test", transport=fake.transport, timeout_seconds=5)
    gh = GitHubEnricher(client, max_concurrency=3, clock=lambda: NOW)
    return BatchProcessor(github=gh, clock=CLOCK, **kw).process(items(files))


def by_name(results):
    return {r.resume_filename: r for r in [*results.eligible_candidates, *results.rejected_candidates]}


def baseline(text, name="x.txt"):
    return screen_candidate(make_candidate(text, name))


def test_github_points_are_added_to_the_deterministic_total():
    fake = FakeGitHub({"ravi": STRONG_USER})
    text = with_gh(RAG_PIPELINE, "ravi")
    result = by_name(batch(fake, {"r.txt": text}))["r.txt"]
    base = baseline(text).score_breakdown
    gh = result.github_enrichment
    assert gh.status == "ok" and 0 < gh.total_points <= 10
    s = result.score_breakdown
    assert s.github == gh.total_points and s.github_status == GitHubStatus.OK
    assert s.total_score == base.total_score + gh.total_points
    for field in ("ai_project_depth", "python_backend", "cloud_fullstack", "engineering_depth"):
        assert getattr(s, field) == getattr(base, field)
    ledger = [i for i in s.score_evidence if i.category == "github"]
    assert [(i.signal, i.points) for i in ledger] == [
        ("recent_activity", gh.recent_activity_points), ("repository_signals", gh.repository_points)]
    assert "GitHub: recent public engineering activity" in ledger[0].explanation
    assert result.github_url == "https://github.com/ravi"


def test_candidate_without_github_is_still_processed_with_an_explained_zero():
    fake = FakeGitHub()
    result = by_name(batch(fake, {"r.txt": RAG_PIPELINE}))["r.txt"]
    assert result.eligible and result.github_enrichment.status == "missing"
    assert result.score_breakdown.github == 0 and result.score_breakdown.github_status == "missing"
    item = [i for i in result.score_breakdown.score_evidence if i.category == "github"][0]
    assert item.points == 0 and "no GitHub link" in item.explanation
    assert fake.requests == []
    assert result.score_breakdown.total_score == baseline(RAG_PIPELINE).score_breakdown.total_score


def test_rejected_candidates_never_call_github():
    fake = FakeGitHub({"alex": STRONG_USER, "ravi": STRONG_USER})
    files = {"no_python.txt": NO_PYTHON.replace("alex@example.com", "alex@example.com | github.com/alex"),
             "ok.txt": with_gh(RAG_PIPELINE, "ravi")}
    results = batch(fake, files)
    assert fake.usernames_requested() == {"ravi"}
    rejected = results.rejected_candidates[0]
    assert not rejected.eligible and rejected.score_breakdown is None and rejected.rank is None
    assert rejected.github_enrichment.status == "not_evaluated" and rejected.github_enrichment.reason == "not_eligible"
    assert results.batch_summary.github_status_counts == {"not_evaluated": 1, "ok": 1}


def test_a_perfect_github_cannot_make_an_ineligible_candidate_eligible():
    fake = FakeGitHub({"alex": STRONG_USER})
    text = NO_PYTHON.replace("alex@example.com", "alex@example.com | github.com/alex")
    result = by_name(batch(fake, {"a.txt": text}))["a.txt"]
    assert not result.eligible and result.rejection_reasons and fake.requests == []


def test_github_failure_preserves_candidate_and_remaining_score_and_batch_continues():
    fake = FakeGitHub({"flaky": {"response": httpx.Response(500)}, "ravi": STRONG_USER})
    files = {
        "a_flaky.txt": with_gh(RAG_PIPELINE, "flaky", "Ann Flaky"),
        "b_fine.txt": with_gh(RAG_PIPELINE, "ravi", "Bob Fine"),
        "c_ghost.txt": with_gh(RAG_PIPELINE, "ghost", "Cy Ghost"),
        "d_bad_url.txt": RAG_PIPELINE.replace("ravi@example.com", "ravi@example.com | github.com/Cy/Repo github.com/Other/Lib").replace("Ravi Kumar", "Di Badurl"),
    }
    results = batch(fake, files)
    r = by_name(results)
    assert results.batch_summary.failed == 0 and results.batch_summary.eligible == 4
    assert r["a_flaky.txt"].github_enrichment.status == "api_error" and r["a_flaky.txt"].github_enrichment.reason == "HTTP 500"
    assert r["c_ghost.txt"].github_enrichment.status == "not_found"
    # repo links to two different owners: the candidate's account is ambiguous, so nothing is guessed
    assert r["d_bad_url.txt"].github_enrichment.status == "missing"
    base_total = baseline(RAG_PIPELINE).score_breakdown.total_score
    for name in ("a_flaky.txt", "c_ghost.txt", "d_bad_url.txt"):
        assert r[name].eligible and r[name].score_breakdown.github == 0
        assert r[name].score_breakdown.total_score == base_total
    assert any("GitHub not scored (api_error)" in c for c in r["a_flaky.txt"].concerns)
    failed_item = [i for i in r["a_flaky.txt"].score_breakdown.score_evidence if i.category == "github"][0]
    assert failed_item.explanation == "GitHub: 0 points - GitHub API error."
    assert r["b_fine.txt"].score_breakdown.total_score > base_total
    assert results.eligible_candidates[0].resume_filename == "b_fine.txt"
    assert results.batch_summary.github_status_counts["api_error"] == 1


def test_same_username_on_two_resumes_is_enriched_once():
    fake = FakeGitHub({"shared": STRONG_USER})
    files = {"a.txt": with_gh(RAG_PIPELINE, "shared", "Ann One"), "b.txt": with_gh(RAG_PIPELINE, "Shared", "Bob Two")}
    results = batch(fake, files)
    assert len(fake.requests) == 2
    a, b = results.eligible_candidates
    assert a.github_enrichment == b.github_enrichment and a.score_breakdown.github > 0


def test_final_score_never_exceeds_100_and_github_is_capped_at_ten():
    assert ScoreBreakdown.build(
        ai_project_depth=40, python_backend=30, cloud_fullstack=15, engineering_depth=5,
        github=10, penalties=[], score_evidence=[]).total_score == 100
    big = {"repos": [repo(f"rag-{i}", description="RAG service FastAPI embeddings", days=i + 1) for i in range(30)],
           "events": events(90, spread_days=10)}
    result = by_name(batch(FakeGitHub({"janedoe": big}), {"j.txt": STRONG_AGENTIC}))["j.txt"]
    assert result.github_enrichment.total_points == 10 and result.score_breakdown.github == 10
    assert result.score_breakdown.total_score <= 100
    try:
        GitHubEnrichment(total_points=11)
        raise AssertionError("expected validation error")
    except ValueError:
        pass


def test_github_changes_the_ranking_deterministically_and_stably():
    users = {"alpha": STRONG_USER, "beta": {"repos": [], "events": []}}
    files = {
        "a.txt": with_gh(RAG_PIPELINE, "beta", "Zed Last"),
        "b.txt": with_gh(RAG_PIPELINE, "alpha", "Amy First"),
        "c.txt": with_gh(RAG_PIPELINE, None, "Amy Aaa"),
    }
    first = batch(FakeGitHub(users), files)
    second = batch(FakeGitHub(users), dict(reversed(list(files.items()))))
    order = lambda res: [(r.rank, r.resume_filename) for r in res.eligible_candidates]  # noqa: E731
    assert order(first) == order(second) == [(1, "b.txt"), (2, "c.txt"), (3, "a.txt")]
    # equal scores (beta has no activity, c has no link) fall back to the name tie-break
    assert first.eligible_candidates[1].score_breakdown.total_score == first.eligible_candidates[2].score_breakdown.total_score


def test_results_json_is_valid_and_contains_no_secrets_or_raw_payloads():
    fake = FakeGitHub({"ravi": {**STRONG_USER, "events": [*STRONG_USER["events"], event(days=1, repo_name="secret/private-looking")]}})
    results = batch(fake, {"r.txt": with_gh(RAG_PIPELINE, "ravi")})
    blob = results.model_dump_json()
    json.loads(blob)
    assert ScreeningResults.model_validate_json(blob) == results
    gh = json.loads(blob)["eligible_candidates"][0]["github_enrichment"]
    assert set(gh) >= {"status", "total_points", "recent_activity_points", "repository_points",
                       "public_repositories", "maintained_repositories", "relevant_repositories", "summary", "evidence"}
    assert len(gh["relevant_repositories"]) <= 5
    assert "private-looking" not in blob and "actor" not in blob


def test_thin_wrapper_penalty_and_github_compose_with_floor_at_zero():
    result = by_name(batch(FakeGitHub({"john": STRONG_USER}), {"t.txt": THIN_WRAPPER.replace("john.smith@example.com", "j@x.com github.com/john")}))["t.txt"]
    s = result.score_breakdown
    assert s.penalties and s.github > 0
    assert s.total_score == max(0, s.ai_project_depth + s.python_backend + s.cloud_fullstack + s.github + s.engineering_depth - s.penalties[0].amount)
