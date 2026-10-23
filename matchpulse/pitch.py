"""Schematic pitch and key-move helpers. Deterministic; derived only from zone, lane, team and order.

There are no tracking coordinates in the data. Each event is placed at the centre of its
zone × lane cell (as seen by the acting team), with a small fixed offset when several events of the
same move share a cell. Curves and styling are presentation only; positions are schematic, never measured.
"""
from __future__ import annotations

import math

from .metrics import _sequence_summary, event_time, event_weight, momentum_at
from .replay import clock_label
from .threat import NO_GAIN, THREAT_SCALE, threat_color

# Pitch drawn 0–100 on both axes. The home team attacks left → right in both halves (broadcast
# convention for the schematic); the away team attacks right → left.
ZONE_X = {"own_box": 8, "defensive_third": 24, "middle_third": 50, "attacking_third": 75, "opp_box": 91}
LANE_Y = {"left": 80, "center": 50, "right": 20, None: 50}
# Offsets for the 1st, 2nd, 3rd… event of a move in the same cell: step towards goal, alternate sides.
STACK_OFFSETS = ((0, 0), (4, 4), (8, -3), (12, 3), (16, -4))

ACTION_LABELS = {"free_kick": "Free kick", "kickoff": "Kick-off"}


def action_label(event_type: str) -> str:
    return ACTION_LABELS.get(event_type, event_type.replace("_", " ").capitalize())


def schematic_xy(zone: str, lane: str | None, attacks_right: bool, stack: int = 0) -> tuple[float, float]:
    """Pitch position for a zone/lane seen from the acting team, mirrored for the side attacking left."""
    dx, dy = STACK_OFFSETS[min(stack, len(STACK_OFFSETS) - 1)]
    dx += 4 * max(0, stack - len(STACK_OFFSETS) + 1)
    x = min(ZONE_X[zone] + dx, 97)
    y = max(3, min(97, LANE_Y[lane] + dy))
    return (x, y) if attacks_right else (100 - x, 100 - y)


def corner_xy(lane: str | None, attacks_right: bool) -> tuple[float, float]:
    """Corner flag on the lane's side of the attacked goal (left lane / default → left flag)."""
    x, y = 99, (3 if lane == "right" else 97)
    return (x, y) if attacks_right else (100 - x, 100 - y)


def move_events(snapshot: dict, sequence_id: str) -> list[dict]:
    return [ev for ev in snapshot["events"] if ev["sequence_id"] == sequence_id]


def all_moves(snapshot: dict, match: dict, config: dict) -> list[dict]:
    """Every move (sequence) played so far, latest first, with the same summary fields as key moves."""
    seqs: dict[str, list[dict]] = {}
    for ev in snapshot["events"]:
        seqs.setdefault(ev["sequence_id"], []).append(ev)
    moves = [_sequence_summary(sid, evs, match, config) for sid, evs in seqs.items()]
    return sorted(moves, key=lambda m: (-m["start_seconds"], m["sequence_id"]))


def move_points(events: list[dict], home_id: str, players: dict, config: dict) -> list[dict]:
    """One plotting point per event, in order, with stable schematic positions."""
    seen: dict[tuple, int] = {}
    points = []
    for i, ev in enumerate(events, 1):
        cell = (ev["team_id"], ev["zone"], ev["lane"])
        stack = seen.get(cell, 0)
        seen[cell] = stack + 1
        attacks_right = ev["team_id"] == home_id
        if ev["type"] == "corner":  # by definition taken at the corner flag on its side
            x, y = corner_xy(ev["lane"], attacks_right)
        else:
            x, y = schematic_xy(ev["zone"], ev["lane"], attacks_right, stack)
        player = players.get(ev["player_id"], {}).get("name", "") if ev["player_id"] else ""
        points.append({"step": i, "x": x, "y": y, "event_id": ev["event_id"], "team_id": ev["team_id"],
                       "type": ev["type"], "action": action_label(ev["type"]), "outcome": ev["outcome"],
                       "player": player, "time": clock_label(event_time(ev)), "attacks_right": attacks_right,
                       "weight": round(event_weight(ev, config), 2)})
    return points


