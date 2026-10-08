"""Split resume text into labelled sections using heading heuristics."""

import re
from dataclasses import dataclass

from app.models import EvidenceSource

_ALIASES: dict[str, EvidenceSource] = {}


def _register(kind: EvidenceSource, *names: str) -> None:
    for name in names:
        _ALIASES[name] = kind


_register(
    EvidenceSource.SUMMARY,
    "summary", "professional summary", "career summary", "profile", "professional profile",
    "objective", "career objective", "about", "about me",
)
_register(
    EvidenceSource.SKILLS,
    "skills", "technical skills", "tech skills", "key skills", "core skills",
    "core competencies", "technical proficiencies", "skills and tools", "skills and technologies",
    "programming languages", "technologies", "tools and technologies", "technical expertise",
)
_register(
    EvidenceSource.PROJECT,
    "projects", "personal projects", "academic projects", "selected projects", "key projects",
    "project experience", "technical projects", "side projects", "projects and hackathons",
)
_register(
    EvidenceSource.EXPERIENCE,
    "experience", "work experience", "professional experience", "internships",
    "internship experience", "internship", "employment", "employment history", "work history",
    "relevant experience", "experience and internships", "industry experience",
)
_register(
    EvidenceSource.EDUCATION,
    "education", "academic background", "qualifications", "academic qualifications",
)
_register(
    EvidenceSource.CERTIFICATIONS,
    "certifications", "certificates", "licenses and certifications", "courses",
    "training", "online courses",
)
_register(
    EvidenceSource.OTHER,
    "achievements", "awards", "publications", "extracurricular activities", "activities",
    "volunteering", "volunteer experience", "interests", "hobbies", "positions of responsibility",
    "leadership", "references",
)

# Labels that also introduce per-project lines ("Technologies: Python, ..."),
# so they only count as headings when they stand alone on their line.
_STANDALONE_ONLY = {"technologies", "tools and technologies", "skills and technologies"}

_KEYWORD_KINDS = (
    ("skills", EvidenceSource.SKILLS),
    ("projects", EvidenceSource.PROJECT),
    ("experience", EvidenceSource.EXPERIENCE),
    ("education", EvidenceSource.EDUCATION),
)

_INLINE_RE = re.compile(r"^([A-Za-z][A-Za-z &/]{2,40}?)\s*:\s*(\S.*)$")
_BULLET_START = re.compile(r"^[•\-*–—]\s")


@dataclass(frozen=True)
class Section:
    kind: EvidenceSource
    heading: str | None
    lines: tuple[str, ...]  # blank lines preserved; they separate project entries


def _normalize_heading(text: str) -> str:
    text = text.lower().replace("&", " and ").replace("/", " ")
    text = re.sub(r"[^a-z ]", " ", text)
    return " ".join(text.split())


def match_heading(line: str) -> tuple[EvidenceSource, str, str] | None:
    """Return (kind, heading, remainder-on-same-line) if ``line`` starts a section."""
    stripped = line.strip()
    if not stripped or len(stripped) > 60 or _BULLET_START.match(stripped):
        return None

    inline = _INLINE_RE.match(stripped)
    if inline:
        key = _normalize_heading(inline.group(1))
        if key in _ALIASES and key not in _STANDALONE_ONLY:
            return _ALIASES[key], inline.group(1).strip(), inline.group(2).strip()

    key = _normalize_heading(stripped)
    if key in _ALIASES:
        return _ALIASES[key], stripped.rstrip(":").strip(), ""

    # e.g. "SELECTED TECHNICAL PROJECTS" - only for shouty / colon-terminated lines
    words = key.split()
    if 1 <= len(words) <= 4 and (stripped.isupper() or stripped.endswith(":")):
        for keyword, kind in _KEYWORD_KINDS:
            if keyword in words:
                return kind, stripped.rstrip(":").strip(), ""
    return None


def split_sections(text: str) -> list[Section]:
    sections: list[Section] = []
    kind = EvidenceSource.HEADER
    heading: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        if buffer or heading is not None:
            sections.append(Section(kind, heading, tuple(buffer)))

    for line in text.split("\n"):
        match = match_heading(line)
        if match:
            flush()
            kind, heading, remainder = match
            buffer = [remainder] if remainder else []
        else:
            buffer.append(line.strip())
    flush()
    return sections
