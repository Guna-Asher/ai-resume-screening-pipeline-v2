import httpx
import pytest
from github_fakes import NOW, STRONG_USER, FakeGitHub, rate_limited_response

from app.github import GitHubClient, GitHubEnricher

TOKEN = "ghp_TEST_TOKEN_SHOULD_NEVER_LEAK"


def enricher(fake, *, token=None, concurrency=3):
    client = GitHubClient(base_url="http://gh.test", token=token, timeout_seconds=5, transport=fake.transport)
    return GitHubEnricher(client, max_concurrency=concurrency, clock=lambda: NOW)


def run(e, *urls):
    return e.enrich_many([(f"k{i}", u) for i, u in enumerate(urls)])


def test_valid_profile_scores_and_makes_exactly_two_requests():
    fake = FakeGitHub({"alice": STRONG_USER})
    result = run(enricher(fake), "https://github.com/alice")["k0"]
    assert result.status == "ok" and 0 < result.total_points <= 10
    assert result.total_points == result.recent_activity_points + result.repository_points
    assert fake.paths == ["/users/alice/repos", "/users/alice/events/public"]
    assert {r.name for r in result.relevant_repositories} == {"rag-service", "agent-toolkit"}


def test_requests_are_public_and_unauthenticated_without_a_token():
    fake = FakeGitHub({"alice": STRONG_USER})
    run(enricher(fake), "github.com/alice")
    assert all("authorization" not in r.headers for r in fake.requests)
    assert fake.requests[0].headers["accept"] == "application/vnd.github+json"
    assert fake.requests[0].url.params["per_page"] == "100" and fake.requests[0].url.params["type"] == "owner"


def test_token_is_sent_as_bearer_and_never_leaks():
    fake = FakeGitHub({"alice": STRONG_USER, "flaky": {"response": httpx.Response(500, text=TOKEN)}})
    e = enricher(fake, token=TOKEN)
    results = run(e, "github.com/alice", "github.com/flaky")
    assert all(r.headers["authorization"] == f"Bearer {TOKEN}" for r in fake.requests)
    assert TOKEN not in repr(e._client) and e.authenticated
    assert TOKEN not in "".join(r.model_dump_json() for r in results.values())


def test_missing_and_malformed_urls_make_no_requests():
    fake = FakeGitHub({"alice": STRONG_USER})
    out = run(enricher(fake), None, "", "not a url", "https://github.com/alice/some-repo", "https://example.com/alice")
    assert [out[f"k{i}"].status for i in range(5)] == ["missing", "missing", "invalid_url", "invalid_url", "invalid_url"]
    assert all(r.total_points == 0 for r in out.values())
    assert fake.requests == []
    assert "profile missing" not in out["k0"].summary and "no GitHub link" in out["k0"].summary


def test_profile_not_found_stops_after_one_request():
    fake = FakeGitHub()
    result = run(enricher(fake), "github.com/ghost")["k0"]
    assert (result.status, result.total_points) == ("not_found", 0)
    assert fake.paths == ["/users/ghost/repos"]


@pytest.mark.parametrize(
    "response",
    [
        rate_limited_response(),
        httpx.Response(429, json={"message": "slow down"}),
        httpx.Response(403, json={"message": "You have exceeded a secondary rate limit"}),
        httpx.Response(403, headers={"retry-after": "30"}, json={}),
    ],
)
def test_rate_limit_responses(response):
    fake = FakeGitHub({"alice": {"response": response}})
    result = run(enricher(fake), "github.com/alice")["k0"]
    assert (result.status, result.total_points) == ("rate_limited", 0)


def test_after_a_rate_limit_no_further_requests_are_made():
    fake = FakeGitHub({"a": {"response": rate_limited_response()}, "b": STRONG_USER, "c": STRONG_USER})
    e = enricher(fake, concurrency=1)
    out = run(e, "github.com/a", "github.com/b", "github.com/c")
    assert [out[k].status for k in ("k0", "k1", "k2")] == ["rate_limited"] * 3
    assert fake.usernames_requested() == {"a"} and len(fake.requests) == 1
    assert run(e, "github.com/b")["k0"].status == "rate_limited"  # still stopped for the run


def test_forbidden_without_rate_limit_hints_is_a_plain_api_error():
    fake = FakeGitHub({"alice": {"response": httpx.Response(403, json={"message": "Forbidden"})}})
    assert run(enricher(fake), "github.com/alice")["k0"].status == "api_error"


def test_timeout():
    fake = FakeGitHub({"alice": {"raise": httpx.ReadTimeout("slow")}})
    result = run(enricher(fake), "github.com/alice")["k0"]
    assert (result.status, result.total_points) == ("timeout", 0)


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, text="boom"), httpx.Response(502), httpx.Response(401, json={}),
        httpx.Response(200, text="<html>not json</html>"), httpx.Response(200, json={"not": "a list"}),
    ],
)
def test_generic_api_errors(response):
    fake = FakeGitHub({"alice": {"response": response}})
    result = run(enricher(fake), "github.com/alice")["k0"]
    assert (result.status, result.total_points) == ("api_error", 0)
    assert "boom" not in result.model_dump_json()


def test_connection_error_is_an_api_error():
    fake = FakeGitHub({"alice": {"raise": httpx.ConnectError("refused")}})
    assert run(enricher(fake), "github.com/alice")["k0"].status == "api_error"


def test_same_username_is_fetched_once_per_run_case_insensitively():
    fake = FakeGitHub({"alice": STRONG_USER})
    e = enricher(fake)
    out = run(e, "https://github.com/alice", "github.com/Alice/", "https://www.github.com/ALICE")
    assert len(fake.requests) == 2  # one repos + one events call, not six
    assert out["k0"] == out["k1"] == out["k2"]
    run(e, "github.com/alice")  # second call in the same run: served from the cache
    assert len(fake.requests) == 2


def test_failures_are_cached_too():
    fake = FakeGitHub()
    e = enricher(fake)
    run(e, "github.com/ghost"); run(e, "github.com/ghost")
    assert len(fake.requests) == 1


@pytest.mark.parametrize("limit", [1, 2, 3])
def test_concurrency_is_bounded(limit):
    fake = FakeGitHub({f"user{i}": STRONG_USER for i in range(9)}, delay=0.03)
    out = run(enricher(fake, concurrency=limit), *[f"github.com/user{i}" for i in range(9)])
    assert all(r.status == "ok" for r in out.values())
    assert fake.max_in_flight == limit


def test_one_failing_user_does_not_affect_the_others():
    fake = FakeGitHub({"good": STRONG_USER, "bad": {"response": httpx.Response(500)}})
    out = run(enricher(fake), "github.com/good", "github.com/bad", "github.com/nobody")
    assert [out[k].status for k in ("k0", "k1", "k2")] == ["ok", "api_error", "not_found"]
