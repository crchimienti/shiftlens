"""Schematic pitch, key-move helpers and the key-move UI flow. Deterministic, no new metrics."""
import pytest
from streamlit.testing.v1 import AppTest

from matchpulse.metrics import momentum_at
from matchpulse.pitch import (
    chain_summary,
    momentum_figure,
    momentum_trend,
    move_events,
    move_points,
    move_stats,
    pitch_figure,
    pressure_bar_figure,
    schematic_xy,
)
from matchpulse.replay import Replay
from matchpulse.validator import CONFIG_PATH, ROOT, load_json, load_match


@pytest.fixture(scope="module")
def replay():
    match, _ = load_match()
    return Replay(match, load_json(CONFIG_PATH))


@pytest.fixture(scope="module")
def full(replay):
    return replay.snapshot(5400)


def teams(replay):
    return replay.match["home_team"], replay.match["away_team"]


# --- schematic positions ------------------------------------------------------

def test_home_attacks_right_away_is_mirrored():
    assert schematic_xy("opp_box", "right", attacks_right=True) == (91, 20)
    assert schematic_xy("opp_box", "right", attacks_right=False) == (9, 80)
    assert schematic_xy("own_box", "center", attacks_right=True) == (8, 50)
    assert schematic_xy("middle_third", None, attacks_right=True) == (50, 50)


def test_stacked_events_step_towards_goal_and_stay_on_pitch():
    assert schematic_xy("attacking_third", "left", True, stack=2) == (83, 77)
    assert schematic_xy("attacking_third", "left", False, stack=1) == (21, 16)  # mirrored offset
    assert schematic_xy("opp_box", "left", True, stack=5)[0] == 97


def test_move_points_are_ordered_deterministic_and_sum_to_impact(replay, full):
    move = next(m for m in full["metrics"]["highlighted_sequences"]["value"] if m["sequence_id"] == "S216")
    events = move_events(full, "S216")
    pts = move_points(events, "NBR", replay.players, replay.config)
    assert [p["step"] for p in pts] == list(range(1, len(events) + 1))
    assert [p["event_id"] for p in pts] == move["event_ids"]
    assert pts == move_points(events, "NBR", replay.players, replay.config)
    assert all(0 <= p["x"] <= 100 and 0 <= p["y"] <= 100 for p in pts)
    assert pts[-1]["type"] == "goal" and pts[-1]["player"] == "Adrian Novak"
    assert round(sum(p["weight"] for p in pts), 2) == round(move["score"], 2)


def test_away_move_points_sit_in_the_mirrored_half(replay, full):
    pts = move_points(move_events(full, "S093"), "NBR", replay.players, replay.config)
    goal = pts[-1]
    assert goal["team_id"] == "HBC" and goal["type"] == "goal" and goal["x"] < 20  # HBC attack right → left


# --- chain and stats -----------------------------------------------------------

def test_chain_summary(full):
    assert chain_summary(move_events(full, "S063")) == "Pass → Pressure → Pass → Carry → Shot (saved) → Save"
    assert chain_summary(move_events(full, "S216")).endswith("Cross → Goal")


def test_move_stats(replay, full):
    s = move_stats(move_events(full, "S216"), "NBR", replay.config["attacking_zones"])
    assert s == {"actions": 5, "passes": 1, "attacking_actions": 3, "shots": 1, "players": 4, "duration_seconds": 15}


def test_move_stats_count_only_the_moving_team(replay, full):
    s = move_stats(move_events(full, "S063"), "NBR", replay.config["attacking_zones"])
    assert s["actions"] == 4  # the Harbor City pressure and save are not counted for Northbridge FC


# --- momentum trend (existing metric, sampled) ---------------------------------

def test_momentum_trend_samples_existing_metric(replay):
    trend = momentum_trend(replay.match, replay.config, 2400, step=30)
    assert trend[0][0] == 0 and trend[-1][0] == 2400
    assert all(v == momentum_at(replay.match, replay.config, t)[0] for t, v in trend)
    assert all(-1 <= v <= 1 for _, v in trend)


# --- figures -------------------------------------------------------------------