def chain_summary(events: list[dict]) -> str:
    """'Interception → Carry → Shot (saved) → Save'."""
    parts = []
    for ev in events:
        label = action_label(ev["type"])
        if ev["type"] == "shot" and ev["outcome"]:
            label += f" ({ev['outcome'].replace('_', ' ')})"
        parts.append(label)
    return " → ".join(parts)


def move_stats(events: list[dict], team_id: str, attacking_zones) -> dict:
    """Plain counts for the selected move, from the move's own events."""
    own = [ev for ev in events if ev["team_id"] == team_id]
    zones = set(attacking_zones)
    times = [event_time(ev) for ev in events]
    return {
        "actions": len(own),
        "passes": sum(1 for ev in own if ev["type"] == "pass"),
        "attacking_actions": sum(1 for ev in own if ev["zone"] in zones),
        "shots": sum(1 for ev in own if ev["type"] in ("shot", "goal")),
        "players": len({ev["player_id"] for ev in own if ev["player_id"]}),
        "duration_seconds": (max(times) - min(times)) if times else 0,
    }


def momentum_trend(match: dict, config: dict, at: int, step: int = 30) -> list[tuple[int, float]]:
    """Existing momentum value sampled every `step` seconds up to `at` (no new formula)."""
    times = list(range(0, at + 1, step))
    if not times or times[-1] != at:
        times.append(at)
    return [(t, momentum_at(match, config, t)[0]) for t in times]


# --- rendering (Plotly) -----------------------------------------------------

HOME_COLOR, AWAY_COLOR = "#2563eb", "#ea580c"
LINE_COLOR, GRASS, GRASS_STRIPE = "rgba(255,255,255,0.85)", "#2f7d4a", "#2a7343"
GOLD = "#facc15"
SYMBOLS = {"pass": "circle", "carry": "circle-open", "dribble": "diamond-open", "cross": "triangle-up",
           "shot": "triangle-right", "goal": "star", "save": "square", "corner": "diamond", "free_kick": "diamond",
           "foul": "x", "tackle": "hexagon", "interception": "hexagon", "clearance": "square-open",
           "offside": "x-thin-open", "kickoff": "circle-dot"}
SIZES = {"goal": 24, "shot": 17, "cross": 14, "corner": 14, "free_kick": 13, "save": 13, "dribble": 12,
         "tackle": 11, "interception": 11, "foul": 11, "offside": 11, "clearance": 11, "pass": 10, "carry": 9}
# How the ball travels *from* an event to the next one: (curve bend, line dash, width).
PATH_STYLE = {"pass": (0.12, "solid", 2), "cross": (0.35, "solid", 2.5), "corner": (0.3, "solid", 2.5),
              "free_kick": (0.2, "solid", 2.5), "carry": (0.0, "dash", 2), "dribble": (0.06, "dot", 2.5),
              "shot": (0.0, "solid", 3.5)}
DEFAULT_PATH = (0.0, "dot", 1.2)  # turnovers, saves, clearances


def _curve(a: dict, b: dict, bend: float, flip: bool) -> tuple[str, tuple[float, float]]:
    """Quadratic Bézier from a to b; returns the SVG path and its control point."""
    mx, my = (a["x"] + b["x"]) / 2, (a["y"] + b["y"]) / 2
    dx, dy = b["x"] - a["x"], b["y"] - a["y"]
    sign = -1 if flip else 1
    cx, cy = mx - dy * bend * sign, my + dx * bend * sign
    return f"M {a['x']},{a['y']} Q {cx},{cy} {b['x']},{b['y']}", (cx, cy)


# Five tactical lanes across the pitch (wing, half-space, centre, half-space, wing). The boundaries follow
# the penalty-box and six-yard-box edges, the usual convention for half-spaces.
FIVE_LANES = (0, 21, 37, 63, 79, 100)
FIVE_LANE_NAMES = ("Wing", "Half-space", "Centre", "Half-space", "Wing")


