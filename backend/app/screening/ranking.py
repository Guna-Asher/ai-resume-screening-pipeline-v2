"""Deterministic ranking of eligible candidates.

Order: ``total_score`` descending, then (ties) candidate name A-Z
case-insensitively with missing names last, then resume filename, then
resume hash. Ranks are sequential 1..N (tied scores still get distinct,
stable ranks).
"""

from collections.abc import Iterable

from app.models import CandidateResult


def _sort_key(result: CandidateResult) -> tuple:
    assert result.score_breakdown is not None, "only scored (eligible) candidates are ranked"
    name = result.candidate_name
    return (
        -result.score_breakdown.total_score,
        name is None,
        (name or "").casefold(),
        result.resume_filename.casefold(),
        result.resume_hash or "",
    )


def rank_candidates(eligible: Iterable[CandidateResult]) -> list[CandidateResult]:
    ordered = sorted(eligible, key=_sort_key)
    return [r.model_copy(update={"rank": i}) for i, r in enumerate(ordered, start=1)]
