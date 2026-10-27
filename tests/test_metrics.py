import copy
import json

import pytest

from matchpulse.metrics import (
    ConfigError,
    compute_metrics,
    danger_score,
    data_sufficiency,
    highlighted_sequences,
    inflection_point,
    momentum,
    momentum_at,
    pass_share,
    score,
    territorial_control,
)
from matchpulse.validator import CONFIG_PATH, load_json, load_match, validate_config, validate_match

# Tiny config with round numbers so expected values can be computed by hand.
CONFIG = {
    "config_version": "test",
    "schema_version": "1.1.0",
    "windows": {"pass_share_seconds": 60, "danger_seconds": 60, "momentum_seconds": 60,
                "territorial_seconds": 60, "sufficiency_seconds": 60},
    "momentum": {"half_life_seconds": 30},
    "inflection": {"threshold": 1.0, "span_seconds": 60, "step_seconds": 10, "min_window_events": 1},
    "sufficiency": {"med_from": 3, "high_from": 5},
    "highlights": {"top_n": 3},
    "attacking_zones": ["attacking_third", "opp_box"],
    "weights": {
        "event": {"pass": 1, "shot": 2, "goal": 4, "tackle": 1},
        "zone": {"middle_third": 1, "attacking_third": 2, "opp_box": 3},
    },
}


def make_match(events):
    """events: (t_seconds, team 'H'|'A', type, zone, sequence_id[, outcome])."""
    rows = []
    for i, (t, team, etype, zone, seq, *outcome) in enumerate(events, 1):
        ev = {"event_id": f"E{i}", "minute": t // 60, "second": t % 60, "period": 1,
              "team_id": team, "player_id": f"{team}-01", "type": etype, "zone": zone, "sequence_id": seq}
        if outcome:
            ev["outcome"] = outcome[0]
        rows.append(ev)
    goals = {s: sum(1 for e in rows if e["type"] == "goal" and e["team_id"] == s) for s in "HA"}
    team = lambda tid: {"id": tid, "name": tid, "players": [{"id": f"{tid}-01", "name": "P", "number": 1, "position": "FW"}]}
    return {"match_id": "T", "schema_version": "1.1.0", "seed": 0, "duration_minutes": 18,
            "home_team": team("H"), "away_team": team("A"),
            "final_score": {"home": goals["H"], "away": goals["A"]}, "events": rows}


@pytest.fixture
def cfg():
    return copy.deepcopy(CONFIG)


@pytest.fixture(scope="module")
def demo():
    match, errors = load_match()
    assert errors == []
    return match, load_json(CONFIG_PATH)


def test_fixture_helpers_are_valid():
    assert validate_config(CONFIG) == []
    assert validate_match(make_match([(10, "H", "goal", "opp_box", "S1")])) == []


# --- score ------------------------------------------------------------------

def test_score_no_goals(cfg):
    m = score(make_match([(10, "H", "pass", "middle_third", "S1")]), cfg, 60)
    assert m["value"] == {"H": 0, "A": 0} and m["source_event_ids"] == []


def test_score_counts_goals_up_to_clock_inclusive(cfg):
    match = make_match([(30, "H", "goal", "opp_box", "S1"), (100, "A", "goal", "opp_box", "S2")])
    assert score(match, cfg, 50)["value"] == {"H": 1, "A": 0}
    m = score(match, cfg, 100)
    assert m["value"] == {"H": 1, "A": 1} and m["source_event_ids"] == ["E1", "E2"]


# --- pass_share -------------------------------------------------------------

PASSES = [(10, "H", "pass", "middle_third", "S1"), (20, "H", "pass", "middle_third", "S1"),
          (30, "A", "pass", "middle_third", "S2"), (40, "H", "shot", "opp_box", "S3")]


def test_pass_share_known_values(cfg):
    m = pass_share(make_match(PASSES), cfg, 40)
    assert m["value"] == {"H": 66.67, "A": 33.33}
    assert m["details"]["pass_counts"] == {"H": 2, "A": 1}
    assert m["source_event_ids"] == ["E1", "E2", "E3"]
    assert "not possession" in m["notes"]


def test_pass_share_empty_window(cfg):
    m = pass_share(make_match(PASSES), cfg, 200)
    assert m["value"] == {"H": None, "A": None} and "No passes" in m["notes"]


def test_pass_share_short_window(cfg):
    cfg["windows"]["pass_share_seconds"] = 15
    m = pass_share(make_match(PASSES), cfg, 30)
    assert m["window"] == {"start_seconds": 15, "end_seconds": 30, "length_seconds": 15}
    assert m["value"] == {"H": 50.0, "A": 50.0}


# --- danger_score -----------------------------------------------------------

