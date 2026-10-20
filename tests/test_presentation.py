"""Display helpers: relabel and format existing values only (no new metrics)."""
import pytest

from matchpulse.explain import traceability_rows
from matchpulse.presentation import (
    friendly_trace_rows,
    match_summary,
    metric_label,
    momentum_cue,
    momentum_reading,
    pressure_split,
    window_label,
)
from matchpulse.replay import Replay
from matchpulse.validator import CONFIG_PATH, load_json, load_match


@pytest.fixture(scope="module")
def replay():
    match, _ = load_match()
    return Replay(match, load_json(CONFIG_PATH))


@pytest.mark.parametrize("value, reading", [
    (0.98, "Northbridge FC on top"), (0.6, "Northbridge FC on top"), (0.3, "Northbridge FC edging it"),
    (0.0, "Balanced spell"), (-0.19, "Balanced spell"), (-0.2, "Harbor City edging it"), (-0.82, "Harbor City on top"),
])
def test_momentum_reading(value, reading):
    assert momentum_reading(value, "Northbridge FC", "Harbor City") == reading


def test_momentum_cue_points_at_the_leading_side():
    assert momentum_cue(-0.82, "Northbridge FC", "Harbor City") == "◀ Harbor City on top"
    assert momentum_cue(0.82, "Northbridge FC", "Harbor City") == "Northbridge FC on top ▶"


def test_pressure_split_is_the_momentum_rearranged():
    assert pressure_split(-0.82) == (9, 91)
    assert pressure_split(0.0) == (50, 50)
    assert pressure_split(1.0) == (100, 0)


def test_labels():
    assert metric_label("danger_score") == "Danger index"
    assert metric_label("data_sufficiency") == "Evidence level"
    assert window_label({"length_seconds": 180}) == "last 3 min"
    assert window_label({"length_seconds": None}) == "match so far"


def test_match_summary_counts():
    events = [
        {"team_id": "H", "type": "shot", "outcome": "saved", "zone": "opp_box"},
        {"team_id": "A", "type": "save", "outcome": None, "zone": "own_box"},
        {"team_id": "H", "type": "goal", "outcome": None, "zone": "opp_box"},
        {"team_id": "H", "type": "shot", "outcome": "off_target", "zone": "attacking_third"},
        {"team_id": "A", "type": "pass", "outcome": "incomplete", "zone": "middle_third"},
        {"team_id": "A", "type": "pass", "outcome": "complete", "zone": "attacking_third"},
        {"team_id": "H", "type": "corner", "outcome": "complete", "zone": "attacking_third"},
        {"team_id": "A", "type": "foul", "outcome": None, "zone": "defensive_third"},
    ]
    s = match_summary(events, ("H", "A"), ["attacking_third", "opp_box"])
    assert s["Shots"] == {"H": 3, "A": 0} and s["On target"] == {"H": 2, "A": 0}
    assert s["Saves"]["A"] == 1 and s["Corners"]["H"] == 1 and s["Fouls"]["A"] == 1
    assert s["Passes"]["A"] == 2 and s["Unsuccessful passes"]["A"] == 1
    assert s["Attacking actions"] == {"H": 4, "A": 1}


def test_match_summary_full_time_is_consistent_with_score(replay):
    snap = replay.snapshot(1320)
    s = match_summary(snap["events"], ("NBR", "HBC"), replay.config["attacking_zones"])
    goals = snap["metrics"]["score"]["value"]
    for team in ("NBR", "HBC"):
        assert s["Shots"][team] >= s["On target"][team] >= goals[team]
        assert s["Passes"][team] >= s["Unsuccessful passes"][team]


@pytest.mark.parametrize("mode", ["fan", "analyst"])
def test_friendly_trace_rows_keep_keys_and_counts(replay, mode):
    metrics = replay.snapshot(674)["metrics"]
    raw = traceability_rows(metrics, mode)
    nice = friendly_trace_rows(raw, metrics, {"NBR": "Northbridge FC", "HBC": "Harbor City"})
    assert [set(r) for r in nice] == [set(r) for r in raw]
    assert [r["sources"] for r in nice] == [r["sources"] for r in raw]
    by_metric = {r["metric"]: r for r in nice}
    assert by_metric["Momentum"]["value"] == "-0.82 (Harbor City on top)"
    assert by_metric["Pass share"]["value"] == "NBR 60% · HBC 40%"
    assert by_metric["Evidence level"]["value"] == "High (28 events)"
    assert by_metric["Momentum"]["window"] == "08:14–11:14 (last 3 min)"
