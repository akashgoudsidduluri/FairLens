"""Shared Plotly styling and figures for FairLens.

One template (`FAIRLENS_TEMPLATE`) gives every chart the same transparent
background, accent colour, typography, and grid.  The Streamlit helper in
``ui/app.py`` passes ``PLOTLY_CONFIG`` so the modebar never appears.
"""

from __future__ import annotations

from typing import Any, Sequence

import plotly.graph_objects as go

ACCENT = "#5EEAD4"
DANGER = "#F87171"
WARN = "#FBBF24"
OK = "#34D399"
BLUE = "#60A5FA"
VIOLET = "#A78BFA"
TEXT = "#E5E7EB"
MUTED = "#94A3B8"
PANEL = "#0F1622"
GRID = "rgba(148, 163, 184, 0.14)"
FONT = "Inter, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"

PLOTLY_CONFIG: dict[str, Any] = {
    "displayModeBar": False,
    "displaylogo": False,
    "responsive": True,
    "scrollZoom": False,
}

FAIRLENS_TEMPLATE = go.layout.Template(
    layout=go.Layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT, color=TEXT, size=13),
        colorway=[ACCENT, DANGER, WARN, BLUE, VIOLET, OK],
        margin=dict(l=16, r=16, t=46, b=18),
        title=dict(
            font=dict(family=FONT, size=15, color=TEXT),
            x=0,
            xanchor="left",
        ),
        xaxis=dict(
            gridcolor=GRID,
            zerolinecolor=GRID,
            linecolor=GRID,
            tickcolor=GRID,
            tickfont=dict(family=FONT, size=11, color=MUTED),
            title=dict(font=dict(family=FONT, size=12, color=MUTED)),
        ),
        yaxis=dict(
            gridcolor=GRID,
            zerolinecolor=GRID,
            linecolor=GRID,
            tickcolor=GRID,
            tickfont=dict(family=FONT, size=11, color=MUTED),
            title=dict(font=dict(family=FONT, size=12, color=MUTED)),
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            x=0,
            bgcolor="rgba(0,0,0,0)",
            font=dict(family=FONT, size=11, color=MUTED),
        ),
        hoverlabel=dict(
            bgcolor="#111827",
            bordercolor=GRID,
            font=dict(family=FONT, color=TEXT),
        ),
        hovermode="x unified",
    )
)


def apply_theme(fig: go.Figure) -> go.Figure:
    """Apply the shared template to a figure."""

    fig.update_layout(template=FAIRLENS_TEMPLATE)
    return fig


def heatmap_figure(cells: Sequence[dict[str, Any]], gender: str) -> go.Figure:
    """Net approval loss by age band and location for one target gender.

    Red means more harm (a larger net flip toward the target group).  The
    colour scale is diverging when both signs occur, otherwise sequential from
    neutral to red.  Missing cells are shown with a dash rather than a zero.
    """

    ages = ["<35", "35-44", "45+"]
    locations = ["urban", "rural"]
    z: list[list[float | None]] = []
    text: list[list[str]] = []
    values: list[float] = []
    for age in ages:
        zrow: list[float | None] = []
        trow: list[str] = []
        for location in locations:
            match = next(
                (
                    c
                    for c in cells
                    if str(c.get("target_gender")) == gender
                    and str(c.get("age_band")) == age
                    and str(c.get("urban_rural")) == location
                ),
                None,
            )
            if match is None:
                zrow.append(None)
                trow.append("—")
            else:
                value = float(match.get("net_flip_rate", 0.0)) * 100.0
                values.append(value)
                zrow.append(value)
                trow.append(f"{value:+.1f}%")
        z.append(zrow)
        text.append(trow)

    if not values:
        zmin, zmax = 0.0, 1.0
        colorscale = [[0.0, PANEL], [1.0, PANEL]]
    elif min(values) < 0:
        bound = max(max(abs(v) for v in values), 0.5)
        zmin, zmax = -bound, bound
        colorscale = [[0.0, ACCENT], [0.5, "#0B1018"], [1.0, DANGER]]
    else:
        # Fixed 0-100 pp context keeps cell colours comparable across models.
        zmin, zmax = 0.0, 100.0
        colorscale = [
            [0.0, "#0B1018"],
            [0.2, "#5B2115"],
            [0.55, "#B91C1C"],
            [1.0, DANGER],
        ]

    fig = go.Figure(
        data=go.Heatmap(
            z=z,
            x=["Urban", "Rural"],
            y=ages,
            text=text,
            texttemplate="%{text}",
            textfont=dict(family="JetBrains Mono, monospace", size=13, color=TEXT),
            colorscale=colorscale,
            zmin=zmin,
            zmax=zmax,
            xgap=3,
            ygap=3,
            colorbar=dict(
                title=dict(text="Net flip %", font=dict(size=11, color=MUTED)),
                thickness=10,
                len=0.82,
                tickfont=dict(size=10, color=MUTED),
                outlinewidth=0,
            ),
            hovertemplate="Age %{y}<br>%{x}<br>Net flip %{z:+.1f}%<extra></extra>",
        )
    )
    apply_theme(fig)
    fig.update_layout(
        title=f"Net approval loss · {gender.title()} cells",
        height=350,
        xaxis=dict(title=dict(text="Location", standoff=10), side="bottom"),
        yaxis=dict(title="Age band", autorange="reversed"),
        margin=dict(l=76, r=14, t=54, b=52),
    )
    fig.add_annotation(
        text="red = more harm",
        xref="paper",
        yref="paper",
        x=1,
        y=1.08,
        showarrow=False,
        font=dict(size=10, color=MUTED),
        xanchor="right",
    )
    return fig


def mitigation_figure(
    curve: Sequence[dict[str, Any]], recommendation: dict[str, Any] | None
) -> go.Figure:
    """Fairness gap and accuracy loss against the segment score offset."""

    offsets = [int(point["offset"]) for point in curve]
    gaps = [float(point["fairness_gap"]) * 100.0 for point in curve]
    losses = [float(point["accuracy_loss"]) * 100.0 for point in curve]

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=offsets,
            y=gaps,
            mode="lines+markers",
            name="Fairness gap (pp)",
            line=dict(color=DANGER, width=2.4),
            marker=dict(size=5, color=DANGER),
            hovertemplate="offset +%{x}<br>gap %{y:.2f} pp<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=offsets,
            y=losses,
            mode="lines+markers",
            name="Accuracy loss (pp)",
            line=dict(color=ACCENT, width=2, dash="dot"),
            marker=dict(size=5, color=ACCENT),
            hovertemplate="offset +%{x}<br>loss %{y:+.2f} pp<extra></extra>",
        )
    )
    fig.add_hline(
        y=0,
        line_color=GRID,
        line_width=1,
        line_dash="dot",
    )
    if recommendation:
        offset = int(recommendation["offset"])
        fig.add_vline(
            x=offset,
            line_dash="dash",
            line_color=WARN,
            line_width=1.4,
            annotation_text=f"recommended +{offset}",
            annotation_position="top right",
            annotation_font=dict(size=10, color=WARN),
        )

    apply_theme(fig)
    fig.update_layout(
        title="Fairness–accuracy trade-off",
        height=380,
        xaxis=dict(
            title=dict(text="Score offset for affected group", standoff=10),
            dtick=max(1, (max(offsets) - min(offsets)) // 8),
        ),
        yaxis=dict(title=dict(text="Percentage points (pp)", standoff=6)),
        legend=dict(
            orientation="h",
            x=1,
            xanchor="right",
            y=1.07,
            yanchor="bottom",
        ),
        margin=dict(l=70, r=24, t=74, b=58),
    )
    return fig
