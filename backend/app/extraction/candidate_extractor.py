"""Turn raw resume text into a structured ``Candidate``."""

import re

from app.extraction.fields import (
    extract_email,
    extract_github_profile,
    extract_name,
)
from app.extraction.projects import parse_projects
from app.extraction.sections import split_sections
from app.extraction.text import normalize_text
from app.models import Candidate, EvidenceSource, ResumeLine

_BULLET = re.compile(r"^[•\-*–—]\s*")
_SKILL_SPLIT = re.compile(r"[,;|•]|\s·\s")
_MAX_SKILL_LEN = 40


def parse_skills(lines: list[str]) -> list[str]:
    """Skill tokens from skills-section lines ('Languages: Python, Java' -> Python, Java)."""
    skills: list[str] = []
    seen: set[str] = set()
    for line in lines:
        body = _BULLET.sub("", line.strip())
        if ":" in body:
            body = body.split(":", 1)[1]
        for token in _SKILL_SPLIT.split(body):
            token = token.strip(" .\t")
            if token and len(token) <= _MAX_SKILL_LEN and token.casefold() not in seen:
                seen.add(token.casefold())
                skills.append(token)
    return skills


def extract_candidate(text: str, resume_filename: str, resume_hash: str) -> Candidate:
    normalized = normalize_text(text)
    sections = split_sections(normalized)
    warnings: list[str] = []

    lines: list[ResumeLine] = []
    skill_lines: list[str] = []
    projects = []
    header_lines: list[str] = []

    for section in sections:
        content = list(section.lines)
        if section.kind == EvidenceSource.HEADER:
            header_lines.extend(content)
        if section.kind == EvidenceSource.SKILLS:
            skill_lines.extend(content)
        if section.kind == EvidenceSource.PROJECT:
            parsed = parse_projects(content)
            projects.extend(parsed)
            for project in parsed:
                for text in (project.name, *project.bullets):
                    lines.append(
                        ResumeLine(source=EvidenceSource.PROJECT, text=text, project=project.name)
                    )
            continue
        lines.extend(ResumeLine(source=section.kind, text=ln) for ln in content if ln.strip())

    recognised = {s.kind for s in sections} - {EvidenceSource.HEADER}
    if not recognised:
        warnings.append("No resume sections (skills/projects/experience) could be identified")
    elif EvidenceSource.PROJECT not in recognised:
        warnings.append("No projects section found")

    name = extract_name(header_lines or normalized.split("\n"))
    email = extract_email(normalized)
    if name is None:
        warnings.append("Candidate name not found")
    if email is None:
        warnings.append("Email not found")

    return Candidate(
        candidate_name=name,
        email=email,
        resume_filename=resume_filename,
        resume_hash=resume_hash,
        skills=parse_skills(skill_lines),
        github_url=extract_github_profile(normalized),
        projects=projects,
        lines=lines,
        parse_warnings=warnings,
    )
