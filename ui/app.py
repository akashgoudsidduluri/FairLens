"""FairLens India — single-page fairness auditor dashboard.

Run from the repository root::

    .venv\\Scripts\\streamlit run ui/app.py

The page streams agent events while an audit runs, shows kept and rejected
findings, an intersectional heatmap, human impact, a mitigation trade-off
slider, the number-checked narrative, and the human sign-off + Audit Record
verification flow.
"""

from __future__ import annotations

import html
import os
import sys
from pathlib import Path
from typing import Any, Iterable, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from auditor.pipeline import run_audit
from config_loader import load_config
from impact.mitigate import recommend
from schemas import AgentEvent, AuditReport
from trust.certificate import (
    build_certificate_payload,
    fresh_demo_db,
    init_db,
    issue,
    list_records,
    tamper_for_demo,
    verify,
)
from ui import components as ui_components
from ui.plotting import PLOTLY_CONFIG, heatmap_figure, mitigation_figure

CONFIG = load_config()
DB_PATH = CONFIG["certificate"]["db_path"]


def _default_api_url() -> str:
    """Launcher-provided URL, falling back to the frozen config default.

    run.ps1 / run.sh export the port they actually started the sandbox on.
    Without this the dashboard would keep pointing at 8010 when the launcher
    used another port, and the advertised FAIRLENS_API_PORT override would fail.
    """

    return os.environ.get("FAIRLENS_API_URL") or str(CONFIG["api"]["base_url"])


init_db(DB_PATH)

DEMO_MODELS = (2, 7, 5)
AUDIT_AGENTS = ("planner", "prober", "statistician", "skeptic", "impact", "reporter")

