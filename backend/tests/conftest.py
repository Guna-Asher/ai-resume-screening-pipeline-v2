import pytest

from app.extraction import extract_candidate
from app.models import Candidate, CandidateResult
from app.screening.engine import screen_candidate


def make_candidate(text: str, filename: str = "resume.txt") -> Candidate:
    return extract_candidate(text, filename, resume_hash=f"hash-{filename}")


def screen_text(text: str, filename: str = "resume.txt") -> CandidateResult:
    return screen_candidate(make_candidate(text, filename))


@pytest.fixture
def screen():
    return screen_text
