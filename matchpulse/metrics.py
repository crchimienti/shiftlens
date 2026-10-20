"""Deterministic match metrics, computed at a given clock time from events + config only.

Every metric is a plain dict (JSON-serializable) with traceability metadata.
Clock: t = minute * 60 + second on the summary clock. A window [start, end] is inclusive.
"""
from __future__ import annotations

from .validator import validate_config

FORMULA_VERSIONS = {
    "score": "1.0",
    "pass_share": "1.0",
    "danger_score": "1.0",
    "momentum": "1.0",
    "territorial_control": "1.0",
    "highlighted_sequences": "1.0",
    "inflection_point": "1.0",
    "data_sufficiency": "1.0",
}


class ConfigError(ValueError):
    pass


# --- helpers ----------------------------------------------------------------

def event_time(ev: dict) -> int:
    return ev["minute"] * 60 + ev["second"]


def team_ids(match: dict) -> tuple[str, str]:
    return match["home_team"]["id"], match["away_team"]["id"]


def events_in(match: dict, start: int, end: int) -> list[dict]:
    return [ev for ev in match["events"] if start <= event_time(ev) <= end]


def window(at: int, length: int | None) -> dict:
    start = 0 if length is None else max(0, at - length)
    return {"start_seconds": start, "end_seconds": at, "length_seconds": length}


def event_weight(ev: dict, config: dict) -> float:
    """Event-type weight x zone weight. Types without a configured weight count 0."""
    w = config["weights"]
    return w["event"].get(ev["type"], 0.0) * w["zone"].get(ev["zone"], 0.0)


def metric(name: str, value, win: dict, config: dict, source_ids: list[str],
           team_id: str | None = None, notes: str | None = None, details: dict | None = None) -> dict:
    return {
        "metric_name": name,
        "value": value,
        "window": win,
        "formula_version": FORMULA_VERSIONS[name],
        "config_version": config["config_version"],
        "source_event_ids": source_ids,
        "team_id": team_id,
        "notes": notes,
        "details": details or {},
    }


def pct(part: float, whole: float) -> float | None:
    return None if whole == 0 else round(100.0 * part / whole, 2)


# --- metrics ----------------------------------------------------------------

def score(match: dict, config: dict, at: int) -> dict:
    win = window(at, None)
    goals = [ev for ev in events_in(match, 0, at) if ev["type"] == "goal"]
    value = {tid: sum(1 for g in goals if g["team_id"] == tid) for tid in team_ids(match)}
    return metric("score", value, win, config, [g["event_id"] for g in goals],
                  notes="Derived from goal events only.")


def pass_share(match: dict, config: dict, at: int) -> dict:
    win = window(at, config["windows"]["pass_share_seconds"])
    passes = [ev for ev in events_in(match, win["start_seconds"], at) if ev["type"] == "pass"]
    counts = {tid: sum(1 for p in passes if p["team_id"] == tid) for tid in team_ids(match)}
    value = {tid: pct(n, len(passes)) for tid, n in counts.items()}
    notes = "Share of pass events in window (%), not possession."
    if not passes:
        notes += " No passes in window."
    return metric("pass_share", value, win, config, [p["event_id"] for p in passes],
                  notes=notes, details={"pass_counts": counts})


def danger_score(match: dict, config: dict, at: int) -> dict:
    win = window(at, config["windows"]["danger_seconds"])
    weighted = [(ev, event_weight(ev, config)) for ev in events_in(match, win["start_seconds"], at)]
    weighted = [(ev, w) for ev, w in weighted if w > 0]
    value = {tid: round(sum(w for ev, w in weighted if ev["team_id"] == tid), 4) for tid in team_ids(match)}
    return metric("danger_score", value, win, config, [ev["event_id"] for ev, _ in weighted],
                  notes="Sum of event-type weight x zone weight in window.")


def momentum_at(match: dict, config: dict, at: int) -> tuple[float, list[dict]]:
    """Return (momentum, contributing events). Positive favours home, negative away."""
    home, _ = team_ids(match)
    start = max(0, at - config["windows"]["momentum_seconds"])
    half_life = config["momentum"]["half_life_seconds"]
    net, total, used = 0.0, 0.0, []
    for ev in events_in(match, start, at):
        w = event_weight(ev, config)
        if w <= 0:
            continue
        decayed = w * 0.5 ** ((at - event_time(ev)) / half_life)
        net += decayed if ev["team_id"] == home else -decayed
        total += decayed
        used.append(ev)
    return (0.0 if total == 0 else round(net / total, 4)), used


def momentum(match: dict, config: dict, at: int) -> dict:
    home, away = team_ids(match)
    value, used = momentum_at(match, config, at)
    leader = home if value > 0 else away if value < 0 else None
    notes = "Range [-1, 1]; +1 = all weighted, time-decayed activity by home, -1 = by away."
    if not used:
        notes += " No weighted events in window."
    return metric("momentum", value, window(at, config["windows"]["momentum_seconds"]), config,
                  [ev["event_id"] for ev in used], team_id=leader, notes=notes,
                  details={"half_life_seconds": config["momentum"]["half_life_seconds"]})


