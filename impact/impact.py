"""Human-impact translation.

Formula, stated explicitly:

    wrongly_rejected_per_10k = max(net_flip_rate, 0) * 10,000

CI bounds are converted identically:
    ci_low_per_10k  = max(ci_low, 0) * 10,000
    ci_high_per_10k = max(ci_high, 0) * 10,000

``net_flip_rate`` is the paired net proportion of applicants who would be
rejected when moved from the comparison group into the target group, holding
all other signals fixed. Multiplying by 10,000 is only a per-10,000 rescaling;
there is no additional multiplier. For intersectional findings this counts
people within that subgroup, not the whole population.
"""

from __future__ import annotations

from schemas import Finding, ImpactEstimate


def impact_per_10k(finding: Finding) -> ImpactEstimate:
    net = max(float(finding.evidence.net_flip_rate), 0.0)
    low = max(float(finding.evidence.ci_low), 0.0)
    high = max(float(finding.evidence.ci_high), 0.0)
    scope = (
        "within this intersectional subgroup"
        if finding.kind == "intersectional"
        else "within the affected group"
    )
    return ImpactEstimate(
        finding_id=finding.id,
        subgroup=finding.attribute_or_subgroup,
        net_flip_rate=net,
        per_10k=round(net * 10_000, 1),
        ci_low_per_10k=round(low * 10_000, 1),
        ci_high_per_10k=round(high * 10_000, 1),
        explanation=(
            f"About {net * 10_000:,.0f} people per 10,000 {scope} would be "
            "wrongly rejected because of the changed signal, holding other "
            "factors fixed. This is evidence of disparate treatment, not proof "
            "of intent."
        ),
    )