st.set_page_config(
    page_title="FairLens India",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

_CSS = (ROOT / "ui" / "style.css").read_text(encoding="utf-8")
st.markdown(f"<style>{_CSS}</style>", unsafe_allow_html=True)


def _init_state() -> None:
    defaults: dict[str, Any] = {
        "events": [],
        "report": None,
        "last_cert": None,
        "audit_error": None,
        "running": False,
        "signoff_notice": None,
        "cert_notice": None,
        "verify_state": None,
        "demo_reports": {},
        "demo_summary": [],
        "demo_events": {},
        "approver_name": "",
        "confirm_tamper": False,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


_init_state()


# --------------------------------------------------------------------------- helpers
def _pct(value: float, digits: int = 2, signed: bool = False) -> str:
    try:
        number = float(value) * 100.0
    except (TypeError, ValueError):
        return "—"
    sign = "+" if signed and number > 0 else ""
    return f"{sign}{number:.{digits}f}%"


def _pval(value: float | None) -> str:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "—"
    if number == 0:
        return "0"
    return f"{number:.1e}" if number < 0.001 else f"{number:.4f}"


def _section_head(title: str, kicker: str = "") -> str:
    kicker_html = (
        f'<span class="fl-kicker">{html.escape(kicker)}</span>' if kicker else ""
    )
    return (
        f'<div class="fl-section-head"><h2>{html.escape(title)}</h2>'
        f"{kicker_html}</div>"
    )


def _section_sub(title: str) -> str:
    return f'<div class="fl-section-sub">{html.escape(title)}</div>'


def _set_notice(bucket: str, level: str, message: str) -> None:
    st.session_state[bucket] = {"level": level, "message": message}


def _render_notice(notice: dict[str, Any] | None) -> None:
    if not notice:
        return
    level = str(notice.get("level", "info"))
    message = str(notice.get("message", ""))
    if level == "success":
        st.success(message)
    elif level == "warning":
        st.warning(message)
    elif level == "error":
        st.error(message)
    else:
        st.info(message)


def _pipeline_state(
    events: Sequence[AgentEvent],
    report: AuditReport | None,
    running: bool,
    error: str | None,
    last_cert: Any,
) -> dict[str, str]:
    """Derive pipeline status from the events seen so far."""

    seen = {getattr(event, "agent", "") for event in events}
    state: dict[str, str] = {}
    first_missing: str | None = None
    for key in AUDIT_AGENTS:
        if key in seen:
            state[key] = "done"
        elif first_missing is None:
            first_missing = key

    if running and first_missing is not None:
        state[first_missing] = "active"

    if error:
        last_agent = getattr(events[-1], "agent", None) if events else None
        if last_agent in AUDIT_AGENTS:
            state[last_agent] = "failed"
        elif first_missing is not None:
            state[first_missing] = "failed"

    if report is not None and not error:
        for key in AUDIT_AGENTS:
            state[key] = "done"

    if last_cert is not None:
        state["signoff"] = "done"
    elif report is not None:
        state["signoff"] = "active"
    else:
        state["signoff"] = "pending"
    return state


def _render_log(placeholder: Any, events: Iterable[AgentEvent], running: bool) -> None:
    placeholder.markdown(
        ui_components.log_feed(events, running=running), unsafe_allow_html=True
    )


def _demo_summary_html(rows: Sequence[dict[str, Any]]) -> str:
    cards: list[str] = []
    for row in rows:
        kept = int(row.get("kept", 0))
        if kept:
            value = f"{kept} kept"
            meta = f"{row.get('rejected', 0)} rejected · {row.get('immaterial', 0)} immaterial"
        else:
            value = "0 kept"
            meta = "no finding survived the Skeptic"
        cards.append(
            '<div class="fl-demo-card">'
            f'<div class="fl-demo-card__model">Model {int(row.get("model_id", 0))}</div>'
            f'<div class="fl-demo-card__value">{value}</div>'
            f'<div class="fl-demo-card__meta">{html.escape(str(meta))}</div>'
            "</div>"
        )
    return '<div class="fl-demo-summary">' + "".join(cards) + "</div>"


def _impact_rows_html(estimates: Sequence[Any]) -> str:
    rows: list[str] = []
    for estimate in estimates:
        rows.append(
            '<div class="fl-impact-row">'
            "<div>"
            f"<b>{html.escape(str(estimate.subgroup))}</b>"
            f"<span>95% range {estimate.ci_low_per_10k:,.0f}–{estimate.ci_high_per_10k:,.0f} "
            "per 10,000</span>"
            "</div>"
            f'<div class="fl-impact-row__value">~{estimate.per_10k:,.0f}'
            "<span>per 10,000</span></div>"
            "</div>"
        )
    return '<div class="fl-impact-list">' + "".join(rows) + "</div>"


def _certificate_card(cert: Any) -> str:
    payload = cert.payload
    decision = str(payload.get("decision", "—")).upper()
    return (
        '<div class="fl-cert-card">'
        f"<h4>Audit Record #{cert.index} · Model {html.escape(str(payload.get('model_id', '—')))}</h4>"
        f"<p><b>{html.escape(decision)}</b> by {html.escape(str(payload.get('approver', '—')))}</p>"
        f"<p>{html.escape(str(payload.get('timestamp', '—')))}</p>"
        f'<p class="fl-hash">record_hash: {html.escape(cert.record_hash)}</p>'
        f'<p class="fl-hash">prev_hash: {html.escape(cert.prev_hash)}</p>'
        "</div>"
    )


def _cell_table(cells: Sequence[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Gender": cell.get("target_gender"),
                "Age": cell.get("age_band"),
                "Location": cell.get("urban_rural"),
                "n": cell.get("n"),
                "b": cell.get("b"),
                "c": cell.get("c"),
                "Net flip": _pct(cell.get("net_flip_rate", 0.0)),
                "Adj. p": _pval(cell.get("p_adjusted")),
            }
            for cell in cells
        ]
    )


def _mitigation_table(curve: Sequence[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Offset": point["offset"],
                "Segment approval": _pct(point["segment_approval_rate"]),
                "Comparison approval": _pct(point["comparison_approval_rate"]),
                "Fairness gap": _pct(point["fairness_gap"]),
                "Accuracy": _pct(point["accuracy"]),
                "Accuracy loss": _pct(point["accuracy_loss"]),
            }
            for point in curve
        ]
    )


# --------------------------------------------------------------------------- callbacks
def _approve() -> None:
    report: AuditReport | None = st.session_state.get("report")
    name = str(st.session_state.get("approver_name", "") or "").strip()
    if report is None:
        _set_notice("signoff_notice", "error", "Run an audit before signing off.")
        return
    if not name:
        _set_notice(
            "signoff_notice",
            "error",
            "Enter the approver's name before issuing or rejecting.",
        )
        return
    try:
        payload = build_certificate_payload(report, report.config, name, "approve")
        certificate = issue(payload, name, "approve", DB_PATH)
    except Exception as exc:  # noqa: BLE001
        _set_notice(
            "signoff_notice",
            "error",
            f"Audit Record could not be issued: {exc}",
        )
        return
    st.session_state.last_cert = certificate
    st.session_state.verify_state = None
    _set_notice(
        "signoff_notice",
        "success",
        f"Audit Record #{certificate.index} issued for Model {report.model_id} by {name}.",
    )