def territorial_control(match: dict, config: dict, at: int) -> dict:
    win = window(at, config["windows"]["territorial_seconds"])
    evs = events_in(match, win["start_seconds"], at)
    zones = set(config["attacking_zones"])
    value, counts = {}, {}
    for tid in team_ids(match):
        own = [ev for ev in evs if ev["team_id"] == tid]
        attacking = sum(1 for ev in own if ev["zone"] in zones)
        value[tid] = pct(attacking, len(own))
        counts[tid] = {"events": len(own), "attacking": attacking}
    return metric("territorial_control", value, win, config, [ev["event_id"] for ev in evs],
                  notes="% of each team's events in attacking zones; null if the team has no events.",
                  details={"counts": counts, "attacking_zones": sorted(zones)})


def highlighted_sequences(match: dict, config: dict, at: int) -> dict:
    seqs: dict[str, list[dict]] = {}
    for ev in events_in(match, 0, at):
        seqs.setdefault(ev["sequence_id"], []).append(ev)
    ranked = sorted((_sequence_summary(sid, evs, match, config) for sid, evs in seqs.items()),
                    key=lambda s: (-s["score"], s["start_seconds"], s["sequence_id"]))
    top = ranked[: config["highlights"]["top_n"]]
    sources = [eid for s in top for eid in s["event_ids"]]
    return metric("highlighted_sequences", top, window(at, None), config, sources,
                  notes="Top sequences by summed event weight; ties -> earlier, then sequence_id.")


def _sequence_summary(sid: str, evs: list[dict], match: dict, config: dict) -> dict:
    by_team = {tid: sum(event_weight(ev, config) for ev in evs if ev["team_id"] == tid)
               for tid in team_ids(match)}
    best = max(by_team.values())
    leaders = [tid for tid, w in by_team.items() if w == best]
    team = leaders[0] if len(leaders) == 1 else evs[0]["team_id"]
    return {
        "sequence_id": sid,
        "score": round(sum(by_team.values()), 4),
        "team_id": team,
        "start_seconds": event_time(evs[0]),
        "end_seconds": event_time(evs[-1]),
        "event_ids": [ev["event_id"] for ev in evs],
        "has_goal": any(ev["type"] == "goal" for ev in evs),
    }


def inflection_point(match: dict, config: dict, at: int) -> dict:
    cfg = config["inflection"]
    samples = _momentum_samples(match, config, at)
    best = None
    for j, (tj, mj) in enumerate(samples):
        for ti, mi in samples[:j]:
            if tj - ti > cfg["span_seconds"]:
                continue
            delta = round(mj - mi, 4)
            if abs(delta) > cfg["threshold"] and (best is None or abs(delta) > abs(best["delta"])):
                best = {"from_seconds": ti, "to_seconds": tj, "from_momentum": mi,
                        "to_momentum": mj, "delta": delta}
    home, away = team_ids(match)
    details = {"threshold": cfg["threshold"], "span_seconds": cfg["span_seconds"],
               "step_seconds": cfg["step_seconds"], "samples_used": len(samples)}
    if best is None:
        return metric("inflection_point", None, window(at, None), config, [],
                      notes="No momentum change above threshold within span.", details=details)
    towards = home if best["delta"] > 0 else away
    sources = [ev["event_id"] for ev in events_in(match, best["from_seconds"] + 1, best["to_seconds"])]
    return metric("inflection_point", best, window(at, None), config, sources, team_id=towards,
                  notes="Largest momentum swing within span; ties -> earliest. team_id = side it swung to.",
                  details=details)


def _momentum_samples(match: dict, config: dict, at: int) -> list[tuple[int, float]]:
    """Momentum on a fixed time grid, skipping samples with too few weighted events."""
    step, min_events = config["inflection"]["step_seconds"], config["inflection"]["min_window_events"]
    grid = list(range(0, at + 1, step))
    if grid[-1] != at:
        grid.append(at)
    samples = []
    for t in grid:
        value, used = momentum_at(match, config, t)
        if len(used) >= min_events:
            samples.append((t, value))
    return samples


def data_sufficiency(match: dict, config: dict, at: int) -> dict:
    win = window(at, config["windows"]["sufficiency_seconds"])
    evs = events_in(match, win["start_seconds"], at)
    thresholds = config["sufficiency"]
    n = len(evs)
    level = "high" if n >= thresholds["high_from"] else "med" if n >= thresholds["med_from"] else "low"
    return metric("data_sufficiency", level, win, config, [ev["event_id"] for ev in evs],
                  notes="Event count in window vs config thresholds.",
                  details={"event_count": n, "med_from": thresholds["med_from"],
                           "high_from": thresholds["high_from"]})


METRICS = (score, pass_share, danger_score, momentum, territorial_control,
           highlighted_sequences, inflection_point, data_sufficiency)


def compute_metrics(match: dict, config: dict, at_seconds: int | None = None) -> dict:
    """All metrics at `at_seconds` (default: end of match). Raises ConfigError on bad config."""
    errors = validate_config(config)
    if errors:
        raise ConfigError("; ".join(errors))
    end = match["duration_minutes"] * 60
    at = end if at_seconds is None else at_seconds
    if not isinstance(at, int) or not 0 <= at <= end:
        raise ValueError(f"at_seconds must be an integer in [0, {end}], got {at!r}")
    return {
        "match_id": match["match_id"],
        "at_seconds": at,
        "config_version": config["config_version"],
        "metrics": {fn.__name__: fn(match, config, at) for fn in METRICS},
    }
