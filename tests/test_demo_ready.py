"""Demo-ready iteration: replay speed, lineups, story feed, cards, pitch upgrades and the UI wiring."""
import copy

import pytest
from streamlit.testing.v1 import AppTest

from matchpulse.lineups import (
    fallback_lineup,
    formation_lines,
    lineup_errors,
    lineup_figure,
    lineup_slots,
    load_lineups,
    team_lineup,
)
from matchpulse.pitch import FIVE_LANES, corner_xy, move_events, move_points, pitch_figure
from matchpulse.presentation import match_summary
from matchpulse.replay import Replay, ReplayState
from matchpulse.story import card_counts, event_focus, speed_step, story_moments
from matchpulse.validator import CONFIG_PATH, ROOT, load_json, load_match


@pytest.fixture(scope="module")
def replay():
    match, _ = load_match()
    return Replay(match, load_json(CONFIG_PATH))


@pytest.fixture(scope="module")
def full(replay):
    return replay.snapshot(1320)


# --- speed ---------------------------------------------------------------------

@pytest.mark.parametrize("label, step", [("0.5x", 5), ("1x", 10), ("1.5x", 15), ("2x", 20), (None, 10), ("9x", 10)])
def test_speed_step(label, step):
    assert speed_step(label) == step


@pytest.mark.parametrize("label, ticks", [("0.5x", 264), ("1x", 132), ("1.5x", 88), ("2x", 66)])
def test_full_playthrough_at_each_speed_is_deterministic(label, ticks):
    state = ReplayState(duration=1320)
    state.play()
    n = 0
    while state.playing:
        state.tick(speed_step(label))
        n += 1
    assert (n, state.clock) == (ticks, 1320)


# --- lineups -------------------------------------------------------------------

def test_demo_lineups_are_valid_and_use_the_authored_formations(replay):
    lineups = load_lineups()
    assert lineup_errors(replay.match, lineups) == []
    assert team_lineup(replay.match, replay.match["home_team"], lineups)["formation"] == "4-3-3"
    assert team_lineup(replay.match, replay.match["away_team"], lineups)["formation"] == "4-2-3-1"
    assert formation_lines("4-2-3-1") == [4, 2, 3, 1]


def test_lineup_slots_are_deterministic_and_mirrored(replay):
    lineup = team_lineup(replay.match, replay.match["home_team"], load_lineups())
    home = lineup_slots(lineup, attacks_right=True)
    away = lineup_slots(lineup, attacks_right=False)
    assert len(home) == 11 and home == lineup_slots(lineup, attacks_right=True)
    gk = home[0]
    assert (gk["player_id"], gk["x"], gk["y"]) == ("NBR-01", 5, 50)
    assert all(s["x"] <= 48 for s in home)  # own half
    assert [(a["x"], a["y"]) for a in away] == [(100 - h["x"], 100 - h["y"]) for h in home]
    left_back = next(s for s in home if s["player_id"] == "NBR-03")
    assert left_back["y"] == 80  # listed first = left side of the attacking team


def test_fallback_lineup_groups_by_position(replay):
    fb = fallback_lineup(replay.match["away_team"])
    assert fb["formation"] == "4-3-3" and len(fb["lines"][0]) == 1
    other = {**replay.match, "match_id": "OTHER"}
    assert lineup_errors(other, load_lineups()) == []  # falls back cleanly


def test_lineup_errors_catch_bad_config(replay):
    bad = copy.deepcopy(load_lineups())
    bad["matches"]["MP-DEMO-001"]["NBR"]["lines"][3].pop()
    bad["matches"]["MP-DEMO-001"]["HBC"]["formation"] = "4-4-2"
    errors = lineup_errors(replay.match, bad)
    assert any("NBR: lineup players" in e for e in errors) and any("HBC: formation 4-4-2" in e for e in errors)


def test_lineup_figure_builds(replay):
    fig = lineup_figure(replay.match, load_lineups(), "#00f", "#f80")
    assert len(fig.data) == 4 and len(fig.data[0].x) == 11
    assert any("4-2-3-1" in a.text for a in fig.layout.annotations)


# --- story feed, cards, event focus ----------------------------------------------

def test_story_moments_are_factual_and_latest_first(replay, full):
    moments = story_moments(full, replay.match, replay.players)
    assert [m["seconds"] for m in moments] == sorted((m["seconds"] for m in moments), reverse=True)
    goals = [m["text"] for m in moments if m["kind"] == "goal"]
    assert goals == ["GOAL — Adrian Novak (Northbridge FC), set up by Samuel Adeyemi's pass",
                     "GOAL — Daniel Kowalski (Harbor City), set up by Felix Brandt's corner",
                     "GOAL — Marcus Lindqvist (Northbridge FC), set up by Diego Varela's cross"]
    assert any(m["text"] == "Chance — Adrian Novak (Northbridge FC), saved by Pavel Horvat" for m in moments)
    turning = next(m for m in moments if m["kind"] == "turning")
    assert "Northbridge FC" in turning["text"] and turning["sequence_id"]
    assert all(m["seconds"] <= 1320 for m in moments)


