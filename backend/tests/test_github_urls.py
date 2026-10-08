import pytest

from app.github import parse_github_url
from app.models import GitHubStatus


@pytest.mark.parametrize(
    "raw",
    [
        "https://github.com/alice",
        "https://www.github.com/alice/",
        "github.com/alice",
        "http://github.com/alice?tab=repositories",
        "  GitHub.com/alice#readme ",
    ],
)
def test_profile_forms_normalise_to_the_username(raw):
    parsed = parse_github_url(raw)
    assert parsed.status == GitHubStatus.OK and parsed.username == "alice"
    assert parsed.cache_key == "alice"


def test_case_is_preserved_for_display_but_lowered_for_cache_key():
    parsed = parse_github_url("github.com/Alice-Dev")
    assert parsed.username == "Alice-Dev" and parsed.cache_key == "alice-dev"


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_missing(raw):
    assert parse_github_url(raw).status == GitHubStatus.MISSING


@pytest.mark.parametrize(
    "raw",
    [
        "https://github.com/",
        "https://github.com/alice/rag-service",  # repo URL: owner not confirmed
        "https://gitlab.com/alice",
        "https://github.com.evil.com/alice",
        "github.com/features",
        "github.com/-bad-",
        "github.com/a--b",
        "github.com/" + "a" * 40,
        "https://github.com:bad/alice",
        "John Smith",  # a person's name is never turned into a username
    ],
)
def test_invalid_urls(raw):
    parsed = parse_github_url(raw)
    assert parsed.status == GitHubStatus.INVALID_URL and parsed.username is None and parsed.reason
