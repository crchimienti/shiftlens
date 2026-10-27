"""Synthetic lineups and formations: a presentation layer only.

Formations and slots come from `config/lineups.json`, authored for display. They are not part of the
match data, are never read by metrics or explanations, and do not describe real positioning. When a
match has no entry, a deterministic fallback groups players by position (GK / DF / MF / FW).
"""
from __future__ import annotations

from .validator import ROOT, load_json

LINEUPS_PATH = ROOT / "config" / "lineups.json"
POSITION_ORDER = ("GK", "DF", "MF", "FW")


def load_lineups(path=LINEUPS_PATH) -> dict:
    try:
        return load_json(path)
    except FileNotFoundError:
        return {"matches": {}}


def formation_lines(formation: str) -> list[int]:
    """'4-2-3-1' → [4, 2, 3, 1] (outfield lines, back to front)."""
    return [int(n) for n in formation.split("-")]


def starters(team: dict) -> list[dict]:
    """The starting eleven (players without a `starter` flag count as starters: older single-squad data)."""
    return [p for p in team["players"] if p.get("starter", True)]


def bench(team: dict) -> list[dict]:
    return [p for p in team["players"] if not p.get("starter", True)]


def fallback_lineup(team: dict) -> dict:
    """Group starters by position, ordered by shirt number; formation label from the group sizes."""
    groups = {p: sorted((pl for pl in starters(team) if pl["position"] == p), key=lambda pl: pl["number"])
              for p in POSITION_ORDER}
    lines = [[pl["id"] for pl in groups[p]] for p in POSITION_ORDER if groups[p]]
    return {"formation": "-".join(str(len(line)) for line in lines[1:]), "lines": lines}


def team_lineup(match: dict, team: dict, lineups: dict) -> dict:
    entry = lineups.get("matches", {}).get(match["match_id"], {}).get(team["id"])
    return entry if entry else fallback_lineup(team)


def lineup_errors(match: dict, lineups: dict) -> list[str]:
    """Each team: formation matches the outfield lines, every starter appears exactly once, one goalkeeper line."""
    errors = []
    for team in (match["home_team"], match["away_team"]):
        lineup = team_lineup(match, team, lineups)
        ids = [pid for line in lineup["lines"] for pid in line]
        roster = {p["id"] for p in starters(team)}
        if sorted(ids) != sorted(roster):
            errors.append(f"{team['id']}: lineup players do not match the roster")
        if len(lineup["lines"][0]) != 1:
            errors.append(f"{team['id']}: first line must be the single goalkeeper")
        if formation_lines(lineup["formation"]) != [len(line) for line in lineup["lines"][1:]]:
            errors.append(f"{team['id']}: formation {lineup['formation']} does not match its lines")
    return errors


def lineup_slots(lineup: dict, attacks_right: bool) -> list[dict]:
    """Deterministic pitch slots in the team's own half (0–100 pitch). Lines spread evenly from goal to
    halfway; players spread evenly across each line, listed left → right as the team attacks."""
    lines = lineup["lines"]
    slots = []
    for li, line in enumerate(lines):
        depth = 5 + li * (43 / max(1, len(lines) - 1))  # goalkeeper at 5, front line near halfway (48)
        for pi, pid in enumerate(line):
            lateral = 100 * (pi + 1) / (len(line) + 1)  # left of the attacking team first
            x, y = depth, 100 - lateral
            if not attacks_right:
                x, y = 100 - x, 100 - y
            slots.append({"player_id": pid, "line": li, "x": round(x, 2), "y": round(y, 2)})
    return slots


