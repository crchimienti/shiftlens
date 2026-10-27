"""Animated sequence player: one move replayed in the browser with Plotly animation frames (Play / Pause / Restart
and a step slider inside the chart; no server reruns, and it never moves the match clock).

Event-based reconstruction on the synthetic coordinates, not tracking:
- the ball travels from an action's start (x, y) to its recorded end (end_x, end_y); with no end it does not move
- between two actions the ball jumps to the next action's start (no invented path for the gap)
- only the acting player is drawn; their marker moves only during a carry
- reduced motion: no interpolated movement, each step is shown in place
Coordinates are in the acting team's frame; the home team attacks left → right on screen, the away team is mirrored.
"""
from __future__ import annotations

import textwrap

import plotly.graph_objects as go

from .pitch import AWAY_COLOR, HOME_COLOR, _pitch_shapes, action_label

LABEL = "Animated reconstruction of recorded synthetic events · interpolated between recorded points · not tracking"
MOVE_STEPS, HOLD_STEPS = 8, 3
MOVING = ("pass", "carry", "cross", "shot", "goal", "free_kick", "corner")
WRAP = 70


def screen_xy(x: float, y: float, attacks_right: bool) -> tuple[float, float]:
    return (x, y) if attacks_right else (100 - x, 100 - y)


def _surname(players: dict, pid) -> str:
    return players.get(pid, {}).get("name", "").split()[-1] if pid else ""


def describe(ev: dict, players: dict, team_names: dict) -> str:
    who = players.get(ev.get("player_id"), {}).get("name") or team_names.get(ev["team_id"], ev["team_id"])
    out = f" ({ev['outcome'].replace('_', ' ')})" if ev.get("outcome") else ""
    xg = f" · synthetic xG {ev['xg']:.2f}" if ev.get("xg") is not None else ""
    return f"{ev['minute']:02d}:{ev['second']:02d} · {who}: {action_label(ev['type'])}{out}{xg}"


def frames_for(events: list[dict], players: dict, home_id: str, reduce_motion: bool = False) -> list[dict]:
    """Plain frame descriptions (testable): ball, actor marker, path drawn so far, step index."""
    out, trail = [], []
    seq = [e for e in events if e.get("x") is not None]
    for i, e in enumerate(seq, 1):
        right = e["team_id"] == home_id
        start = screen_xy(e["x"], e["y"], right)
        end = screen_xy(e["end_x"], e["end_y"], right) if e.get("end_x") is not None and e["type"] in MOVING else None
        steps = 1 if reduce_motion else (MOVE_STEPS if end else HOLD_STEPS)
        for k in range(steps + 1):
            f = 1.0 if reduce_motion and end else k / steps
            ball = (start[0] + (end[0] - start[0]) * f, start[1] + (end[1] - start[1]) * f) if end else start
            out.append({"step": i, "sub": k, "ball": ball, "actor": ball if e["type"] == "carry" else start,
                        "actor_name": _surname(players, e.get("player_id")), "team_id": e["team_id"],
                        "path": (start, ball), "trail": list(trail), "event_id": e["event_id"],
                        "end_recorded": end is not None or e["type"] not in MOVING})
        if end:
            trail.append((start, end))
    return out