def _pitch_shapes(tactical: bool = False, simple: bool = False) -> list[dict]:
    """Pitch markings. `simple` drops the guide lines (Fan Lens); `tactical` draws the five-lane grid."""
    line = {"color": LINE_COLOR, "width": 1.5}
    faint = {"color": "rgba(255,255,255,0.3)", "width": 1, "dash": "dot"}
    s = [{"type": "rect", "x0": 0, "y0": 0, "x1": 100, "y1": 100, "line": line, "fillcolor": GRASS, "layer": "below"}]
    s += [{"type": "rect", "x0": x, "y0": 0, "x1": x + 10, "y1": 100, "line": {"width": 0},
           "fillcolor": GRASS_STRIPE, "layer": "below"} for x in range(0, 100, 20)]
    s += [
        {"type": "line", "x0": 50, "y0": 0, "x1": 50, "y1": 100, "line": line},
        {"type": "circle", "x0": 41, "y0": 37, "x1": 59, "y1": 63, "line": line},
        {"type": "rect", "x0": 0, "y0": 21, "x1": 16, "y1": 79, "line": line},
        {"type": "rect", "x0": 84, "y0": 21, "x1": 100, "y1": 79, "line": line},
        {"type": "rect", "x0": 0, "y0": 37, "x1": 5, "y1": 63, "line": line},
        {"type": "rect", "x0": 95, "y0": 37, "x1": 100, "y1": 63, "line": line},
        {"type": "rect", "x0": -2, "y0": 45, "x1": 0, "y1": 55, "line": line},
        {"type": "rect", "x0": 100, "y0": 45, "x1": 102, "y1": 55, "line": line},
    ]
    if simple:
        return s
    s += [{"type": "line", "x0": x, "y0": 0, "x1": x, "y1": 100, "line": faint} for x in (33.3, 66.7)]
    if tactical:
        s += [{"type": "rect", "x0": 0, "y0": lo, "x1": 100, "y1": hi, "line": {"width": 0},
               "fillcolor": "rgba(255,255,255,0.07)", "layer": "below"}
              for lo, hi in ((FIVE_LANES[1], FIVE_LANES[2]), (FIVE_LANES[3], FIVE_LANES[4]))]
        lane = {"color": "rgba(255,255,255,0.45)", "width": 1, "dash": "dash"}
        s += [{"type": "line", "x0": 0, "y0": y, "x1": 100, "y1": y, "line": lane} for y in FIVE_LANES[1:-1]]
    else:
        s += [{"type": "line", "x0": 0, "y0": y, "x1": 100, "y1": y, "line": faint} for y in (33.3, 66.7)]
    return s


def _path_shapes(points: list[dict], color: dict, threat: dict | None = None,
                 focus: str | None = None) -> tuple[list[dict], list[dict]]:
    """Curved action paths and one arrowhead annotation per step (deterministic). With `threat`
    (event_id -> threat move), a path is coloured by the threat gain of the action it starts from; actions
    without a measured gain (turnovers, shots, saves) keep the team colour. With `focus`, paths that do not
    touch the focused event are dimmed."""
    shapes, arrows = [], []
    for i, (a, b) in enumerate(zip(points, points[1:])):
        bend, dash, width = PATH_STYLE.get(a["type"], DEFAULT_PATH)
        path, (cx, cy) = _curve(a, b, bend, flip=bool(i % 2) != a["attacks_right"])
        move = (threat or {}).get(a["event_id"])
        ink = threat_color(move["gain"]) if move else color[b["team_id"]]
        opacity = 0.9 if not focus or focus in (a["event_id"], b["event_id"]) else 0.3
        shapes.append({"type": "path", "path": path, "line": {"color": ink, "width": width + (1 if move else 0),
                                                                "dash": dash}, "opacity": opacity})
        tx, ty = b["x"] - cx, b["y"] - cy  # tangent at the end of the curve
        norm = math.hypot(tx, ty) or 1.0
        arrows.append({"x": b["x"], "y": b["y"], "ax": b["x"] - tx / norm * 3, "ay": b["y"] - ty / norm * 3,
                       "xref": "x", "yref": "y", "axref": "x", "ayref": "y", "showarrow": True, "arrowhead": 2,
                       "arrowsize": 1.2, "arrowwidth": width, "arrowcolor": ink, "opacity": opacity, "text": ""})
    for p in points:  # a scoring shot goes into the net; a shot off target flies past the post
        gx = 101 if p["attacks_right"] else -1
        if p["type"] == "goal":
            shapes.append({"type": "line", "x0": p["x"], "y0": p["y"], "x1": gx, "y1": 50,
                           "line": {"color": GOLD, "width": 4}})
        elif p["type"] == "shot" and p["outcome"] == "off_target":
            wide = 62 if p["y"] >= 50 else 38
            shapes.append({"type": "line", "x0": p["x"], "y0": p["y"], "x1": gx, "y1": wide,
                           "line": {"color": color[p["team_id"]], "width": 2.5, "dash": "dash"}})
    return shapes, arrows


