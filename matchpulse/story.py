"""Replay speed, the factual 'story so far' feed, card counts and event → move focus.

Pure Python and deterministic. The story feed restates events from the data (goals, shots, the turning
point); it is not generated text and adds no facts.
"""
from __future__ import annotations

from .metrics import event_time
from .replay import clock_label

BASE_STEP_SECONDS = 10  # simulated seconds per real-second tick at 1x
SPEEDS = {"0.5x": 0.5, "1x": 1.0, "1.5x": 1.5, "2x": 2.0, "4x": 4.0}
DEFAULT_SPEED = "1x"
SHOT_WORDS = {"saved": "saved", "off_target": "wide", "blocked": "blocked"}
CARD_TYPES = {"yellow_card": "yellow", "red_card": "red"}  # not in schema 1.0.0; counted if ever present


def speed_step(label: str | None) -> int:
    """Simulated seconds advanced per tick for a speed label; unknown labels fall back to 1x."""
    return int(round(BASE_STEP_SECONDS * SPEEDS.get(label or DEFAULT_SPEED, 1.0)))


def card_counts(events: list[dict]) -> tuple[dict, dict]:
    """(per player {'yellow': n, 'red': n}, per team {'yellow': n, 'red': n}). Empty for schema 1.0.0 data."""
    by_player: dict[str, dict] = {}
    by_team: dict[str, dict] = {}
    for ev in events:
        colour = CARD_TYPES.get(ev["type"])
        if not colour:
            continue
        for bucket, key in ((by_player, ev.get("player_id")), (by_team, ev["team_id"])):
            if key:
                bucket.setdefault(key, {"yellow": 0, "red": 0})[colour] += 1
    return by_player, by_team


def _name(players: dict, ev: dict | None) -> str | None:
    return players.get(ev["player_id"], {}).get("name") if ev and ev.get("player_id") else None


def story_moments(snapshot: dict, match: dict, players: dict) -> list[dict]:
    """Key moments so far, latest first: goals (with the setup when it is the previous action of the
    same team in the move), shots and their outcome, and the turning point."""
    names = {t["id"]: t["name"] for t in (match["home_team"], match["away_team"])}
    events = snapshot["events"]
    moments = []
    for i, ev in enumerate(events):
        t = event_time(ev)
        base = {"seconds": t, "clock": clock_label(t), "event_id": ev["event_id"], "sequence_id": ev["sequence_id"]}
        who = _name(players, ev) or names[ev["team_id"]]
        if ev["type"] == "goal":
            prev = events[i - 1] if i > 0 else None
            setup = ""
            if (prev and prev["sequence_id"] == ev["sequence_id"] and prev["team_id"] == ev["team_id"]
                    and _name(players, prev) and prev["player_id"] != ev["player_id"]):
                setup = f", set up by {_name(players, prev)}'s {prev['type'].replace('_', ' ')}"
            moments.append({**base, "kind": "goal", "icon": "⚽",
                            "text": f"GOAL — {who} ({names[ev['team_id']]}){setup}"})
        elif ev["type"] == "shot":
            nxt = events[i + 1] if i + 1 < len(events) else None
            keeper = _name(players, nxt) if nxt and nxt["type"] == "save" else None
            outcome = SHOT_WORDS.get(ev["outcome"], ev["outcome"] or "")
            detail = f"saved by {keeper}" if keeper else outcome
            moments.append({**base, "kind": "shot", "icon": "🧤" if ev["outcome"] == "saved" else "🎯",
                            "text": f"Chance — {who} ({names[ev['team_id']]}), {detail}"})
    inf = snapshot["metrics"]["inflection_point"]
    if inf["value"]:
        v = inf["value"]
        ids = inf["source_event_ids"]
        seq = next((e["sequence_id"] for e in events if e["event_id"] == (ids[-1] if ids else None)), None)
        moments.append({"seconds": v["to_seconds"], "clock": clock_label(v["to_seconds"]), "kind": "turning",
                        "icon": "🔄", "event_id": ids[-1] if ids else None, "sequence_id": seq,
                        "text": f"Turning point — the game swings towards {names[inf['team_id']]} "
                                f"({clock_label(v['from_seconds'])} → {clock_label(v['to_seconds'])})"})
    return sorted(moments, key=lambda m: (-m["seconds"], m["kind"]))


def event_focus(snapshot: dict, event_id: str) -> str | None:
    """The move (sequence_id) an event belongs to, for 'show on pitch'."""
    return next((ev["sequence_id"] for ev in snapshot["events"] if ev["event_id"] == event_id), None)


# --- match read: a broadcaster-style interpretation of the current state ----------------
# Display-only. Every sentence is derived from the snapshot's metrics or from event counts in the last
# READ_WINDOW seconds; the thresholds are fixed and documented in docs/methods.md ("Match read").

READ_WINDOW = 300
STATE_ICONS = {"settling": "⏳", "shifting": "🔄", "controlled": "🎯", "pressing": "🔥", "building": "📈",
               "chaotic": "⚡", "even": "⚖️"}
