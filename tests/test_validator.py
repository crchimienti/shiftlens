import copy

import pytest

from matchpulse.validator import (
    CONFIG_PATH,
    DEFAULT_DATASET,
    canonical_json,
    fingerprint,
    load_json,
    load_match,
    normalize,
    validate_config,
    validate_match,
)


@pytest.fixture
def match():
    return copy.deepcopy(load_json(DEFAULT_DATASET))


def assert_error(data, fragment):
    errors = validate_match(data)
    assert any(fragment in e for e in errors), errors


# --- sample dataset ---------------------------------------------------------

def test_sample_dataset_is_valid(match):
    assert validate_match(match) == []


def test_sample_is_a_full_90_minute_match(match):
    assert match["duration_minutes"] == 90
    assert {e["period"] for e in match["events"]} == {1, 2}


def test_sample_config_is_valid():
    assert validate_config(load_json(CONFIG_PATH)) == []


# --- schema rules -----------------------------------------------------------

def test_unknown_event_type_rejected(match):
    match["events"][3]["type"] = "bicycle_kick"
    assert_error(match, "events/3/type")


def test_unknown_zone_rejected(match):
    match["events"][3]["zone"] = "car_park"
    assert_error(match, "events/3/zone")


@pytest.mark.parametrize("value", ["", "   "])
def test_blank_sequence_id_rejected(match, value):
    match["events"][0]["sequence_id"] = value
    assert_error(match, "events/0/sequence_id")


def test_missing_sequence_id_rejected(match):
    del match["events"][0]["sequence_id"]
    assert_error(match, "'sequence_id' is a required property")


def test_duration_out_of_range_rejected(match):
    match["duration_minutes"] = 121
    assert_error(match, "duration_minutes")


# --- cross-field rules ------------------------------------------------------

def test_duplicate_event_id_rejected(match):
    match["events"][1]["event_id"] = match["events"][0]["event_id"]
    assert_error(match, "duplicate event_id")


def test_duplicate_player_id_rejected(match):
    match["away_team"]["players"][0]["id"] = match["home_team"]["players"][0]["id"]
    assert_error(match, "duplicate player id")


def test_same_team_ids_rejected(match):
    match["away_team"]["id"] = match["home_team"]["id"]
    assert_error(match, "share id")


def test_equal_timestamp_rejected(match):
    a, b = match["events"][0], match["events"][1]
    b["minute"], b["second"] = a["minute"], a["second"]
    assert_error(match, "not strictly after")


def test_out_of_order_rejected(match):
    match["events"][0], match["events"][1] = match["events"][1], match["events"][0]
    assert_error(match, "not strictly after")


def test_period_going_back_rejected(match):
    match["events"][-1]["period"] = 1
    assert_error(match, "not strictly after")


def test_event_beyond_duration_rejected(match):
    match["events"][-1]["minute"] = match["duration_minutes"]
    assert_error(match, "outside duration")


def test_unknown_team_id_rejected(match):
    match["events"][0]["team_id"] = "XXX"
    assert_error(match, "unknown team_id")


def test_unknown_player_id_rejected(match):
    match["events"][0]["player_id"] = "NBR-99"
    assert_error(match, "unknown player_id")


def test_player_from_other_team_rejected(match):
    ev = match["events"][0]
    other = match["away_team"] if ev["team_id"] == match["home_team"]["id"] else match["home_team"]
    ev["player_id"] = other["players"][0]["id"]
    assert_error(match, "does not belong to team")


def test_player_id_is_optional(match):
    del match["events"][1]["player_id"]
    assert validate_match(match) == []


def test_final_score_mismatch_rejected(match):
    match["final_score"]["home"] += 1
    assert_error(match, "does not match goal events")


def test_removed_goal_breaks_score(match):
    goal = next(e for e in match["events"] if e["type"] == "goal")
    goal["type"] = "shot"
    goal["outcome"] = "off_target"
    assert_error(match, "does not match goal events")


def test_goal_without_player_rejected(match):
    goal = next(e for e in match["events"] if e["type"] == "goal")
    del goal["player_id"]
    assert_error(match, "goal without player_id")


# --- loading and determinism ------------------------------------------------

def test_load_match_returns_normalized(match):
    loaded, errors = load_match()
    assert errors == []
    assert all(set(e) >= {"player_id", "outcome", "lane"} for e in loaded["events"])


def test_two_loads_are_identical():
    first, _ = load_match()
    second, _ = load_match()
    assert first == second
    assert canonical_json(first) == canonical_json(second)
    assert fingerprint(first) == fingerprint(second)


def test_normalize_is_idempotent_and_pure(match):
    before = copy.deepcopy(match)
    once = normalize(match)
    assert normalize(once) == once
    assert match == before


def test_fingerprint_detects_change(match):
    original = fingerprint(match)
    match["events"][0]["second"] += 1
    assert fingerprint(match) != original


def test_load_missing_file_reports_clearly(tmp_path):
    loaded, errors = load_match(tmp_path / "nope.json")
    assert loaded is None and "not found" in errors[0]


def test_load_bad_json_reports_clearly(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{ not json", encoding="utf-8")
    loaded, errors = load_match(bad)
    assert loaded is None and "invalid JSON" in errors[0]


# --- config -----------------------------------------------------------------

def test_config_unknown_weight_key_rejected():
    config = load_json(CONFIG_PATH)
    config["weights"]["event"]["teleport"] = 1.0
    assert any("unknown event type" in e for e in validate_config(config))


def test_config_non_positive_window_rejected():
    config = load_json(CONFIG_PATH)
    config["windows"]["momentum_seconds"] = 0
    assert any("positive integer" in e for e in validate_config(config))
