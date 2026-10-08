"""Deterministic 100-point scoring.

    ai_project_depth  40   see ai_depth.py
    python_backend    30   Python language 12 (4 any qualifying evidence + 5 in a project
                           + 3 in work) + web framework 5 + database 4 + async 3
                           + Redis 3 + backend implementation 3
    cloud_fullstack   15   cloud provider 4 + containers 3 + deployment 4
                           + frontend framework 2 + end-to-end system 2
    github            10   0 for now (status: not_evaluated)
    engineering_depth  5   1 each: testing, architecture, caching/queues,
                           concurrency, reliability/observability

For the backend / cloud / engineering rules, a keyword that only appears in a
skills list earns reduced points (``skills_points``); engineering signals
earn nothing from a skills list. Evidence in a project or work entry earns
full points.

    total_score = sum(categories) - shallow-project penalty, clamped to 0..100
"""

from app.config.scoring import (
    CLOUD_FULLSTACK_MAX,
    ENGINEERING_DEPTH_MAX,
    PYTHON_BACKEND_MAX,
)
from app.models import (
    Candidate,
    EligibilityResult,
    EvidenceSource,
    ScoreBreakdown,
    ScoreItem,
    Strength,
)
from app.screening import rules
from app.screening.ai_depth import analyze_units, score_ai_depth, shallow_penalty
from app.screening.signals import score_signal_rules


def _score_python(eligibility: EligibilityResult) -> ScoreItem:
    qualifying = [e for e in eligibility.python_evidence if e.strength.rank >= Strength.MODERATE.rank]
    in_project = [e for e in qualifying if e.source == EvidenceSource.PROJECT]
    in_work = [e for e in qualifying if e.source == EvidenceSource.EXPERIENCE]

    points = rules.PYTHON_BASE_POINTS if qualifying else 0
    parts = ["base 4 (qualifying Python evidence)"] if qualifying else ["no qualifying evidence"]
    if in_project:
        points += rules.PYTHON_PROJECT_POINTS
        parts.append("+5 used in a project")
    if in_work:
        points += rules.PYTHON_WORK_POINTS
        parts.append("+3 used in work/internship")
    shown = (in_project[:1] + in_work[:1]) or qualifying[:1]
    return ScoreItem(
        category="python_backend",
        signal="python_language",
        points=points,
        max_points=rules.PYTHON_BASE_POINTS + rules.PYTHON_PROJECT_POINTS + rules.PYTHON_WORK_POINTS,
        explanation="Python: " + ", ".join(parts),
        evidence=shown,
    )


def _sum(items: list[ScoreItem], cap: int) -> int:
    return min(cap, sum(i.points for i in items))


def score_candidate(candidate: Candidate, eligibility: EligibilityResult) -> ScoreBreakdown:
    """Score an *eligible* candidate. Rejected candidates are never scored."""
    lines = candidate.lines
    units = analyze_units(lines)

    ai_points, ai_items = score_ai_depth(lines, units)
    py_items = [_score_python(eligibility)] + score_signal_rules(
        "python_backend", rules.BACKEND_SIGNALS, lines
    )
    cloud_items = score_signal_rules("cloud_fullstack", rules.CLOUD_SIGNALS, lines)
    eng_items = score_signal_rules("engineering_depth", rules.ENGINEERING_SIGNALS, lines)

    github_item = ScoreItem(
        category="github",
        signal="github_activity",
        points=0,
        max_points=10,
        explanation="GitHub enrichment not evaluated yet; scored 0 and not counted against eligibility",
    )
    penalty = shallow_penalty(units)

    return ScoreBreakdown.build(
        ai_project_depth=ai_points,
        python_backend=_sum(py_items, PYTHON_BACKEND_MAX),
        cloud_fullstack=_sum(cloud_items, CLOUD_FULLSTACK_MAX),
        engineering_depth=_sum(eng_items, ENGINEERING_DEPTH_MAX),
        penalties=[penalty] if penalty else [],
        score_evidence=[*ai_items, *py_items, *cloud_items, github_item, *eng_items],
    )