TURNOVER_TYPES = ("interception", "tackle")


def _leader(value: dict, home: str, away: str, margin: float = 0.0) -> str | None:
    h, a = value.get(home), value.get(away)
    if h is None or a is None or abs(h - a) <= margin:
        return None
    return home if h > a else away


def match_read(snapshot: dict, match: dict, config: dict) -> dict:
    """{'state', 'icon', 'headline', 'lines'}: who presses, who has the ball, who connects passes, who gets
    near the box, and whether the game feels settling / shifting / controlled / building / chaotic / even."""
    from .metrics import momentum_at

    home, away = match["home_team"]["id"], match["away_team"]["id"]
    names = {t["id"]: t["name"] for t in (match["home_team"], match["away_team"])}
    m, t = snapshot["metrics"], snapshot["at_seconds"]
    recent = [ev for ev in snapshot["events"] if event_time(ev) >= t - READ_WINDOW]
    mom = m["momentum"]["value"]
    mom_then = momentum_at(match, config, max(0, t - 120))[0]

    passes = {tid: [ev for ev in recent if ev["team_id"] == tid and ev["type"] == "pass"] for tid in (home, away)}
    completion = {tid: (round(100 * sum(ev["outcome"] == "complete" for ev in p) / len(p)) if len(p) >= 3 else None)
                  for tid, p in passes.items()}
    box = {tid: sum(1 for ev in recent if ev["team_id"] == tid and ev["zone"] == "opp_box") for tid in (home, away)}
    turnovers = sum(1 for ev in recent if ev["type"] in TURNOVER_TYPES
                    or (ev["type"] == "pass" and ev["outcome"] == "incomplete"))

    lines = []
    leader = home if mom > 0 else away
    if abs(mom) >= 0.6:
        lines.append(f"{names[leader]} are on the front foot: most of the recent attacking actions are theirs.")
    elif abs(mom) >= 0.2:
        lines.append(f"{names[leader]} are edging the pressure without taking over.")
    else:
        lines.append("Neither side is pressing home an advantage right now.")
    ball = _leader(m["pass_share"]["value"], home, away, margin=5)
    if ball:
        lines.append(f"{names[ball]} are seeing more of the ball ({m['pass_share']['value'][ball]:.0f}% of passes, "
                     f"last 5 min).")
    sharp = _leader(completion, home, away, margin=5)
    if sharp:
        other = away if sharp == home else home
        lines.append(f"{names[sharp]} are connecting their passes better ({completion[sharp]}% completed "
                     f"vs {completion[other]}%).")
    near = _leader(box, home, away)
    if near:
        other = away if near == home else home
        lines.append(f"{names[near]} are getting closer to goal: {box[near]} actions in the opponent's box "
                     f"to {box[other]} in the last 5 min.")

    inf = m["inflection_point"]["value"]
    terr = _leader(m["territorial_control"]["value"], home, away, margin=5)
    if len(recent) < 10:
        state, text = "settling", "Early exchanges: too little has happened yet to call it."
    elif (inf and t - 90 <= inf["to_seconds"] <= t) or (mom * mom_then < 0 and min(abs(mom), abs(mom_then)) >= 0.2):
        state, text = "shifting", "The game is shifting: the pressure has changed hands in the last two minutes."
    elif abs(mom) >= 0.6 and ball in (leader, None) and terr in (leader, None):
        state, text = "controlled", f"{names[leader]} are controlling this spell: ball, territory and pressure all point their way."
    elif abs(mom) >= 0.6:
        other = names[away if leader == home else home]
        state, text = "pressing", (f"{names[leader]} are pressing hard while {other} keep more of the ball: "
                                   f"possession without penetration for {other}." if ball and ball != leader else
                                   f"{names[leader]} are on top, though not everywhere on the pitch yet.")
    elif abs(mom) >= 0.2 and mom * mom_then > 0 and abs(mom) > abs(mom_then) + 0.15:
        state, text = "building", f"Pressure is building for {names[leader]}: their grip is tighter than two minutes ago."
    elif abs(mom) < 0.3 and turnovers >= 0.35 * len(recent):
        state, text = "chaotic", "It's scrappy: the ball keeps changing hands and nobody can settle."
    else:
        state, text = "even", "An even, open phase: no side has a clear hold on the game."
    team = leader if state in ("controlled", "pressing", "building") else None
    return {"state": state, "icon": STATE_ICONS[state], "headline": text, "lines": lines, "team": team}


def state_arc(reads: list[tuple[int, dict]]) -> list[dict]:
    """Compress (seconds, match_read) samples into the game's story: consecutive identical
    (state, team) samples merge into one phase with a start time."""
    arc: list[dict] = []
    for t, r in reads:
        key = (r["state"], r.get("team"))
        if not arc or (arc[-1]["state"], arc[-1]["team"]) != key:
            arc.append({"from_seconds": t, "state": r["state"], "icon": r["icon"], "team": r.get("team")})
    return arc
