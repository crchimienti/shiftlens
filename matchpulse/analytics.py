"""Advanced analytics proxies for the synthetic event model. Deterministic, documented, display-only.

Nothing here is xG, xA or xT, and nothing feeds the 8 core metrics or the explanation validator.
Every value is derived from fields the data actually has: event type, outcome, zone, lane, team,
player, sequence order. See docs/methods.md, "Advanced proxies".
"""
from __future__ import annotations

from .metrics import event_time
from .pitch import schematic_xy
from .replay import clock_label

# --- Shot Quality Index (SQI) -------------------------------------------------
# A transparent 0–1 index of how promising a shot's situation was, from where it was taken (zone, lane)
# and the action that set it up. It is NOT a probability and NOT xG.
SQI_ZONE_BASE = {"opp_box": 0.45, "attacking_third": 0.18, "middle_third": 0.05, "defensive_third": 0.02,
                 "own_box": 0.02}
SQI_LANE_FACTOR = {"center": 1.0, "left": 0.75, "right": 0.75, None: 0.9}
SQI_SETUP_BONUS = {"cross": 0.08, "dribble": 0.06, "corner": 0.05, "free_kick": 0.04, "pass": 0.03}
SQI_CAP = 0.95
SHOT_TYPES = ("shot", "goal")
PASS_LIKE = ("pass", "cross", "corner", "free_kick")
DEFENSIVE_TYPES = ("tackle", "interception", "clearance", "save")


def shot_quality(zone: str, lane: str | None, setup_type: str | None) -> float:
    base = SQI_ZONE_BASE.get(zone, 0.02) * SQI_LANE_FACTOR.get(lane, 0.9)
    bonus = SQI_SETUP_BONUS.get(setup_type, 0.0) if setup_type else 0.0
    if setup_type == "pass" and zone == "opp_box":
        bonus += 0.03  # a pass played inside the box (cut-back / through ball proxy)
    return round(min(base + bonus, SQI_CAP), 2)


def _setup(events: list[dict], i: int) -> dict | None:
    """The previous action of the same team in the same move, if a different player made it."""
    ev = events[i]
    prev = events[i - 1] if i > 0 else None
    if prev and prev["sequence_id"] == ev["sequence_id"] and prev["team_id"] == ev["team_id"] \
            and prev.get("player_id") and prev["player_id"] != ev.get("player_id"):
        return prev
    return None


def shots(events: list[dict], home_id: str) -> list[dict]:
    """Every shot or goal so far with its SQI, setup action and schematic position."""
    out = []
    seen: dict[tuple, int] = {}  # shots from the same cell get the fixed schematic offsets, not real positions
    for i, ev in enumerate(events):
        if ev["type"] not in SHOT_TYPES:
            continue
        cell = (ev["team_id"], ev["zone"], ev["lane"])
        stack = seen.get(cell, 0)
        seen[cell] = stack + 1
        setup = _setup(events, i)
        nxt = events[i + 1] if i + 1 < len(events) else None
        keeper = nxt if nxt and nxt["type"] == "save" and nxt["sequence_id"] == ev["sequence_id"] else None
        x, y = schematic_xy(ev["zone"], ev["lane"], ev["team_id"] == home_id, stack)
        out.append({"event_id": ev["event_id"], "team_id": ev["team_id"], "player_id": ev.get("player_id"),
                    "seconds": event_time(ev), "clock": clock_label(event_time(ev)),
                    "outcome": "goal" if ev["type"] == "goal" else (ev["outcome"] or "unknown"),
                    "sqi": shot_quality(ev["zone"], ev["lane"], setup["type"] if setup else None),
                    "setup_event_id": setup["event_id"] if setup else None,
                    "setup_player_id": setup["player_id"] if setup else None,
                    "setup_type": setup["type"] if setup else None,
                    "keeper_id": keeper["player_id"] if keeper else None, "x": x, "y": y})
    return out