def _reject() -> None:
    report: AuditReport | None = st.session_state.get("report")
    name = str(st.session_state.get("approver_name", "") or "").strip()
    if report is None:
        _set_notice("signoff_notice", "error", "Run an audit before signing off.")
        return
    if not name:
        _set_notice(
            "signoff_notice",
            "error",
            "Enter the approver's name before issuing or rejecting.",
        )
        return
    try:
        payload = build_certificate_payload(report, report.config, name, "reject")
        certificate = issue(payload, name, "reject", DB_PATH)
    except Exception as exc:  # noqa: BLE001
        _set_notice("signoff_notice", "error", f"Decision could not be logged: {exc}")
        return
    st.session_state.last_cert = certificate
    st.session_state.verify_state = None
    _set_notice(
        "signoff_notice",
        "warning",
        f"Rejection logged as Audit Record #{certificate.index}. "
        "No approval record was issued.",
    )


def _verify_chain() -> None:
    if not list_records(DB_PATH):
        st.session_state.verify_state = {"ok": None, "broken": None}
        _set_notice(
            "cert_notice",
            "warning",
            "There are no audit records to verify yet.",
        )
        return
    ok, broken = verify(DB_PATH)
    st.session_state.verify_state = {"ok": ok, "broken": broken}
    if ok:
        _set_notice(
            "cert_notice",
            "success",
            "Chain verified: every record hash and link is intact.",
        )
    else:
        _set_notice(
            "cert_notice",
            "error",
            f"Verification FAILED at record #{broken}. The chain was modified.",
        )


def _tamper() -> None:
    if not st.session_state.get("confirm_tamper"):
        _set_notice("cert_notice", "warning", "Tick the confirmation box first.")
        return
    records = list_records(DB_PATH)
    if not records:
        _set_notice("cert_notice", "warning", "There is no audit record to tamper with.")
        return
    result = tamper_for_demo(records[-1].index, DB_PATH)
    ok, broken = verify(DB_PATH)
    st.session_state.verify_state = {"ok": ok, "broken": broken}
    _set_notice(
        "cert_notice",
        "warning",
        f"Tampered field '{result['field']}' at record #{result['index']}. "
        f"Verification now returns ok={ok}, first broken record={broken}.",
    )


def _reset_demo_db() -> None:
    fresh_demo_db(DB_PATH)
    st.session_state.last_cert = None
    st.session_state.verify_state = None
    _set_notice(
        "cert_notice",
        "success",
        "Audit Record database reset for a fresh demo.",
    )


def _open_demo_report() -> None:
    reports: dict[int, AuditReport] = st.session_state.get("demo_reports") or {}
    selected = st.session_state.get("demo_inspect")
    try:
        selected = int(selected)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return
    report = reports.get(selected)
    if report is None:
        _set_notice("signoff_notice", "error", "That demo result is not available.")
        return
    st.session_state.report = report
    st.session_state.last_cert = None
    st.session_state.audit_error = None
    st.session_state.signoff_notice = None
    # Keep the log and pipeline consistent with the report being inspected;
    # otherwise they would still describe the last model in the demo run.
    st.session_state.events = list(
        (st.session_state.get("demo_events") or {}).get(selected, [])
    )
    st.session_state.running = False


