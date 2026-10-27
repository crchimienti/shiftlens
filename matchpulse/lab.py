"""Tactical Hypothesis Lab and Decision Journal: deterministic window comparisons over recorded events.

A hypothesis compares one team's measure in window A with window B ("higher in B" / "lower in B"). A decision is
logged at a clock time and reviewed by comparing the same measure before and after it. Pure Python, no Streamlit, no
model. Nothing after the replay clock is ever read: a window that ends later is "pending". Records are plain dicts
kept in the session (the UI offers a JSON download); verdict text stays English and canonical, labels are
translated in the UI.
"""
from __future__ import annotations

from .metrics import event_time

VERSION = "lab-1.0"
MEASURES = ("pressures", "shots", "xg", "attacking", "box", "pass_share")
MIN_EVENTS = 3          # fewer measured events in both windows together → inconclusive
MIN_CHANGE = {"pass_share": 5.0, "xg": 0.1}  # smaller differences are inconclusive (counts need at least 1)
DECISION_KINDS = ("substitution", "press_higher", "drop_deeper", "switch_flank", "other")
ATTACKING_ZONES = ("attacking_third", "opp_box")


def window_events(events: list[dict], start: int, end: int) -> list[dict]:
    return [e for e in events if start <= event_time(e) <= end]


def measure(events: list[dict], team_id: str, name: str) -> tuple[float, list[str]]:
    """(value, evidence event IDs) for one team over a list of events."""
    own = [e for e in events if e["team_id"] == team_id]
    if name == "pressures":
        hits = [e for e in own if e["type"] == "pressure"]
        return float(len(hits)), [e["event_id"] for e in hits]
    if name == "shots":
        hits = [e for e in own if e["type"] in ("shot", "goal")]
        return float(len(hits)), [e["event_id"] for e in hits]
    if name == "xg":
        hits = [e for e in own if e["type"] in ("shot", "goal") and e.get("xg") is not None]
        return round(sum(e["xg"] for e in hits), 2), [e["event_id"] for e in hits]
    if name == "attacking":
        hits = [e for e in own if e["zone"] in ATTACKING_ZONES]
        return float(len(hits)), [e["event_id"] for e in hits]
    if name == "box":
        hits = [e for e in own if e["zone"] == "opp_box"]
        return float(len(hits)), [e["event_id"] for e in hits]
    if name == "pass_share":
        passes = [e for e in events if e["type"] == "pass"]
        mine = [e for e in passes if e["team_id"] == team_id]
        return (round(100 * len(mine) / len(passes), 1) if passes else 0.0), [e["event_id"] for e in passes]
    raise ValueError(f"unknown measure '{name}'")


def compare(events: list[dict], team_id: str, name: str, a: tuple[int, int], b: tuple[int, int],
            direction: str, clock: int) -> dict:
    """Verdict for 'measure is {direction} in B than in A'. Windows are inclusive seconds."""
    if direction not in ("higher", "lower"):
        raise ValueError("direction must be 'higher' or 'lower'")
    if a[0] > a[1] or b[0] > b[1]:
        raise ValueError("each window needs start <= end")
    base = {"measure": name, "team_id": team_id, "window_a": list(a), "window_b": list(b), "direction": direction,
            "version": VERSION}
    if max(a[1], b[1]) > clock:
        return {**base, "verdict": "pending", "value_a": None, "value_b": None, "evidence_event_ids": []}
    seen = [e for e in events if event_time(e) <= clock]
    va, ida = measure(window_events(seen, *a), team_id, name)
    vb, idb = measure(window_events(seen, *b), team_id, name)
    evidence = sorted(set(ida) | set(idb))
    delta = round(vb - va, 2)
    if len(evidence) < MIN_EVENTS or abs(delta) < MIN_CHANGE.get(name, 1):
        verdict = "inconclusive"
    else:
        verdict = "supported" if (delta > 0) == (direction == "higher") else "not_supported"
    return {**base, "verdict": verdict, "value_a": va, "value_b": vb, "delta": delta, "evidence_event_ids": evidence}


def make_hypothesis(seq: int, statement: str, team_id: str, name: str, a: tuple[int, int], b: tuple[int, int],
                    direction: str, created_at: int) -> dict:
    return {"id": seq, "kind": "hypothesis", "statement": statement.strip(), "team_id": team_id, "measure": name,
            "window_a": list(a), "window_b": list(b), "direction": direction, "created_at": created_at}


def evaluate_hypothesis(h: dict, events: list[dict], clock: int) -> dict:
    return compare(events, h["team_id"], h["measure"], tuple(h["window_a"]), tuple(h["window_b"]), h["direction"],
                   clock)


def make_decision(seq: int, at: int, team_id: str, kind: str, rationale: str, name: str, direction: str,
                  review_minutes: int) -> dict:
    if kind not in DECISION_KINDS:
        raise ValueError(f"unknown decision '{kind}'")
    return {"id": seq, "kind": "decision", "at": at, "team_id": team_id, "decision": kind,
            "rationale": rationale.strip(), "measure": name, "direction": direction,
            "review_seconds": max(60, int(review_minutes) * 60)}


def review_end(d: dict, duration: int | None = None) -> int:
    """End of the after-window: `review_seconds` after the decision, cut at full time."""
    end = d["at"] + d["review_seconds"]
    return min(end, duration) if duration is not None else end


def review_decision(d: dict, events: list[dict], clock: int, duration: int | None = None) -> dict:
    """Before window [at - w, at - 1] vs after window [at, review_end]; pending until the clock passes its end."""
    w, at = d["review_seconds"], d["at"]
    return compare(events, d["team_id"], d["measure"], (max(0, at - w), max(0, at - 1)),
                   (at, review_end(d, duration)), d["direction"], clock)