def team_shot_summary(shot_list: list[dict], team_ids: tuple[str, str]) -> dict[str, dict]:
    out = {}
    for t in team_ids:
        own = [s for s in shot_list if s["team_id"] == t]
        total = round(sum(s["sqi"] for s in own), 2)
        out[t] = {"shots": len(own), "goals": sum(1 for s in own if s["outcome"] == "goal"),
                  "sqi_total": total, "sqi_avg": round(total / len(own), 2) if own else 0.0,
                  "best": max((s["sqi"] for s in own), default=0.0)}
    return out


def chance_creation(shot_list: list[dict]) -> dict[str, dict]:
    """Chance Creation Index per player: sum of the SQI of shots they set up; assists = setups of goals."""
    out: dict[str, dict] = {}
    for s in shot_list:
        pid = s["setup_player_id"]
        if not pid:
            continue
        row = out.setdefault(pid, {"cci": 0.0, "chances": 0, "assists": 0})
        row["cci"] = round(row["cci"] + s["sqi"], 2)
        row["chances"] += 1
        row["assists"] += s["outcome"] == "goal"
    return out


def prevented_danger(shot_list: list[dict]) -> dict[str, dict]:
    """Per goalkeeper: saves and the summed SQI of the shots they saved (Prevented Danger proxy)."""
    out: dict[str, dict] = {}
    for s in shot_list:
        if s["outcome"] == "saved" and s["keeper_id"]:
            row = out.setdefault(s["keeper_id"], {"saves": 0, "prevented": 0.0})
            row["saves"] += 1
            row["prevented"] = round(row["prevented"] + s["sqi"], 2)
    return out


def player_badges(events: list[dict]) -> dict[str, dict]:
    """Goals, assists (setup of a goal, see _setup) and cards per player, from the event chain only."""
    badges: dict[str, dict] = {}
    blank = lambda: {"goals": 0, "assists": 0, "yellow": 0, "red": 0}
    for i, ev in enumerate(events):
        pid = ev.get("player_id")
        if ev["type"] == "goal" and pid:
            badges.setdefault(pid, blank())["goals"] += 1
            setup = _setup(events, i)
            if setup:
                badges.setdefault(setup["player_id"], blank())["assists"] += 1
        elif ev["type"] in ("yellow_card", "red_card") and pid:  # not in schema 1.0.0; counted if present
            badges.setdefault(pid, blank())["yellow" if ev["type"] == "yellow_card" else "red"] += 1
    return badges


# --- zone activity, defensive actions, pass links ------------------------------

ZONE_ORDER = ("own_box", "defensive_third", "middle_third", "attacking_third", "opp_box")
ZONE_SPAN = {"own_box": (0, 16), "defensive_third": (16, 33.3), "middle_third": (33.3, 66.7),
             "attacking_third": (66.7, 84), "opp_box": (84, 100)}
LANE_SPAN = {"left": (66.7, 100), "center": (33.3, 66.7), "right": (0, 33.3), None: (33.3, 66.7)}


def zone_activity(events: list[dict], team_id: str, player_id: str | None = None) -> dict[tuple[str, str], int]:
    """Count of a team's (or one player's) actions per (zone, lane) cell, as the team sees the pitch.
    Counts, not positions."""
    out: dict[tuple[str, str], int] = {}
    for ev in events:
        if ev["team_id"] == team_id and (player_id is None or ev.get("player_id") == player_id):
            key = (ev["zone"], ev["lane"] or "center")
            out[key] = out.get(key, 0) + 1
    return out


def cell_rect(zone: str, lane: str, attacks_right: bool) -> tuple[float, float, float, float]:
    x0, x1 = ZONE_SPAN[zone]
    y0, y1 = LANE_SPAN[lane]
    if not attacks_right:
        x0, x1, y0, y1 = 100 - x1, 100 - x0, 100 - y1, 100 - y0
    return x0, y0, x1, y1


