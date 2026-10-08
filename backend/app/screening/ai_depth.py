"""AI / Agentic / RAG project depth (40 pts) and the shallow-project penalty.

Formula (all integers, see ``rules`` for the signal tables)
-----------------------------------------------------------
Text is grouped into *units*: each project, the work/internship entries
together, and "claims" (cued mentions in other sections). Lines in a
tutorial/learning context are ignored.

A unit is an AI unit only if it mentions at least one AI term.

    unit_score = 5 (baseline: AI term present)
               + sum of points for each depth signal present
                 retrieval 7, embeddings/vector store/chunking 4, tool calling 5,
                 agents 6, orchestration/state 5, evaluation 5,
                 data/product logic 4, backend integration 3
    claims unit is capped at 10 (unsubstantiated).

    ai_project_depth = min(40, best_unit
                              + min(6, 2 per *other* AI unit scoring >= 10)
                              + min(3, 1 per AI framework/technique seen only in skills))

Shallow-project penalty (5-15)
------------------------------
If the candidate has AI units but NONE contains a *strong* signal (retrieval,
embeddings, tool calling, agents, orchestration/state, evaluation) it is a thin
LLM/API wrapper. Penalty by supporting signals (data/product logic, backend)
in the best unit:  0 -> 15,  1 -> 10,  2 -> 5.
A candidate with at least one non-shallow AI project is never penalised, so
a small side chatbot next to a real RAG project costs nothing.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field

from app.config.scoring import AI_PROJECT_DEPTH_MAX
from app.models import (
    Evidence,
    EvidenceCategory,
    EvidenceSource,
    Penalty,
    ResumeLine,
    ScoreItem,
    Strength,
)
from app.screening import rules
from app.screening.ai_evidence import ai_strength, matching_terms
from app.screening.context import Role, classify_line, make_evidence

CLAIMS_LABEL = "Claims outside project/work sections"
WORK_LABEL = "Work experience"
SHALLOW_CODE = "shallow_ai_project"


@dataclass
class UnitAnalysis:
    label: str
    kind: str  # "project" | "work" | "claims"
    score: int = 0
    signals: list[str] = field(default_factory=list)
    strong_signals: int = 0
    supporting_signals: int = 0
    ai_terms: list[str] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)

    @property
    def is_ai(self) -> bool:
        return bool(self.ai_terms)

    @property
    def shallow(self) -> bool:
        return self.is_ai and self.strong_signals == 0


def _unit_key(line: ResumeLine) -> tuple[str, str]:
    if line.source == EvidenceSource.PROJECT:
        return "project", line.project or "Untitled project"
    if line.source == EvidenceSource.EXPERIENCE:
        return "work", WORK_LABEL
    return "claims", CLAIMS_LABEL


def analyze_units(lines: Sequence[ResumeLine]) -> list[UnitAnalysis]:
    grouped: dict[tuple[str, str], list[ResumeLine]] = {}
    for line in lines:
        role = classify_line(line)
        if role in (Role.PROJECT_WORK, Role.CUED):
            grouped.setdefault(_unit_key(line), []).append(line)
    return [_analyze_unit(kind, label, unit) for (kind, label), unit in grouped.items()]


def _analyze_unit(kind: str, label: str, unit_lines: list[ResumeLine]) -> UnitAnalysis:
    unit = UnitAnalysis(label=label, kind=kind)
    text = " \n".join(line.text for line in unit_lines)

    for line in unit_lines:
        for term in matching_terms(line.text):
            if term.name not in unit.ai_terms:
                unit.ai_terms.append(term.name)
                unit.evidence.append(
                    make_evidence(term.category, term.name, line, ai_strength(term, classify_line(line)))
                )
    if not unit.is_ai:
        return unit

    score = rules.BASELINE_POINTS
    for signal in rules.DEPTH_SIGNALS:
        if signal.pattern.search(text):
            score += signal.points
            unit.signals.append(signal.name)
            if signal.strong:
                unit.strong_signals += 1
            else:
                unit.supporting_signals += 1
    unit.score = min(score, rules.CLAIMS_UNIT_CAP) if kind == "claims" else score
    return unit


def _skills_claim_terms(lines: Sequence[ResumeLine]) -> list[Evidence]:
    """AI frameworks/techniques that appear in a skills list (deduplicated)."""
    seen: dict[str, Evidence] = {}
    for line in lines:
        if line.source != EvidenceSource.SKILLS or classify_line(line) != Role.SKILL_LISTING:
            continue
        for term in matching_terms(line.text):
            if term.kind != rules.AIKind.GENERIC and term.name not in seen:
                seen[term.name] = make_evidence(term.category, term.name, line, Strength.WEAK)
    return list(seen.values())


def score_ai_depth(
    lines: Sequence[ResumeLine], units: Sequence[UnitAnalysis]
) -> tuple[int, list[ScoreItem]]:
    ai_units = sorted((u for u in units if u.is_ai), key=lambda u: (-u.score, u.label))
    items: list[ScoreItem] = []
    total = 0

    if ai_units:
        best = ai_units[0]
        total += best.score
        items.append(
            ScoreItem(
                category="ai_project_depth",
                signal="best_ai_unit",
                points=best.score,
                max_points=AI_PROJECT_DEPTH_MAX,
                explanation=(
                    f"'{best.label}': baseline {rules.BASELINE_POINTS} for AI usage"
                    + "".join(f" + {s}" for s in best.signals)
                    + (" (capped: claims outside project/work)" if best.kind == "claims" else "")
                ),
                evidence=best.evidence[:6],
            )
        )
        extras = [u for u in ai_units[1:] if u.score >= rules.EXTRA_PROJECT_THRESHOLD]
        extra_pts = min(rules.EXTRA_PROJECT_CAP, rules.EXTRA_PROJECT_POINTS * len(extras))
        if extra_pts:
            total += extra_pts
            items.append(
                ScoreItem(
                    category="ai_project_depth",
                    signal="additional_ai_projects",
                    points=extra_pts,
                    max_points=rules.EXTRA_PROJECT_CAP,
                    explanation="Breadth: other AI work scoring >= 10: "
                    + ", ".join(f"'{u.label}'" for u in extras),
                    evidence=[e for u in extras for e in u.evidence[:1]],
                )
            )

    claims = _skills_claim_terms(lines)
    claim_pts = min(rules.SKILLS_CLAIM_CAP, len(claims))
    if claim_pts:
        total += claim_pts
        items.append(
            ScoreItem(
                category="ai_project_depth",
                signal="skills_list_claims",
                points=claim_pts,
                max_points=rules.SKILLS_CLAIM_CAP,
                explanation="AI frameworks/techniques listed in skills only: 1 point each, "
                f"capped at {rules.SKILLS_CLAIM_CAP} (a keyword list is not project evidence)",
                evidence=claims[: rules.SKILLS_CLAIM_CAP],
            )
        )
    if not items:
        items.append(
            ScoreItem(
                category="ai_project_depth",
                signal="no_ai_project_evidence",
                points=0,
                max_points=AI_PROJECT_DEPTH_MAX,
                explanation="No AI project, work or skills-list evidence to score",
            )
        )
    return min(AI_PROJECT_DEPTH_MAX, total), items


def shallow_penalty(units: Sequence[UnitAnalysis]) -> Penalty | None:
    ai_units = [u for u in units if u.is_ai]
    if not ai_units or any(not u.shallow for u in ai_units):
        return None

    best = max(ai_units, key=lambda u: (u.supporting_signals, u.score, u.label))
    amount = rules.SHALLOW_PENALTY_BY_SUPPORT.get(
        best.supporting_signals, rules.SHALLOW_PENALTY_DEFAULT
    )
    has_support = f" (only supporting signals: {', '.join(best.signals)})" if best.signals else ""
    return Penalty(
        code=SHALLOW_CODE,
        amount=amount,
        reason=(
            f"AI work looks like a thin LLM/API wrapper: no retrieval, embeddings, tool "
            f"calling, agents, orchestration/state or evaluation found in "
            f"{', '.join(repr(u.label) for u in ai_units)}{has_support}"
        ),
        evidence=best.evidence[:4],
    )