def _swatch(c: str, text: str) -> str:
    return f"<span style='color:{c}'>■</span> {text}"


def _hex(rgb: tuple) -> str:
    return "#%02x%02x%02x" % rgb


THREAT_LEGEND = ("Path colour = threat gain (Zone Threat grid): " + _swatch(NO_GAIN, "none / back") + "  "
                 + "  ".join(_swatch(_hex(c), f"+{g:.2f}") for g, c in THREAT_SCALE[1:])
                 + "  · team colour = not measured")
SYMBOL_LEGEND = "● pass  ◌ carry (dashed)  ◇ dribble  ▲ cross  ▶ shot  ★ goal  ■ save  ⬡ tackle / interception"


def _threat_hover(move: dict | None) -> str:
    if not move:
        return ""
    return f"<br>Threat {move['from']:.2f} → {move['to']:.2f} (gain {move['gain']:+.2f}, grid proxy)"


def pitch_figure(points: list[dict], home: dict, away: dict, detailed: bool = False,
                 highlight: str | None = None, palette: dict | None = None, threat: dict | None = None,
                 underlay: list[dict] | None = None):
    """Schematic pitch with the move as a curved action chain.

    detailed (Analyst Lens): step numbers, the five-lane tactical grid with lane and third labels and a legend.
    Otherwise (Fan Lens): clean pitch, goal emphasis only. `highlight` rings one event (event_id) and dims the
    rest. `threat` (event_id -> threat move) colours paths by threat gain; `underlay` adds background cell
    shapes (e.g. the Zone Threat grid) just above the grass."""
    import plotly.graph_objects as go

    color = {home["id"]: HOME_COLOR, away["id"]: AWAY_COLOR}
    pal = {"label": "#64748b", "home_text": HOME_COLOR, "away_text": AWAY_COLOR, **(palette or {})}
    focus = next((p for p in points if p["event_id"] == highlight), None)
    paths, arrows = _path_shapes(points, color, threat, focus["event_id"] if focus else None)
    fig = go.Figure()
    for arrow in arrows:
        fig.add_annotation(**arrow)
    goals = [p for p in points if p["type"] == "goal"]
    if goals:  # soft halo under the scoring action, drawn first so the star sits on top
        fig.add_trace(go.Scatter(x=[p["x"] for p in goals], y=[p["y"] for p in goals], mode="markers", name="Goal",
                                 marker={"size": 46, "color": "rgba(250,204,21,0.28)", "line": {"width": 0}},
                                 hoverinfo="skip"))
    for team in (home, away):
        pts = [p for p in points if p["team_id"] == team["id"]]
        if not pts:
            continue
        labels = [str(p["step"]) if detailed else
                  (f"⚽ {p['player'].split()[-1]}" if p["type"] == "goal" and p["player"] else "") for p in pts]
        fig.add_trace(go.Scatter(
            x=[p["x"] for p in pts], y=[p["y"] for p in pts], mode="markers+text",
            name=team["name"], text=labels, textposition="top center",
            textfont={"color": "white", "size": 12 if detailed else 16},
            marker={"color": [GOLD if p["type"] == "goal" else color[team["id"]] for p in pts],
                    "size": [SIZES.get(p["type"], 10) for p in pts],
                    "symbol": [SYMBOLS.get(p["type"], "circle") for p in pts],
                    "opacity": [1.0 if not focus or p is focus else 0.35 for p in pts],
                    "line": {"color": "white", "width": 1.5}},
            customdata=[[p["step"], p["time"], p["action"], p["outcome"] or "", p["player"], p["event_id"],
                         _threat_hover((threat or {}).get(p["event_id"]))] for p in pts],
            hovertemplate="%{customdata[0]}. %{customdata[1]} · %{customdata[2]} %{customdata[3]}"
                          "<br>%{customdata[4]} · %{customdata[5]}%{customdata[6]}<extra></extra>",
        ))
    if focus:
        fig.add_trace(go.Scatter(x=[focus["x"]], y=[focus["y"]], mode="markers", name="Selected action",
                                 marker={"size": 34, "color": "rgba(0,0,0,0)", "line": {"color": GOLD, "width": 3}},
                                 hovertemplate=f"Selected: {focus['time']} · {focus['action']}<extra></extra>"))
        callout = f"{focus['time']} · {focus['action']}" + (f" · {focus['player']}" if focus["player"] else "")
        fig.add_annotation(x=focus["x"], y=min(focus["y"] + 9, 101), text=f"<b>{callout}</b>", showarrow=False,
                           font={"size": 11, "color": "#111827"}, bgcolor="rgba(250,204,21,0.92)", borderpad=3)
    if detailed:
        for (lo, hi), name in zip(zip(FIVE_LANES, FIVE_LANES[1:]), FIVE_LANE_NAMES):
            fig.add_annotation(x=101.5, y=(lo + hi) / 2, text=name, showarrow=False, textangle=90,
                               font={"size": 8, "color": pal["label"]})
        for x, name in ((16.7, "Defensive third"), (50, "Middle third"), (83.3, "Final third")):
            fig.add_annotation(x=x, y=-3, text=f"{name} ({home['id']})", showarrow=False,
                               font={"size": 8, "color": pal["label"]})
        legend = [THREAT_LEGEND, SYMBOL_LEGEND] if threat is not None else [SYMBOL_LEGEND]
        for i, text in enumerate(legend):
            fig.add_annotation(x=0, y=-8 - 5 * i, text=text, showarrow=False, xanchor="left",
                               font={"size": 9, "color": pal["label"]})
    fig.add_annotation(x=99, y=105, text=f"{home['name']} attack →", showarrow=False, xanchor="right",
                       font={"color": pal["home_text"], "size": 11})
    fig.add_annotation(x=1, y=105, text=f"← {away['name']} attack", showarrow=False, xanchor="left",
                       font={"color": pal["away_text"], "size": 11})
    markings = _pitch_shapes(tactical=detailed, simple=not detailed)
    bottom = (-11 - 5 * (threat is not None)) if detailed else -6
    grass = [s for s in markings if s.get("layer") == "below"]  # pitch + stripes, then the underlay, then lines
    lines = [s for s in markings if s.get("layer") != "below"]
    fig.update_layout(shapes=grass + list(underlay or []) + lines + paths,
                      height=380 + (40 if detailed else 0), margin={"l": 4, "r": 4, "t": 18, "b": 4},
                      xaxis={"range": [-3, 103], "visible": False, "fixedrange": True},
                      yaxis={"range": [bottom, 109], "visible": False, "fixedrange": True, "scaleanchor": "x",
                             "scaleratio": 0.68},
                      showlegend=False, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    return fig


def momentum_figure(trend: list[tuple[int, float]], home: dict, away: dict,
                    goals: list[tuple[int, str]] | None = None, turning: tuple[int, int, str] | None = None,
                    ink: str = "#334155"):
    """Match flow: the momentum value as a smoothed tide (home above, away below), with goals and the
    turning point marked. Smoothing is visual only; hover shows the exact sampled values."""
    import plotly.graph_objects as go

    xs = [t / 60 for t, _ in trend]
    color = {home["id"]: HOME_COLOR, away["id"]: AWAY_COLOR}
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=xs, y=[max(v, 0) for _, v in trend], fill="tozeroy", mode="lines",
                             line={"width": 0, "shape": "spline", "smoothing": 0.6},
                             fillcolor="rgba(37,99,235,0.40)", hoverinfo="skip", name=home["name"]))
    fig.add_trace(go.Scatter(x=xs, y=[min(v, 0) for _, v in trend], fill="tozeroy", mode="lines",
                             line={"width": 0, "shape": "spline", "smoothing": 0.6},
                             fillcolor="rgba(234,88,12,0.40)", hoverinfo="skip", name=away["name"]))
    fig.add_trace(go.Scatter(x=xs, y=[v for _, v in trend], mode="lines",
                             line={"color": ink, "width": 1.5, "shape": "spline", "smoothing": 0.6},
                             customdata=[clock_label(t) for t, _ in trend],
                             hovertemplate="%{customdata}: %{y:+.2f}<extra></extra>"))
    fig.add_hline(y=0, line={"color": "#94a3b8", "width": 1})
    if turning:
        fig.add_vrect(x0=turning[0] / 60, x1=turning[1] / 60, fillcolor="rgba(250,204,21,0.25)", line_width=0)
        fig.add_annotation(x=turning[1] / 60, y=1.0, text="turning point", showarrow=False, yanchor="top",
                           xanchor="right", font={"size": 10, "color": "#a16207"})
    for t, team_id in goals or []:
        fig.add_vline(x=t / 60, line={"color": color.get(team_id, ink), "width": 1.5, "dash": "dot"})
        fig.add_annotation(x=t / 60, y=-1.0, text="⚽", showarrow=False, yanchor="bottom", font={"size": 14})
    fig.update_layout(height=170, margin={"l": 4, "r": 4, "t": 4, "b": 20}, showlegend=False,
                      xaxis={"title": None, "ticksuffix": "'", "fixedrange": True},
                      yaxis={"range": [-1.05, 1.05], "visible": False, "fixedrange": True},
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    return fig


def pressure_bar_figure(value: float, home: dict, away: dict):
    """Tug-of-war split of recent pressure: away share from the left, home share from the right."""
    import plotly.graph_objects as go

    from .presentation import pressure_split

    home_pct, away_pct = pressure_split(value)
    fig = go.Figure()
    fig.add_trace(go.Bar(x=[away_pct], y=[""], orientation="h", marker={"color": AWAY_COLOR}, name=away["name"],
                         text=[f"{away['name']} {away_pct}%"], textposition="inside", insidetextanchor="start",
                         hovertemplate=f"{away['name']}: {away_pct}%<extra></extra>"))
    fig.add_trace(go.Bar(x=[home_pct], y=[""], orientation="h", marker={"color": HOME_COLOR}, name=home["name"],
                         text=[f"{home['name']} {home_pct}%"], textposition="inside", insidetextanchor="end",
                         hovertemplate=f"{home['name']}: {home_pct}%<extra></extra>"))
    fig.add_vline(x=50, line={"color": "white", "width": 2, "dash": "dot"})
    fig.update_layout(barmode="stack", height=56, margin={"l": 0, "r": 0, "t": 0, "b": 0}, showlegend=False,
                      bargap=0.15, uniformtext={"minsize": 10, "mode": "hide"},
                      xaxis={"range": [0, 100], "visible": False, "fixedrange": True},
                      yaxis={"visible": False, "fixedrange": True},
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    return fig
