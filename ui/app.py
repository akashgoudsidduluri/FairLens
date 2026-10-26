"""FairLens India — single-page auditor dashboard.

Run from the repository root:
    .venv\\Scripts\\streamlit run ui/app.py

The page streams agent events while an audit runs, shows kept vs rejected
findings, an intersectional heatmap, human impact, a mitigation trade-off
slider, the number-checked narrative, and the human sign-off + certificate
verification flow.
"""

from __future__ import annotations

import html
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from auditor.pipeline import run_audit
from config_loader import load_config
from impact.mitigate import recommend
from schemas import AuditReport
from trust.certificate import (
    build_certificate_payload,
    fresh_demo_db,
    init_db,
    issue,
    list_records,
    tamper_for_demo,
    verify,
)

CONFIG = load_config()
DB_PATH = CONFIG["certificate"]["db_path"]
init_db(DB_PATH)

st.set_page_config(
    page_title="FairLens India",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .block-container {padding-top: 1.4rem; padding-bottom: 3rem; max-width: 1250px;}
    .fl-hero {padding: 1.1rem 1.3rem; border-radius: 14px;
              background: linear-gradient(120deg,#102a43,#1f4e79); color:#fff;}
    .fl-hero h1 {margin: 0; font-size: 2rem; letter-spacing: .2px;}
    .fl-hero p {margin: .35rem 0 0; color:#d9e2ec; font-size: .98rem;}
    .fl-log {max-height: 330px; overflow-y: auto; border: 1px solid #d9e2ec;
             border-radius: 10px; padding: .55rem .7rem; background:#fbfdff;
             font-size: .84rem; line-height: 1.35rem;}
    .fl-event {margin: .18rem 0; padding-left: .45rem; border-left: 3px solid #bcccdc;}
    .fl-agent {font-weight: 700; text-transform: uppercase; font-size: .68rem;
               letter-spacing: .04em; color:#486581; margin-right:.35rem;}
    .fl-kept {border-left-color:#2f855a;} .fl-kept .fl-agent {color:#276749;}
    .fl-rejected {border-left-color:#c53030;} .fl-rejected .fl-agent {color:#9b2c2c;}
    .fl-immaterial {border-left-color:#b7791f;} .fl-immaterial .fl-agent {color:#975a16;}
    .fl-badge {display:inline-block; padding:.15rem .55rem; border-radius:999px;
               font-size:.78rem; font-weight:700;}
    .fl-pass {background:#e3f9e5; color:#1e6b35;}
    .fl-fail {background:#ffe3e3; color:#9b2c2c;}
    .fl-note {color:#627d98; font-size:.82rem;}
    div[data-testid="stMetricValue"] {font-size: 1.45rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="fl-hero">
      <h1>FairLens India</h1>
      <p>An agentic auditor for black-box lending models. It probes with counterfactual
      twins, challenges its own findings, translates them into human impact, and asks a
      named human to sign a tamper-evident certificate.</p>
    </div>
    """,
    unsafe_allow_html=True,
)
st.caption(
    "Synthetic sandbox only · no real applicants · evidence of disparate treatment, not proof of intent"
)


def _event_class(event) -> str:
    message = event.message.upper()
    if event.agent == "skeptic":
        if message.startswith("REJECTED") or "REJECTED:" in message:
            return "fl-rejected"
        if message.startswith("IMMATERIAL") or "IMMATERIAL:" in message:
            return "fl-immaterial"
        if message.startswith("KEPT") or "KEPT:" in message:
            return "fl-kept"
    if event.agent == "planner" and "ABORTED" in message:
        return "fl-rejected"
    return ""


def _render_events(events) -> str:
    rows = []
    for event in events[-300:]:
        stamp = event.timestamp.strftime("%H:%M:%S")
        rows.append(
            f'<div class="fl-event {_event_class(event)}">'
            f'<span class="fl-agent">{html.escape(event.agent)}</span>'
            f'<span style="color:#829ab1">{stamp}</span> '
            f"{html.escape(event.message)}</div>"
        )
    return '<div class="fl-log">' + "".join(rows) + "</div>"


def _pct(value: float, digits: int = 2) -> str:
    return f"{value * 100:.{digits}f}%"


def _pval(value: float) -> str:
    if value == 0:
        return "0"
    return f"{value:.2e}" if value < 0.001 else f"{value:.4f}"


def _finding_rows(findings) -> pd.DataFrame:
    rows = []
    for f in findings:
        ev = f.evidence
        rows.append(
            {
                "Status": f.status,
                "Finding": f.attribute_or_subgroup,
                "n": ev.n,
                "b (harm)": ev.b,
                "c (help)": ev.c,
                "Net flip": _pct(ev.net_flip_rate),
                "95% CI": f"{_pct(ev.ci_low)} to {_pct(ev.ci_high)}",
                "Adj. p": _pval(ev.p_adjusted),
                "Obs. gap": _pct(f.observational_gap),
                "Matched net": (
                    _pct(f.matched_evidence.net_flip_rate)
                    if f.matched_evidence
                    else "—"
                ),
                "Why": f.reason,
            }
        )
    return pd.DataFrame(rows)


def _heatmap(cells, gender: str):
    ages = ["<35", "35-44", "45+"]
    urbans = ["urban", "rural"]
    z, text = [], []
    for age in ages:
        zrow, trow = [], []
        for urban in urbans:
            match = next(
                (
                    c
                    for c in cells
                    if c["target_gender"] == gender
                    and c["age_band"] == age
                    and c["urban_rural"] == urban
                ),
                None,
            )
            if match is None:
                zrow.append(None)
                trow.append("n/a")
            else:
                value = match["net_flip_rate"] * 100
                zrow.append(value)
                trow.append(f"{value:.1f}%")
        z.append(zrow)
        text.append(trow)
    fig = go.Figure(
        data=go.Heatmap(
            z=z,
            x=["Urban", "Rural"],
            y=ages,
            text=text,
            texttemplate="%{text}",
            colorscale="RdYlGn_r",
            zmid=0,
            zmin=-20,
            zmax=70,
            colorbar=dict(title="Net flip %"),
            hovertemplate="Age %{y}<br>%{x}<br>Net flip %{z:.1f}%<extra></extra>",
        )
    )
    fig.update_layout(
        title=f"Net approval loss when moving into the {gender} cell (red = harm)",
        height=330,
        margin=dict(l=10, r=10, t=55, b=10),
        yaxis_title="Age band",
        xaxis_title="Location",
    )
    return fig


def _mitigation_figure(curve, rec):
    offsets = [p["offset"] for p in curve]
    gaps = [p["fairness_gap"] * 100 for p in curve]
    losses = [p["accuracy_loss"] * 100 for p in curve]
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=offsets,
            y=gaps,
            mode="lines+markers",
            name="Fairness gap (pp)",
            line=dict(color="#b42318", width=2.4),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=offsets,
            y=losses,
            mode="lines+markers",
            name="Accuracy loss (pp)",
            yaxis="y2",
            line=dict(color="#175cd3", width=2, dash="dot"),
        )
    )
    if rec:
        fig.add_vline(
            x=rec["offset"],
            line_dash="dash",
            line_color="#2f855a",
            annotation_text=f"recommended +{rec['offset']}",
            annotation_position="top right",
        )
    fig.update_layout(
        height=350,
        margin=dict(l=10, r=10, t=25, b=10),
        xaxis_title="Score offset for affected group",
        yaxis=dict(title="Fairness gap (pp)"),
        yaxis2=dict(title="Accuracy loss (pp)", overlaying="y", side="right"),
        legend=dict(orientation="h", y=1.08),
    )
    return fig


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("Audit controls")
    api_url = st.text_input("Sandbox API URL", value=CONFIG["api"]["base_url"])
    model_id = st.selectbox(
        "Model under audit",
        options=list(range(1, 8)),
        index=1,
        format_func=lambda n: f"Model {n}",
    )
    st.markdown(
        '<div class="fl-note">Demo order: <b>Model 2 → Model 7 → Model 5</b>. '
        "The model selector does not reveal which model is biased.</div>",
        unsafe_allow_html=True,
    )
    run_clicked = st.button("Run audit", type="primary", use_container_width=True)
    st.divider()
    st.caption(
        "Pre-registered: alpha 0.05 · materiality 2% · Holm correction · "
        "2,000 natural twins per attribute · 500 per intersectional cell."
    )
    st.divider()
    st.markdown(
        '<div class="fl-note">The auditor talks to the model only over HTTP. '
        "LLM narrative never computes numbers. Human approval is mandatory.</div>",
        unsafe_allow_html=True,
    )

if "events" not in st.session_state:
    st.session_state.events = []
if "report" not in st.session_state:
    st.session_state.report = None
if "last_cert" not in st.session_state:
    st.session_state.last_cert = None

audit_tab, certificate_tab = st.tabs(["Audit", "Certificates"])

with audit_tab:
    st.subheader("Live agent log")
    log_placeholder = st.empty()
    log_placeholder.markdown(
        _render_events(st.session_state.events)
        if st.session_state.events
        else '<div class="fl-note">No audit yet. Choose a model and press Run audit.</div>',
        unsafe_allow_html=True,
    )

    if run_clicked:
        st.session_state.events = []
        st.session_state.report = None
        st.session_state.last_cert = None
        events = []
        try:
            generator = run_audit(model_id, api_url, CONFIG, seed=CONFIG["seed"])
            while True:
                try:
                    event = next(generator)
                except StopIteration as stop:
                    st.session_state.report = stop.value
                    break
                events.append(event)
                st.session_state.events = list(events)
                log_placeholder.markdown(_render_events(events), unsafe_allow_html=True)
        except Exception as exc:  # noqa: BLE001
            st.session_state.events = list(events)
            log_placeholder.markdown(_render_events(events), unsafe_allow_html=True)
            st.error(f"Audit could not run: {exc}")
            st.info(
                "Check the API URL and start the sandbox (see run.sh). "
                "The auditor handles unreachable or invalid URLs without crashing."
            )

    report: AuditReport | None = st.session_state.report
    if report is not None:
        kept = [f for f in report.findings if f.status == "kept"]
        rejected = [f for f in report.findings if f.status == "rejected"]
        immaterial = [f for f in report.findings if f.status == "immaterial"]
        st.caption(
            f"Showing audit of Model {report.model_id}. Thresholds: "
            f"alpha {report.config['audit']['alpha']}, materiality "
            f"{report.config['audit']['materiality']}, "
            f"{report.config['audit']['correction'].upper()} correction."
        )

        cols = st.columns(4)
        cols[0].metric("Kept findings", len(kept))
        cols[1].metric("Rejected", len(rejected))
        cols[2].metric("Significant but immaterial", len(immaterial))
        if report.impact:
            top = max(report.impact, key=lambda i: i.per_10k)
            cols[3].metric("Largest impact", f"~{top.per_10k:,.0f}", "per 10,000")
        else:
            cols[3].metric("Largest impact", "0", "per 10,000")

        st.subheader("Findings")
        st.caption(
            "Kept requires counterfactual significance after Holm correction, "
            "pre-registered materiality, a directional effect, and persistence in "
            "an income-matched re-test. Rejected candidates stay visible."
        )
        if kept:
            st.markdown("**Kept**")
            st.dataframe(
                _finding_rows(kept),
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.info("No findings survived the Skeptic for this model.")
        if rejected or immaterial:
            with st.expander(
                f"Rejected and immaterial candidates ({len(rejected) + len(immaterial)})",
                expanded=False,
            ):
                st.dataframe(
                    _finding_rows(rejected + immaterial),
                    hide_index=True,
                    use_container_width=True,
                )

        st.subheader("Intersectional scan")
        cells = report.observational.get("intersectional_cells", [])
        if cells:
            heat_gender = st.radio(
                "Cell gender", options=["female", "male"], horizontal=True, key="heat_gender"
            )
            try:
                st.plotly_chart(
                    _heatmap(cells, heat_gender), use_container_width=True
                )
            except Exception as exc:  # noqa: BLE001
                st.warning(f"Heatmap unavailable ({exc}); showing the cell table.")
            with st.expander("Cell table (fallback)"):
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "Gender": c["target_gender"],
                                "Age": c["age_band"],
                                "Location": c["urban_rural"],
                                "n": c["n"],
                                "b": c["b"],
                                "c": c["c"],
                                "Net flip": _pct(c["net_flip_rate"]),
                                "Adj. p": _pval(c["p_adjusted"]),
                            }
                            for c in cells
                        ]
                    ),
                    hide_index=True,
                    use_container_width=True,
                )
        else:
            st.info("No intersectional cells available in this report.")

        st.subheader("Human impact")
        if report.impact:
            impact_cols = st.columns(min(3, len(report.impact)))
            for idx, estimate in enumerate(report.impact[:3]):
                impact_cols[idx % len(impact_cols)].metric(
                    estimate.subgroup,
                    f"~{estimate.per_10k:,.0f} per 10,000",
                    f"95% range {estimate.ci_low_per_10k:,.0f}–{estimate.ci_high_per_10k:,.0f}",
                )
            st.caption(
                "Formula: max(net flip rate, 0) × 10,000. No additional multipliers. "
                "For intersectional findings this is within the affected subgroup."
            )
        else:
            st.info(
                "No kept finding, so no per-10,000 impact is claimed. "
                "Observational gaps alone are not treated as bias."
            )

        st.subheader("Mitigation trade-off")
        curve = report.mitigation_curve
        if curve:
            max_loss_pct = st.slider(
                "Maximum acceptable accuracy loss",
                min_value=0.0,
                max_value=5.0,
                value=float(
                    CONFIG["mitigation"]["max_accuracy_loss_default"] * 100
                ),
                step=0.5,
                format="%.1f%%",
                key="max_loss",
            )
            rec = recommend(curve, max_loss_pct / 100.0)
            try:
                st.plotly_chart(_mitigation_figure(curve, rec), use_container_width=True)
            except Exception as exc:  # noqa: BLE001
                st.warning(f"Trade-off chart unavailable ({exc}); showing the table.")
            if rec:
                rcols = st.columns(3)
                rcols[0].metric("Recommended offset", f"+{rec['offset']}")
                rcols[1].metric("Fairness gap", _pct(rec["fairness_gap"]))
                rcols[2].metric("Accuracy loss", _pct(rec["accuracy_loss"]))
                st.caption(rec["rationale"] + " Negative accuracy loss means accuracy improved.")
                if rec.get("sampling", "").startswith("stratified"):
                    st.caption(
                        "Rare intersectional segment: curve uses a stratified sample "
                        "(1,000 segment applicants plus natural comparison applicants)."
                    )
            with st.expander("Mitigation curve table"):
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "Offset": p["offset"],
                                "Segment approval": _pct(p["segment_approval_rate"]),
                                "Comparison approval": _pct(
                                    p["comparison_approval_rate"]
                                ),
                                "Fairness gap": _pct(p["fairness_gap"]),
                                "Accuracy": _pct(p["accuracy"]),
                                "Accuracy loss": _pct(p["accuracy_loss"]),
                            }
                            for p in curve
                        ]
                    ),
                    hide_index=True,
                    use_container_width=True,
                )
        else:
            st.info("No mitigation curve because no finding was kept.")

        st.subheader("Auditor narrative")
        check = report.number_check_result or {}
        passed = bool(check.get("passed"))
        source = check.get("source", "unknown")
        badge = (
            '<span class="fl-badge fl-pass">NUMBER CHECK PASSED</span>'
            if passed
            else '<span class="fl-badge fl-fail">NUMBER CHECK FAILED</span>'
        )
        st.markdown(f"{badge} &nbsp; <span class='fl-note'>source: {html.escape(str(source))}</span>", unsafe_allow_html=True)
        if report.narrative:
            st.write(report.narrative)
            st.caption(
                f"Every number is checked against the computed JSON "
                f"({check.get('numeric_tokens', 0)} numeric tokens, "
                f"{len(check.get('unknown', []))} unknown). The LLM never calculates."
            )
        else:
            st.warning("Narrative unavailable. The computed findings above are still valid.")
        if check.get("unknown"):
            st.warning(f"Unknown numbers: {check['unknown']}")

        st.subheader("Human sign-off")
        st.caption(
            "No certificate is issued without an explicit Approve or Reject action and "
            "a named approver. A hash chain proves tamper-evidence, not authorship; "
            "signing is future work."
        )
        approver = st.text_input("Approver name", key="approver_name")
        approve_col, reject_col = st.columns(2)
        decision = None
        if approve_col.button("Approve & issue certificate", type="primary", use_container_width=True):
            decision = "approve"
        if reject_col.button("Reject & log decision", use_container_width=True):
            decision = "reject"
        if decision:
            if not approver.strip():
                st.error("Enter the approver's name before issuing or rejecting.")
            else:
                payload = build_certificate_payload(report, CONFIG, approver, decision)
                certificate = issue(payload, approver, decision, DB_PATH)
                st.session_state.last_cert = certificate
                if decision == "approve":
                    st.success(
                        f"Certificate #{certificate.index} issued for Model {report.model_id} "
                        f"by {approver.strip()}."
                    )
                else:
                    st.warning(
                        f"Rejection logged as certificate #{certificate.index}. "
                        "No approval certificate was issued."
                    )
                st.code(
                    f"record_hash: {certificate.record_hash}\n"
                    f"prev_hash:   {certificate.prev_hash}",
                    language="text",
                )
        if st.session_state.last_cert is not None:
            last = st.session_state.last_cert
            st.caption(
                f"Last record: #{last.index} · {last.payload['decision']} · "
                f"{last.payload['approver']} · {last.payload['timestamp']}"
            )
    elif not run_clicked:
        st.info(
            "Run an audit to see findings, the intersectional heatmap, impact, "
            "mitigation, and the human sign-off flow."
        )

with certificate_tab:
    st.subheader("Certificate chain")
    notice = st.session_state.pop("cert_notice", None)
    if notice:
        getattr(st, notice["level"])(notice["message"])
    records = list_records(DB_PATH)
    if records:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "#": r.index,
                        "Model": r.payload.get("model_id"),
                        "Approver": r.payload.get("approver"),
                        "Decision": r.payload.get("decision"),
                        "UTC timestamp": r.payload.get("timestamp"),
                        "Record hash": r.record_hash[:16] + "…",
                    }
                    for r in records
                ]
            ),
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.info("No certificates yet. Approve or reject an audit to create one.")

    verify_col, tamper_col = st.columns(2)
    if verify_col.button("Verify chain", type="primary", use_container_width=True):
        ok, broken = verify(DB_PATH)
        if ok:
            st.success("Chain verified: every record hash and link is intact.")
        else:
            st.error(f"Verification FAILED at record #{broken}. The chain was modified.")
    if records:
        confirm = st.checkbox(
            "I understand this demo button modifies the local certificate database",
            key="confirm_tamper",
        )
        if tamper_col.button(
            "Demo: tamper with the newest record",
            disabled=not confirm,
            use_container_width=True,
        ):
            result = tamper_for_demo(records[-1].index, DB_PATH)
            ok, broken = verify(DB_PATH)
            st.session_state.cert_notice = {
                "level": "warning",
                "message": (
                    f"Tampered field '{result['field']}' at record #{result['index']}. "
                    f"Verification now returns ok={ok}, first broken record={broken}."
                ),
            }
            st.rerun()
        reset_col, _ = st.columns(2)
        if reset_col.button("Reset demo certificate database", use_container_width=True):
            fresh_demo_db(DB_PATH)
            st.session_state.last_cert = None
            st.session_state.cert_notice = {
                "level": "success",
                "message": "Certificate database reset for a fresh demo.",
            }
            st.rerun()

    st.caption(
        "record_hash = sha256(prev_hash + canonical_json(payload)). Verification "
        "recomputes the whole chain. This proves tamper-evidence, not authorship: "
        "anyone who can rewrite all rows can recompute it. Digital signatures are "
        "future work. The certificate payload includes the findings hash, report "
        "hash, config hash, approver, decision, and UTC timestamp."
    )
    if st.session_state.last_cert is not None:
        with st.expander("Last certificate payload"):
            st.json(st.session_state.last_cert.payload)
