"""Context-aware detection of genuine Python evidence.

A bare ``"python" in text`` check is not used. Each match is graded by the
line's context (see ``context.classify_line``):

    project / work entry        -> STRONG
    claim with a usage cue      -> MODERATE   ("Python developer", "built X in Python")
    skills list                 -> MODERATE   ("Languages: Java, Python")
    tutorial / coursework / bare keyword -> WEAK (does not count)

Python-only libraries (FastAPI, Django, pandas...) count as MODERATE evidence
when used in a project or job, but never from a skills list alone.
"""

from collections.abc import Sequence

from app.models import Evidence, EvidenceCategory, ResumeLine, Strength
from app.screening import rules
from app.screening.context import Role, classify_line, make_evidence

_PYTHON_STRENGTH = {
    Role.PROJECT_WORK: Strength.STRONG,
    Role.CUED: Strength.MODERATE,
    Role.SKILL_LISTING: Strength.MODERATE,
    Role.WEAK: Strength.WEAK,
}
_ECOSYSTEM_STRENGTH = {
    Role.PROJECT_WORK: Strength.MODERATE,
    Role.CUED: Strength.MODERATE,
    Role.SKILL_LISTING: Strength.WEAK,
    Role.WEAK: Strength.WEAK,
}


def detect_python_evidence(lines: Sequence[ResumeLine]) -> list[Evidence]:
    evidence: list[Evidence] = []
    for line in lines:
        role = classify_line(line)
        if rules.PYTHON_PATTERN.search(line.text):
            evidence.append(
                make_evidence(EvidenceCategory.PYTHON, "Python", line, _PYTHON_STRENGTH[role])
            )
        for name, pattern in rules.PYTHON_ECOSYSTEM:
            if pattern.search(line.text):
                evidence.append(
                    make_evidence(
                        EvidenceCategory.PYTHON_ECOSYSTEM, name, line, _ECOSYSTEM_STRENGTH[role]
                    )
                )
    return evidence


def qualifies(evidence: Sequence[Evidence]) -> bool:
    return any(e.strength.rank >= Strength.MODERATE.rank for e in evidence)
