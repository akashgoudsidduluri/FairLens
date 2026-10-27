"""Charts share one accessible Plotly theme and never expose the modebar."""

from __future__ import annotations

from ui.plotting import PLOTLY_CONFIG, heatmap_figure, mitigation_figure


def _cell(gender: str, age: str, location: str, value: float) -> dict:
    return {
        "target_gender": gender,
        "age_band": age,
        "urban_rural": location,
        "net_flip_rate": value,
        "n": 500,
    }


def test_heatmap_uses_shared_theme_and_handles_missing_cells():
    cells = [
        _cell("female", "<35", "urban", 0.61),
        _cell("female", "35-44", "rural", 0.68),
    ]
    fig = heatmap_figure(cells, "female")

    assert fig.layout.template.layout.paper_bgcolor == "rgba(0,0,0,0)"
    assert fig.layout.template.layout.plot_bgcolor == "rgba(0,0,0,0)"
    assert fig.layout.template.layout.font.family.startswith("Inter")

    trace = fig.data[0]
    assert list(trace.z[0]) == [61.0, None]
    assert trace.text[0][1] == "—"
    assert trace.text[1][1] == "+68.0%"
    assert trace.zmin == 0.0 and trace.zmax == 100.0


def test_mitigation_chart_keeps_both_series_on_one_axis():
    curve = [
        {"offset": 0, "fairness_gap": 0.35, "accuracy_loss": -0.015},
        {"offset": 80, "fairness_gap": 0.046, "accuracy_loss": -0.013},
        {"offset": 160, "fairness_gap": 0.30, "accuracy_loss": -0.002},
    ]
    fig = mitigation_figure(curve, {"offset": 80})

    assert len(fig.data) == 2
    assert fig.data[1].yaxis is None or fig.data[1].yaxis == "y"
    assert fig.layout.to_plotly_json().get("yaxis2") is None
    assert list(fig.data[0].y) == [35.0, 4.6, 30.0]
    assert list(fig.data[1].y) == [-1.5, -1.3, -0.2]
    assert fig.layout.yaxis.title.text == "Percentage points (pp)"
    assert any(getattr(shape, "xref", "") == "x" for shape in fig.layout.shapes)


def test_plotly_config_hides_the_modebar():
    assert PLOTLY_CONFIG["displayModeBar"] is False
    assert PLOTLY_CONFIG["responsive"] is True
