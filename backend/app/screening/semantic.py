"""Turn advisory LLM output into deterministic, grounded scoring evidence.

Scoring policy (the LLM never supplies numbers):

* Grounding. A signal is accepted only if its evidence quote can be found in a
  resume line (>= 80% of the quote's words appear in that line). Invented quotes
  are discarded, so every accepted signal is tied to real resume text, its section
  and, for projects, its project.
* Implementation only. The grounded line must be project/work evidence (or a cued
  claim). Skills-list, tutorial and coursework lines earn nothing from the LLM.
* One target per signal. Every vocabulary signal maps to exactly one scoring target;
  aliases share a target (rag + vector_search -> retrieval) and a target counts
  once per unit, so synonyms and keyword-stuffed sentences cannot stack points.
* Additive only. Accepted signals are *added* to what the rules found. Nothing the
  rules detected is ever removed, so a failed LLM leaves the Step-1 score intact.
* ``python`` is ignored: Python evidence is already decided by deterministic rules.
"""

import re
from collections import Counter
from dataclasses import dataclass, field

from app.extraction.text import snippet
from app.llm.schemas import ProjectAnalysis, SemanticAnalysis, Signal
from app.models import Evidence, EvidenceCategory, ResumeLine, Strength
from app.screening.context import Role, classify_line, unit_key

GROUNDING_THRESHOLD = 0.8
MIN_QUOTE_WORDS = 3

BASELINE_TARGET = "ai_application"

# signal -> AI-depth target (a signal name in rules.DEPTH_SIGNALS, or the baseline)
AI_DEPTH_TARGETS: dict[str, str] = {
    Signal.LLM_USAGE: BASELINE_TARGET,
    Signal.RAG: "retrieval",
    Signal.VECTOR_SEARCH: "retrieval",
    Signal.EMBEDDINGS: "embeddings_vector_store",
    Signal.TOOL_CALLING: "tool_calling",
    Signal.AGENTS: "agents",
    Signal.MULTI_AGENT: "agents",
    Signal.STATE_MANAGEMENT: "orchestration_state",
    Signal.ORCHESTRATION: "orchestration_state",
    Signal.EVALUATION: "evaluation",
    Signal.DATA_PROCESSING: "data_product_logic",
    Signal.PRODUCT_LOGIC: "data_product_logic",
    Signal.BACKEND_LOGIC: "backend_integration",
}

# signal -> (score category, rule name in rules.BACKEND/CLOUD/ENGINEERING_SIGNALS)
RULE_TARGETS: dict[str, tuple[str, str]] = {
    Signal.FASTAPI: ("python_backend", "web_framework"),
    Signal.ASYNC: ("python_backend", "async"),
    Signal.POSTGRESQL: ("python_backend", "database"),
    Signal.REDIS: ("python_backend", "redis"),
    Signal.GCP: ("cloud_fullstack", "cloud_provider"),
    Signal.DOCKER: ("cloud_fullstack", "containers"),
    Signal.DEPLOYMENT: ("cloud_fullstack", "deployment"),
    Signal.REACT: ("cloud_fullstack", "frontend"),
    Signal.NEXTJS: ("cloud_fullstack", "frontend"),
    Signal.TESTING: ("engineering_depth", "testing"),
    Signal.ARCHITECTURE: ("engineering_depth", "architecture"),
    Signal.CACHING: ("engineering_depth", "caching_queues"),
    Signal.QUEUES: ("engineering_depth", "caching_queues"),
    Signal.CONCURRENCY: ("engineering_depth", "concurrency"),
    Signal.OBSERVABILITY: ("engineering_depth", "reliability_observability"),
    Signal.FAILURE_HANDLING: ("engineering_depth", "reliability_observability"),
}
IGNORED_SIGNALS = {Signal.PYTHON.value}


@dataclass(frozen=True)
class SemanticHit:
    signal: str
    line: ResumeLine  # the real resume line the LLM quote was grounded to
    quote: str


@dataclass
class SemanticSignals:
    """Grounded, de-duplicated semantic evidence ready for the deterministic scorer."""

    ai_depth: dict[tuple[str, str], dict[str, SemanticHit]] = field(default_factory=dict)
    rule_hits: dict[str, dict[str, SemanticHit]] = field(default_factory=dict)
    accepted: int = 0
    rejected: Counter = field(default_factory=Counter)
    projects: list[ProjectAnalysis] = field(default_factory=list)
    overall_evidence: list[str] = field(default_factory=list)
    confidence_notes: list[str] = field(default_factory=list)

    def match_project(self, name: str) -> ProjectAnalysis | None:
        wanted = name.casefold().strip()
        for project in self.projects:
            candidate = project.project_name.casefold().strip()
            if candidate and (candidate == wanted or candidate in wanted or wanted in candidate):
                return project
        return None

    def flags_shallow(self, label: str) -> bool:
        project = self.match_project(label)
        return bool(project and project.shallow_wrapper)

    @property
    def concerns(self) -> list[str]:
        return [c for p in self.projects for c in p.concerns]


def hit_evidence(hit: SemanticHit, category: EvidenceCategory) -> Evidence:
    """Evidence text is the resume line itself, never the model's wording."""
    return Evidence(
        category=category,
        term=hit.signal,
        text=snippet(hit.line.text),
        source=hit.line.source,
        strength=Strength.STRONG,
        context=hit.line.project,
        note=f"semantic analysis (LLM): '{snippet(hit.quote, 120)}'",
        origin="llm",
    )


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.casefold()) if len(t) >= 3}


def ground_quote(quote: str, lines: list[ResumeLine]) -> ResumeLine | None:
    """The resume line that (almost) contains ``quote``, or None if it is not in the resume."""
    wanted = _tokens(quote)
    if len(wanted) < MIN_QUOTE_WORDS:
        return None
    best: ResumeLine | None = None
    best_cover = 0.0
    for line in lines:
        cover = len(wanted & _tokens(line.text)) / len(wanted)
        if cover > best_cover:
            best, best_cover = line, cover
    return best if best_cover >= GROUNDING_THRESHOLD else None


def ground_signals(lines: list[ResumeLine], analysis: SemanticAnalysis) -> SemanticSignals:
    result = SemanticSignals(
        projects=list(analysis.projects),
        overall_evidence=list(analysis.overall_evidence),
        confidence_notes=list(analysis.confidence_notes),
    )
    for project in analysis.projects:
        for hit in project.signals:
            name = hit.signal.strip().casefold().replace("-", "_").replace(" ", "_")
            if name in IGNORED_SIGNALS:
                result.rejected["not_scored"] += 1
                continue
            if name not in AI_DEPTH_TARGETS and name not in RULE_TARGETS:
                result.rejected["unknown_signal"] += 1
                continue
            line = ground_quote(hit.evidence, lines)
            if line is None:
                result.rejected["ungrounded"] += 1
                continue
            if classify_line(line) not in (Role.PROJECT_WORK, Role.CUED):
                result.rejected["not_implementation"] += 1
                continue

            sem_hit = SemanticHit(signal=name, line=line, quote=hit.evidence)
            if name in AI_DEPTH_TARGETS:
                unit_hits = result.ai_depth.setdefault(unit_key(line), {})
                target = AI_DEPTH_TARGETS[name]
            else:
                category, target = RULE_TARGETS[name]
                unit_hits = result.rule_hits.setdefault(category, {})
            if target not in unit_hits:  # first grounded hit per target wins; aliases merge
                unit_hits[target] = sem_hit
                result.accepted += 1
    return result
