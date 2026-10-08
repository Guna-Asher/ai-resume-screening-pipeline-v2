"""API-only models. Screening results use the canonical ``ScreeningResults`` model."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str = "ok"


class ErrorResponse(BaseModel):
    detail: str
