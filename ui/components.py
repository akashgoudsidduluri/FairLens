"""Pure HTML renderers for the FairLens dashboard.

Everything in this module is a pure function: it takes data and returns an HTML
string.  No Streamlit calls, no I/O, no scoring logic.  Keeping the renderers
pure makes them easy to test and keeps the black-box boundary intact.

The returned fragments are intended to be passed to ``st.markdown(...,
unsafe_allow_html=True)``.  ``impact_counter`` is the one exception: its
returned document contains a little JavaScript for the count-up animation and
should be embedded with ``streamlit.components.v1.html``.
"""

from __future__ import annotations

import hashlib
import html
from datetime import datetime
from typing import Any, Iterable, Mapping, Sequence

# Pipeline steps shown in the strip.  ``signoff`` is not an agent; it is the
# human gate at the end of the audit.
PIPELINE_STEPS: tuple[tuple[str, str, str], ...] = (
    ("planner", "Plan", "scope + seed"),
    ("prober", "Probe", "HTTP twins"),
    ("statistician", "Test", "McNemar + Holm"),
    ("skeptic", "Skeptic", "challenge"),
    ("impact", "Impact", "people / 10k"),
    ("reporter", "Report", "number check"),
    ("signoff", "Sign-off", "human gate"),
)

AGENT_LABELS: dict[str, str] = {
    "planner": "planner",
    "prober": "prober",
    "statistician": "statistician",
    "skeptic": "skeptic",
    "impact": "impact",
    "reporter": "reporter",
    "system": "demo",
}

_VALID_STATUSES = {"pending", "active", "done", "failed", "skipped"}