# --------------------------------------------------------------------------- audit runner
def _run_audit_models(
    model_ids: Sequence[int],
    api_url: str,
    pipeline_placeholder: Any,
    log_placeholder: Any,
    *,
    demo: bool = False,
) -> None:
    st.session_state.running = True
    st.session_state.audit_error = None
    display_events: list[AgentEvent] = []
    reports: list[tuple[int, AuditReport]] = []
    per_model_events: dict[int, list[AgentEvent]] = {}
    error_message: str | None = None

    for position, model_id in enumerate(model_ids):
        current_events: list[AgentEvent] = []
        if demo:
            banner = AgentEvent(
                agent="system",
                message=(
                    f"Demo run {position + 1}/{len(model_ids)} · "
                    f"Model {model_id} · seed {CONFIG['seed']}"
                ),
            )
            display_events.append(banner)
            current_events.append(banner)
        report: AuditReport | None = None
        error: Exception | None = None
        try:
            generator = run_audit(
                model_id,
                api_url,
                CONFIG,
                seed=CONFIG["seed"],
            )
            while True:
                try:
                    event = next(generator)
                except StopIteration as stop:
                    report = stop.value
                    break
                current_events.append(event)
                display_events.append(event)
                st.session_state.events = list(display_events)
                pipeline_placeholder.markdown(
                    ui_components.pipeline_strip(
                        _pipeline_state(
                            current_events,
                            None,
                            True,
                            None,
                            st.session_state.last_cert,
                        )
                    ),
                    unsafe_allow_html=True,
                )
                _render_log(log_placeholder, display_events, True)
        except Exception as exc:  # noqa: BLE001
            error = exc
            error_message = f"{type(exc).__name__}: {exc}"

        if report is not None:
            reports.append((model_id, report))
            per_model_events[model_id] = list(current_events)
            st.session_state.report = report
            pipeline_placeholder.markdown(
                ui_components.pipeline_strip(
                    _pipeline_state(
                        current_events,
                        report,
                        False,
                        None,
                        st.session_state.last_cert,
                    )
                ),
                unsafe_allow_html=True,
            )
            _render_log(log_placeholder, display_events, False)
        else:
            pipeline_placeholder.markdown(
                ui_components.pipeline_strip(
                    _pipeline_state(
                        current_events,
                        None,
                        False,
                        error_message,
                        st.session_state.last_cert,
                    )
                ),
                unsafe_allow_html=True,
            )
            _render_log(log_placeholder, display_events, False)
            break

    st.session_state.running = False
    st.session_state.events = list(display_events)
    if error_message:
        st.session_state.audit_error = error_message
    if reports:
        st.session_state.report = reports[-1][1]
    if demo:
        st.session_state.demo_reports = {model: report for model, report in reports}
        st.session_state.demo_events = per_model_events
        st.session_state.demo_summary = [
            {
                "model_id": model,
                "kept": sum(1 for finding in report.findings if finding.status == "kept"),
                "rejected": sum(
                    1 for finding in report.findings if finding.status == "rejected"
                ),
                "immaterial": sum(
                    1 for finding in report.findings if finding.status == "immaterial"
                ),
            }
            for model, report in reports
        ]


