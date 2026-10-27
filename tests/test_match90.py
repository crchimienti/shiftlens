"""Synthetic 90-minute match (schema 1.1.0): reproducible generator, coordinate/zone consistency, synthetic xG,
pressures, full squads and the scripted arc."""
import copy
import importlib.util

import pytest

from matchpulse.validator import DEFAULT_DATASET, ROOT, lane_of, load_json, validate_match, zone_of

spec = importlib.util.spec_from_file_location("build_match", ROOT / "tools" / "build_match.py")
BM = importlib.util.module_from_spec(spec)
spec.loader.exec_module(BM)


@pytest.fixture
def match():
    return copy.deepcopy(load_json(DEFAULT_DATASET))


def errors_for(match, i, **changes):
    match["events"][i].update(changes)
    return validate_match(match)


def test_committed_dataset_is_exactly_the_seeded_build():
    assert DEFAULT_DATASET.read_text(encoding="utf-8") == BM.dump(BM.build())
    assert BM.dump(BM.build()) == BM.dump(BM.build())  # same seed, same file


def test_fictional_clubs_full_squads_and_both_halves(match):
    assert (match["home_team"]["name"], match["away_team"]["name"]) == ("Northbridge FC", "Harbor City")
    for team in (match["home_team"], match["away_team"]):
        starters = [p for p in team["players"] if p["starter"]]
        assert len(starters) == 11 and len(team["players"]) == 16
        assert sum(p["position"] == "GK" for p in starters) == 1
    halves = {p: [e["minute"] for e in match["events"] if e["period"] == p] for p in (1, 2)}
    assert max(halves[1]) < 45 <= min(halves[2]) and max(halves[2]) < 90


def test_every_event_carries_coordinates_matching_its_zone_and_lane(match):
    for ev in match["events"]:
        assert 0 <= ev["x"] <= 100 and 0 <= ev["y"] <= 100
        assert ev["zone"] == zone_of(ev["x"], ev["y"]) and ev["lane"] == lane_of(ev["y"])


def test_shots_carry_synthetic_xg_and_pressures_are_recorded(match):
    shots = [e for e in match["events"] if e["type"] in ("shot", "goal")]
    assert len(shots) >= 30 and all(0 < e["xg"] < 1 for e in shots)
    assert not any("xg" in e for e in match["events"] if e["type"] not in ("shot", "goal"))
    assert sum(e["type"] == "pressure" for e in match["events"]) >= 100
    assert BM.xg(94, 50) > BM.xg(80, 50) > BM.xg(80, 15)  # closer and more central is better


def test_scripted_arc_goals_and_second_half_pressure(match):
    goals = [(e["minute"], e["team_id"]) for e in match["events"] if e["type"] == "goal"]
    assert goals == [(23, "NBR"), (38, "HBC"), (84, "NBR")] and match["final_score"] == {"home": 2, "away": 1}
    shots = lambda team, lo, hi: sum(e["type"] in ("shot", "goal") and e["team_id"] == team and lo <= e["minute"] < hi
                                     for e in match["events"])
    assert shots("NBR", 0, 15) > shots("HBC", 0, 15)  # Northbridge control the opening
    assert shots("HBC", 45, 60) > shots("NBR", 45, 60)  # Harbor City push after the break


def test_coordinate_rules_are_enforced(match):
    i = next(i for i, e in enumerate(match["events"]) if e["zone"] == "middle_third")
    assert any("does not match x/y" in e for e in errors_for(copy.deepcopy(match), i, x=95.0, y=50.0))
    assert any("lane" in e for e in errors_for(copy.deepcopy(match), i, y=99.0))
    bad = copy.deepcopy(match)
    del bad["events"][i]["y"]
    assert any("x/y pairs" in e for e in validate_match(bad))
    assert any("xg on a non-shot" in e for e in errors_for(copy.deepcopy(match), i, xg=0.2))
    j = next(i for i, e in enumerate(match["events"]) if e["period"] == 2)
    assert any("does not match minute" in e for e in errors_for(copy.deepcopy(match), j, period=1))
