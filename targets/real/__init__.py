"""R3 real-data targets: two models trained on public UCI datasets.

The seven synthetic sandbox models remain the validation suite. These targets
are the out-of-sample test: nobody planted their behaviour.

Use ``targets.real.train`` to build artifacts, ``targets.real.serve`` to expose
them over HTTP, and ``targets/real/*.yaml`` with ``build_target`` to audit them.
"""

from __future__ import annotations

from targets.real.adapter import RealTargetAdapter
from targets.real.datasets import DatasetUnavailable, load_dataset
from targets.real.models import (
    RealModelUnavailable,
    available_models,
    load_real_model,
    score_applicants,
)

__all__ = [
    "DatasetUnavailable",
    "RealModelUnavailable",
    "RealTargetAdapter",
    "available_models",
    "load_dataset",
    "load_real_model",
    "score_applicants",
]
