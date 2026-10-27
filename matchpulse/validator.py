"""Load, validate and normalize a ShiftLens synthetic match dataset."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "config" / "match_schema.json"
CONFIG_PATH = ROOT / "config" / "metrics_config.json"
DEFAULT_DATASET = ROOT / "data" / "match_demo.json"

OPTIONAL_EVENT_FIELDS = ("player_id", "outcome", "lane", "x", "y", "end_x", "end_y", "xg")
SHOT_TYPES = ("shot", "goal")


def zone_of(x: float, y: float) -> str:
    """Zone from synthetic coordinates in the acting team's frame (x 0–100 towards the attacked goal)."""
    in_box_width = 21 <= y <= 79
    if x <= 17 and in_box_width:
        return "own_box"
    if x >= 83 and in_box_width:
        return "opp_box"
    return "defensive_third" if x < 100 / 3 else "middle_third" if x < 200 / 3 else "attacking_third"


def lane_of(y: float) -> str:
    """Lane from y (100 = the acting team's left touchline)."""
    return "left" if y > 200 / 3 else "right" if y < 100 / 3 else "center"


def load_json(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_schema() -> dict:
    return load_json(SCHEMA_PATH)


def schema_errors(data: dict, schema: dict | None = None) -> list[str]:
    validator = Draft202012Validator(schema or load_schema())
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
    return [f"schema: {'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}" for e in errors]


def rule_errors(data: dict) -> list[str]:
    """Cross-field rules JSON Schema cannot express. Assumes the schema already passed."""
    errors: list[str] = []
    home, away = data["home_team"], data["away_team"]

    if home["id"] == away["id"]:
        errors.append(f"teams: home and away share id '{home['id']}'")

    player_team: dict[str, str] = {}
    for team in (home, away):
        for p in team["players"]:
            if p["id"] in player_team:
                errors.append(f"players: duplicate player id '{p['id']}'")
            player_team[p["id"]] = team["id"]

    team_side = {home["id"]: "home", away["id"]: "away"}
    seen_ids: set[str] = set()
    goals = {"home": 0, "away": 0}
    prev_key = None

    for i, ev in enumerate(data["events"]):
        where = f"events[{i}] ({ev['event_id']})"

        if ev["event_id"] in seen_ids:
            errors.append(f"{where}: duplicate event_id")
        seen_ids.add(ev["event_id"])

        key = (ev["period"], ev["minute"], ev["second"])
        if prev_key is not None and key <= prev_key:
            errors.append(f"{where}: not strictly after previous event (period/minute/second {key} <= {prev_key})")
        prev_key = key

        if ev["minute"] >= data["duration_minutes"]:
            errors.append(f"{where}: minute {ev['minute']} is outside duration {data['duration_minutes']}")

        if ev["team_id"] not in team_side:
            errors.append(f"{where}: unknown team_id '{ev['team_id']}'")
        pid = ev.get("player_id")
        if pid is not None:
            if pid not in player_team:
                errors.append(f"{where}: unknown player_id '{pid}'")
            elif player_team[pid] != ev["team_id"]:
                errors.append(f"{where}: player '{pid}' does not belong to team '{ev['team_id']}'")

        if ("x" in ev) != ("y" in ev) or ("end_x" in ev) != ("end_y" in ev):
            errors.append(f"{where}: coordinates must come in x/y pairs")
        elif "x" in ev:
            if zone_of(ev["x"], ev["y"]) != ev["zone"]:
                errors.append(f"{where}: zone '{ev['zone']}' does not match x/y ({ev['x']}, {ev['y']})")
            if ev.get("lane") is not None and lane_of(ev["y"]) != ev["lane"]:
                errors.append(f"{where}: lane '{ev['lane']}' does not match y {ev['y']}")
        if "xg" in ev and ev["type"] not in SHOT_TYPES:
            errors.append(f"{where}: xg on a non-shot event")
        if data["duration_minutes"] >= 90 and (ev["period"] == 1) != (ev["minute"] < data["duration_minutes"] // 2):
            errors.append(f"{where}: period {ev['period']} does not match minute {ev['minute']}")

        if ev["type"] == "goal":
            if pid is None:
                errors.append(f"{where}: goal without player_id")
            if ev["team_id"] in team_side:
                goals[team_side[ev["team_id"]]] += 1

    declared = data["final_score"]
    if goals != {"home": declared["home"], "away": declared["away"]}:
        errors.append(
            f"score: final_score {declared['home']}-{declared['away']} "
            f"does not match goal events {goals['home']}-{goals['away']}"
        )
    return errors


def validate_match(data: dict) -> list[str]:
    """Return a list of human-readable errors; empty means valid."""
    errors = schema_errors(data)
    if errors:
        return errors  # rules rely on the shape, so stop here
    return rule_errors(data)


def normalize(data: dict) -> dict:
    """Canonical form: optional event fields present (None), keys sorted on dump."""
    out = copy.deepcopy(data)
    for ev in out["events"]:
        for field in OPTIONAL_EVENT_FIELDS:
            ev.setdefault(field, None)
    return out


def canonical_json(data: dict) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def fingerprint(data: dict) -> str:
    return hashlib.sha256(canonical_json(normalize(data)).encode("utf-8")).hexdigest()


def load_match(path: str | Path = DEFAULT_DATASET) -> tuple[dict | None, list[str]]:
    """Load + validate. Returns (normalized_match, errors); match is None when invalid."""
    try:
        data = load_json(path)
    except FileNotFoundError:
        return None, [f"file: not found: {path}"]
    except json.JSONDecodeError as e:
        return None, [f"file: invalid JSON in {path}: line {e.lineno} col {e.colno}: {e.msg}"]
    errors = validate_match(data)
    return (None, errors) if errors else (normalize(data), [])


REQUIRED_WINDOWS = ("pass_share_seconds", "danger_seconds", "momentum_seconds", "territorial_seconds", "sufficiency_seconds")
CONFIG_SECTIONS = ("config_version", "schema_version", "windows", "momentum", "inflection",
                   "sufficiency", "highlights", "attacking_zones", "weights")


def _is_pos_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v > 0


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def validate_config(config: dict, schema: dict | None = None) -> list[str]:
    """Checks on metrics_config.json, including references to the match schema enums."""
    schema = schema or load_schema()
    event_props = schema["$defs"]["event"]["properties"]
    types, zones = event_props["type"]["enum"], event_props["zone"]["enum"]
    errors = [f"config: missing '{k}'" for k in CONFIG_SECTIONS if k not in config]
    if errors:
        return errors

    if config["schema_version"] != schema["properties"]["schema_version"]["const"]:
        errors.append(f"config: schema_version '{config['schema_version']}' does not match dataset schema")
    for name in REQUIRED_WINDOWS:
        if not _is_pos_int(config["windows"].get(name)):
            errors.append(f"config: window '{name}' must be a positive integer")

    half_life = config["momentum"].get("half_life_seconds")
    if not _is_number(half_life) or half_life <= 0:
        errors.append("config: momentum.half_life_seconds must be a positive number")

    inf = config["inflection"]
    if not _is_number(inf.get("threshold")) or not 0 < inf["threshold"] <= 2:
        errors.append("config: inflection.threshold must be in (0, 2]")
    for key in ("span_seconds", "step_seconds"):
        if not _is_pos_int(inf.get(key)):
            errors.append(f"config: inflection.{key} must be a positive integer")
    if _is_pos_int(inf.get("span_seconds")) and _is_pos_int(inf.get("step_seconds"))             and inf["step_seconds"] > inf["span_seconds"]:
        errors.append("config: inflection.step_seconds must not exceed span_seconds")
    if not isinstance(inf.get("min_window_events"), int) or inf["min_window_events"] < 0:
        errors.append("config: inflection.min_window_events must be an integer >= 0")

    suf = config["sufficiency"]
    if not (_is_pos_int(suf.get("med_from")) and _is_pos_int(suf.get("high_from"))
            and suf["med_from"] < suf["high_from"]):
        errors.append("config: sufficiency needs positive integers med_from < high_from")

    if not _is_pos_int(config["highlights"].get("top_n")):
        errors.append("config: highlights.top_n must be a positive integer")

    if not config["attacking_zones"]:
        errors.append("config: attacking_zones must not be empty")
    for zone in config["attacking_zones"]:
        if zone not in zones:
            errors.append(f"config: attacking_zones references unknown zone '{zone}'")

    for section, allowed, label in (("event", types, "event type"), ("zone", zones, "zone")):
        weights = config["weights"].get(section)
        if not isinstance(weights, dict):
            errors.append(f"config: weights.{section} missing")
            continue
        for key, w in weights.items():
            if key not in allowed:
                errors.append(f"config: {section} weight for unknown {label} '{key}'")
            elif not _is_number(w) or w < 0:
                errors.append(f"config: {section} weight for '{key}' must be a number >= 0")
    return errors