def animation_figure(events: list[dict], players: dict, home: dict, away: dict, start_step: int = 1,
                     reduce_motion: bool = False, height: int = 470):
    """start_step (1-based): the step shown before Play (the selected action); Restart goes back to step 1."""
    seq = [e for e in events if e.get("x") is not None]
    frames = frames_for(seq, players, home["id"], reduce_motion)
    total = len(seq)
    start_step = max(1, min(start_step, total))
    names = {home["id"]: home["name"], away["id"]: away["name"]}

    def traces(fr):
        tx, ty = [], []
        for a, b in fr["trail"]:
            tx += [a[0], b[0], None]
            ty += [a[1], b[1], None]
        ink = HOME_COLOR if fr["team_id"] == home["id"] else AWAY_COLOR
        return [
            go.Scatter(x=tx or [None], y=ty or [None], mode="lines", hoverinfo="skip",
                       line={"color": "rgba(255,255,255,0.35)", "width": 1.5}),
            go.Scatter(x=[fr["path"][0][0], fr["path"][1][0]], y=[fr["path"][0][1], fr["path"][1][1]], mode="lines",
                       line={"color": ink, "width": 3}, hoverinfo="skip"),
            go.Scatter(x=[fr["actor"][0]], y=[fr["actor"][1]], mode="markers+text", text=[fr["actor_name"]],
                       textposition="top center", textfont={"color": "white", "size": 12}, hoverinfo="skip",
                       marker={"size": 16, "color": ink, "line": {"color": "white", "width": 2}}),
            go.Scatter(x=[fr["ball"][0]], y=[fr["ball"][1]], mode="markers", hoverinfo="skip",
                       marker={"size": 10, "color": "white", "line": {"color": "#111827", "width": 2}}),
        ]

    def title(fr):
        return f"<b>Animated step {fr['step']} of {total}</b>"

    def caption(fr):
        e = seq[fr["step"] - 1]
        text = describe(e, players, names) + ("" if fr["end_recorded"] else " · end point not recorded")
        lines = textwrap.wrap(f"Step {fr['step']}: {text}", WRAP)[:2]
        return [{"text": "<br>".join(lines), "x": 0, "y": -0.015, "xref": "paper", "yref": "paper",
                 "xanchor": "left", "yanchor": "top", "align": "left", "showarrow": False, "font": {"size": 13}}]

    keys = [f"s{fr['step']}_{fr['sub']}" for fr in frames]
    first = next(fr for fr in frames if fr["step"] == start_step and fr["sub"] == 0)
    fig = go.Figure(data=traces(first),
                    frames=[go.Frame(name=n, data=traces(fr), layout={"title": {"text": title(fr)},
                                                                       "annotations": caption(fr)})
                            for n, fr in zip(keys, frames)])
    play = {"frame": {"duration": 600 if reduce_motion else 110, "redraw": True}, "transition": {"duration": 0},
            "fromcurrent": True}
    fig.update_layout(
        shapes=_pitch_shapes(strong=True), height=height,
        title={"text": title(first), "font": {"size": 13}, "x": 0.01, "y": 0.99, "yanchor": "top"},
        annotations=caption(first), margin={"l": 4, "r": 4, "t": 30, "b": 150}, showlegend=False,
        xaxis={"range": [-3, 103], "visible": False, "fixedrange": True},
        yaxis={"range": [-3, 103], "visible": False, "fixedrange": True, "scaleanchor": "x", "scaleratio": 0.68},
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        updatemenus=[{"type": "buttons", "direction": "left", "x": 0, "y": -0.16, "xanchor": "left", "yanchor": "top",
                      "pad": {"t": 0, "r": 6, "b": 0, "l": 0}, "showactive": False, "font": {"size": 13},
                      "buttons": [
                          {"label": "▶ Play", "method": "animate", "args": [None, play]},
                          {"label": "⏸ Pause", "method": "animate",
                           "args": [[None], {"mode": "immediate", "frame": {"duration": 0}, "transition": {"duration": 0}}]},
                          {"label": "⟲ Restart", "method": "animate", "args": [keys, {**play, "fromcurrent": False}]}]}],
        sliders=[{"active": start_step - 1, "x": 0, "len": 1, "y": -0.31, "yanchor": "top",
                  "currentvalue": {"visible": False}, "pad": {"t": 0, "b": 0, "l": 8, "r": 8}, "font": {"size": 12},
                  "steps": [{"label": str(fr["step"]), "method": "animate",
                             "args": [[n], {"mode": "immediate", "frame": {"duration": 0, "redraw": True},
                                            "transition": {"duration": 0}}]}
                            for n, fr in zip(keys, frames) if fr["sub"] == 0]}])
    return fig
