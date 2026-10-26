"""HTTP surface of the synthetic "Biased Bank" sandbox.

The auditor only ever talks to these endpoints. Responses intentionally do not
disclose which model has a planted bias or what the scoring formula is.
"""

from __future__ import annotations

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

from config_loader import load_config
from sandbox.models import score_applicant, score_batch
from schemas import Applicant, ModelResponse

CONFIG = load_config()

app = FastAPI(
    title="FairLens Sandbox Bank",
    description="Synthetic black-box lending decisions for audit research. Not a real lender.",
    version="1.0.0",
)


@app.get("/health")
def health() -> dict[str, object]:
    return {"status": "ok", "models": 7, "synthetic": True}


@app.post("/score", response_model=ModelResponse)
def score(
    applicant: Applicant,
    model: int = Query(1, ge=1, le=7, description="Black-box model selector"),
) -> ModelResponse:
    return score_applicant(model, applicant, CONFIG)


@app.post("/score_batch", response_model=list[ModelResponse])
def score_batch_endpoint(
    applicants: list[Applicant],
    model: int = Query(1, ge=1, le=7, description="Black-box model selector"),
) -> list[ModelResponse]:
    if len(applicants) > 5000:
        return JSONResponse(  # type: ignore[return-value]
            status_code=413,
            content={"detail": "batch too large; maximum 5000 applicants"},
        )
    return score_batch(model, applicants, CONFIG)