def test_danger_score_weighted_by_type_and_zone(cfg):
    match = make_match([(10, "H", "pass", "middle_third", "S1"),    # 1 x 1
                        (20, "H", "shot", "opp_box", "S1"),         # 2 x 3
                        (30, "A", "tackle", "middle_third", "S2"),  # 1 x 1
                        (40, "A", "clearance", "own_box", "S2")])   # unweighted
    m = danger_score(match, cfg, 40)
    assert m["value"] == {"H": 7.0, "A": 1.0}
    assert m["source_event_ids"] == ["E1", "E2", "E3"]


def test_danger_score_empty_window(cfg):
    assert danger_score(make_match(PASSES), cfg, 500)["value"] == {"H": 0, "A": 0}


# --- momentum ---------------------------------------------------------------

def test_momentum_time_decay_known_value(cfg):
    # H pass at 10 decays one half-life by t=40 -> 0.5; A pass at 40 -> 1. (0.5 - 1) / 1.5
    match = make_match([(10, "H", "pass", "middle_third", "S1"), (40, "A", "pass", "middle_third", "S2")])
    m = momentum(match, cfg, 40)
    assert m["value"] == -0.3333 and m["team_id"] == "A"


def test_momentum_tied(cfg):
    # H shot (2) decays to 1 by t=40; A tackle (1) at t=40.
    match = make_match([(10, "H", "shot", "middle_third", "S1"), (40, "A", "tackle", "middle_third", "S2")])
    m = momentum(match, cfg, 40)
    assert m["value"] == 0.0 and m["team_id"] is None


def test_momentum_one_sided_hits_bounds(cfg):
    assert momentum(make_match([(10, "H", "pass", "middle_third", "S1")]), cfg, 10)["value"] == 1.0
    assert momentum(make_match([(10, "A", "pass", "middle_third", "S1")]), cfg, 10)["value"] == -1.0


def test_momentum_empty_window(cfg):
    m = momentum(make_match(PASSES), cfg, 500)
    assert m["value"] == 0.0 and m["source_event_ids"] == [] and "No weighted events" in m["notes"]


def test_momentum_bounded_on_demo(demo):
    match, config = demo
    for t in range(0, match["duration_minutes"] * 60 + 1, 5):
        assert -1.0 <= momentum_at(match, config, t)[0] <= 1.0


# --- territorial_control ----------------------------------------------------

def test_territorial_control_known_values(cfg):
    match = make_match([(10, "H", "pass", "middle_third", "S1"), (20, "H", "shot", "opp_box", "S1"),
                        (30, "H", "pass", "attacking_third", "S1"), (40, "A", "tackle", "middle_third", "S2")])
    m = territorial_control(match, cfg, 40)
    assert m["value"] == {"H": 66.67, "A": 0.0}
    assert m["details"]["counts"] == {"H": {"events": 3, "attacking": 2}, "A": {"events": 1, "attacking": 0}}


def test_territorial_control_team_without_events(cfg):
    m = territorial_control(make_match([(10, "H", "pass", "opp_box", "S1")]), cfg, 10)
    assert m["value"] == {"H": 100.0, "A": None}


# --- highlighted_sequences --------------------------------------------------

SEQS = [(10, "H", "pass", "middle_third", "S1"), (20, "H", "shot", "opp_box", "S1"),          # 7
        (30, "A", "tackle", "middle_third", "S2"), (40, "A", "pass", "attacking_third", "S2"),  # 3
        (50, "H", "goal", "opp_box", "S3"),                                                     # 12
        (60, "A", "pass", "middle_third", "S4")]                                                # 1


def test_highlighted_sequences_top3(cfg):
    m = highlighted_sequences(make_match(SEQS), cfg, 60)
    assert [(s["sequence_id"], s["score"], s["team_id"]) for s in m["value"]] == \
        [("S3", 12.0, "H"), ("S1", 7.0, "H"), ("S2", 3.0, "A")]
    assert m["value"][0]["has_goal"] is True
    assert m["source_event_ids"] == ["E5", "E1", "E2", "E3", "E4"]


def test_highlighted_sequences_tie_prefers_earlier(cfg):
    match = make_match([(10, "A", "pass", "middle_third", "S9"), (20, "H", "pass", "middle_third", "S1")])
    assert [s["sequence_id"] for s in highlighted_sequences(match, cfg, 20)["value"]] == ["S9", "S1"]


def test_highlighted_sequences_respects_clock_and_top_n(cfg):
    cfg["highlights"]["top_n"] = 1
    m = highlighted_sequences(make_match(SEQS), cfg, 40)  # goal at 50 not yet played
    assert [s["sequence_id"] for s in m["value"]] == ["S1"]


# --- inflection_point -------------------------------------------------------

SWING = [(10, "H", "pass", "middle_third", "S1"), (20, "H", "pass", "middle_third", "S1"),
         (30, "H", "pass", "middle_third", "S1"), (70, "A", "shot", "opp_box", "S2"),
         (80, "A", "shot", "opp_box", "S2")]


