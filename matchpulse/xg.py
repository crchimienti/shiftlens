"""Cumulative synthetic xG per team up to the replay clock (the dataset's `xg` field; never a provider model)."""
from __future__ import annotations

import plotly.graph_objects as go

from .metrics import event_time

SHOT_TYPES = ("shot", "goal")


def xg_timeline(events: list[dict], team_ids: tuple[str, str], clock: int) -> dict[str, list[tuple[int, float]]]:
    """Step points (seconds, cumulative xG) per team, starting at (0, 0) and ending at the clock."""
    out = {}
    for team in team_ids:
        total, pts = 0.0, [(0, 0.0)]
        for e in events:
            if e["team_id"] == team and e["type"] in SHOT_TYPES and e.get("xg") is not None and event_time(e) <= clock:
                total = round(total + e["xg"], 2)
                pts.append((event_time(e), total))
        pts.append((clock, total))
        out[team] = pts
    return out


def xg_totals(events: list[dict], team_ids: tuple[str, str], clock: int) -> dict[str, dict]:
    shots = [e for e in events if e["type"] in SHOT_TYPES and e.get("xg") is not None and event_time(e) <= clock]
    return {t: {"xg": round(sum(e["xg"] for e in shots if e["team_id"] == t), 2),
                "shots": sum(e["team_id"] == t for e in shots)} for t in team_ids}


def xg_figure(events: list[dict], teams: tuple[dict, dict], colors: dict[str, str], clock: int, ink: str = "#334155"):
    ids = (teams[0]["id"], teams[1]["id"])
    timeline = xg_timeline(events, ids, clock)
    fig = go.Figure()
    for team in teams:
        pts = timeline[team["id"]]
        fig.add_trace(go.Scatter(x=[p[0] / 60 for p in pts], y=[p[1] for p in pts], mode="lines", name=team["name"],
                                 line={"color": colors[team["id"]], "width": 2.5, "shape": "hv"},
                                 hovertemplate=team["name"] + " %{y:.2f} xG<extra></extra>"))
    for e in events:
        if e["type"] == "goal" and event_time(e) <= clock:
            y = next(v for s, v in timeline[e["team_id"]] if s == event_time(e))
            fig.add_annotation(x=event_time(e) / 60, y=y, text="⚽", showarrow=False, yshift=12)
    fig.add_vline(x=45, line={"color": "#94a3b8", "width": 1, "dash": "dot"})
    fig.update_layout(height=240, margin={"l": 4, "r": 4, "t": 10, "b": 24}, showlegend=True,
                      legend={"orientation": "h", "y": 1.14, "x": 0},
                      xaxis={"title": None, "ticksuffix": "'", "color": ink, "range": [0, max(clock, 600) / 60]},
                      yaxis={"title": "xG", "color": ink, "rangemode": "tozero"},
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    return fig
