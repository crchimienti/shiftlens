import json

import pytest
from streamlit.testing.v1 import AppTest

from matchpulse.replay import Replay, ReplayState, clock_label
from matchpulse.validator import CONFIG_PATH, ROOT, load_json, load_match

DURATION = 22 * 60


@pytest.fixture(scope="module")
def replay():
    match, errors = load_match()
    assert errors == []
    return Replay(match, load_json(CONFIG_PATH))


def dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True)


# --- ReplayState ------------------------------------------------------------

def test_new_state_starts_paused_at_zero(replay):
    state = replay.new_state()
    assert (state.clock, state.playing, state.duration) == (0, False, DURATION)


def test_play_pause():
    state = ReplayState(duration=100)
    state.play()
    assert state.playing
    state.pause()
    assert not state.playing


def test_tick_only_advances_while_playing():
    state = ReplayState(duration=100)
    state.tick(10)
    assert state.clock == 0
    state.play()
    state.tick(10)
    state.tick(10)
    assert state.clock == 20


def test_tick_stops_at_full_time():
    state = ReplayState(duration=25, clock=20, playing=True)
    state.tick(10)
    assert state.clock == 25 and not state.playing


def test_play_at_full_time_is_noop():
    state = ReplayState(duration=25, clock=25)
    state.play()
    assert not state.playing


@pytest.mark.parametrize("target, expected", [(-5, 0), (42, 42), (999, 100)])
def test_seek_clamps(target, expected):
    state = ReplayState(duration=100)
    state.seek(target)
    assert state.clock == expected


def test_seek_keeps_playing_unless_full_time():
    state = ReplayState(duration=100, playing=True)
    state.seek(50)
    assert state.playing
    state.seek(100)
    assert not state.playing


def test_reset_returns_to_zero_and_stops():
    state = ReplayState(duration=100, clock=73, playing=True)
    state.reset()
    assert (state.clock, state.playing) == (0, False)


def test_clock_label():
    assert clock_label(0) == "00:00" and clock_label(605) == "10:05" and clock_label(1320) == "22:00"


# --- snapshots --------------------------------------------------------------

def test_snapshot_at_zero(replay):
    snap = replay.snapshot(0)
    assert snap["clock"] == "00:00" and snap["period"] == 1
    assert [e["event_id"] for e in snap["events"]] == ["E001"]  # kickoff at 00:00 is visible
    assert snap["metrics"]["score"]["value"] == {"NBR": 0, "HBC": 0}


def test_snapshot_fixed_time_is_stable(replay):
    first = dumps(replay.snapshot(660))
    replay.snapshot(1200)  # visiting other times must not change it
    assert dumps(replay.snapshot(660)) == first
    match, _ = load_match()
    assert dumps(Replay(match, load_json(CONFIG_PATH)).snapshot(660)) == first  # fresh instance


def test_snapshot_period_follows_events(replay):
    assert replay.snapshot(659)["period"] == 1
    assert replay.snapshot(660)["period"] == 2


def test_reset_gives_same_snapshot_as_fresh_start(replay):
    state = replay.new_state()
    state.play()
    for _ in range(30):
        state.tick(10)
    state.reset()
    assert dumps(replay.snapshot(state.clock)) == dumps(replay.snapshot(replay.new_state().clock))


def test_full_playthrough_is_deterministic(replay):
    def run():
        state, clocks = replay.new_state(), []
        state.play()
        while state.playing:
            state.tick(10)
            clocks.append((state.clock, dumps(replay.snapshot(state.clock)["metrics"]["score"])))
        return clocks
    first = run()
    assert first == run()
    assert first[-1][0] == DURATION
    assert replay.snapshot(DURATION)["metrics"]["score"]["value"] == {"NBR": 2, "HBC": 1}


def test_replay_rejects_invalid_config(replay):
    bad = load_json(CONFIG_PATH)
    bad["attacking_zones"] = ["moon"]
    with pytest.raises(ValueError, match="unknown zone"):
        Replay(replay.match, bad)


# --- Streamlit UI smoke tests (AppTest, no browser) --------------------------

APP = str(ROOT / "streamlit_app.py")


def button(at, label):
    return next(b for b in at.button if b.label == label)


@pytest.fixture
def app():
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    assert not at.exception
    return at


def test_ui_renders_initial_state(app):
    assert app.title[0].value == "ShiftLens"
    assert any("0 – 0" in m.value for m in app.markdown)
    assert app.session_state["replay_state"].clock == 0
    assert [r.value for r in app.radio] == ["Fan"]


def test_ui_seek_play_pause_reset(app):
    app.select_slider[0].set_value(1320).run()
    assert app.session_state["replay_state"].clock == 1320
    assert any("2 – 1" in m.value for m in app.markdown)

    app.select_slider[0].set_value(300).run()
    button(app, "Play").click().run()
    assert app.session_state["replay_state"].playing
    button(app, "Pause").click().run()
    assert not app.session_state["replay_state"].playing

    button(app, "Reset").click().run()
    state = app.session_state["replay_state"]
    assert (state.clock, state.playing) == (0, False)
    assert app.select_slider[0].value == 0
    assert not app.exception