def defensive_actions(events: list[dict], home_id: str) -> list[dict]:
    """Tackles, interceptions, clearances and saves at schematic positions (stacked within a cell)."""
    seen: dict[tuple, int] = {}
    out = []
    for ev in events:
        if ev["type"] not in DEFENSIVE_TYPES:
            continue
        cell = (ev["team_id"], ev["zone"], ev["lane"])
        stack = seen.get(cell, 0)
        seen[cell] = stack + 1
        x, y = schematic_xy(ev["zone"], ev["lane"], ev["team_id"] == home_id, stack)
        out.append({"event_id": ev["event_id"], "team_id": ev["team_id"], "type": ev["type"],
                    "player_id": ev.get("player_id"), "clock": clock_label(event_time(ev)), "x": x, "y": y})
    return out


def pass_links(events: list[dict], team_id: str) -> dict[tuple[str, str], int]:
    """(from player, to player) → count, when a pass-like action is followed by the same team's next
    action in the same move by a different player. Links, not measured passes."""
    out: dict[tuple[str, str], int] = {}
    for a, b in zip(events, events[1:]):
        if (a["team_id"] == team_id and b["team_id"] == team_id and a["sequence_id"] == b["sequence_id"]
                and a["type"] in PASS_LIKE and a.get("player_id") and b.get("player_id")
                and a["player_id"] != b["player_id"]):
            key = (a["player_id"], b["player_id"])
            out[key] = out.get(key, 0) + 1
    return out


# --- ball progression (xT-like idea, honest version) ----------------------------------
# A "progressive action" is a pass, carry, dribble or cross whose next action by the same team in the same
# move happens in a more advanced zone. It counts how often a player moves the ball up the pitch. It is a
# count, not a threat value: there is no xT grid behind it.
PROGRESSIVE_TYPES = ("pass", "carry", "dribble", "cross")
ZONE_RANK = {z: i for i, z in enumerate(ZONE_ORDER)}


def progressive_actions(events: list[dict]) -> dict[str, dict]:
    """Per player: progressive actions and how many zones they gained in total."""
    out: dict[str, dict] = {}
    for a, b in zip(events, events[1:]):
        if (a["type"] in PROGRESSIVE_TYPES and a.get("player_id") and b["team_id"] == a["team_id"]
                and b["sequence_id"] == a["sequence_id"] and ZONE_RANK[b["zone"]] > ZONE_RANK[a["zone"]]):
            row = out.setdefault(a["player_id"], {"progressive": 0, "zones_gained": 0})
            row["progressive"] += 1
            row["zones_gained"] += ZONE_RANK[b["zone"]] - ZONE_RANK[a["zone"]]
    return out


def team_progression(events: list[dict], team_ids: tuple[str, str]) -> dict[str, int]:
    prog = progressive_actions(events)
    return {t: sum(r["progressive"] for p, r in prog.items() if p.startswith(f"{t}-")) for t in team_ids}


def average_action_positions(events: list[dict], team_id: str, attacks_right: bool) -> list[dict]:
    """Per player of `team_id`: the mean of the schematic cell centres of their actions so far (derived from
    zone × lane, not tracking). Same shape as lineup slots, plus the action count `n`."""
    sums: dict[str, list[float]] = {}
    for ev in events:
        if ev["team_id"] == team_id and ev.get("player_id"):
            x, y = schematic_xy(ev["zone"], ev["lane"], attacks_right)
            row = sums.setdefault(ev["player_id"], [0.0, 0.0, 0])
            row[0] += x
            row[1] += y
            row[2] += 1
    return [{"player_id": pid, "x": round(sx / n, 2), "y": round(sy / n, 2), "n": n}
            for pid, (sx, sy, n) in sorted(sums.items())]


# --- figures ---------------------------------------------------------------------

