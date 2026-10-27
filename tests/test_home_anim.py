"""Animated sequence player (synthetic coordinates, chart-side controls, reduced motion), the Home landing view, the
Quick Tour and navigation across all four spaces."""
import json

import pytest
from streamlit.testing.v1 import AppTest

from matchpulse import anim as AN
from matchpulse.replay import Replay
from matchpulse.validator import CONFIG_PATH, ROOT, load_json, load_match


@pytest.fixture(scope="module")
def replay():
    match, _ = load_match()
    return Replay(match, load_json(CONFIG_PATH))


def move(replay, sid):
    return [e for e in replay.match["events"] if e["sequence_id"] == sid]


def teams(replay):
    return replay.match["home_team"], replay.match["away_team"]


def app(**state):
    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=60)
    for k, v in state.items():
        at.session_state[k] = v
    at.run()
    assert not at.exception, at.exception
    return at


def button(at, prefix):
    return next(b for b in at.button if b.label.startswith(prefix))


# --- animation frames ---------------------------------------------------------------------------------------------

def test_ball_travels_from_recorded_start_to_recorded_end(replay):
    events = move(replay, "S216")  # Northbridge's late winner: pass, carry, dribble, cross, goal
    frames = AN.frames_for(events, replay.players, "NBR")
    assert [f["step"] for f in frames if f["sub"] == 0] == list(range(1, len(events) + 1))
    cross = next(e for e in events if e["type"] == "cross")
    i = events.index(cross) + 1
    steps = [f for f in frames if f["step"] == i]
    assert steps[0]["ball"] == (cross["x"], cross["y"]) and steps[-1]["ball"] == (cross["end_x"], cross["end_y"])
    dribble = next(f for f in frames if f["event_id"] == next(e for e in events if e["type"] == "dribble")["event_id"])
    assert dribble["end_recorded"]  # a dribble has no end point and does not move: nothing is invented
    carry = [f for f in frames if f["event_id"] == next(e for e in events if e["type"] == "carry")["event_id"]]
    assert carry[-1]["actor"] == carry[-1]["ball"]  # the carrier moves with the ball; others stay put


def test_away_moves_are_mirrored_like_the_static_pitch(replay):
    events = move(replay, "S093")  # Harbor City's corner goal
    goal = next(f for f in AN.frames_for(events, replay.players, "NBR") if f["sub"] == 0 and f["step"] == 2)
    e = events[1]
    assert goal["ball"] == (100 - e["x"], 100 - e["y"]) and goal["ball"][0] < 20  # attacking right → left


def test_reduced_motion_shows_steps_in_place(replay):
    events = move(replay, "S216")
    smooth = AN.frames_for(events, replay.players, "NBR")
    calm = AN.frames_for(events, replay.players, "NBR", reduce_motion=True)
    assert len(calm) < len(smooth) and max(f["sub"] for f in calm) == 1
    fig = AN.animation_figure(events, replay.players, *teams(replay), reduce_motion=True)
    assert fig.layout.updatemenus[0].buttons[0].args[1]["frame"]["duration"] == 600


def test_figure_has_play_pause_restart_slider_and_starts_at_the_selection(replay):
    events = move(replay, "S216")
    fig = AN.animation_figure(events, replay.players, *teams(replay), start_step=4)
    assert [b.label for b in fig.layout.updatemenus[0].buttons] == ["▶ Play", "⏸ Pause", "⟲ Restart"]
    assert len(fig.layout.sliders[0].steps) == len(events) and fig.layout.sliders[0].active == 3
    assert fig.layout.title.text == f"<b>Animated step 4 of {len(events)}</b>"
    assert "Adeyemi" in fig.layout.annotations[0].text  # the cross by Samuel Adeyemi
    assert fig.to_json() == AN.animation_figure(events, replay.players, *teams(replay), start_step=4).to_json()


@pytest.mark.parametrize("lens", ["Fan", "Analyst"])
def test_static_animated_toggle_in_both_lenses_never_moves_the_clock(lens):
    at = app(mode=lens)
    button(at, "Goal moment").click().run()
    clock = at.session_state["replay_state"].clock
    assert at.session_state["pitch_view"] == "Static"
    at.segmented_control(key="pitch_view").set_value("Animated").run()
    charts = [json.loads(c.proto.spec) for c in at.get("plotly_chart")]
    anim = [c for c in charts if c.get("frames")]
    assert len(anim) == 1 and anim[0]["layout"]["title"]["text"].startswith("<b>Animated step")
    assert at.session_state["replay_state"].clock == clock and not at.session_state["replay_state"].playing
    assert any("not tracking" in c.value for c in at.caption)


# --- Home, tour and navigation -------------------------------------------------------------------------------------

def test_home_is_the_landing_view_with_logo_claim_and_quick_starts():
    at = app()
    assert at.session_state["mode"] == "Home"
    text = " ".join(m.value for m in at.markdown)
    assert "From moments to evidence. From evidence to insight." in text and 'aria-label="ShiftLens logo"' in text
    assert not any(b.label == "Play" for b in at.button)  # no replay controls on Home
    button(at, "Open Analyst Lens").click().run()
    assert at.session_state["mode"] == "Analyst" and any(b.label == "Play" for b in at.button)


def test_quick_tour_steps_and_try_it_jumps_to_the_right_place():
    at = app()
    assert any("1 · Replay controls" in m.value for m in at.markdown)
    assert at.button(key="tour_back").disabled
    at.button(key="tour_next").click().run()
    assert any("2 · Evidence trace" in m.value for m in at.markdown)
    at.button(key="tour_next").click().run()
    assert any("3 · Hypothesis testing" in m.value for m in at.markdown) and at.button(key="tour_next").disabled
    at.button(key="tour_try").click().run()
    assert at.session_state["mode"] == "Analyst" and at.session_state["replay_state"].clock == 5060
    assert any("Tactical Hypothesis Lab" in m.value for m in at.markdown)


def test_all_four_spaces_render_in_both_languages():
    for lang in ("en", "es"):
        for mode in ("Home", "Fan", "Analyst", "Capture"):
            app(mode=mode, lang=lang)  # app() asserts no exception


def test_agents_and_capture_are_still_visible():
    at = app(mode="Analyst")
    assert any("Agent architecture" in m.value for m in at.markdown)
    cap = app(mode="Capture")
    assert any("Planned · Future Architecture" in m.value for m in cap.markdown)