def test_figures_build_and_are_deterministic(replay, full):
    home, away = teams(replay)
    pts = move_points(move_events(full, "S063"), "NBR", replay.players, replay.config)
    fig = pitch_figure(pts, home, away, detailed=True)
    arrows = [a for a in fig.layout.annotations if a.showarrow]
    assert len(arrows) == len(pts) - 1
    assert {t.name for t in fig.data} == {"Northbridge FC", "Harbor City"}
    assert fig.to_json() == pitch_figure(pts, home, away, detailed=True).to_json()
    bar = pressure_bar_figure(-0.82, home, away)  # away 91% from the left, home 9% from the right
    assert (bar.data[0].x, bar.data[1].x) == ((91,), (9,))
    assert len(momentum_figure(momentum_trend(replay.match, replay.config, 600), home, away).data) == 3


# --- UI flow -------------------------------------------------------------------

def button(at, prefix):
    return next(b for b in at.button if b.label.startswith(prefix))


def test_ui_key_move_jump_and_lens_layouts():
    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=30)
    at.session_state["mode"] = "Fan"  # Home is the landing view; these flows start in Fan Lens
    at.run()
    button(at, "Goal moment").click().run()
    assert at.session_state["selected_move"] == "S216"  # defaults to the top-ranked move (the late winner)
    assert any(e.label == "See the evidence behind this explanation" for e in at.expander)  # fan: hidden

    at.session_state["selected_move"] = "S216"
    at.run()
    button(at, "Jump replay to").click().run()
    state = at.session_state["replay_state"]
    assert (state.clock, state.playing) == (5060, False)  # end of S216, paused
    assert at.session_state["selected_move"] == "S216"

    at.radio[0].set_value("Analyst").run()
    assert any(m.value == "**Move breakdown**" for m in at.markdown)
    assert "formula_version" in at.dataframe[-1].value.columns  # traceability visible and last

    button(at, "Reset").click().run()
    assert at.session_state["selected_move"] == "S001"  # back to the only move at 00:00
    assert not at.exception


# --- Iteration 3: all moves, curved paths, match-flow markers -------------------

from matchpulse.pitch import all_moves  # noqa: E402


def test_all_moves_lists_every_sequence_latest_first_with_key_move_impacts(replay):
    snap = replay.snapshot(2400)
    moves = all_moves(snap, replay.match, replay.config)
    assert len(moves) == len({e["sequence_id"] for e in snap["events"]})
    assert [m["start_seconds"] for m in moves] == sorted((m["start_seconds"] for m in moves), reverse=True)
    impact = {m["sequence_id"]: m["score"] for m in moves}
    for key_move in snap["metrics"]["highlighted_sequences"]["value"]:
        assert impact[key_move["sequence_id"]] == key_move["score"]


def test_pitch_paths_are_curved_styled_and_end_in_the_net(replay, full):
    home, away = teams(replay)
    pts = move_points(move_events(full, "S216"), "NBR", replay.players, replay.config)
    fig = pitch_figure(pts, home, away)
    paths = [s for s in fig.layout.shapes if s.type == "path"]
    assert len(paths) == len(pts) - 1 and all(" Q " in s.path for s in paths)
    dashes = {s.line.dash for s in paths}
    assert {"solid", "dash"} <= dashes  # passes vs carries
    net = [s for s in fig.layout.shapes if s.type == "line" and s.x1 == 101]
    assert len(net) == 1  # the goal goes into Harbor City's net (home attacks right)


def test_match_flow_marks_goals_and_turning_point(replay, full):
    home, away = teams(replay)
    trend = momentum_trend(replay.match, replay.config, 5400)
    fig = momentum_figure(trend, home, away, goals=[(1390, "NBR"), (2284, "HBC")], turning=(1290, 1390, "NBR"))
    assert all(t.line.shape == "spline" for t in fig.data)
    assert sum(1 for a in fig.layout.annotations if a.text == "⚽") == 2
    assert any(a.text == "turning point" for a in fig.layout.annotations)


def test_ui_any_move_selector_reaches_moves_outside_the_top_three():
    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=30)
    at.session_state["mode"] = "Fan"  # Home is the landing view; these flows start in Fan Lens
    at.run()
    button(at, "Momentum swing").click().run()
    at.selectbox[0].set_value("S004").run()  # a quiet early move, not a featured key move
    assert at.session_state["selected_move"] == "S004"
    assert at.session_state["featured_move"] is None
    button(at, "Jump replay to").click().run()
    assert at.session_state["replay_state"].clock == 55 and at.session_state["selected_move"] == "S004"
    assert not at.exception