def lineup_figure(match: dict, lineups: dict, home_color: str, away_color: str, card_counts: dict | None = None):
    """Both teams on one schematic pitch: home in the left half attacking right, away mirrored."""
    import plotly.graph_objects as go

    from .pitch import _pitch_shapes

    players = {p["id"]: p for t in (match["home_team"], match["away_team"]) for p in t["players"]}
    fig = go.Figure()
    for team, attacks_right, color in ((match["home_team"], True, home_color), (match["away_team"], False, away_color)):
        lineup = team_lineup(match, team, lineups)
        slots = lineup_slots(lineup, attacks_right)
        cards = card_counts or {}
        fig.add_trace(go.Scatter(
            x=[s["x"] for s in slots], y=[s["y"] for s in slots], mode="markers+text", name=team["name"],
            marker={"size": 24, "color": color, "line": {"color": "white", "width": 2}},
            text=[str(players[s["player_id"]]["number"]) for s in slots], textfont={"color": "white", "size": 11},
            hovertext=[f"{players[s['player_id']]['name']} ({players[s['player_id']]['position']})"
                       + (" 🟨" * cards.get(s["player_id"], {}).get("yellow", 0))
                       + (" 🟥" * cards.get(s["player_id"], {}).get("red", 0)) for s in slots],
            hoverinfo="text"))
        fig.add_trace(go.Scatter(
            x=[s["x"] for s in slots], y=[s["y"] - 7 for s in slots], mode="text", hoverinfo="skip",
            text=[players[s["player_id"]]["name"].split()[-1] for s in slots],
            textfont={"color": "white", "size": 9}, showlegend=False))
        fig.add_annotation(x=25 if attacks_right else 75, y=106, showarrow=False,
                           text=f"<b>{team['name']}</b> · {lineup['formation']} "
                                f"{'→' if attacks_right else '←'}", font={"color": color, "size": 12})
    fig.update_layout(shapes=_pitch_shapes(), height=330, margin={"l": 4, "r": 4, "t": 22, "b": 4},
                      xaxis={"range": [-3, 103], "visible": False, "fixedrange": True},
                      yaxis={"range": [-4, 110], "visible": False, "fixedrange": True, "scaleanchor": "x",
                             "scaleratio": 0.68},
                      showlegend=False, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    return fig


# --- single-team vertical lineup (more legible) -----------------------------------

HALF_PITCH_RATIO = 52.5 / 68  # half-pitch length / width, so y units are drawn shorter than x units


def vertical_slots(lineup: dict) -> list[dict]:
    """Slots on a vertical half pitch, team attacking upwards: x = width (left of the attack on the left),
    y = 0 at the team's own goal line to 100 at halfway. Derived from `lineup_slots`; deterministic."""
    out = []
    for s in lineup_slots(lineup, attacks_right=True):
        out.append({**s, "x": round(100 - s["y"], 2), "y": round(min(96.0, s["x"] * 2), 2)})
    return out


def badge_text(badge: dict | None) -> str:
    """'⚽ 🅰️ 🟨' for one goal, assist and card; counts above one are compact: '⚽×2'. '' when none."""
    if not badge:
        return ""
    parts = []
    for key, icon in (("goals", "⚽"), ("assists", "🅰️"), ("yellow", "🟨"), ("red", "🟥")):
        n = badge.get(key, 0)
        if n:
            parts.append(icon if n == 1 else f"{icon}×{n}")
    return " ".join(parts)


def _half_pitch_shapes() -> list[dict]:
    line = {"color": "rgba(255,255,255,0.85)", "width": 1.5}
    s = [{"type": "rect", "x0": 0, "y0": 0, "x1": 100, "y1": 100, "line": line, "fillcolor": "#2f7d4a", "layer": "below"}]
    s += [{"type": "rect", "x0": 0, "y0": y, "x1": 100, "y1": y + 10, "line": {"width": 0}, "fillcolor": "#2a7343",
           "layer": "below"} for y in range(0, 100, 20)]
    s += [{"type": "rect", "x0": 21, "y0": 0, "x1": 79, "y1": 31, "line": line},
          {"type": "rect", "x0": 37, "y0": 0, "x1": 63, "y1": 10, "line": line},
          {"type": "rect", "x0": 45, "y0": -3, "x1": 55, "y1": 0, "line": line},
          {"type": "path", "path": "M 37,100 Q 50,66 63,100", "line": line}]  # centre-circle half in own half
    return s


def team_lineup_figure(team: dict, lineup: dict, color: str, players: dict, badges: dict | None = None,
                       detailed: bool = False, title_color: str | None = None):
    """One team on a vertical half pitch, attacking upwards. Fan: number, surname, badges.
    Analyst adds position labels and dashed guides for each line of the formation."""
    import plotly.graph_objects as go

    badges = badges or {}
    slots = vertical_slots(lineup)
    shapes = _half_pitch_shapes()
    if detailed:
        for y in sorted({s["y"] for s in slots})[1:]:
            shapes.append({"type": "line", "x0": 2, "y0": y, "x1": 98, "y1": y,
                           "line": {"color": "rgba(255,255,255,0.35)", "width": 1, "dash": "dot"}})
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=[s["x"] for s in slots], y=[s["y"] for s in slots], mode="markers+text",
        marker={"size": 26, "color": color, "line": {"color": "white", "width": 2}},
        text=[str(players[s["player_id"]]["number"]) for s in slots], textfont={"color": "white", "size": 12},
        hovertext=[f"{players[s['player_id']]['name']} · {players[s['player_id']]['position']}"
                   + (f" · {badge_text(badges.get(s['player_id']))}" if badges.get(s["player_id"]) else "")
                   for s in slots], hoverinfo="text"))
    labels = []
    for s in slots:
        p = players[s["player_id"]]
        label = p["name"].split()[-1]
        if detailed:
            label += f" · {p['position']}"
        labels.append(label)
    fig.add_trace(go.Scatter(x=[s["x"] for s in slots], y=[s["y"] - 8.5 for s in slots], mode="text",
                             text=labels, textfont={"color": "white", "size": 10}, hoverinfo="skip"))
    marked = [s for s in slots if badge_text(badges.get(s["player_id"]))]
    if marked:
        # badges hug the player (just right of the shirt), clamped inside the pitch
        fig.add_trace(go.Scatter(x=[min(s["x"] + 5, 90) for s in marked], y=[s["y"] + 1 for s in marked],
                                 mode="text", textposition="middle right",
                                 text=[badge_text(badges.get(s["player_id"])) for s in marked],
                                 textfont={"size": 12}, hoverinfo="skip"))
    fig.add_annotation(x=50, y=108, showarrow=False, text=f"<b>{team['name']}</b> · {lineup['formation']} · attacking ↑",
                       font={"color": title_color or color, "size": 13})
    fig.update_layout(shapes=shapes, height=420, margin={"l": 2, "r": 2, "t": 8, "b": 2}, showlegend=False,
                      xaxis={"range": [-3, 103], "visible": False, "fixedrange": True},
                      yaxis={"range": [-6, 112], "visible": False, "fixedrange": True, "scaleanchor": "x",
                             "scaleratio": HALF_PITCH_RATIO},
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    return fig
