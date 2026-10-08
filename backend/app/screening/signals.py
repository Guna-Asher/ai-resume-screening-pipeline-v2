"""Generic evaluator for rule tables (backend / cloud / engineering categories)."""

from collections.abc import Sequence

from app.models import Evidence, ResumeLine, ScoreItem, Strength
from app.screening.context import Role, classify_line, make_evidence
from app.screening.rules import SignalRule
from app.screening.semantic import SemanticHit, hit_evidence


def score_signal_rules(
    category: str,
    rule_table: Sequence[SignalRule],
    lines: Sequence[ResumeLine],
    semantic_hits: dict[str, SemanticHit] | None = None,
) -> list[ScoreItem]:
    """One ScoreItem per rule.

    Full ``applied_points`` when a project / work / cued line matches;
    ``skills_points`` when the keyword only appears in a skills list.
    ``semantic_hits`` (rule name -> grounded LLM hit) can only upgrade a rule to full
    points; it never lowers anything the rules found.
    """
    classified = [(line, classify_line(line)) for line in lines]
    items: list[ScoreItem] = []
    for rule in rule_table:
        applied: list[Evidence] = []
        listed: list[Evidence] = []
        for line, role in classified:
            if not rule.pattern.search(line.text):
                continue
            if role in (Role.PROJECT_WORK, Role.CUED):
                applied.append(make_evidence(rule.category, rule.name, line, Strength.STRONG))
            elif role == Role.SKILL_LISTING:
                listed.append(make_evidence(rule.category, rule.name, line, Strength.MODERATE))

        semantic = (semantic_hits or {}).get(rule.name)
        if applied:
            points, evidence, how = rule.applied_points, applied[:2], "used in project/work"
        elif semantic:
            points, how = rule.applied_points, "used in project/work (semantic analysis)"
            evidence = [hit_evidence(semantic, rule.category)]
        elif listed and rule.skills_points:
            points, evidence, how = rule.skills_points, listed[:1], "keyword in skills list only"
        else:
            points, evidence, how = 0, [], "no evidence"
        items.append(
            ScoreItem(
                category=category,  # type: ignore[arg-type]
                signal=rule.name,
                points=points,
                max_points=rule.applied_points,
                explanation=f"{rule.explanation}: {how}",
                evidence=evidence,
            )
        )
    return items
