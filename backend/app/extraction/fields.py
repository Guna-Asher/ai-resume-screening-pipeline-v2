"""Simple regex-based extraction of contact fields."""

import re

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
_GITHUB_RE = re.compile(
    r"(?:https?://)?(?:www\.)?github\.com/([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))(?:/([A-Za-z0-9._-]+))?",
    re.IGNORECASE,
)
# Paths on github.com that are not user accounts.
_GITHUB_RESERVED = {"features", "about", "pricing", "orgs", "topics", "marketplace", "sponsors"}

_NAME_TOKEN = re.compile(r"^[A-Za-z][A-Za-z.'’-]*$")
_NAME_STOPWORDS = {
    "resume", "curriculum", "vitae", "cv", "profile", "summary", "objective", "contact",
    "engineer", "developer", "intern", "student", "software", "engineering", "science",
    "technologies", "university", "college", "institute", "skills", "projects", "education",
}
_NAME_LINES_SCANNED = 8


def extract_email(text: str) -> str | None:
    match = _EMAIL_RE.search(text)
    return match.group(0).lower() if match else None


def extract_github_urls(text: str) -> list[str]:
    """Normalised GitHub links in order of appearance (profile or repo URLs)."""
    urls: list[str] = []
    for match in _GITHUB_RE.finditer(text):
        user, repo = match.group(1), match.group(2)
        if user.lower() in _GITHUB_RESERVED:
            continue
        repo = repo.removesuffix(".git").rstrip(".") if repo else None
        url = f"https://github.com/{user}" + (f"/{repo}" if repo else "")
        if url not in urls:
            urls.append(url)
    return urls


def extract_github_profile(text: str) -> str | None:
    """Profile URL of the candidate: a bare profile link, else the owner of a repo link."""
    urls = extract_github_urls(text)
    for url in urls:
        if url.count("/") == 3:  # https://github.com/user
            return url
    if urls:
        return "/".join(urls[0].split("/")[:4])
    return None


def extract_name(lines: list[str]) -> str | None:
    """First plausible person name in the opening lines (2-4 alphabetic tokens)."""
    scanned = 0
    for line in lines:
        if not line.strip():
            continue
        scanned += 1
        if scanned > _NAME_LINES_SCANNED:
            break
        for piece in re.split(r"[|•·,;]", line):
            candidate = _as_name(piece.strip())
            if candidate:
                return candidate
    return None


def _as_name(piece: str) -> str | None:
    if not piece or "@" in piece or "http" in piece.lower() or sum(c.isdigit() for c in piece) > 0:
        return None
    tokens = piece.split()
    if not 2 <= len(tokens) <= 4:
        return None
    if not all(_NAME_TOKEN.match(t) for t in tokens):
        return None
    if any(t.lower().strip(".") in _NAME_STOPWORDS for t in tokens):
        return None
    return " ".join(t.title() if t.isupper() else t for t in tokens)
