"""User-facing labels and formatting. Pure Python, no Streamlit, no new metrics.

Everything here only renames, formats or counts values that already exist in the snapshot.
"""
from __future__ import annotations

from .replay import clock_label

METRIC_LABELS = {
    "score": "Score",
    "pass_share": "Pass share",
    "danger_score": "Danger index",
    "momentum": "Momentum",
    "territorial_control": "Territory",
    "highlighted_sequences": "Key moves",
    "inflection_point": "Turning point",
    "data_sufficiency": "Evidence level",
}

EVIDENCE_LEVELS = {"low": "Low", "med": "Medium", "high": "High"}


def metric_label(name: str) -> str:
    return METRIC_LABELS.get(name, name.replace("_", " ").capitalize())


def window_label(window: dict) -> str:
    """'last 3 min' for a rolling window, 'match so far' for kick-off → now."""
    length = window.get("length_seconds")
    if length is None:
        return "match so far"
    return f"last {length // 60} min" if length % 60 == 0 else f"last {length} s"


ZONE_LABELS = {"own_box": "Own box", "opp_box": "Opponent box"}


def nice(text: str | None) -> str:
    """'attacking_third' → 'Attacking third'; 'opp_box' → 'Opponent box'."""
    return ZONE_LABELS.get(text, (text or "").replace("_", " ").capitalize())


# --- momentum ---------------------------------------------------------------

def momentum_reading(value: float, home: str, away: str) -> str:
    """Plain-language reading of the existing momentum value (same thresholds as the Fan Lens text)."""
    leader = home if value > 0 else away
    if abs(value) >= 0.6:
        return f"{leader} on top"
    if abs(value) >= 0.2:
        return f"{leader} edging it"
    return "Balanced spell"


def momentum_cue(value: float, home: str, away: str) -> str:
    """Reading with a direction arrow matching the bar (away on the left, home on the right)."""
    reading = momentum_reading(value, home, away)
    if reading == "Balanced spell":
        return reading
    return f"{reading} ▶" if value > 0 else f"◀ {reading}"


def pressure_split(value: float) -> tuple[int, int]:
    """Home/away % of recent weighted activity. Exact rearrangement of momentum = (h − a) / (h + a)."""
    home = round((value + 1) / 2 * 100)
    return home, 100 - home


# --- match summary (plain event counts, no models) ---------------------------

SUMMARY_ROWS = ("Shots", "On target", "Saves", "Corners", "Fouls", "Yellow cards", "Red cards", "Passes",
                "Unsuccessful passes", "Attacking actions")


def match_summary(events: list[dict], team_ids: tuple[str, str], attacking_zones) -> dict[str, dict[str, int]]:
    """Counts per team from events played so far. A goal is the scoring shot, so it counts as a shot on target."""
    zones = set(attacking_zones)
    out = {row: {t: 0 for t in team_ids} for row in SUMMARY_ROWS}
    for ev in events:
        t, kind, outcome = ev["team_id"], ev["type"], ev.get("outcome")
        if t not in team_ids:
            continue
        if kind in ("shot", "goal"):
            out["Shots"][t] += 1
            if kind == "goal" or outcome == "saved":
                out["On target"][t] += 1
        counts = {"save": "Saves", "corner": "Corners", "foul": "Fouls", "pass": "Passes",
                  "yellow_card": "Yellow cards", "red_card": "Red cards"}  # card types: not in schema 1.0.0
        if kind in counts:
            out[counts[kind]][t] += 1
        if kind == "pass" and outcome == "incomplete":
            out["Unsuccessful passes"][t] += 1
        if ev["zone"] in zones:
            out["Attacking actions"][t] += 1
    return out


# --- traceability display ---------------------------------------------------

def _pair(value: dict, fmt: str, suffix: str = "") -> str:
    show = lambda v: "–" if v is None else f"{format(v, fmt)}{suffix}"
    return " · ".join(f"{team} {show(v)}" for team, v in value.items())


def friendly_value(name: str, metric: dict, names: dict[str, str]) -> str:
    v = metric["value"]
    if name == "score":
        (h, hv), (a, av) = v.items()
        return f"{h} {hv} – {av} {a}"
    if name == "pass_share" or name == "territorial_control":
        return _pair(v, ".0f" if name == "pass_share" else ".1f", "%")
    if name == "danger_score":
        return _pair(v, ".2f")
    if name == "momentum":
        home, away = list(names.values())
        return f"{v:+.2f} ({momentum_reading(v, home, away)})"
    if name == "highlighted_sequences":
        return ", ".join(f"{s['sequence_id']} ({s['score']:.2f})" for s in v) or "None yet"
    if name == "inflection_point":
        if not v:
            return "None yet"
        return (f"{clock_label(v['from_seconds'])}→{clock_label(v['to_seconds'])}, "
                f"to {metric['team_id']} ({v['delta']:+.2f})")
    if name == "data_sufficiency":
        return f"{EVIDENCE_LEVELS.get(v, v)} ({metric['details']['event_count']} events)"
    return str(v)


def friendly_trace_rows(rows: list[dict], metrics: dict, names: dict[str, str]) -> list[dict]:
    """Same rows and keys as `traceability_rows`, with readable metric names, values and windows."""
    out = []
    for row in rows:
        name, m = row["metric"], metrics[row["metric"]]
        w = m["window"]
        out.append({**row,
                    "metric": metric_label(name),
                    "value": friendly_value(name, m, names),
                    "window": f"{clock_label(w['start_seconds'])}–{clock_label(w['end_seconds'])} ({window_label(w)})"})
    return out
