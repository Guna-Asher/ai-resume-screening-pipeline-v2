"""Resume GitHub link -> account username. Never guesses a username from a person's name."""

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.models import GitHubStatus

_HOSTS = {"github.com", "www.github.com"}
_USERNAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$")
# github.com/<these> are site pages, not accounts
_RESERVED = {
    "features", "about", "pricing", "orgs", "topics", "marketplace", "sponsors", "settings",
    "login", "join", "explore", "collections", "events", "notifications", "pulls", "issues",
    "organizations", "enterprise", "security", "search", "apps", "trending",
}


@dataclass(frozen=True)
class ParsedGitHubUrl:
    status: GitHubStatus  # MISSING, INVALID_URL, or OK
    username: str | None = None
    reason: str | None = None

    @property
    def cache_key(self) -> str | None:
        return self.username.lower() if self.username else None


def parse_github_url(raw: str | None) -> ParsedGitHubUrl:
    """Accepts ``https://github.com/u``, ``https://www.github.com/u/``, ``github.com/u``.

    Only profile URLs are accepted. A repository URL (``github.com/u/repo``) is rejected here
    because the repo may belong to someone else; resume extraction decides when the owner of a
    repo link can be trusted and hands this function a profile URL.
    """
    text = (raw or "").strip()
    if not text:
        return ParsedGitHubUrl(GitHubStatus.MISSING, reason="no GitHub link on the resume")
    if "://" not in text:
        text = "https://" + text
    try:
        parts = urlsplit(text)
        host = (parts.hostname or "").lower()
        _ = parts.port  # raises ValueError for a malformed port such as 'github.com:bad'
    except ValueError:
        return ParsedGitHubUrl(GitHubStatus.INVALID_URL, reason="malformed URL")
    if host not in _HOSTS:
        return ParsedGitHubUrl(GitHubStatus.INVALID_URL, reason="not a github.com URL")
    segments = [s for s in parts.path.split("/") if s]
    if not segments:
        return ParsedGitHubUrl(GitHubStatus.INVALID_URL, reason="URL has no account name")
    if len(segments) > 1:
        return ParsedGitHubUrl(
            GitHubStatus.INVALID_URL, reason="repository link: account owner not confirmed"
        )
    name = segments[0]
    if name.lower() in _RESERVED or not _USERNAME.match(name):
        return ParsedGitHubUrl(GitHubStatus.INVALID_URL, reason="not a valid GitHub username")
    return ParsedGitHubUrl(GitHubStatus.OK, username=name)
