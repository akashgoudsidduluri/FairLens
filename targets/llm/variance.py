"""Run-to-run variance for the R3c LLM screener.

A pair is flipped only on the majority outcome, but the repeats still contain
information: a pair whose repeats disagree is less trustworthy than a unanimous
one. These functions report that separately from the b/c flip count.

Definitions
-----------
- Repeat flip indicator: for one repeat slot, 1 if the original and twin
  decisions differ, 0 if they agree, ``None`` if either side did not parse.
- Pair variance: the sample variance (denominator n-1) of the pair's non-null
  flip indicators. This is 0 for unanimity and rises with disagreement.
- Applicant disagreement: ``1 - max(approve_count, reject_count) / valid_n`` for
  one applicant's repeats. 0 is unanimous, 1 is an even split.
"""

from __future__ import annotations

from statistics import mean

from targets.llm.adapter import ScreenResult


def pair_flip_series(
    original: ScreenResult, twin: ScreenResult
) -> list[bool | None]:
    length = max(len(original.approvals), len(twin.approvals))
    series: list[bool | None] = []
    for index in range(length):
        left = original.approvals[index] if index < len(original.approvals) else None
        right = twin.approvals[index] if index < len(twin.approvals) else None
        if left is None or right is None:
            series.append(None)
        else:
            series.append(bool(left) != bool(right))
    return series


def pair_variance(series: list[bool | None]) -> float | None:
    values = [1.0 if value else 0.0 for value in series if value is not None]
    if len(values) < 2:
        return None
    average = mean(values)
    return sum((value - average) ** 2 for value in values) / (len(values) - 1)


def applicant_disagreement(result: ScreenResult) -> float | None:
    valid = [value for value in result.approvals if value is not None]
    if not valid:
        return None
    approvals = sum(1 for value in valid if value)
    majority = max(approvals, len(valid) - approvals)
    return 1.0 - majority / len(valid)


def summarize_variance(pairs: list[tuple[ScreenResult, ScreenResult]]) -> dict:
    pair_variances: list[float] = []
    flip_rates: list[float] = []
    mixed_pairs = 0
    unresolved = 0
    disagreements: list[float] = []

    for original, twin in pairs:
        series = pair_flip_series(original, twin)
        valid = [value for value in series if value is not None]
        if not valid:
            unresolved += 1
            continue
        variance = pair_variance(series)
        if variance is not None:
            pair_variances.append(variance)
        rate = sum(1 for value in valid if value) / len(valid)
        flip_rates.append(rate)
        if any(valid) and not all(valid):
            mixed_pairs += 1
        for result in (original, twin):
            value = applicant_disagreement(result)
            if value is not None:
                disagreements.append(value)

    return {
        "pairs": len(pairs),
        "pairs_scored": len(flip_rates),
        "unresolved_pairs": unresolved,
        "mean_pair_variance": mean(pair_variances) if pair_variances else None,
        "max_pair_variance": max(pair_variances) if pair_variances else None,
        "pairs_with_repeat_disagreement": mixed_pairs,
        "share_pairs_with_repeat_disagreement": (
            mixed_pairs / len(flip_rates) if flip_rates else None
        ),
        "mean_applicant_disagreement": mean(disagreements) if disagreements else None,
        "mean_repeat_flip_rate": mean(flip_rates) if flip_rates else None,
    }
