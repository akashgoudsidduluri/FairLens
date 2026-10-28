"""HTTP service for the two real-data targets.

Run from the repository root:

    .venv\\Scripts\\python -m targets.real.serve --port 8030

``POST /score_batch?model=uci_credit_default`` accepts a JSON list of canonical
``Applicant`` objects and returns ``[{approved, score}]`` in the same shape as
the sandbox. The service maps applicants to the dataset's own columns with
``targets.real.features``; it never imports the sandbox.
"""

from __future__ import annotations

import argparse
import os

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from schemas import Applicant
from targets.real.models import (
    InfeasibleApplicant,
    RealModelUnavailable,
    available_models,
    metrics_for,
    score_applicants,
)

app = FastAPI(
    title="FairLens real-data targets",
    description=(
        "Two models trained on public UCI datasets. Audit probes are synthetic "
        "canonical applicants mapped to dataset columns; no rows are fabricated."
    ),
    version="1.0.0",
)


@app.get("/health")
def health() -> dict[str, object]:
    models = available_models()
    return {
        "status": "ok" if models else "degraded",
        "models": models,
        "real_data": True,
    }


@app.get("/models")
def models() -> dict[str, object]:
    return {
        "models": available_models(),
        "metrics": {
            name: {
                "holdout": metrics_for(name)["holdout"],
                "dataset": metrics_for(name)["dataset"],
            }
            for name in available_models()
        },
    }


@app.post("/score_batch")
def score_batch(
    applicants: list[Applicant],
    model: str = Query(..., description="uci_credit_default or adult_income"),
) -> JSONResponse:
    try:
        responses = score_applicants(model, applicants)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown model: {model}") from exc
    except RealModelUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except InfeasibleApplicant as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return JSONResponse([response.model_dump(mode="json") for response in responses])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--host", default=os.environ.get("FAIRLENS_REAL_HOST", "127.0.0.1")
    )
    parser.add_argument(
        "--port", type=int, default=int(os.environ.get("FAIRLENS_REAL_PORT", "8030"))
    )
    args = parser.parse_args(argv)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
