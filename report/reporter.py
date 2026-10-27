"""Narrative reporter.

The LLM receives computed JSON and is asked to rewrite it in plain language. It
never computes. Every number is verified against the JSON; on failure we
regenerate once, then use a deterministic template. If no API key is present we
use the template directly.

The reporter intentionally does NOT receive the full config: planted penalties
are sandbox internals and would undermine the black-box audit. Only audit
thresholds and computed results are sent.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

try:  # optional convenience; the app also works without a .env file
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # noqa: BLE001
    pass

from impact.mitigate import recommend
from report.number_check import check_numbers
from schemas import AuditReport

SYSTEM_PROMPT = """You are writing a fairness audit summary for a non-technical
auditor. Use ONLY numbers that appear in the supplied JSON. Never calculate,
estimate, or introduce a number that is not in the JSON. Say "evidence of",
never "proof of". Do not infer intent. Mention the main limitation that this is
a synthetic black-box probe. Keep it under 250 words. Do not mention or guess
which penalties a model contains."""


def _human_subgroup(finding: dict[str, Any]) -> str:
    if finding["kind"] == "intersectional":
        gender, age, urban = finding["target_group"].split("|")
        age_label = {"<35": "younger", "35-44": "mid-career", "45+": "older"}[age]
        return f"{age_label} {urban} {gender} applicants"
    attribute = finding["attribute_or_subgroup"].split("=", 1)[0]
    value = finding["target_group"]
    if attribute == "gender":
        return f"{value} applicants"
    if attribute == "pincode_group":
        return f"applicants in the {value} pincode group"
    if attribute == "name_group":
        return f"applicants in the {value} name group"
    return f"applicants in the {value} group"


def build_payload(report: AuditReport, events: list[Any] | None = None) -> dict[str, Any]:
    """Computed JSON only. No applicants, responses, or planted penalties."""

    kept = [f for f in report.findings if f.status == "kept"]
    rejected = [f for f in report.findings if f.status == "rejected"]
    immaterial = [f for f in report.findings if f.status == "immaterial"]
    audit_cfg = report.config.get("audit", {})
    impact_by_id = {item.finding_id: item.model_dump(mode="json") for item in report.impact}
    default_budget = float(
        report.config.get("mitigation", {}).get("max_accuracy_loss_default", 0.02)
    )
    payload: dict[str, Any] = {
        "model_id": report.model_id,
        "summary": {
            "total_candidates": len(report.findings),
            "kept": len(kept),
            "rejected": len(rejected),
            "immaterial": len(immaterial),
            "n_pairs": int(audit_cfg.get("n_pairs", 0)),
            "matched_n_pairs": int(audit_cfg.get("matched_n_pairs", 0)),
            "intersectional_cells": len(
                report.observational.get("intersectional_cells", [])
            ),
        },
        "audit": {
            "alpha": float(audit_cfg.get("alpha", 0.05)),
            "materiality": float(audit_cfg.get("materiality", 0.02)),
            "correction": str(audit_cfg.get("correction", "holm")),
            "ci_level": float(audit_cfg.get("ci_level", 0.95)),
            "impact_scale": 10_000,
        },
        "findings": [
            {
                "id": finding.id,
                "kind": finding.kind,
                "attribute_or_subgroup": finding.attribute_or_subgroup,
                "target_group": finding.target_group,
                "status": finding.status,
                "reason": finding.reason,
                "observational_gap": finding.observational_gap,
                "evidence": finding.evidence.model_dump(mode="json"),
                "matched_net_flip_rate": (
                    finding.matched_evidence.net_flip_rate
                    if finding.matched_evidence
                    else None
                ),
            }
            for finding in report.findings
        ],
        "impact": [item.model_dump(mode="json") for item in report.impact],
        "mitigation": {
            "curve": report.mitigation_curve,
            "recommended_default": (
                recommend(report.mitigation_curve, default_budget)
                if report.mitigation_curve
                else None
            ),
            "default_budget": default_budget,
        },
        "limitations": [
            "Synthetic sandbox data; not real Indian lending data.",
            "Twin probing is evidence of disparate treatment, not proof of intent.",
            "Fairness metrics can conflict; no single metric is definitive.",
            "A named human auditor must review before a certificate is issued.",
        ],
    }
    if events is not None:
        payload["event_count"] = len(events)
    return payload


def _word_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


def template_narrative(payload: dict[str, Any], max_words: int = 250) -> str:
    s = payload["summary"]
    a = payload["audit"]
    kept = [f for f in payload["findings"] if f["status"] == "kept"]
    impact_by_id = {i["finding_id"]: i for i in payload["impact"]}
    ci_pct = int(round(a["ci_level"] * 100))
    parts: list[str] = [
        f"FairLens audited model {payload['model_id']} through its API using "
        f"{s['n_pairs']} counterfactual twin pairs per single-attribute test and "
        f"{s['intersectional_cells']} intersectional cells."
    ]
    if kept:
        parts.append(
            f"The Skeptic kept {s['kept']} of {s['total_candidates']} candidate findings "
            "after correction, materiality, symmetry, and income-matched checks."
        )
        for finding in kept[:2]:
            evidence = finding["evidence"]
            impact = impact_by_id.get(finding["id"], {})
            per_10k = float(impact.get("per_10k", 0.0))
            parts.append(
                f"For {_human_subgroup(finding)}, the net flip rate was "
                f"{evidence['net_flip_rate']:.4f}, with a {ci_pct}% interval from "
                f"{evidence['ci_low']:.4f} to {evidence['ci_high']:.4f} "
                f"(adjusted p {evidence['p_adjusted']:.2e}). That corresponds to about "
                f"{per_10k:.0f} people per {a['impact_scale']:,} in the affected group."
            )
    else:
        parts.append(
            f"The Skeptic kept none of the {s['total_candidates']} candidate findings. "
            "An observational gap was not treated as bias without counterfactual evidence."
        )
    parts.append(
        f"{s['rejected']} candidates were rejected and {s['immaterial']} were "
        "significant but immaterial; every candidate remains in the report."
    )
    parts.append(
        f"Thresholds were fixed before the audit: alpha {a['alpha']}, materiality "
        f"{a['materiality']}, and Holm correction. This is evidence of disparate "
        "treatment in a synthetic sandbox, not proof of intent or a claim about a real "
        "lender. Synthetic twins are approximations, fairness metrics can conflict, and "
        "results may not generalize. A named human auditor must approve before any "
        "certificate is issued."
    )
    text = " ".join(parts)
    if _word_count(text) > max_words:
        # Drop the per-finding detail sentences first; never drop the headline,
        # the rejected/immaterial disclosure, or the limitations paragraph.
        detail_positions = [
            index for index, part in enumerate(parts) if part.startswith("For ")
        ]
        for position in reversed(detail_positions):
            if _word_count(" ".join(parts)) <= max_words:
                break
            parts.pop(position)
        text = " ".join(parts)
    return text


def _call_anthropic(payload: dict[str, Any], extra_instruction: str = "") -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("no ANTHROPIC_API_KEY")
    from anthropic import Anthropic

    model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514").strip()
    client = Anthropic(api_key=api_key, timeout=25.0)
    prompt = (
        "Rewrite this computed audit JSON for a non-technical auditor. Use ONLY the "
        "numbers in the JSON. State limitations. Under 250 words.\n\n"
        + json.dumps(payload, indent=2, ensure_ascii=False)
        + ("\n\n" + extra_instruction if extra_instruction else "")
    )
    message = client.messages.create(
        model=model,
        max_tokens=700,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    chunks = [
        block.text
        for block in getattr(message, "content", [])
        if getattr(block, "type", None) == "text"
    ]
    text = "".join(chunks).strip()
    if not text:
        raise RuntimeError("empty LLM response")
    return text


def generate_narrative(payload: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """Return {narrative, source, error?, number_check} with fallback."""

    max_words = int(config.get("report", {}).get("max_words", 250))
    fallback = template_narrative(payload, max_words=max_words)
    fallback_check = check_numbers(fallback, payload)
    if not fallback_check["passed"]:
        # A template failure is a programming error; surface it rather than lying.
        raise RuntimeError(
            f"Template narrative failed number check: {fallback_check['unknown']}"
        )

    if not os.getenv("ANTHROPIC_API_KEY", "").strip():
        return {
            "narrative": fallback,
            "source": "template",
            "number_check": fallback_check,
            "error": None,
        }

    unknown: list[str] = []
    try:
        for attempt in range(2):
            extra = ""
            if attempt == 1:
                extra = (
                    "Your previous draft used numbers not present in the JSON: "
                    f"{unknown}. Rewrite without them. Copy numbers exactly from the JSON."
                )
            text = _call_anthropic(payload, extra)
            check = check_numbers(text, payload)
            if check["passed"] and _word_count(text) <= max_words:
                return {
                    "narrative": text,
                    "source": "anthropic",
                    "number_check": check,
                    "error": None,
                }
            unknown = check["unknown"]
            if _word_count(text) > max_words:
                unknown = unknown + [f"word_count>{max_words}"]
        return {
            "narrative": fallback,
            "source": "template_fallback",
            "number_check": fallback_check,
            "error": f"LLM output failed verification twice: {unknown}",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "narrative": fallback,
            "source": "template_fallback",
            "number_check": fallback_check,
            "error": f"{type(exc).__name__}: {exc}",
        }