def _base_layout(fig, height: int = 300):
    from .pitch import _pitch_shapes

    fig.update_layout(shapes=_pitch_shapes() + list(fig.layout.shapes), height=height,
                      margin={"l": 4, "r": 4, "t": 6, "b": 4}, showlegend=False,
                      xaxis={"range": [-3, 103], "visible": False, "fixedrange": True},
                      yaxis={"range": [-3, 103], "visible": False, "fixedrange": True, "scaleanchor": "x",
                             "scaleratio": 0.68},
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    return fig


def zone_heatmap_figure(events: list[dict], team: dict, attacks_right: bool, color_rgb: str,
                        player_id: str | None = None):
    """Zone × lane activity grid for one team or one of its players (opacity ∝ count)."""
    import plotly.graph_objects as go

    counts = zone_activity(events, team["id"], player_id)
    peak = max(counts.values(), default=1)
    fig = go.Figure()
    shapes, xs, ys, texts = [], [], [], []
    for (zone, lane), n in counts.items():
        x0, y0, x1, y1 = cell_rect(zone, lane, attacks_right)
        shapes.append({"type": "rect", "x0": x0, "y0": y0, "x1": x1, "y1": y1, "line": {"width": 0},
                       "fillcolor": f"rgba({color_rgb},{0.15 + 0.7 * n / peak:.2f})"})
        xs.append((x0 + x1) / 2)
        ys.append((y0 + y1) / 2)
        texts.append(str(n))
    fig.update_layout(shapes=shapes)
    fig.add_trace(go.Scatter(x=xs, y=ys, mode="text", text=texts, textfont={"color": "white", "size": 12},
                             hoverinfo="skip"))
    return _base_layout(fig)


def defensive_map_figure(points: list[dict], home: dict, away: dict, colors: dict, players: dict):
    import plotly.graph_objects as go

    symbols = {"tackle": "x", "interception": "hexagon", "clearance": "triangle-up", "save": "square"}
    fig = go.Figure()
    for team in (home, away):
        pts = [p for p in points if p["team_id"] == team["id"]]
        if pts:
            fig.add_trace(go.Scatter(
                x=[p["x"] for p in pts], y=[p["y"] for p in pts], mode="markers", name=team["name"],
                marker={"symbol": [symbols[p["type"]] for p in pts], "size": 12, "color": colors[team["id"]],
                        "line": {"color": "white", "width": 1}},
                hovertext=[f"{p['clock']} · {p['type'].capitalize()} · "
                           f"{players.get(p['player_id'], {}).get('name', '')}" for p in pts], hoverinfo="text"))
    return _base_layout(fig)


def shot_map_figure(shot_list: list[dict], home: dict, away: dict, colors: dict, players: dict):
    """Schematic shot map: zone × lane positions. Size and opacity grow with SQI; the result sets the symbol
    (★ goal in gold, ● saved, ○ off target, ✕ blocked). Hover shows player, time, result and SQI."""
    import plotly.graph_objects as go

    style = {"goal": "star", "saved": "circle", "off_target": "circle-open", "blocked": "x-thin-open"}
    fig = go.Figure()
    for team in (home, away):
        own = [s for s in shot_list if s["team_id"] == team["id"]]
        if not own:
            continue
        fig.add_trace(go.Scatter(
            x=[s["x"] for s in own], y=[s["y"] for s in own], mode="markers", name=team["name"],
            marker={"symbol": [style.get(s["outcome"], "circle") for s in own],
                    "size": [9 + 16 * s["sqi"] + (6 if s["outcome"] == "goal" else 0) for s in own],
                    "color": ["#facc15" if s["outcome"] == "goal" else colors[team["id"]] for s in own],
                    "opacity": [0.45 + 0.55 * s["sqi"] / SQI_CAP for s in own],
                    "line": {"color": [colors[team["id"]] if s["outcome"] in ("off_target", "blocked") else "white"
                                       for s in own], "width": 2}},
            hovertext=[f"{s['clock']} · {players.get(s['player_id'], {}).get('name', '')} ({team['name']})<br>"
                       f"{s['outcome'].replace('_', ' ')} · SQI {s['sqi']:.2f}"
                       + (f" · set up by {players.get(s['setup_player_id'], {}).get('name', '')}"
                          if s["setup_player_id"] else "") for s in own], hoverinfo="text"))
    return _base_layout(fig)


def merged_links(links: dict, threat: dict | None = None) -> dict[tuple[str, str], dict]:
    """Both directions of a link merged: {(a, b) sorted: {"n": count, "gain": summed threat gain or None}}."""
    pairs: dict[tuple[str, str], dict] = {}
    for (a, b), n in links.items():
        row = pairs.setdefault(tuple(sorted((a, b))), {"n": 0, "gain": 0.0 if threat is not None else None})
        row["n"] += n
        if threat is not None:
            row["gain"] = round(row["gain"] + threat.get((a, b), 0.0), 2)
    return pairs


def pass_network_figure(links: dict, slots: list[dict], team: dict, color: str, players: dict,
                        threat: dict | None = None, player_threat: dict | None = None, label_top: int = 0):
    """Schematic pass network. Players sit at the given positions (formation slots or average action cells).
    Lines get thicker / more opaque with repeated links. With `threat` ((passer, receiver) -> summed threat
    gain) a line is coloured by the threat gain moved along it (grey = none); `label_top` writes the count on
    the busiest links. Hover a line or a player for the counts."""
    import plotly.graph_objects as go

    from .threat import threat_color

    pos = {s["player_id"]: (s["x"], s["y"]) for s in slots}
    fig = go.Figure()
    peak = max(links.values(), default=1)
    pairs = merged_links(links, threat)
    for (a, b), row in sorted(pairs.items()):
        n, gain = row["n"], row["gain"]
        if a in pos and b in pos:
            ink = threat_color(gain) if threat is not None else color
            hover = f"{players[a]['name']} ↔ {players[b]['name']} · {n} link(s)"
            if gain is not None:
                hover += f" · threat gain {gain:+.2f} (grid proxy)"
            fig.add_trace(go.Scatter(
                x=[pos[a][0], pos[b][0]], y=[pos[a][1], pos[b][1]], mode="lines",
                line={"color": ink, "width": 1 + 4 * min(n, peak) / peak}, opacity=0.4 + 0.5 * min(n, peak) / peak,
                hovertext=hover, hoverinfo="text"))
    drawn = [(k, r) for k, r in pairs.items() if k[0] in pos and k[1] in pos]
    for (a, b), row in sorted(drawn, key=lambda kv: (-kv[1]["n"], kv[0]))[:label_top]:
        fig.add_annotation(x=(pos[a][0] + pos[b][0]) / 2, y=(pos[a][1] + pos[b][1]) / 2, text=f"<b>{row['n']}</b>",
                           showarrow=False, font={"size": 10, "color": "#111827"}, bgcolor="rgba(255,255,255,0.85)",
                           borderpad=1)
    involvement = {pid: 0 for pid in pos}
    for (a, b), n in links.items():
        for pid in (a, b):
            if pid in involvement:
                involvement[pid] += n
    ids = list(pos)
    added = {p: (player_threat or {}).get(p, {}).get("added") for p in ids}
    fig.add_trace(go.Scatter(
        x=[pos[p][0] for p in ids], y=[pos[p][1] for p in ids], mode="markers+text",
        text=[players[p]["name"].split()[-1] for p in ids], textposition="bottom center",
        textfont={"color": "white", "size": 9},
        marker={"size": [9 + min(involvement[p], 6) * 1.5 for p in ids], "color": color,
                "line": {"color": "white", "width": 1.5}},
        hovertext=[f"{players[p]['name']} · {involvement[p]} links"
                   + (f" · threat added {added[p]:.2f}" if added[p] is not None else "") for p in ids],
        hoverinfo="text"))
    fig = _base_layout(fig, height=330)
    xs, ys = [x for x, _ in pos.values()], [y for _, y in pos.values()]
    if xs:  # zoom both axes to the area the formation occupies, so the network reads at panel size
        fig.update_xaxes(range=[max(-3, min(xs) - 8), min(103, max(xs) + 8)])
        fig.update_yaxes(range=[max(-3, min(ys) - 12), min(103, max(ys) + 12)])
    return fig
