"""Minimal FastAPI app. Upload/screening endpoints arrive in a later step."""

from fastapi import FastAPI

from app.models import SCHEMA_VERSION

app = FastAPI(title="AI Resume Screening", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "results_schema_version": SCHEMA_VERSION}
