"""The one place that assembles the screening pipeline. CLI and API both call this.

A fresh processor (and therefore fresh LLM / GitHub caches) is built per run, so two
independent runs never share candidate results.
"""

import logging
from dataclasses import dataclass

from app.config import Settings
from app.github import GitHubEnricher
from app.llm import SemanticAnalyzer
from app.screening.batch import BatchProcessor

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PipelineOptions:
    """The only knobs exposed to callers. Scoring weights and rules are not configurable."""

    use_llm: bool = True
    use_github: bool = True


def build_processor(settings: Settings, options: PipelineOptions | None = None) -> BatchProcessor:
    options = options or PipelineOptions()

    analyzer = None
    if options.use_llm:
        analyzer = SemanticAnalyzer.from_settings(settings)
        if analyzer.unavailable_reason:
            logger.warning(
                "LLM analysis unavailable (%s); continuing with deterministic scoring only",
                analyzer.unavailable_reason,
            )

    github = None
    if options.use_github:
        github = GitHubEnricher.from_settings(settings)
        if not github.authenticated:
            logger.info("GITHUB_TOKEN not set: unauthenticated GitHub requests (low rate limit)")

    return BatchProcessor(analyzer=analyzer, github=github)