def _value(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _pct(value: Any, digits: int = 2, signed: bool = False) -> str:
    try:
        number = float(value) * 100.0
    except (TypeError, ValueError):
        return "—"
    sign = "+" if signed and number > 0 else ""
    return f"{sign}{number:.{digits}f}%"


def _pval(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    if number == 0:
        return "0"
    if number < 0.001:
        return f"{number:.1e}"
    return f"{number:.4f}"


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _escape(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def badge(label: str, tone: str = "neutral") -> str:
    """Small status pill. ``tone`` is ok/bad/warn/accent/neutral."""

    tone = tone if tone in {"ok", "bad", "warn", "accent", "neutral"} else "neutral"
    return (
        f'<span class="fl-badge fl-badge--{tone}">{_escape(label)}</span>'
    )


def empty_state(title: str, body: str, icon: str = "◇") -> str:
    """A consistent empty/loading/error card."""

    return (
        '<div class="fl-empty">'
        f'<div class="fl-empty__icon" aria-hidden="true">{_escape(icon)}</div>'
        f"<h3>{_escape(title)}</h3>"
        f"<p>{_escape(body)}</p>"
        "</div>"
    )


def pipeline_strip(state: Mapping[str, str] | None) -> str:
    """Render the seven-step audit pipeline.

    ``state`` maps a step key (planner, prober, statistician, skeptic, impact,
    reporter, signoff) to one of pending/active/done/failed/skipped.  Missing
    keys are treated as pending.
    """

    state = state or {}
    items: list[str] = []
    for key, label, detail in PIPELINE_STEPS:
        raw = str(state.get(key, "pending")).lower()
        status = raw if raw in _VALID_STATUSES else "pending"
        icon = {
            "pending": "·",
            "active": "",
            "done": "✓",
            "failed": "×",
            "skipped": "–",
        }[status]
        active = ' aria-current="step"' if status == "active" else ""
        items.append(
            f'<div class="fl-pipe-step fl-pipe-step--{status}" role="listitem"{active}>'
            '<div class="fl-pipe-top">'
            f'<span class="fl-pipe-dot fl-pipe-dot--{status}" aria-hidden="true">{icon}</span>'
            f'<span class="fl-pipe-name">{_escape(label)}</span>'
            "</div>"
            f'<span class="fl-pipe-detail">{_escape(detail)}</span>'
            f'<span class="fl-sr-only">status: {status}</span>'
            "</div>"
        )
    return (
        '<div class="fl-pipeline" role="list" aria-label="Audit pipeline">'
        + "".join(items)
        + "</div>"
    )


def _event_severity(agent: str, message: str) -> str:
    upper = message.upper()
    if agent == "skeptic":
        if "REJECTED" in upper:
            return "reject"
        if "IMMATERIAL" in upper:
            return "warn"
        if "KEPT" in upper:
            return "keep"
    if "ABORTED" in upper or "UNREACHABLE" in upper:
        return "reject"
    if "FAILED" in upper or "ERROR" in upper or "UNAVAILABLE" in upper:
        return "warn"
    return ""


def _event_time(event: Any) -> str:
    stamp = _value(event, "timestamp", None)
    if isinstance(stamp, datetime):
        try:
            return stamp.strftime("%H:%M:%S")
        except ValueError:
            return "--:--:--"
    text = str(stamp or "")
    return text[-8:] if len(text) >= 8 else text


def log_feed(events: Iterable[Any], running: bool = False) -> str:
    """Render the live agent log, newest entry first.

    Re-rendering the placeholder resets an overflow container's scroll position,
    so the newest event is placed at the top.  Skeptic rejections are red;
    immaterial verdicts are amber; kept verdicts are green.
    """

    events = list(events or [])
    if not events:
        title = "Connecting to the sandbox" if running else "No audit yet"
        body = (
            "The auditor is opening a connection and preparing probes."
            if running
            else "Choose a model and press Start Audit, or run the three-model demo."
        )
        return empty_state(title, body, icon="⌁")

    rows: list[str] = []
    for event in events[-300:]:
        agent = str(_value(event, "agent", "system") or "system").lower()
        message = str(_value(event, "message", "") or "")
        severity = _event_severity(agent, message)
        classes = [f"fl-event--{agent}" if agent in AGENT_LABELS else "fl-event--system"]
        if severity:
            classes.append(f"fl-event--{severity}")
        label = AGENT_LABELS.get(agent, agent)
        rows.append(
            f'<div class="fl-event {" ".join(classes)}" role="listitem">'
            f'<span class="fl-event__time">{_escape(_event_time(event))}</span>'
            f'<span class="fl-event__agent">{_escape(label)}</span>'
            f'<span class="fl-event__msg">{_escape(message)}</span>'
            "</div>"
        )

    # Reverse the chronological order: with flex-direction: column-reverse the
    # newest item lands at the bottom but remains the first DOM child.
    rows.reverse()
    cursor = (
        '<div class="fl-log__cursor" aria-hidden="true">'
        '<span class="fl-log__caret"></span> working</div>'
        if running
        else ""
    )
    return (
        '<div class="fl-log" role="log" aria-live="polite">'
        + cursor
        + "".join(rows)
        + "</div>"
    )


def finding_card(finding: Any) -> str:
    """Render one finding as a card.

    Rejected findings carry a visible REJECTED stamp; immaterial candidates get
    an IMMATERIAL stamp.  The card never hides a rejected candidate.
    """

    status = str(_value(finding, "status", "candidate") or "candidate").lower()
    if status not in {"candidate", "kept", "rejected", "immaterial"}:
        status = "candidate"
    title = str(_value(finding, "attribute_or_subgroup", "—") or "—")
    title = title.replace("|", " · ")
    kind = str(_value(finding, "kind", "single_attribute") or "single_attribute")
    kind_label = "intersectional" if kind == "intersectional" else "single attribute"
    target = str(_value(finding, "target_group", "—") or "—").replace("|", " · ")
    comparison = str(_value(finding, "comparison_group", "—") or "—").replace("|", " · ")
    reason = str(_value(finding, "reason", "") or "")
    evidence = _value(finding, "evidence", None)
    net = float(_value(evidence, "net_flip_rate", 0.0) or 0.0)
    n = _int(_value(evidence, "n", 0))
    b = _int(_value(evidence, "b", 0))
    c = _int(_value(evidence, "c", 0))
    low = float(_value(evidence, "ci_low", 0.0) or 0.0)
    high = float(_value(evidence, "ci_high", 0.0) or 0.0)
    p_adj = _value(evidence, "p_adjusted", None)
    obs_gap = float(_value(finding, "observational_gap", 0.0) or 0.0)
    matched = _value(finding, "matched_evidence", None)
    matched_text = "—"
    if matched is not None:
        matched_net = float(_value(matched, "net_flip_rate", 0.0) or 0.0)
        matched_text = f"{_pct(matched_net, signed=True)} (p {_pval(_value(matched, 'p_adjusted', None))})"

    stamp = ""
    if status == "rejected":
        stamp = '<span class="fl-stamp">REJECTED</span>'
    elif status == "immaterial":
        stamp = '<span class="fl-stamp fl-stamp--warn">IMMATERIAL</span>'

    status_label = {
        "kept": "KEPT",
        "rejected": "REJECTED",
        "immaterial": "IMMATERIAL",
        "candidate": "CANDIDATE",
    }[status]
    net_text = _pct(net, digits=1, signed=True)
    ci_text = f"{_pct(low, digits=1, signed=True)} to {_pct(high, digits=1, signed=True)}"

    return (
        f'<article class="fl-finding fl-finding--{status}" '
        f'aria-label="{_escape(title)} ({status_label})">'
        '<div class="fl-finding__top">'
        '<div class="fl-finding__tags">'
        f'<span class="fl-pill fl-pill--{status}">{status_label}</span>'
        f'<span class="fl-kicker">{_escape(kind_label)}</span>'
        "</div>"
        f"{stamp}"
        "</div>"
        f"<h4>{_escape(title)}</h4>"
        '<div class="fl-finding__metric">'
        f"<strong>{net_text}</strong>"
        f"<span>net flip toward {_escape(target)}</span>"
        "</div>"
        '<div class="fl-finding__grid">'
        f"<div><span>pairs</span><b>{n:,}</b></div>"
        f"<div><span>harm / help</span><b>{b} / {c}</b></div>"
        f"<div><span>Holm p</span><b>{_pval(p_adj)}</b></div>"
        f"<div><span>95% CI</span><b>{ci_text}</b></div>"
        f"<div><span>obs. gap</span><b>{_pct(obs_gap, digits=1, signed=True)}</b></div>"
        f"<div><span>matched</span><b>{matched_text}</b></div>"
        "</div>"
        f'<p class="fl-finding__reason"><span>Why</span> {_escape(reason or "No reason recorded.")}</p>'
        f'<p class="fl-finding__compare">Moved from {_escape(comparison)} into {_escape(target)}; '
        "all other applicant signals held fixed.</p>"
        "</article>"
    )


def impact_counter(
    value: float,
    label: str = "people per 10,000",
    sublabel: str = "",
) -> str:
    """Return a self-contained HTML document with a JS count-up counter.

    Embed with ``streamlit.components.v1.html(impact_counter(value), height=...)``.
    The animation respects ``prefers-reduced-motion`` and always ends on the
    exact integer target.
    """

    try:
        target = max(float(value), 0.0)
    except (TypeError, ValueError):
        target = 0.0
    rounded = int(round(target))
    uid = "fl-counter-" + hashlib.sha1(
        f"{rounded}|{label}|{sublabel}".encode("utf-8")
    ).hexdigest()[:10]
    label_html = _escape(label)
    sublabel_html = (
        f'<div class="fl-counter__sub">{_escape(sublabel)}</div>' if sublabel else ""
    )
    template = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
  * { box-sizing: border-box; }
  html, body {
    margin: 0;
    padding: 0;
    background: transparent;
    color: #E5E7EB;
    font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  }
  .fl-counter {
    position: relative;
    overflow: hidden;
    min-height: 132px;
    display: flex;
    flex-direction: column;
    justify-content: center;
    border: 1px solid rgba(94, 234, 212, 0.35);
    border-radius: 16px;
    background: linear-gradient(120deg, rgba(94, 234, 212, 0.14), rgba(15, 22, 34, 0.94));
    padding: 16px 20px;
    box-shadow: 0 0 46px rgba(94, 234, 212, 0.08);
  }
  .fl-counter::after {
    content: "";
    position: absolute;
    right: -70px;
    top: -90px;
    width: 260px;
    height: 260px;
    border-radius: 999px;
    background: radial-gradient(circle, rgba(94, 234, 212, 0.16), transparent 65%);
    pointer-events: none;
  }
  .fl-counter__eyebrow {
    position: relative;
    z-index: 1;
    font-size: 0.66rem;
    font-weight: 700;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: #5EEAD4;
  }
  .fl-counter__value {
    position: relative;
    z-index: 1;
    font-family: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: clamp(2.2rem, 5.8vw, 3.6rem);
    font-weight: 600;
    line-height: 1;
    letter-spacing: -0.05em;
    color: #5EEAD4;
    margin: 6px 0 3px;
  }
  .fl-counter__label {
    position: relative;
    z-index: 1;
    font-size: 0.78rem;
    color: #CBD5E1;
  }
  .fl-counter__sub {
    position: relative;
    z-index: 1;
    margin-top: 3px;
    font-family: "JetBrains Mono", ui-monospace, monospace;
    font-size: 0.7rem;
    color: #94A3B8;
  }
</style>
</head>
<body>
  <div class="fl-counter">
    <div class="fl-counter__eyebrow">Human impact</div>
    <div class="fl-counter__value" id="__UID__">0</div>
    <div class="fl-counter__label">__LABEL__</div>
    __SUB__
  </div>
  <script>
    (function () {
      var el = document.getElementById("__UID__");
      var target = __TARGET__;
      var formatter = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
      if (!el) { return; }
      var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      if (reduce) {
        el.textContent = formatter.format(target);
        return;
      }
      var start = null;
      var duration = 950;
      function tick(now) {
        if (start === null) { start = now; }
        var progress = Math.min(1, (now - start) / duration);
        var eased = 1 - Math.pow(1 - progress, 3);
        el.textContent = formatter.format(Math.round(target * eased));
        if (progress < 1) { window.requestAnimationFrame(tick); }
      }
      window.requestAnimationFrame(tick);
    })();
  </script>
</body>
</html>
"""
    return (
        template.replace("__UID__", uid)
        .replace("__TARGET__", str(rounded))
        .replace("__LABEL__", label_html)
        .replace("__SUB__", sublabel_html)
    )


def _cert_value(cert: Any, key: str, default: Any = None) -> Any:
    payload = _value(cert, "payload", {}) or {}
    if key in {"index", "record_hash", "prev_hash", "created_at"}:
        return _value(cert, key, default)
    return _value(payload, key, default)


def chain_view(certificates: Sequence[Any], broken_index: int | None) -> str:
    """Render the hash chain as linked records, marking a broken record."""

    records = list(certificates or [])
    if not records:
        return empty_state(
            "No certificates yet",
            "Approve or reject an audit to issue the first record in the chain.",
            icon="⛓",
        )

    broken: int | None
    try:
        broken = int(broken_index) if broken_index is not None else None
    except (TypeError, ValueError):
        broken = None

    blocks: list[str] = [
        '<div class="fl-chain">'
        '<div class="fl-chain__genesis">'
        '<span class="fl-chain__genesis-dot" aria-hidden="true"></span>'
        "<div><b>GENESIS</b>"
        '<div class="fl-hash">prev_hash = 0000000000000000000000000000000000000000000000000000000000000000</div>'
        "</div></div>"
    ]
    for cert in records:
        index = _int(_cert_value(cert, "index", 0))
        is_broken = broken is not None and index == broken
        decision = str(_cert_value(cert, "decision", "—") or "—")
        decision_tone = "ok" if decision == "approve" else "warn"
        record_hash = str(_cert_value(cert, "record_hash", "") or "")
        prev_hash = str(_cert_value(cert, "prev_hash", "") or "")
        model_id = _cert_value(cert, "model_id", "—")
        approver = _cert_value(cert, "approver", "—")
        timestamp = _cert_value(cert, "timestamp", _cert_value(cert, "created_at", "—"))
        short_hash = (
            f"{record_hash[:14]}…{record_hash[-8:]}" if len(record_hash) > 26 else record_hash
        )
        classes = "fl-chain__record" + (" is-broken" if is_broken else "")
        marker = (
            ' <span class="fl-badge fl-badge--bad">HASH MISMATCH</span>'
            if is_broken
            else ""
        )
        blocks.append(
            f'<article class="{classes}" aria-label="Certificate {index}">'
            '<div class="fl-chain__row">'
            f'<span class="fl-chain__index">#{index}</span>'
            f'<span class="fl-badge fl-badge--{decision_tone}">{_escape(decision.upper())}</span>'
            f'<b>Model {_escape(model_id)}</b>'
            f"<span>{_escape(approver)}</span>"
            f'<span class="fl-chain__time">{_escape(timestamp)}</span>'
            f"{marker}"
            "</div>"
            '<div class="fl-chain__row fl-chain__hashrow">'
            f'<span>record_hash</span>'
            f'<code class="fl-hash" title="{_escape(record_hash)}">{_escape(short_hash)}</code>'
            f'<span>prev</span><code class="fl-hash" title="{_escape(prev_hash)}">{_escape(prev_hash[:14])}…</code>'
            "</div>"
            "</article>"
        )
    blocks.append(
        '<div class="fl-chain__note">'
        "record_hash = sha256(prev_hash + canonical_json(payload)). "
        "A broken link is highlighted in red."
        "</div></div>"
    )
    return "".join(blocks)


def verify_badge(ok: bool | None) -> str:
    """Render the chain verification state."""

    if ok is True:
        return '<span class="fl-badge fl-badge--ok fl-glow">CHAIN VERIFIED</span>'
    if ok is False:
        return '<span class="fl-badge fl-badge--bad fl-glow">CHAIN BROKEN</span>'
    return '<span class="fl-badge fl-badge--neutral">NOT CHECKED</span>'
