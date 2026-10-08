import json
from datetime import UTC, datetime

from samples import (
    NO_PYTHON,
    RAG_PIPELINE,
    STRONG_AGENTIC,
    THIN_WRAPPER,
)

from app.errors import ResumeParseError
from app.extraction import extract_candidate
from app.models import ScreeningResults
from app.screening.batch import BatchProcessor
from app.screening.engine import screen_candidate
from app.screening.ranking import rank_candidates
from conftest import screen_text
from pdf_utils import make_pdf

FIXED_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _items(files: dict[str, bytes | str]):
    return [
        (name, (lambda d=data: d if isinstance(d, bytes) else d.encode()))
        for name, data in files.items()
    ]


def _processor(**kwargs):
    return BatchProcessor(clock=lambda: FIXED_NOW, **kwargs)


def test_ranking_is_descending_and_deterministic_under_input_order():
    results = [screen_text(t, f"{i}.txt") for i, t in enumerate([THIN_WRAPPER, STRONG_AGENTIC, RAG_PIPELINE])]
    forward = rank_candidates(results)
    backward = rank_candidates(list(reversed(results)))
    assert [r.resume_filename for r in forward] == [r.resume_filename for r in backward]
    scores = [r.score_breakdown.total_score for r in forward]
    assert scores == sorted(scores, reverse=True)
    assert [r.rank for r in forward] == [1, 2, 3]
    assert forward[0].candidate_name == "Jane Doe"


def test_ties_break_by_name_then_filename():
    a = screen_text(RAG_PIPELINE.replace("Ravi Kumar", "Zed Zimmer"), "a.txt")
    b = screen_text(RAG_PIPELINE.replace("Ravi Kumar", "Amy Adams"), "b.txt")
    c = screen_text(RAG_PIPELINE.replace("Ravi Kumar", "Amy Adams"), "a2.txt")
    assert a.score_breakdown.total_score == b.score_breakdown.total_score
    ranked = rank_candidates([a, b, c])
    assert [r.resume_filename for r in ranked] == ["a2.txt", "b.txt", "a.txt"]


def test_rejected_candidates_stay_in_output_unranked():
    results = _processor().process(_items({"good.txt": RAG_PIPELINE, "bad.txt": NO_PYTHON}))
    assert [r.resume_filename for r in results.eligible_candidates] == ["good.txt"]
    rejected = results.rejected_candidates[0]
    assert rejected.resume_filename == "bad.txt"
    assert rejected.rank is None and rejected.score_breakdown is None
    assert rejected.rejection_reasons


def test_one_failing_resume_does_not_terminate_the_batch():
    def boom_on_bad(candidate):
        if "Ravi" in (candidate.candidate_name or ""):
            raise RuntimeError("scoring exploded")
        return screen_candidate(candidate)

    results = _processor(screen=boom_on_bad).process(
        _items({"a.txt": STRONG_AGENTIC, "b.txt": RAG_PIPELINE, "c.txt": THIN_WRAPPER})
    )
    assert results.batch_summary.failed == 1
    assert results.batch_summary.eligible == 2
    failed = results.failed_candidates[0]
    assert failed.resume_filename == "b.txt"
    assert failed.status == "failed"
    assert failed.error.stage == "screen"
    assert failed.error.error_type == "RuntimeError"
    assert "scoring exploded" in failed.error.message


def test_malformed_pdf_empty_file_and_unsupported_type_are_recorded_not_raised():
    results = _processor().process(
        _items(
            {
                "broken.pdf": b"%PDF-1.4 this is not really a pdf",
                "empty.txt": "",
                "photo.png": b"\x89PNG",
                "ok.txt": STRONG_AGENTIC,
            }
        )
    )
    s = results.batch_summary
    assert (s.total_resumes, s.eligible, s.failed) == (4, 1, 3)
    errors = {f.resume_filename: f.error for f in results.failed_candidates}
    assert errors["broken.pdf"].stage == "parse"
    assert errors["empty.txt"].error_type == ResumeParseError.__name__
    assert errors["photo.png"].error_type == "UnsupportedFormatError"


def test_unreadable_file_is_a_read_failure():
    def unreadable() -> bytes:
        raise PermissionError("denied")

    results = _processor().process([("locked.pdf", unreadable), ("ok.txt", lambda: RAG_PIPELINE.encode())])
    assert results.failed_candidates[0].error.stage == "read"
    assert results.batch_summary.eligible == 1


def test_duplicates_are_detected_by_bytes_and_by_text():
    results = _processor().process(
        _items(
            {
                "a.txt": RAG_PIPELINE,
                "b_copy.txt": RAG_PIPELINE,
                "c_reformatted.txt": "  " + RAG_PIPELINE.upper().replace("RAVI KUMAR", "Ravi Kumar") + "\n\n",
                "d.txt": STRONG_AGENTIC,
            }
        )
    )
    reasons = {d.resume_filename: (d.duplicate_of, d.reason) for d in results.duplicates}
    assert reasons["b_copy.txt"] == ("a.txt", "identical_file")
    assert results.batch_summary.duplicates == len(results.duplicates)
    s = results.batch_summary
    assert s.total_resumes == s.successfully_parsed + s.failed + s.duplicates
    assert s.successfully_parsed == s.eligible + s.rejected


def test_pdf_resume_end_to_end():
    pdf = make_pdf(
        [
            "Ravi Kumar",
            "ravi@example.com",
            "SKILLS",
            "Python, FastAPI",
            "PROJECTS",
            "Document QA",
            "- Built a RAG pipeline with embeddings and vector retrieval (FAISS)",
        ]
    )
    results = _processor().process(_items({"ravi.pdf": pdf}))
    assert results.batch_summary.eligible == 1, results.failed_candidates
    top = results.eligible_candidates[0]
    assert top.candidate_name == "Ravi Kumar" and top.email == "ravi@example.com"


def test_results_json_round_trips_and_has_expected_contract():
    results = _processor().process(_items({"a.txt": STRONG_AGENTIC, "b.txt": NO_PYTHON}))
    payload = json.loads(results.model_dump_json())
    assert payload["schema_version"] == "1.0"
    assert set(payload) >= {
        "generated_at", "batch_summary", "eligible_candidates", "rejected_candidates",
        "failed_candidates", "duplicates",
    }
    top = payload["eligible_candidates"][0]
    assert set(top["score_breakdown"]) >= {
        "ai_project_depth", "python_backend", "cloud_fullstack", "github",
        "engineering_depth", "penalties", "total_score", "score_evidence",
    }
    assert ScreeningResults.model_validate(payload) == results


def test_process_directory_skips_hidden_files_and_reads_subfolders(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "r.txt").write_text(STRONG_AGENTIC)
    (tmp_path / ".DS_Store").write_bytes(b"x")
    results = _processor().process_directory(tmp_path)
    assert results.batch_summary.total_resumes == 1
    assert results.eligible_candidates[0].resume_filename == "sub/r.txt"
