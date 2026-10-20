"""Explanation layer: request payload, strict output validation, deterministic fallback, retry.

No Streamlit and no network here. An optional online generator is any callable
`generator(request, previous_errors) -> dict | str`; it is validated, retried once, and
replaced by the deterministic fallback if it still fails.
"""
from __future__ import annotations

import json
import time
import re
from typing import Callable

from jsonschema import Draft202012Validator

from .replay import clock_label
from .validator import ROOT, load_json

EXPLANATION_SCHEMA_PATH = ROOT / "config" / "explanation_schema.json"
REQUEST_VERSION = "1.0"
EXPLANATION_VERSION = "1.0"
MODES = ("fan", "analyst")
RECENT_EVENTS = 12
FAN_MAX_POINTS, FAN_MAX_NARRATIVE = 3, 300
ANALYST_MIN_POINTS = 3
PAUSE_REQUIRED = "Pause the replay to get an explanation. Explanations are only generated while paused."

Generator = Callable[[dict, list[str] | None], "dict | str"]


def explain_guard(playing: bool) -> str | None:
    """Message to show instead of generating, or None when explaining is allowed."""
    return PAUSE_REQUIRED if playing else None


# --- request ----------------------------------------------------------------

def build_request(match: dict, snapshot: dict, mode: str) -> dict:
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
    team = lambda t: {"id": t["id"], "name": t["name"]}
    events = snapshot["events"]
    slim = lambda ev: {k: ev[k] for k in ("event_id", "minute", "second", "team_id", "player_id",
                                          "type", "outcome", "zone")}
    return {
        "request_version": REQUEST_VERSION,
        "mode": mode,
        "match": {"match_id": match["match_id"], "home": team(match["home_team"]), "away": team(match["away_team"])},
        "clock": {"at_seconds": snapshot["at_seconds"], "label": snapshot["clock"],
                  "minute": snapshot["at_seconds"] // 60, "period": snapshot["period"]},
        "metrics": snapshot["metrics"],
        "recent_events": [slim(ev) for ev in events[-RECENT_EVENTS:]],
        "goals": [slim(ev) for ev in events if ev["type"] == "goal"],
        "allowed_event_ids": [ev["event_id"] for ev in events],
        "players": {p["id"]: p["name"] for t in (match["home_team"], match["away_team"]) for p in t["players"]},
    }


# --- validation -------------------------------------------------------------

def _numeric_leaves(obj, key: str = ""):
    if isinstance(obj, bool) or obj is None:
        return
    if isinstance(obj, (int, float)):
        yield key, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from _numeric_leaves(v, k)
    elif isinstance(obj, list):
        for v in obj:
            yield from _numeric_leaves(v, key)


def _variants(x) -> set[str]:
    """Textual forms a snapshot number may take: 0-2 decimals, no sign."""
    out = {f"{abs(x):.{d}f}" for d in (0, 1, 2)}
    if float(x).is_integer():
        out.add(str(int(abs(x))))
    return out


def allowed_numbers(request: dict) -> set[str]:
    """Every textual form a number from the request may take in an explanation (global whitelist)."""
    out: set[str] = set()
    for _, x in _numeric_leaves({"m": request["metrics"], "c": request["clock"]}):
        out |= _variants(x)
    return out


def allowed_clocks(request: dict) -> set[str]:
    labels = {clock_label(v) for k, v in _numeric_leaves(request["metrics"]) if k.endswith("_seconds")}
    labels.add(request["clock"]["label"])
    labels.update(clock_label(e["minute"] * 60 + e["second"]) for e in request["recent_events"] + request["goals"])
    return labels


CLOCK_RE = re.compile(r"\b\d{1,2}:\d{2}\b")
ID_RE = re.compile(r"\b[A-Z]{1,4}-?\d+\b")
EVENT_ID_RE = re.compile(r"^E\d+$")
NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


def _text_claim_errors(where: str, text: str, request: dict, numbers: set[str], clocks: set[str]) -> list[str]:
    errors = []
    allowed_events = set(request["allowed_event_ids"])
    for c in CLOCK_RE.findall(text):
        if c not in clocks:
            errors.append(f"{where}: clock '{c}' is not in the snapshot")
    text = CLOCK_RE.sub(" ", text)
    for token in ID_RE.findall(text):
        if EVENT_ID_RE.match(token) and token not in allowed_events:
            errors.append(f"{where}: event '{token}' is not a visible event")
    text = ID_RE.sub(" ", text)
    for n in NUMBER_RE.findall(text):
        if n not in numbers:
            errors.append(f"{where}: number '{n}' does not come from the snapshot")
    return errors


# --- claim-to-metric attribution (key points) ----------------------------------
#
# Conservative, deterministic rule set (no NLP):
#  1. Each key point needs >= 1 valid metric_ref.
#  2. Every number in a key point must be a textual variant of a number held by one of its
#     referenced metrics (value, details or window) or by the clock / score.
#  3. Team-keyed numbers (e.g. pass_share {"NBR": 60.0, "HBC": 40.0}) that are not also a
#     neutral number must belong to the nearest team name/id written *before* them.
#     This rejects swapped team values. A number with no team name before it is accepted.
# Score numbers are neutral (scorelines are written "2–1"). Collisions favour acceptance;
# the global whitelist above still applies to every text field.

def _metric_number_sources(name: str, metric: dict, team_ids: set[str]) -> tuple[set[str], dict[str, set[str]]]:
    neutral: set[str] = set()
    by_team: dict[str, set[str]] = {}

    def walk(obj, team=None):
        if isinstance(obj, bool) or obj is None:
            return
        if isinstance(obj, (int, float)):
            if team and name != "score":
                for v in _variants(obj):
                    by_team.setdefault(v, set()).add(team)
            else:
                neutral.update(_variants(obj))
        elif isinstance(obj, dict):
            keyed = bool(obj) and set(obj) <= team_ids
            for k, v in obj.items():
                walk(v, k if keyed else team)
        elif isinstance(obj, list):
            for v in obj:
                walk(v, team)

    for part in ("value", "details", "window"):
        walk(metric[part])
    return neutral, by_team


def _team_mentions(text: str, request: dict) -> list[tuple[int, str]]:
    """(end position, team_id) for each team name or id written in the text."""
    found = []
    for side in ("home", "away"):
        team = request["match"][side]
        for label in (team["name"], team["id"]):
            for m in re.finditer(rf"\b{re.escape(label)}\b", text):
                found.append((m.end(), team["id"]))
    return sorted(found)


def _mask(text: str) -> str:
    """Blank out clocks and ids, keeping character positions."""
    blank = lambda m: " " * len(m.group())
    return ID_RE.sub(blank, CLOCK_RE.sub(blank, text))


def key_point_claim_errors(output: dict, request: dict) -> list[str]:
    team_ids = {request["match"]["home"]["id"], request["match"]["away"]["id"]}
    names = {request["match"][s]["id"]: request["match"][s]["name"] for s in ("home", "away")}
    sources = {n: _metric_number_sources(n, m, team_ids) for n, m in request["metrics"].items()}
    base: set[str] = set()
    for x in (request["clock"]["at_seconds"], request["clock"]["minute"], request["clock"]["period"]):
        base |= _variants(x)
    base |= sources["score"][0]

    errors = []
    for i, p in enumerate(output["key_points"]):
        refs = [m for m in p["metric_refs"] if m in sources]
        if not refs:
            errors.append(f"key_points[{i}]: needs at least one metric_ref that is a valid metric")
            continue
        neutral, by_team = set(base), {}
        for m in refs:
            neutral |= sources[m][0]
            for v, teams in sources[m][1].items():
                by_team.setdefault(v, set()).update(teams)
        text = _mask(p["text"])
        mentions = _team_mentions(text, request)
        for num in NUMBER_RE.finditer(text):
            n = num.group()
            if n in neutral:
                continue
            if n not in by_team:
                errors.append(f"key_points[{i}]: number '{n}' is not attributable to {refs} or the clock/score")
                continue
            before = [tid for pos, tid in mentions if pos <= num.start()]
            if before and before[-1] not in by_team[n]:
                owner = " / ".join(names[t] for t in sorted(by_team[n]))
                errors.append(f"key_points[{i}]: number '{n}' is written for {names[before[-1]]} "
                              f"but belongs to {owner} in {refs}")
    return errors


def validate_explanation(output, request: dict) -> list[str]:
    """Schema + mode rules + reference checks + numeric-claim checks. Empty list = valid."""
    if not isinstance(output, dict):
        return [f"output: expected a JSON object, got {type(output).__name__}"]
    schema = load_json(EXPLANATION_SCHEMA_PATH)
    errors = [f"schema: {'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}"
              for e in sorted(Draft202012Validator(schema).iter_errors(output), key=lambda e: list(e.absolute_path))]
    if errors:
        return errors

    if output["mode"] != request["mode"]:
        errors.append(f"mode: '{output['mode']}' does not match request '{request['mode']}'")
    if output["minute"] != request["clock"]["minute"]:
        errors.append(f"minute: {output['minute']} does not match snapshot {request['clock']['minute']}")
    if output["data_sufficiency"] != request["metrics"]["data_sufficiency"]["value"]:
        errors.append("data_sufficiency: does not match snapshot")

    errors += _mode_errors(output)

    metric_names, event_ids = set(request["metrics"]), set(request["allowed_event_ids"])
    for i, p in enumerate(output["key_points"]):
        errors += [f"key_points[{i}]: unknown metric '{m}'" for m in p["metric_refs"] if m not in metric_names]
        errors += [f"key_points[{i}]: event '{e}' is not a visible event" for e in p["event_refs"] if e not in event_ids]

    numbers, clocks = allowed_numbers(request), allowed_clocks(request)
    texts = [("headline", output["headline"]), ("narrative", output["narrative"])]
    texts += [(f"key_points[{i}]", p["text"]) for i, p in enumerate(output["key_points"])]
    texts += [(f"limitations[{i}]", t) for i, t in enumerate(output["limitations"])]
    for where, text in texts:
        errors += _text_claim_errors(where, text, request, numbers, clocks)
    errors += key_point_claim_errors(output, request)
    return errors


def _mode_errors(output: dict) -> list[str]:
    if output["mode"] == "fan":
        errors = []
        if len(output["key_points"]) > FAN_MAX_POINTS:
            errors.append(f"fan: at most {FAN_MAX_POINTS} key points")
        if len(output["narrative"]) > FAN_MAX_NARRATIVE:
            errors.append(f"fan: narrative longer than {FAN_MAX_NARRATIVE} characters")
        return errors
    if len(output["key_points"]) < ANALYST_MIN_POINTS:
        return [f"analyst: at least {ANALYST_MIN_POINTS} key points"]
    return []


# --- deterministic fallback -------------------------------------------------

class _View:
    """Convenience accessors over a request, used only by the fallback templates."""

    def __init__(self, request: dict):
        self.r = request
        self.m = request["metrics"]
        self.home, self.away = request["match"]["home"], request["match"]["away"]
        self.names = {self.home["id"]: self.home["name"], self.away["id"]: self.away["name"]}
        self.clock = request["clock"]["label"]

    def v(self, name):
        return self.m[name]["value"]

    def side(self, name, team):
        return self.v(name)[team["id"]]

    def last(self, name, n=3):
        return self.m[name]["source_event_ids"][-n:]

    def win(self, name):
        return self.m[name]["window"]["length_seconds"]


def point(text: str, metrics: list[str], events: list[str]) -> dict:
    return {"text": text, "metric_refs": metrics, "event_refs": list(dict.fromkeys(events))}


def _score_headline(x: _View) -> str:
    h, a = x.side("score", x.home), x.side("score", x.away)
    if h > a:
        return f"{x.home['name']} lead {h}–{a}"
    if a > h:
        return f"{x.away['name']} lead {a}–{h}"
    return f"All square at {h}–{a}"


def _momentum_phrase(x: _View) -> str:
    value, leader = x.v("momentum"), x.names.get(x.m["momentum"]["team_id"])
    if leader and abs(value) >= 0.6:
        return f"{leader} are firmly on top right now."
    if leader and abs(value) >= 0.2:
        return f"{leader} have the edge right now."
    return "Neither side is in control right now."


def _latest_goal_point(x: _View) -> dict | None:
    goals = x.m["score"]["source_event_ids"]
    if not goals:
        return None
    ev = next((e for e in x.r["goals"] if e["event_id"] == goals[-1]), None)
    scorer = x.r["players"].get(ev["player_id"]) if ev else None
    who = f"{scorer} ({x.names[ev['team_id']]})" if scorer else "the latest scorer"
    when = f" at {clock_label(ev['minute'] * 60 + ev['second'])}" if ev else ""
    return point(f"Latest goal: {who}{when}.", ["score"], [goals[-1]])


def _top_sequence_point(x: _View, analyst: bool) -> dict | None:
    seqs = x.v("highlighted_sequences")
    if not seqs:
        return None
    s = seqs[0]
    text = (f"Most dangerous move so far: {x.names[s['team_id']]} from {clock_label(s['start_seconds'])} "
            f"to {clock_label(s['end_seconds'])}")
    text += f" (sequence {s['sequence_id']}, weight {s['score']:.2f})." if analyst else "."
    return point(text, ["highlighted_sequences"], s["event_ids"][-5:])


def _territory_leader(x: _View) -> str | None:
    h, a = x.side("territorial_control", x.home), x.side("territorial_control", x.away)
    if h is None or a is None or h == a:
        return None
    return x.home["name"] if h > a else x.away["name"]


def _inflection_text(x: _View) -> str | None:
    inf = x.v("inflection_point")
    if not inf:
        return None
    return (f"The biggest swing came between {clock_label(inf['from_seconds'])} and "
            f"{clock_label(inf['to_seconds'])}, towards {x.names[x.m['inflection_point']['team_id']]}")


RECENT_GOAL_SECONDS = 60   # a goal this recent leads the Fan Lens story
RECENT_CHANCE_SECONDS = 20  # a shot this recent is a "big chance" moment
SHOT_OUTCOMES = {"saved": "is saved", "off_target": "flies wide", "blocked": "is blocked"}


def _ev_seconds(ev: dict) -> int:
    return ev["minute"] * 60 + ev["second"]


def _player(x: _View, ev: dict | None) -> str | None:
    return x.r["players"].get(ev["player_id"]) if ev and ev.get("player_id") else None


def _fan_momentum_phrase(x: _View) -> str:
    """Broadcast-style reading of the existing momentum value (same thresholds as the analyst text)."""
    value, leader = x.v("momentum"), x.names.get(x.m["momentum"]["team_id"])
    if leader and abs(value) >= 0.6:
        return f"{leader} are piling on the pressure."
    if leader and abs(value) >= 0.2:
        return f"{leader} are edging the contest."
    return "It's finely balanced out there."


def _recent_goal(x: _View) -> dict | None:
    goals = x.r["goals"]
    if goals and x.r["clock"]["at_seconds"] - _ev_seconds(goals[-1]) <= RECENT_GOAL_SECONDS:
        return goals[-1]
    return None


def _setup_by(x: _View, goal: dict) -> str | None:
    """'set up by Felix Brandt's corner' when the previous action of the move is in the request."""
    recent = x.r["recent_events"]
    ids = [e["event_id"] for e in recent]
    if goal["event_id"] not in ids:
        return None
    k = ids.index(goal["event_id"])
    prev = recent[k - 1] if k > 0 else None
    name = _player(x, prev)
    if prev is None or name is None or prev["team_id"] != goal["team_id"] or prev["player_id"] == goal["player_id"]:
        return None
    return f"set up by {name}'s {prev['type'].replace('_', ' ')}"


def _big_chance(x: _View) -> dict | None:
    """The latest shot, if it happened in the last few seconds and was not a goal."""
    shots = [e for e in x.r["recent_events"] if e["type"] == "shot"]
    if shots and x.r["clock"]["at_seconds"] - _ev_seconds(shots[-1]) <= RECENT_CHANCE_SECONDS:
        return shots[-1]
    return None


def fallback_fan(request: dict) -> dict:
    x = _View(request)
    headline = _score_headline(x)
    momentum = _fan_momentum_phrase(x)
    points = [point(momentum, ["momentum"], x.last("momentum"))]
    goal, chance = _recent_goal(x), _big_chance(x)
    if goal:
        scorer, team = _player(x, goal) or "A late arrival", x.names[goal["team_id"]]
        setup = _setup_by(x, goal)
        story = f"{scorer} scores for {team}" + (f", {setup}" if setup else "") + "!"
        headline = f"⚽ GOAL! {headline}"
        points.append(point(story, ["score"], [goal["event_id"]]))
        narrative = f"{story} {_score_headline(x)} at {x.clock}. {momentum}"
    elif chance:
        shooter, team = _player(x, chance) or "A shot", x.names[chance["team_id"]]
        story = f"Big chance for {team}! {shooter}'s shot {SHOT_OUTCOMES.get(chance['outcome'], 'goes in')}."
        points.append(point(story, ["danger_score"], [chance["event_id"]]))
        narrative = f"{story} {headline} at {x.clock}. {momentum}"
    else:
        extra = _latest_goal_point(x) or _top_sequence_point(x, analyst=False)
        if extra:
            points.append(extra)
        swing = _inflection_text(x)
        narrative = f"{headline} at {x.clock}. {momentum}" + (f" {swing}." if swing else "")
    leader = _territory_leader(x)
    if leader:
        points.append(point(f"{leader} are camped in the attacking areas.",
                            ["territorial_control"], x.last("territorial_control")))
    if len(narrative) > FAN_MAX_NARRATIVE:
        narrative = f"{headline} at {x.clock}. {momentum}"
    limitations = ["Based on a synthetic match."]
    if x.v("data_sufficiency") == "low":
        limitations.append("Only a few events so far, so this picture can change quickly.")
    return _output(request, headline, narrative, points[:FAN_MAX_POINTS], limitations)


EVIDENCE_WORDS = {"low": "low", "med": "medium", "high": "high"}


def _pct(value) -> str:
    return "no events" if value is None else f"{value:.1f}%"


ZONE_WORDS = {"opp_box": "inside the box", "attacking_third": "from the edge of the final third",
              "middle_third": "from distance"}
SHOT_WORDS = {"saved": "was saved", "off_target": "went wide", "blocked": "was blocked"}


def _side_leader(x: _View, metric: str, margin: float) -> dict | None:
    """The team clearly ahead on a team-keyed metric, or None when level / missing."""
    h, a = x.side(metric, x.home), x.side(metric, x.away)
    if h is None or a is None or abs(h - a) <= margin:
        return None
    return x.home if h > a else x.away


def _other(x: _View, team: dict) -> dict:
    return x.away if team["id"] == x.home["id"] else x.home


def _tactical_read(x: _View) -> tuple[str, str, str]:
    """(headline phrase, synthesis sentence, coaching takeaway) from how momentum, ball, threat and territory
    line up. The takeaway is an interpretation and carries no numbers."""
    mom = x.v("momentum")
    lead = x.home if mom > 0 else x.away
    ball = _side_leader(x, "pass_share", 5)
    threat = _side_leader(x, "danger_score", 0.5)
    terr = _side_leader(x, "territorial_control", 5)
    if abs(mom) < 0.2 and not (ball and threat and ball["id"] == threat["id"]):
        return ("an even phase",
                f"Momentum is close to level ({mom:+.2f}) and no side leads both the ball and the threat: "
                "an open, even phase where the next spell of pressure decides who takes over.",
                "Coaching takeaway: whoever wins the next second balls and sustains a spell in the final third "
                "should take control.")
    if ball and threat and ball["id"] != threat["id"]:
        return (f"{threat['name']} carry the threat, {ball['name']} keep the ball",
                f"{ball['name']} have more of the ball ({x.side('pass_share', ball):.1f}% of passes) but "
                f"{threat['name']} carry the threat (danger index {x.side('danger_score', threat):.2f} against "
                f"{x.side('danger_score', ball):.2f}). The pattern suggests {ball['name']} are circulating in front of "
                f"the opposition while {threat['name']} hurt them when they win it back.",
                f"Coaching takeaway: {ball['name']} need more penetration from their possession; {threat['name']} "
                "can keep looking to break quickly after regains.")
    if terr and terr["id"] != lead["id"]:
        return (f"{lead['name']} hold the momentum, {terr['name']} the territory",
                f"{terr['name']} are higher up the pitch ({x.side('territorial_control', terr):.1f}% of their actions "
                f"in attacking areas) but {lead['name']} hold the momentum ({mom:+.2f}): territory without the end "
                f"product so far for {terr['name']}.",
                f"Coaching takeaway: {terr['name']} need to turn territory into chances; {lead['name']} are "
                "getting more from fewer actions up the pitch.")
    aligned = [m for m in (ball, threat, terr) if m and m["id"] == lead["id"]]
    if abs(mom) >= 0.6 and len(aligned) >= 2:
        return (f"{lead['name']} in control",
                f"{lead['name']} are running this phase: momentum ({mom:+.2f}), ball, threat and territory point "
                f"the same way, so their pressure is sustained rather than a one-off break.",
                f"Coaching takeaway: {_other(x, lead)['name']} need to break the spell, for example by keeping "
                "the ball longer when they win it.")
    return (f"{lead['name']} edging it",
            f"{lead['name']} have the edge in momentum ({mom:+.2f}) without dominating every measure yet: "
            "a contest that can still tilt either way.",
            f"Coaching takeaway: {lead['name']} have a window to press home their edge before it fades.")


def _latest_chance(x: _View) -> str | None:
    shots = [e for e in x.r["recent_events"] + x.r["goals"] if e["type"] in ("shot", "goal")]
    if not shots:
        return None
    ev = max(shots, key=lambda e: (e["minute"], e["second"]))
    team = x.names[ev["team_id"]]
    where = ZONE_WORDS.get(ev["zone"], "from deep")
    if ev["type"] == "goal":
        return f"The latest chance was the goal for {team}, scored {where}."
    return f"The latest chance, for {team}, came {where} and {SHOT_WORDS.get(ev['outcome'], 'did not score')}."


def fallback_analyst(request: dict) -> dict:
    x = _View(request)
    mom = x.v("momentum")
    sh, sa = x.side("score", x.home), x.side("score", x.away)
    half = "first half" if x.r["clock"]["period"] == 1 else "second half"
    phrase, synthesis, takeaway = _tactical_read(x)
    headline = f"{x.clock} · {sh}–{sa} · {phrase}"
    if len(headline) > 120:
        headline = f"{x.clock} · {sh}–{sa} · tactical read"
    parts = [f"At {x.clock} ({half}), {x.home['name']} {sh}–{sa} {x.away['name']}.", synthesis]
    chance, swing = _latest_chance(x), _inflection_text(x)
    if chance:
        parts.append(chance)
    if swing:
        parts.append(f"{swing}.")
    parts.append(takeaway)
    narrative = " ".join(parts)

    ps_h, ps_a = x.side("pass_share", x.home), x.side("pass_share", x.away)
    ball_text = ("Ball and threat: no passes in this window." if ps_h is None else
                 f"Ball and threat: {x.home['name']} {ps_h:.1f}% of passes, {x.away['name']} {ps_a:.1f}%; "
                 f"danger index {x.home['name']} {x.side('danger_score', x.home):.2f}, "
                 f"{x.away['name']} {x.side('danger_score', x.away):.2f}.")
    points = [
        point(f"Momentum {mom:+.2f} over the last {x.win('momentum')}s: {_momentum_phrase(x)}", ["momentum"],
              x.last("momentum")),
        point(ball_text, ["pass_share", "danger_score"], x.last("danger_score")),
        point(f"Territory: {x.home['name']} {_pct(x.side('territorial_control', x.home))} of actions in attacking "
              f"areas, {x.away['name']} {_pct(x.side('territorial_control', x.away))}.", ["territorial_control"],
              x.last("territorial_control")),
    ]
    if swing:
        delta = x.v("inflection_point")["delta"]
        points.append(point(f"{swing} (change {abs(delta):.2f}).", ["inflection_point", "momentum"],
                            x.m["inflection_point"]["source_event_ids"][-5:]))
    top = _top_sequence_point(x, analyst=True)
    if top:
        points.append(top)

    suf = x.m["data_sufficiency"]
    limitations = [
        "Synthetic match data; metrics are deterministic and computed in Python.",
        "Pass share counts pass events only; it is not possession.",
        "Weights use event type and zone only; outcomes are ignored.",
        "Momentum is relative between the two teams and saturates when one side dominates the window.",
        f"Evidence level is {EVIDENCE_WORDS.get(suf['value'], suf['value'])} ({suf['details']['event_count']} events in the last "
        f"{x.win('data_sufficiency')}s).",
    ]
    return _output(request, headline, narrative, points[:6], limitations)


def _output(request: dict, headline: str, narrative: str, points: list[dict], limitations: list[str]) -> dict:
    return {
        "explanation_version": EXPLANATION_VERSION,
        "mode": request["mode"],
        "minute": request["clock"]["minute"],
        "headline": headline,
        "narrative": narrative,
        "key_points": points,
        "limitations": limitations,
        "data_sufficiency": request["metrics"]["data_sufficiency"]["value"],
        "source": "fallback",
    }


def fallback(request: dict) -> dict:
    return fallback_fan(request) if request["mode"] == "fan" else fallback_analyst(request)


# --- orchestration ----------------------------------------------------------

def _parse(raw) -> dict | str:
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            return f"output: invalid JSON ({e.msg})"
    return raw


def explain(request: dict, generator: Generator | None = None, max_attempts: int = 2) -> dict:
    """Return {"explanation", "source", "attempts"}. Online output is tried at most twice."""
    attempts: list[dict] = []
    previous: list[str] | None = None
    if generator is not None:
        for _ in range(max_attempts):
            retryable = True
            try:
                parsed = _parse(generator(request, previous))
            except Exception as e:  # network/provider failures count as a failed attempt
                parsed = f"generator: {type(e).__name__}: {e}"
                retryable = getattr(e, "retryable", True)  # e.g. timeout/auth: fall back at once
            if isinstance(parsed, dict):
                parsed = {**parsed, "source": "llm"}
                errors = validate_explanation(parsed, request)
            else:
                errors = [parsed]
            attempts.append({"ok": not errors, "errors": errors})
            if not errors:
                return {"explanation": parsed, "source": "llm", "attempts": attempts}
            if not retryable:
                break
            previous = errors

    output = fallback(request)
    errors = validate_explanation(output, request)
    if errors:  # a template bug must never reach the UI silently
        raise RuntimeError(f"fallback produced an invalid explanation: {errors}")
    return {"explanation": output, "source": "fallback", "attempts": attempts}


# --- traceability -----------------------------------------------------------

def _short_value(name: str, value) -> str:
    if name == "highlighted_sequences":
        return ", ".join(s["sequence_id"] for s in value) or "none"
    if name == "inflection_point" and value:
        return f"{clock_label(value['from_seconds'])}→{clock_label(value['to_seconds'])} Δ{value['delta']:+.2f}"
    return json.dumps(value, ensure_ascii=False)


def traceability_rows(metrics: dict, mode: str) -> list[dict]:
    """Rows for the traceability panel. Analyst mode exposes every field."""
    rows = []
    for name, m in metrics.items():
        w = m["window"]
        row = {"metric": name, "value": _short_value(name, m["value"]),
               "window": f"{clock_label(w['start_seconds'])}–{clock_label(w['end_seconds'])}",
               "sources": len(m["source_event_ids"])}
        if mode == "analyst":
            row.update({"formula_version": m["formula_version"], "config_version": m["config_version"],
                        "team_id": m["team_id"] or "", "source_event_ids": ", ".join(m["source_event_ids"])})
        rows.append(row)
    return rows


# --- data limits ------------------------------------------------------------

# (topic keyword, sentence). An explanation limitation mentioning a keyword is not repeated.
STANDARD_LIMITS = (
    ("synthetic", "Synthetic football data, not a real match."),
    ("possession", "Pass share counts pass events only; it is not real possession."),
    ("xg", "Danger is a simple weighted index of event type and zone, not xG."),
    ("momentum", "Momentum depends on the time window and decay settings."),
    ("predict", "No predictions, betting advice or outcome probabilities."),
    ("tracking", "Event data only; no continuous player tracking."),
)


def data_limits(explanation: dict) -> list[str]:
    """Standard limits plus any explanation limitation that covers a different topic."""
    extra = [t for t in explanation["limitations"]
             if not any(k in t.lower() for k, _ in STANDARD_LIMITS)]
    return [s for _, s in STANDARD_LIMITS] + extra


# --- cache ------------------------------------------------------------------

class ExplanationCache:
    """In-memory cache keyed by (match_id, at_seconds, mode, explanation_version)."""

    def __init__(self):
        self._store: dict[tuple, dict] = {}

    @staticmethod
    def key(request: dict) -> tuple:
        return (request["match"]["match_id"], request["clock"]["at_seconds"], request["mode"],
                EXPLANATION_VERSION)

    def get(self, request: dict) -> dict | None:
        return self._store.get(self.key(request))

    def put(self, request: dict, result: dict) -> None:
        self._store[self.key(request)] = result

    def clear(self) -> None:
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)


def cached_explain(cache: ExplanationCache, request: dict, generator: Generator | None = None,
                   clock=time.perf_counter) -> dict:
    """explain() behind the cache. Adds cache_hit, latency_ms and validated-reference counts."""
    hit = cache.get(request)
    if hit is not None:
        return {**hit, "cache_hit": True}
    start = clock()
    result = explain(request, generator)
    exp = result["explanation"]
    result = {
        **result,
        "cache_hit": False,
        "latency_ms": round((clock() - start) * 1000, 1),
        "validated": True,  # explain() only returns outputs that passed validate_explanation
        "metric_refs": sorted({m for p in exp["key_points"] for m in p["metric_refs"]}),
        "event_refs": sorted({e for p in exp["key_points"] for e in p["event_refs"]}),
    }
    cache.put(request, result)
    return result
