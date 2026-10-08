"""Human-readable strengths / concerns / project summaries, derived from the score ledger."""

from collections.abc import Sequence

from app.extraction.text import snippet
from app.models import Candidate, ProjectSummary, ScoreBreakdown
from app.screening import rules
from app.screening.ai_depth import UnitAnalysis


def _points(score: ScoreBreakdown, category: str, signal: str) -> int:
    return next(
        (i.points for i in score.score_evidence if i.category == category and i.signal == signal), 0
    )


def build_project_summaries(
    candidate: Candidate, units: Sequence[UnitAnalysis] | None
) -> list[ProjectSummary]:
    """``units`` is None for rejected candidates: no AI scoring is attached."""
    by_label = {u.label: u for u in units or [] if u.kind == "project"}
    summaries: list[ProjectSummary] = []
    for project in candidate.projects:
        detected = [n for n, p in rules.SUPPORTING_SKILLS if p.search(project.name + " " + project.description)]
        technologies = list(dict.fromkeys([*project.technologies, *detected]))
        unit = by_label.get(project.name)
        summaries.append(
            ProjectSummary(
                name=project.name,
                description=snippet(project.description, 300),
                technologies=technologies,
                ai_signals=list(unit.signals) if unit else [],
                ai_depth_points=unit.score if unit else None,
                shallow=unit.shallow if unit and unit.is_ai else None,
            )
        )
    return summaries


def build_strengths_and_concerns(
    candidate: Candidate, score: ScoreBreakdown, units: Sequence[UnitAnalysis]
) -> tuple[list[str], list[str]]:
    strengths: list[str] = []
    concerns: list[str] = []

    ai_units = sorted((u for u in units if u.is_ai), key=lambda u: -u.score)
    deep = [u for u in ai_units if u.strong_signals]
    if deep:
        best = deep[0]
        strengths.append(
            f"AI depth in '{best.label}': {', '.join(best.signals)} ({best.score} unit points)"
        )
        if len(deep) > 1:
            strengths.append(f"{len(deep)} AI projects/work entries with substantive depth")
    penalty = score.penalties[0] if score.penalties else None
    if penalty:
        concerns.append(f"-{penalty.amount} shallow AI project: {penalty.reason}")
    elif not ai_units:
        concerns.append("AI evidence is limited to a skills list; no AI project or work described")

    py_pts = _points(score, "python_backend", "python_language")
    if py_pts >= 9:
        strengths.append("Python used in project and/or work experience")
    elif py_pts:
        concerns.append("Python appears mainly as a listed skill, not described in a project or job")
    for item in score.score_evidence:
        if item.category == "python_backend" and item.signal == "web_framework" and item.points >= 5:
            strengths.append("Python web backend (FastAPI/Flask/Django) in projects or work")
        if item.category == "engineering_depth" and item.points:
            strengths.append(f"Engineering practice: {item.explanation.split(':')[0]}")

    if score.cloud_fullstack >= 8:
        strengths.append("Cloud / deployment / full-stack evidence")
    elif score.cloud_fullstack == 0:
        concerns.append("No cloud, container or deployment evidence")
    if score.engineering_depth == 0:
        concerns.append("No engineering-depth signals (testing, caching, observability, ...)")
    if not candidate.github_url:
        concerns.append("No GitHub URL found on the resume")
    concerns.extend(candidate.parse_warnings)
    return strengths, concerns
