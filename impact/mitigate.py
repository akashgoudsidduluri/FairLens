"""Post-processing mitigation: group-wise score offsets.

The sandbox score is treated as a black-box output. For the affected segment we
add an offset to the RETURNED score and re-apply the same configured approval
threshold. We sweep offsets and record:

    segment approval rate, comparison approval rate
    fairness_gap = abs(segment_rate - comparison_rate)
    accuracy = share of adjusted decisions matching hidden true_repay
    accuracy_loss = base_accuracy - accuracy   (positive = worse)

The recommendation is the point with the smallest fairness gap among offsets
whose accuracy loss is within the user's budget, breaking ties toward the
smaller offset. Nothing is tuned based on audit findings; the offset grid and
default budget come from config.yaml.

For rare intersectional segments (<5% of a natural sample) the curve uses a
stratified sample: 1,000 segment applicants and up to 2,000 natural
non-segment applicants. The fairness gap is therefore a segment-vs-comparison
gap, not a population-prevalence-weighted gap. This is stated in the curve
metadata.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from auditor.prober import Prober
from config_loader import load_config
from sandbox.generator import generate_applicants, generate_segment
from schemas import Applicant


def _matches(applicant: Applicant, segment: dict[str, str]) -> bool:
    return all(getattr(applicant, key) == value for key, value in segment.items())


def _validate_segment(segment: dict[str, str]) -> None:
    allowed = {"gender", "pincode_group", "name_group", "age_band", "urban_rural"}
    if not segment:
        raise ValueError("segment cannot be empty")
    unknown = set(segment) - allowed
    if unknown:
        raise ValueError(f"unsupported segment keys: {unknown}")


def _build_sample(
    segment: dict[str, str], config: dict[str, Any], seed: int
) -> tuple[list[Applicant], list[bool], dict[str, Any]]:
    n = int(config["mitigation"]["n_samples"])
    applicants, labels = generate_applicants(n, seed=seed)
    segment_count = sum(1 for a in applicants if _matches(a, segment))
    share = segment_count / len(applicants)
    metadata: dict[str, Any] = {
        "sampling": "natural population",
        "segment_share": share,
        "sample_n": len(applicants),
    }
    if share < 0.05:
        seg_apps, seg_labels = generate_segment(1000, seed=seed + 1, **segment)
        comparison = [
            (a, y) for a, y in zip(applicants, labels) if not _matches(a, segment)
        ][:2000]
        applicants = list(seg_apps) + [a for a, _ in comparison]
        labels = list(seg_labels) + [y for _, y in comparison]
        metadata = {
            "sampling": "stratified (rare segment): 1000 segment + natural comparison",
            "segment_share": len(seg_apps) / len(applicants),
            "sample_n": len(applicants),
        }
    return applicants, labels, metadata


def build_curve(
    model_id: int,
    api_url: str,
    segment: dict[str, str],
    config: dict[str, Any],
    seed: int = 42,
) -> list[dict[str, Any]]:
    """Sweep offsets and return curve points; first point is offset 0."""

    _validate_segment(segment)
    applicants, labels, metadata = _build_sample(segment, config, seed)
    prober = Prober(api_url, config)
    responses = prober.score_many_sync(model_id, applicants)
    base_scores = np.array([r.score for r in responses], dtype=float)
    base_approved = np.array([r.approved for r in responses], dtype=bool)
    truth = np.array(labels, dtype=bool)
    is_segment = np.array([_matches(a, segment) for a in applicants], dtype=bool)
    if is_segment.sum() == 0 or (~is_segment).sum() == 0:
        raise ValueError("segment or comparison group is empty after sampling")

    threshold = float(config["models"]["approval_threshold"])
    m = config["mitigation"]
    offsets = list(
        range(int(m["offset_min"]), int(m["offset_max"]) + 1, int(m["offset_step"]))
    )
    base_accuracy = float(np.mean(base_approved == truth))
    curve: list[dict[str, Any]] = []
    for offset in offsets:
        adjusted_score = base_scores + np.where(is_segment, float(offset), 0.0)
        approved = adjusted_score >= threshold
        segment_rate = float(np.mean(approved[is_segment]))
        comparison_rate = float(np.mean(approved[~is_segment]))
        accuracy = float(np.mean(approved == truth))
        curve.append(
            {
                "offset": int(offset),
                "segment_approval_rate": round(segment_rate, 4),
                "comparison_approval_rate": round(comparison_rate, 4),
                "fairness_gap": round(abs(segment_rate - comparison_rate), 4),
                "signed_gap": round(comparison_rate - segment_rate, 4),
                "accuracy": round(accuracy, 4),
                "accuracy_loss": round(base_accuracy - accuracy, 4),
                "segment_n": int(is_segment.sum()),
                "comparison_n": int((~is_segment).sum()),
                "base_accuracy": round(base_accuracy, 4),
                "sampling": metadata["sampling"],
                "segment_share": round(float(metadata["segment_share"]), 4),
            }
        )
    return curve


def recommend(
    curve: list[dict[str, Any]], max_accuracy_loss: float
) -> dict[str, Any] | None:
    """Smallest gap subject to the accuracy-loss budget; tie -> smaller offset."""

    if not curve:
        return None
    eligible = [p for p in curve if p["accuracy_loss"] <= max_accuracy_loss + 1e-12]
    pool = eligible or [curve[0]]
    best = min(pool, key=lambda p: (p["fairness_gap"], p["offset"]))
    return {
        **best,
        "max_accuracy_loss": float(max_accuracy_loss),
        "eligible_points": len(eligible),
        "rationale": (
            "Smallest fairness gap among offsets whose accuracy loss is within "
            f"the {max_accuracy_loss:.1%} budget; ties go to the smaller offset."
        ),
    }


def default_curve_config() -> dict[str, Any]:
    """Convenience for scripts that do not already have a config dict."""

    return load_config()
