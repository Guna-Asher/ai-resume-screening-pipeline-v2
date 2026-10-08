"""Structured output the LLM must return: *evidence*, never scores.

Unknown / extra fields (e.g. a model-invented ``score`` or ``penalty``) are
ignored by design. Free-text fields are clipped so a verbose model cannot
bloat the results.
"""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


class Signal(StrEnum):
    """Closed vocabulary of semantic signals the model may report."""

    # AI project depth
    LLM_USAGE = "llm_usage"
    RAG = "rag"
    EMBEDDINGS = "embeddings"
    VECTOR_SEARCH = "vector_search"
    TOOL_CALLING = "tool_calling"
    AGENTS = "agents"
    MULTI_AGENT = "multi_agent"
    STATE_MANAGEMENT = "state_management"
    ORCHESTRATION = "orchestration"
    EVALUATION = "evaluation"
    DATA_PROCESSING = "data_processing"
    BACKEND_LOGIC = "backend_logic"
    PRODUCT_LOGIC = "product_logic"
    # Python / backend
    PYTHON = "python"
    FASTAPI = "fastapi"
    ASYNC = "async"
    POSTGRESQL = "postgresql"
    REDIS = "redis"
    # Cloud / deployment / full stack
    GCP = "gcp"
    DOCKER = "docker"
    DEPLOYMENT = "deployment"
    REACT = "react"
    NEXTJS = "nextjs"
    # Engineering depth
    TESTING = "testing"
    ARCHITECTURE = "architecture"
    CACHING = "caching"
    QUEUES = "queues"
    CONCURRENCY = "concurrency"
    OBSERVABILITY = "observability"
    FAILURE_HANDLING = "failure_handling"


def _clip(limit: int):
    def clip(value):
        return value[:limit] if isinstance(value, str) else value

    return BeforeValidator(clip)


def _clip_list(max_items: int, max_chars: int):
    def clip(value):
        if isinstance(value, list):
            return [v[:max_chars] if isinstance(v, str) else v for v in value[:max_items]]
        return value

    return BeforeValidator(clip)


class SignalHit(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # A string (not the enum) so one unexpected name cannot invalidate the whole
    # response; unknown names are dropped and counted during normalisation.
    signal: Annotated[str, _clip(60)]
    # Short verbatim quote from ONE line of the resume. It is later grounded
    # against the real resume text; quotes that cannot be found are discarded.
    evidence: Annotated[str, _clip(300)]


class ProjectAnalysis(BaseModel):
    model_config = ConfigDict(extra="ignore")

    project_name: Annotated[str, _clip(120)]
    source: Literal["project", "work", "other"] = "project"
    summary: Annotated[str, _clip(400)] = ""
    signals: Annotated[list[SignalHit], _clip_list(40, 10_000)] = Field(default_factory=list)
    depth_assessment: Literal["shallow", "moderate", "substantial", "unclear"] = "unclear"
    shallow_wrapper: bool = False
    concerns: Annotated[list[str], _clip_list(3, 200)] = Field(default_factory=list)


class SemanticAnalysis(BaseModel):
    model_config = ConfigDict(extra="ignore")

    projects: Annotated[list[ProjectAnalysis], _clip_list(12, 10_000)]
    overall_evidence: Annotated[list[str], _clip_list(5, 300)] = Field(default_factory=list)
    confidence_notes: Annotated[list[str], _clip_list(5, 200)] = Field(default_factory=list)