# --------------------------------------------------------------------------- page
st.markdown(
    """
    <div class="fl-hero">
      <div class="fl-hero__inner">
        <div>
          <div class="fl-eyebrow">Black-box fairness audit · synthetic lending</div>
          <h1>Fair<span>Lens</span> India</h1>
          <p class="fl-hero__sub">
            An agentic auditor that probes a lending model with counterfactual twins,
            challenges its own findings, translates them into human impact, and asks a
            named human to sign a tamper-evident Audit Record.
          </p>
          <div class="fl-chips">
            <span class="fl-chip">HTTP twin probes</span>
            <span class="fl-chip">rule-based Skeptic</span>
            <span class="fl-chip">Holm correction</span>
            <span class="fl-chip">human approval required</span>
          </div>
        </div>
        <div class="fl-hero__stats">
          <div class="fl-hero__stat"><b>7</b><span>models</span></div>
          <div class="fl-hero__stat"><b>2,000</b><span>twins / attribute</span></div>
          <div class="fl-hero__stat"><b>0.05</b><span>pre-registered α</span></div>
        </div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.container(border=True):
    control_model, control_start, control_demo = st.columns([1.45, 1, 1])
    with control_model:
        model_id = st.selectbox(
            "Model under audit",
            options=list(range(1, 8)),
            index=1,
            format_func=lambda number: f"Model {number}",
            key="model_id",
        )
    with control_start:
        st.markdown('<div class="fl-sr-only">Start an audit</div>', unsafe_allow_html=True)
        start_clicked = st.button("Start Audit", type="primary", width="stretch")
    with control_demo:
        st.markdown('<div class="fl-sr-only">Run the demo</div>', unsafe_allow_html=True)
        demo_clicked = st.button("Demo mode", width="stretch")

st.markdown(
    '<div class="fl-caption">Demo order: <b>Model 2 → Model 7 → Model 5</b>. '
    "The selector never reveals which model is biased. "
    "Synthetic data only; evidence of disparate treatment, not proof of intent.</div>",
    unsafe_allow_html=True,
)

with st.expander("Audit protocol and connection", expanded=False):
    api_url = st.text_input(
        "Sandbox API URL",
        value=_default_api_url(),
        key="api_url",
    )
    st.markdown(
        f"""
        <div class="fl-caption">
        Pre-registered before the first audit: α = {CONFIG['audit']['alpha']},
        materiality = {CONFIG['audit']['materiality']}, Holm correction over the
        single-attribute family, {CONFIG['audit']['n_pairs']:,} natural twins per
        attribute, {CONFIG['audit']['intersectional_pairs_per_cell']:,} per
        intersectional cell, {CONFIG['audit']['bootstrap_iterations']:,} bootstrap
        iterations. Thresholds are frozen in <code>config.yaml</code>; misses and
        false alarms are reported honestly.
        </div>
        """,
        unsafe_allow_html=True,
    )

if start_clicked or demo_clicked:
    st.session_state.events = []
    st.session_state.report = None
    st.session_state.last_cert = None
    st.session_state.audit_error = None
    st.session_state.running = True
    st.session_state.signoff_notice = None
    st.session_state.cert_notice = None
    st.session_state.verify_state = None
    st.session_state.demo_reports = {}
    st.session_state.demo_summary = []
    st.session_state.demo_events = {}

audit_tab, certificate_tab = st.tabs(["Audit", "Audit Records"])

with audit_tab:
    st.markdown(_section_head("Agent pipeline", "live execution"), unsafe_allow_html=True)
    pipeline_placeholder = st.empty()
    pipeline_placeholder.markdown(
        ui_components.pipeline_strip(
            _pipeline_state(
                st.session_state.events,
                st.session_state.report,
                bool(st.session_state.running),
                st.session_state.audit_error,
                st.session_state.last_cert,
            )
        ),
        unsafe_allow_html=True,
    )

    st.markdown(_section_head("Live agent log", "streamed over HTTP"), unsafe_allow_html=True)
    log_placeholder = st.empty()
    _render_log(
        log_placeholder,
        st.session_state.events,
        bool(st.session_state.running),
    )

    if start_clicked:
        _run_audit_models(
            [int(model_id)],
            str(api_url),
            pipeline_placeholder,
            log_placeholder,
        )
    elif demo_clicked:
        _run_audit_models(
            list(DEMO_MODELS),
            str(api_url),
            pipeline_placeholder,
            log_placeholder,
            demo=True,
        )

    if st.session_state.demo_summary:
        st.markdown(
            _section_head("Demo run", "2 → 7 → 5"), unsafe_allow_html=True
        )
        st.markdown(
            _demo_summary_html(st.session_state.demo_summary),
            unsafe_allow_html=True,
        )
        reports: dict[int, AuditReport] = st.session_state.demo_reports or {}
        if reports:
            inspect_col, open_col = st.columns([2, 1])
            with inspect_col:
                st.selectbox(
                    "Inspect a demo result",
                    options=sorted(reports),
                    format_func=lambda number: (
                        f"Model {number} · "
                        f"{sum(1 for f in reports[number].findings if f.status == 'kept')} kept"
                    ),
                    key="demo_inspect",
                )
            with open_col:
                st.markdown(
                    '<div class="fl-sr-only">Open the selected demo result</div>',
                    unsafe_allow_html=True,
                )
                st.button(
                    "Open demo result",
                    width="stretch",
                    on_click=_open_demo_report,
                )

    if st.session_state.audit_error:
        st.error(f"Audit could not run: {st.session_state.audit_error}")
        st.info(
            "Check the API URL and start the sandbox (see run.ps1 or run.sh). "
            "The auditor handles unreachable or invalid URLs without crashing."
        )

    report: AuditReport | None = st.session_state.report
    if report is None:
        if st.session_state.running:
            st.markdown(
                ui_components.empty_state(
                    "Audit in progress",
                    "The auditor is probing the sandbox and the findings board will "
                    "appear when the report is ready. Watch the pipeline and log above.",
                    icon="◌",
                ),
                unsafe_allow_html=True,
            )
        elif not st.session_state.audit_error:
            st.markdown(
                ui_components.empty_state(
                    "No report yet",
                    "Choose a model and press Start Audit, or run the three-model demo. "
                    "The log and pipeline update while the auditor works.",
                    icon="◎",
                ),
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                ui_components.empty_state(
                    "No report to show",
                    "The audit stopped before a report was produced. The error above "
                    "explains what failed; the previous report was cleared.",
                    icon="!",
                ),
                unsafe_allow_html=True,
            )
    else:
        kept = [finding for finding in report.findings if finding.status == "kept"]
        rejected = [finding for finding in report.findings if finding.status == "rejected"]
        immaterial = [
            finding for finding in report.findings if finding.status == "immaterial"
        ]

        st.markdown(
            _section_head(
                f"Audit of Model {report.model_id}",
                f"{report.config['audit']['correction'].upper()} · α {report.config['audit']['alpha']} · "
                f"materiality {report.config['audit']['materiality']}",
            ),
            unsafe_allow_html=True,
        )
        metric_kept, metric_rejected, metric_immaterial, metric_impact = st.columns(4)
        metric_kept.metric("Kept findings", len(kept))
        metric_rejected.metric("Rejected", len(rejected))
        metric_immaterial.metric("Significant but immaterial", len(immaterial))
        if report.impact:
            top_impact = max(report.impact, key=lambda estimate: estimate.per_10k)
            metric_impact.metric(
                "Largest impact",
                f"~{top_impact.per_10k:,.0f}",
                "per 10,000",
            )
        else:
            metric_impact.metric("Largest impact", "0", "per 10,000")

        st.markdown(
            _section_head("Findings board", "kept vs challenged"), unsafe_allow_html=True
        )
        if kept:
            st.markdown(
                '<div class="fl-findings-grid">'
                + "".join(ui_components.finding_card(finding) for finding in kept)
                + "</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                ui_components.empty_state(
                    "No finding survived the Skeptic",
                    "This model produced no counterfactual finding that passed "
                    "significance, materiality, direction, and the income-matched re-test. "
                    "Observational gaps alone are not treated as bias.",
                    icon="✓",
                ),
                unsafe_allow_html=True,
            )

        if rejected or immaterial:
            st.markdown(
                _section_sub(
                    f"Challenged and not certified ({len(rejected) + len(immaterial)})"
                ),
                unsafe_allow_html=True,
            )
            st.markdown(
                '<div class="fl-findings-grid">'
                + "".join(
                    ui_components.finding_card(finding)
                    for finding in rejected + immaterial
                )
                + "</div>",
                unsafe_allow_html=True,
            )

        st.markdown(
            _section_head("Intersectional scan", "where harm hides"),
            unsafe_allow_html=True,
        )
        cells = report.observational.get("intersectional_cells", [])
        if cells:
            heat_gender = st.radio(
                "Cell gender",
                options=["female", "male"],
                horizontal=True,
                key="heat_gender",
            )
            try:
                st.plotly_chart(
                    heatmap_figure(cells, heat_gender),
                    width="stretch",
                    theme=None,
                    config=PLOTLY_CONFIG,
                )
            except Exception as exc:  # noqa: BLE001
                st.warning(f"Heatmap unavailable ({exc}); showing the cell table.")
            with st.expander("Cell table (fallback)", expanded=False):
                st.dataframe(
                    _cell_table(cells),
                    hide_index=True,
                    width="stretch",
                )
        else:
            st.markdown(
                ui_components.empty_state(
                    "No intersectional cells",
                    "This report does not contain cell-level results.",
                    icon="▦",
                ),
                unsafe_allow_html=True,
            )

        st.markdown(
            _section_head("Human impact", "people per 10,000"),
            unsafe_allow_html=True,
        )
        if report.impact:
            top_impact = max(report.impact, key=lambda estimate: estimate.per_10k)
            components.html(
                ui_components.impact_counter(
                    top_impact.per_10k,
                    label=f"people per 10,000 · {top_impact.subgroup}",
                    sublabel=(
                        f"95% range {top_impact.ci_low_per_10k:,.0f}–"
                        f"{top_impact.ci_high_per_10k:,.0f} per 10,000"
                    ),
                ),
                height=170,
                scrolling=False,
            )
            st.markdown(
                f'<p class="fl-caption">{html.escape(top_impact.explanation)}</p>',
                unsafe_allow_html=True,
            )
            if len(report.impact) > 1:
                st.markdown(
                    _impact_rows_html(report.impact[1:]),
                    unsafe_allow_html=True,
                )
            st.markdown(
                '<div class="fl-caption">Formula: max(net flip rate, 0) × 10,000. '
                "No additional multipliers. For intersectional findings this is "
                "within the affected subgroup.</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                ui_components.empty_state(
                    "No per-10,000 claim",
                    "There is no kept finding, so the dashboard does not invent an "
                    "impact number. Observational gaps alone are not treated as bias.",
                    icon="∅",
                ),
                unsafe_allow_html=True,
            )

        st.markdown(
            _section_head("Mitigation trade-off", "accuracy vs fairness"),
            unsafe_allow_html=True,
        )

        @st.fragment
        def mitigation_panel() -> None:
            current: AuditReport | None = st.session_state.get("report")
            if current is None:
                return
            curve = current.mitigation_curve
            if not curve:
                st.markdown(
                    ui_components.empty_state(
                        "No mitigation curve",
                        "No finding was kept, so there is no affected segment to offset.",
                        icon="↺",
                    ),
                    unsafe_allow_html=True,
                )
                return
            max_loss_pct = st.slider(
                "Maximum acceptable accuracy loss",
                min_value=0.0,
                max_value=5.0,
                value=float(CONFIG["mitigation"]["max_accuracy_loss_default"] * 100),
                step=0.5,
                format="%.1f%%",
                key="max_loss",
            )
            recommendation = recommend(curve, max_loss_pct / 100.0)
            try:
                st.plotly_chart(
                    mitigation_figure(curve, recommendation),
                    width="stretch",
                    theme=None,
                    config=PLOTLY_CONFIG,
                )
            except Exception as exc:  # noqa: BLE001
                st.warning(f"Trade-off chart unavailable ({exc}); showing the table.")
            if recommendation:
                rec_offset, rec_gap, rec_loss = st.columns(3)
                rec_offset.metric(
                    "Recommended offset", f"+{recommendation['offset']}"
                )
                rec_gap.metric(
                    "Fairness gap", _pct(recommendation["fairness_gap"])
                )
                rec_loss.metric(
                    "Accuracy loss", _pct(recommendation["accuracy_loss"])
                )
                if not recommendation.get("within_budget", True):
                    st.warning(
                        "No tested offset keeps accuracy loss inside this budget. "
                        "The metrics show the smallest tested offset; raise the "
                        "budget to see a compliant offset."
                    )
                st.markdown(
                    f'<p class="fl-caption">{html.escape(recommendation["rationale"])} '
                    "Negative accuracy loss means accuracy improved. Both series share "
                    "one percentage-point axis; accuracy loss is measured against the "
                    "unaudited model.</p>",
                    unsafe_allow_html=True,
                )
                if str(recommendation.get("sampling", "")).startswith("stratified"):
                    st.markdown(
                        '<p class="fl-caption">Rare intersectional segment: the curve '
                        "uses a stratified sample (1,000 segment applicants plus "
                        "natural comparison applicants).</p>",
                        unsafe_allow_html=True,
                    )
            with st.expander("Mitigation curve table", expanded=False):
                st.dataframe(
                    _mitigation_table(curve),
                    hide_index=True,
                    width="stretch",
                )

        mitigation_panel()

        st.markdown(
            _section_head("Auditor narrative", "every number checked"),
            unsafe_allow_html=True,
        )
        check = report.number_check_result or {}
        passed = bool(check.get("passed"))
        source = str(check.get("source", "unknown"))
        st.markdown(
            '<div class="fl-narrative-head">'
            + ui_components.badge(
                "NUMBER CHECK PASSED" if passed else "NUMBER CHECK FAILED",
                "ok" if passed else "bad",
            )
            + f'<span class="fl-caption">source: {html.escape(source)}</span>'
            + "</div>",
            unsafe_allow_html=True,
        )
        if report.narrative:
            paragraphs = [
                html.escape(part).replace("\n", "<br>")
                for part in report.narrative.split("\n\n")
                if part.strip()
            ]
            body = "".join(f"<p>{part}</p>" for part in paragraphs)
            st.markdown(
                f'<div class="fl-narrative">{body}</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<p class="fl-caption">Every number is checked against the computed '
                f"JSON ({int(check.get('numeric_tokens', 0))} numeric tokens, "
                f"{len(check.get('unknown', []))} unknown). The LLM never calculates.</p>",
                unsafe_allow_html=True,
            )
        else:
            st.warning(
                "Narrative unavailable. The computed findings above are still valid."
            )
        if check.get("unknown"):
            st.warning(f"Unknown numbers: {check['unknown']}")

        st.markdown(
            _section_head("Human sign-off", "no audit record without a name"),
            unsafe_allow_html=True,
        )
        st.markdown(
            '<p class="fl-caption">No Audit Record is issued without an explicit '
            "Approve or Reject action and a named approver. A hash chain proves "
            "tamper-evidence, not authorship; signing is future work.</p>",
            unsafe_allow_html=True,
        )
        st.text_input(
            "Approver name",
            key="approver_name",
            placeholder="e.g. Dr A. Rao",
        )
        _render_notice(st.session_state.signoff_notice)
        approve_col, reject_col = st.columns(2)
        with approve_col:
            st.button(
                "Approve & issue Audit Record",
                type="primary",
                width="stretch",
                on_click=_approve,
            )
        with reject_col:
            st.button(
                "Reject & log decision",
                width="stretch",
                on_click=_reject,
            )
        if st.session_state.last_cert is not None:
            st.markdown(
                _certificate_card(st.session_state.last_cert),
                unsafe_allow_html=True,
            )

with certificate_tab:
    st.markdown(
        _section_head("Audit Record chain", "tamper-evident · not authorship"),
        unsafe_allow_html=True,
    )
    _render_notice(st.session_state.cert_notice)
    records = list_records(DB_PATH)
    verify_state = st.session_state.get("verify_state") or None
    if not records:
        chain_label = "0 records · nothing to verify"
        badge_state = None
        broken = None
    elif verify_state is None:
        chain_label = (
            f"{len(records)} record{'s' if len(records) != 1 else ''} · press Verify chain"
        )
        badge_state = None
        broken = None
    else:
        broken = verify_state.get("broken")
        chain_label = (
            f"{len(records)} record{'s' if len(records) != 1 else ''} · first broken: "
            f"{broken if broken is not None else 'none'}"
        )
        badge_state = verify_state.get("ok")
    st.markdown(
        '<div class="fl-verify-row">'
        + ui_components.verify_badge(badge_state)
        + f'<span class="fl-caption">{chain_label}</span>'
        + "</div>",
        unsafe_allow_html=True,
    )

    verify_col, tamper_col, reset_col = st.columns([1, 1.4, 1])
    with verify_col:
        st.button(
            "Verify chain",
            type="primary",
            width="stretch",
            on_click=_verify_chain,
        )
    with tamper_col:
        confirm = st.checkbox(
            "I understand this demo button modifies the local Audit Record database",
            key="confirm_tamper",
        )
        st.button(
            "Demo: tamper with the newest record",
            width="stretch",
            disabled=not confirm or not records,
            on_click=_tamper,
        )
    with reset_col:
        st.markdown('<div class="fl-sr-only">Reset the demo Audit Record database</div>', unsafe_allow_html=True)
        st.button(
            "Reset demo Audit Record database",
            width="stretch",
            on_click=_reset_demo_db,
        )

    if records:
        st.markdown(
            ui_components.chain_view(records, broken),
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            ui_components.chain_view([], None),
            unsafe_allow_html=True,
        )

    if st.session_state.last_cert is not None:
        with st.expander("Last Audit Record payload", expanded=False):
            st.json(st.session_state.last_cert.payload)

    st.markdown(
        '<p class="fl-caption">An Audit Record documents what one audit measured '
        "and who signed off on it. It is not a certification that the model is "
        "fair, lawful, or compliant. The hash chain proves tamper-evidence, not "
        "authorship.</p>",
        unsafe_allow_html=True,
    )

    st.markdown(
        '<p class="fl-caption">record_hash = sha256(prev_hash + canonical_json(payload)). '
        "Verification recomputes the whole chain. This proves tamper-evidence, not "
        "authorship: anyone who can rewrite all rows can recompute it. Digital "
        "signatures are future work. The payload includes the findings hash, report "
        "hash, config hash, approver, decision, and UTC timestamp.</p>",
        unsafe_allow_html=True,
    )

st.markdown(
    '<div class="fl-footer"><b>Synthetic sandbox only.</b> '
    "Evidence of disparate treatment, not proof of intent. "
    "Audit Records document measurements; they are not a certification of "
    "fairness, lawfulness, or compliance. The hash chain proves "
    "tamper-evidence, not authorship.</div>",
    unsafe_allow_html=True,
)