def test_inflection_detects_swing_to_away(cfg):
    m = inflection_point(make_match(SWING), cfg, 120)
    # momentum is +1 at t=40 (home only) and -1 at t=100 (away only): earliest max swing.
    assert m["value"] == {"from_seconds": 40, "to_seconds": 100, "from_momentum": 1.0,
                          "to_momentum": -1.0, "delta": -2.0}
    assert m["team_id"] == "A" and m["source_event_ids"] == ["E4", "E5"]


def test_inflection_none_when_one_sided(cfg):
    match = make_match([(t, "H", "pass", "middle_third", "S1") for t in (10, 20, 30, 40)])
    m = inflection_point(match, cfg, 120)
    assert m["value"] is None and m["team_id"] is None


def test_inflection_threshold_is_strict(cfg):
    cfg["inflection"]["threshold"] = 2.0
    assert inflection_point(make_match(SWING), cfg, 120)["value"] is None


def test_inflection_short_span_only_adjacent_samples(cfg):
    cfg["inflection"]["span_seconds"] = 10
    v = inflection_point(make_match(SWING), cfg, 120)["value"]
    assert v["to_seconds"] - v["from_seconds"] == 10


def test_inflection_skips_thin_samples(cfg):
    cfg["inflection"]["min_window_events"] = 10
    m = inflection_point(make_match(SWING), cfg, 120)
    assert m["value"] is None and m["details"]["samples_used"] == 0


# --- data_sufficiency -------------------------------------------------------

@pytest.mark.parametrize("n, level", [(0, "low"), (2, "low"), (3, "med"), (4, "med"), (5, "high")])
def test_data_sufficiency_levels(cfg, n, level):
    match = make_match([(t, "H", "pass", "middle_third", "S1") for t in range(1, n + 1)])
    m = data_sufficiency(match, cfg, max(n, 1))
    assert m["value"] == level and m["details"]["event_count"] == n


# --- compute_metrics --------------------------------------------------------

METRIC_KEYS = {"metric_name", "value", "window", "formula_version", "config_version",
               "source_event_ids", "team_id", "notes", "details"}


def test_compute_metrics_shape_and_serializable(demo):
    match, config = demo
    result = compute_metrics(match, config)
    assert result["at_seconds"] == 90 * 60
    assert len(result["metrics"]) == 8
    for name, m in result["metrics"].items():
        assert set(m) == METRIC_KEYS and m["metric_name"] == name
    json.dumps(result)


def test_compute_metrics_deterministic(demo):
    match, config = demo
    runs = [json.dumps(compute_metrics(match, config, t), sort_keys=True) for t in (700, 700)]
    assert runs[0] == runs[1]
    reloaded, _ = load_match()
    assert json.dumps(compute_metrics(reloaded, config, 700), sort_keys=True) == runs[0]


def test_compute_metrics_demo_story(demo):
    match, config = demo
    end = compute_metrics(match, config)["metrics"]
    assert end["score"]["value"] == {"NBR": 2, "HBC": 1}
    top = end["highlighted_sequences"]["value"][0]
    assert top["sequence_id"] == "S216" and top["has_goal"] and top["start_seconds"] // 60 == 84  # late winner
    assert end["inflection_point"]["team_id"] == "NBR"     # the swing into the 23' opener
    assert end["inflection_point"]["value"]["to_seconds"] == 1390
    assert compute_metrics(match, config, 1000)["metrics"]["inflection_point"]["team_id"] == "HBC"


def test_compute_metrics_rejects_invalid_config_reference(demo):
    match, config = demo
    bad = copy.deepcopy(config)
    bad["attacking_zones"] = ["opp_box", "moon"]
    with pytest.raises(ConfigError, match="unknown zone 'moon'"):
        compute_metrics(match, bad)


@pytest.mark.parametrize("at", [-1, 90 * 60 + 1, 10.5])
def test_compute_metrics_rejects_bad_clock(demo, at):
    match, config = demo
    with pytest.raises(ValueError):
        compute_metrics(match, config, at)


# --- config validation for metric sections ----------------------------------

@pytest.mark.parametrize("mutate, fragment", [
    (lambda c: c["sufficiency"].update(med_from=5, high_from=5), "med_from < high_from"),
    (lambda c: c["inflection"].update(step_seconds=120), "must not exceed span"),
    (lambda c: c["inflection"].update(threshold=0), "threshold"),
    (lambda c: c["highlights"].update(top_n=0), "top_n"),
    (lambda c: c["weights"]["zone"].update(moon=1), "unknown zone 'moon'"),
    (lambda c: c["weights"]["event"].update({"pass": -1}), ">= 0"),
    (lambda c: c.pop("inflection"), "missing 'inflection'"),
])
def test_config_validation_rejects(cfg, mutate, fragment):
    mutate(cfg)
    assert any(fragment in e for e in validate_config(cfg)), validate_config(cfg)
