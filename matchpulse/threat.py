"""Zone Threat: a fixed, published 5 × 3 grid of how dangerous it is to have the ball in each zone × lane cell,
and the threat gain of the actions that move the ball between cells. Deterministic, synthetic, display-only.

The grid is hand-set and versioned, not learned from data. It is NOT xT and NOT a probability: it only ranks
cells (closer to goal and more central = higher), so threat gain says how far up that ranking an action moved
the ball. It never feeds the 8 core metrics, the explanation request or the validator. See docs/methods.md.
"""
from __future__ import annotations

THREAT_VERSION = "1.0"

# Zone × lane values as seen by the acting team (zones and lanes are already relative to its attack).
ZONE_THREAT = {
    "own_box":         {"left": 0.01, "center": 0.01, "right": 0.01},
    "defensive_third": {"left": 0.02, "center": 0.03, "right": 0.02},
    "middle_third":    {"left": 0.05, "center": 0.07, "right": 0.05},
    "attacking_third": {"left": 0.10, "center": 0.16, "right": 0.10},
    "opp_box":         {"left": 0.24, "center": 0.40, "right": 0.24},
}
# Actions that move the ball to a team-mate's next action: the same set as pass links + ball carrying.
LINK_TYPES = ("pass", "cross", "corner", "free_kick")  # = analytics.PASS_LIKE (not imported: import cycle)
THREAT_TYPES = LINK_TYPES + ("carry", "dribble")


def cell_threat(zone: str, lane: str | None) -> float:
    return ZONE_THREAT[zone][lane or "center"]


def threat_gains(events: list[dict]) -> dict[str, dict]:
    """event_id → threat move for every THREAT_TYPES action whose very next event is the same team's, in the
    same move. Turnovers and the last action of a move get no entry (no destination to measure)."""
    out: dict[str, dict] = {}
    for a, b in zip(events, events[1:]):
        if a["type"] in THREAT_TYPES and b["team_id"] == a["team_id"] and b["sequence_id"] == a["sequence_id"]:
            v0, v1 = cell_threat(a["zone"], a["lane"]), cell_threat(b["zone"], b["lane"])
            out[a["event_id"]] = {"event_id": a["event_id"], "type": a["type"], "to_event_id": b["event_id"],
                                  "team_id": a["team_id"],
                                  "player_id": a.get("player_id"), "receiver_id": b.get("player_id"),
                                  "from": v0, "to": v1, "gain": round(v1 - v0, 2)}
    return out


def player_threat(events: list[dict]) -> dict[str, dict]:
    """Per player: threat added (sum of positive gains), net gain and how many actions moved the ball up."""
    out: dict[str, dict] = {}
    for g in threat_gains(events).values():
        if not g["player_id"]:
            continue
        row = out.setdefault(g["player_id"], {"added": 0.0, "net": 0.0, "forward": 0})
        row["added"] = round(row["added"] + max(g["gain"], 0.0), 2)
        row["net"] = round(row["net"] + g["gain"], 2)
        row["forward"] += g["gain"] > 0
    return out


def move_threat(events: list[dict]) -> dict:
    """Threat of one move: net gain of its actions and the most dangerous cell it reached (per acting team)."""
    gains = threat_gains(events)
    return {"net_gain": round(sum(g["gain"] for g in gains.values()), 2),
            "peak": max((cell_threat(ev["zone"], ev["lane"]) for ev in events), default=0.0),
            "measured_actions": len(gains)}


def link_threat(events: list[dict], team_id: str) -> dict[tuple[str, str], float]:
    """(passer, receiver) → summed threat gain of the pass-like actions behind that link (same rule as
    analytics.pass_links; carries and dribbles never create a link)."""
    out: dict[tuple[str, str], float] = {}
    for g in threat_gains(events).values():
        if (g["type"] in LINK_TYPES and g["team_id"] == team_id and g["player_id"] and g["receiver_id"]
                and g["player_id"] != g["receiver_id"]):
            key = (g["player_id"], g["receiver_id"])
            out[key] = round(out.get(key, 0.0) + g["gain"], 2)
    return out


def threat_underlay(attacks_right: bool) -> list[dict]:
    """Background shapes: the Zone Threat grid for the team attacking in that direction, gold opacity ∝ value."""
    from .analytics import cell_rect  # local import: analytics imports pitch, which imports this module

    peak = max(v for lanes in ZONE_THREAT.values() for v in lanes.values())
    shapes = []
    for zone, lanes in ZONE_THREAT.items():
        for lane, v in lanes.items():
            x0, y0, x1, y1 = cell_rect(zone, lane, attacks_right)
            shapes.append({"type": "rect", "x0": x0, "y0": y0, "x1": x1, "y1": y1, "layer": "below",
                           "line": {"width": 0}, "fillcolor": f"rgba(250,204,21,{0.03 + 0.42 * v / peak:.2f})"})
    return shapes


# --- colour scale (presentation) ------------------------------------------------
THREAT_SCALE = ((0.0, (253, 230, 138)), (0.15, (251, 146, 60)), (0.35, (220, 38, 38)))  # amber → orange → red
NO_GAIN = "#94a3b8"  # sideways / backwards


def threat_color(gain: float | None) -> str:
    """Colour for a threat gain: grey when ≤ 0, then amber → red as the gain grows (capped)."""
    if gain is None or gain <= 0:
        return NO_GAIN
    g = min(gain, THREAT_SCALE[-1][0])
    for (g0, c0), (g1, c1) in zip(THREAT_SCALE, THREAT_SCALE[1:]):
        if g <= g1:
            t = (g - g0) / (g1 - g0)
            return "#%02x%02x%02x" % tuple(round(a + (b - a) * t) for a, b in zip(c0, c1))
    return "#%02x%02x%02x" % THREAT_SCALE[-1][1]