def test_story_has_no_future_events(replay):
    early = story_moments(replay.snapshot(300), replay.match, replay.players)
    assert all(m["seconds"] <= 300 for m in early) and not any(m["kind"] == "goal" for m in early)


def test_cards_counted_only_when_present(full):
    assert card_counts(full["events"]) == ({}, {})
    fake = [{"type": "yellow_card", "team_id": "NBR", "player_id": "NBR-06"},
            {"type": "red_card", "team_id": "NBR", "player_id": "NBR-06"}]
    by_player, by_team = card_counts(fake)
    assert by_player["NBR-06"] == {"yellow": 1, "red": 1} and by_team["NBR"] == {"yellow": 1, "red": 1}


def test_match_summary_has_card_rows(replay, full):
    s = match_summary(full["events"], ("NBR", "HBC"), replay.config["attacking_zones"])
    assert s["Yellow cards"] == {"NBR": 0, "HBC": 0} and s["Red cards"] == {"NBR": 0, "HBC": 0}


def test_event_focus(full):
    assert event_focus(full, "E040") == "S09" and event_focus(full, "E999") is None


# --- pitch upgrades --------------------------------------------------------------

def test_corners_sit_at_the_flag(replay, full):
    assert corner_xy("right", True) == (99, 3) and corner_xy("right", False) == (1, 97)
    pts = move_points(move_events(full, "S13"), "NBR", replay.players, replay.config)
    corner = next(p for p in pts if p["type"] == "corner")
    assert (corner["x"], corner["y"]) == (1, 97)  # Harbor City attack right → left, right-lane flag


def test_analyst_pitch_has_five_lane_grid_fan_pitch_is_clean(replay, full):
    home, away = replay.match["home_team"], replay.match["away_team"]
    pts = move_points(move_events(full, "S09"), "NBR", replay.players, replay.config)
    tactical = pitch_figure(pts, home, away, detailed=True)
    lanes = [s for s in tactical.layout.shapes if s.type == "line" and s.line.dash == "dash" and s.x0 == 0]
    assert sorted(s.y0 for s in lanes) == list(FIVE_LANES[1:-1])
    assert sum(1 for a in tactical.layout.annotations if a.text == "Half-space") == 2
    fan = pitch_figure(pts, home, away)
    assert not any(s.type == "line" and s.line.dash in ("dot", "dash") and s.x0 == 0 for s in fan.layout.shapes)


def test_highlight_rings_the_selected_event(replay, full):
    home, away = replay.match["home_team"], replay.match["away_team"]
    pts = move_points(move_events(full, "S09"), "NBR", replay.players, replay.config)
    fig = pitch_figure(pts, home, away, highlight="E040")
    ring = next(t for t in fig.data if t.name == "Selected action")
    goal = next(p for p in pts if p["event_id"] == "E040")
    assert (ring.x[0], ring.y[0]) == (goal["x"], goal["y"])


def test_off_target_shot_flies_past_the_post(replay, full):
    home, away = replay.match["home_team"], replay.match["away_team"]
    pts = move_points(move_events(full, "S03"), "NBR", replay.players, replay.config)
    fig = pitch_figure(pts, home, away)
    assert any(s.type == "line" and s.line.dash == "dash" and s.x1 == 101 for s in fig.layout.shapes)


# --- UI wiring -----------------------------------------------------------------

def button(at, prefix):
    return next(b for b in at.button if b.label.startswith(prefix))


def test_ui_speed_story_lineups_and_lenses():
    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=30)
    at.run()
    assert at.session_state["speed"] == "1x"
    button(at, "Goal moment").click().run()
    assert any("Auto story · deterministic fallback · validated" in c.value for c in at.caption)
    assert "explanation" not in at.session_state  # auto story is not stored or cached
    assert any("👥 Lineups" in m.value and "4-2-3-1" in m.value for m in at.markdown)

    show = next(b for b in at.button if b.label == "Show")
    show.click().run()
    assert at.session_state["selected_event"] and at.session_state["selected_move"]

    at.session_state["speed"] = "2x"
    at.radio[0].set_value("Analyst").run()
    assert at.session_state["speed"] == "2x"
    assert any("📋 Key moments log" in m.value for m in at.markdown)
    assert "formula_version" in at.dataframe[-1].value.columns
    assert not at.exception
