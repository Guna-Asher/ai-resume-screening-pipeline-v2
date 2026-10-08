"""Group the lines of a PROJECTS section into individual projects.

Heuristic, documented limitation: a project starts at the first line, after a
blank line, or at a short capitalised non-bullet line that follows bullets.
Resumes whose bullets lost their markers collapse into one project.
"""

import re

from app.extraction.fields import extract_github_urls
from app.models import Project

_BULLET = re.compile(r"^[•\-*–—]\s*")
_META = re.compile(
    r"^(tech(?:nologies)?(?: used| stack)?|stack|tools|built with|github|link|url|repo(?:sitory)?|demo)\s*[:\-]\s*(.*)$",
    re.IGNORECASE,
)
_TITLE_SPLIT = re.compile(r"\s*\|\s*|\s+[–—-]\s+")
_UNTITLED = "Untitled project"


class _Builder:
    def __init__(self, name: str, extra: str = "") -> None:
        self.name = name
        self.bullets: list[str] = [extra] if extra else []
        self.technologies: list[str] = []
        self.has_bullets = False

    def build(self) -> Project:
        github = extract_github_urls(" ".join(self.bullets))
        return Project(
            name=self.name,
            bullets=self.bullets,
            technologies=self.technologies,
            github_url=github[0] if github else None,
        )


def _looks_like_title(line: str) -> bool:
    words = line.split()
    return (
        len(words) <= 8
        and (line[0].isupper() or line[0].isdigit())
        and not line.endswith((".", ",", ";"))
    )


def _split_title(line: str) -> tuple[str, str]:
    parts = _TITLE_SPLIT.split(line, maxsplit=1)
    name = parts[0].strip(" :")
    return (name or _UNTITLED), (parts[1].strip() if len(parts) > 1 else "")


def parse_projects(lines: list[str]) -> list[Project]:
    projects: list[Project] = []
    current: _Builder | None = None
    blank_before = False

    for raw in lines:
        line = raw.strip()
        if not line:
            blank_before = True
            continue

        meta = _META.match(line)
        if meta and current is not None:
            if meta.group(1).lower().startswith(("tech", "stack", "tools", "built")):
                current.technologies.extend(
                    t.strip() for t in re.split(r"[,;|]", meta.group(2)) if t.strip()
                )
            current.bullets.append(line)
        elif _BULLET.match(line):
            if current is None:
                current = _Builder(_UNTITLED)
            current.bullets.append(_BULLET.sub("", line))
            current.has_bullets = True
        elif current is None or blank_before or (current.has_bullets and _looks_like_title(line)):
            if current is not None:
                projects.append(current.build())
            current = _Builder(*_split_title(line))
        else:
            current.bullets.append(line)  # wrapped / plain description text
        blank_before = False

    if current is not None:
        projects.append(current.build())
    return projects
