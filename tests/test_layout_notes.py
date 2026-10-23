"""UX redesign: compact Fan Lens, Analyst workspace + right rail, selected-action card, timestamped notes."""
import json

import pytest
from streamlit.testing.v1 import AppTest

from matchpulse import notes as N
from matchpulse.explain import build_request
from matchpulse.replay import Replay
from matchpulse.validator import CONFIG_PATH, ROOT, load_json, load_match


@pytest.fixture(scope="module")
def replay():
    match, _ = load_match()
    return Replay(match, load_json(CONFIG_PATH))


def app():
    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=30)
    at.run()
    return at


def button(at, prefix):
    return next(b for b in at.button if b.label.startswith(prefix))


# --- notes module -----------------------------------------------------------------

def test_notes_keep_exact_time_order_and_round_trip(replay):
    notes = [N.make_note(1, 1221, "Late winner from the left", "analyst", "S24"),
             N.make_note(2, 610, "  Pressure flips after the equaliser  ", "analyst", None)]
    assert [n["clock"] for n in N.ordered(notes)] == ["10:10", "20:21"]
    assert notes[1]["text"] == "Pressure flips after the equaliser"
    exported = N.to_json(notes, replay.match["match_id"])
    back, errors = N.parse_import(exported, replay.match["match_id"], replay.duration, 10)
    assert not errors and [(n["seconds"], n["text"]) for n in back] == [(610, notes[1]["text"]), (1221, notes[0]["text"])]
    assert N.merge(notes, back) == notes  # exact duplicates are skipped
    assert "**Min 10:10**" in N.to_markdown(notes, "Northbridge FC vs Harbor City")


@pytest.mark.parametrize("payload, message", [
    ("not json", "Not a JSON file"),
    (json.dumps({"format": "other"}), "Not a ShiftLens notes file"),
    (json.dumps({"format": N.FORMAT, "match_id": "OTHER", "notes": []}), "another match"),
])
def test_notes_import_rejects_foreign_files(replay, payload, message):
    notes, errors = N.parse_import(payload, replay.match["match_id"], replay.duration, 1)
    assert not notes and message in errors[0]


def test_notes_import_skips_bad_rows(replay):
    payload = json.dumps({"format": N.FORMAT, "match_id": replay.match["match_id"], "notes": [
        {"seconds": 99999, "text": "out of range"}, {"seconds": 30, "text": "  "}, {"seconds": True, "text": "bool"},
        {"seconds": 60, "text": "ok", "move_id": 5}]})
    notes, errors = N.parse_import(payload, replay.match["match_id"], replay.duration, 1)
    assert [(n["seconds"], n["move_id"]) for n in notes] == [(60, None)] and len(errors) == 3


def test_notes_never_reach_the_explanation_request(replay):
    import inspect

    request = build_request(replay.match, replay.snapshot(1221), "analyst")
    assert list(inspect.signature(build_request).parameters) == ["match", "snapshot", "mode"]  # no notes input
    assert set(request) == {"request_version", "mode", "match", "clock", "metrics", "recent_events", "goals",
                            "allowed_event_ids", "players"}


# --- Fan Lens -------------------------------------------------------------------------

def test_fan_lens_groups_stats_and_pressure_and_keeps_story_on_the_right():
    at = app()
    assert [t.label for t in at.tabs] == ["⚽ Key move", "📊 Stats & pressure", "👥 Lineups"]
    button(at, "Goal moment").click().run()
    assert any("📊 Match stats" in m.value for m in at.markdown)
    assert any("📰 Match Story" in m.value for m in at.markdown)
    assert any("Auto story · deterministic fallback · validated" in c.value for c in at.caption)  # pause to read
    assert not at.exception


def test_fan_live_story_shows_the_latest_moment_while_playing():
    at = app()
    button(at, "Goal moment").click().run()
    button(at, "Play").click().run()
    assert any("Latest ·" in m.value for m in at.markdown)
    assert any("pause to hear this moment" in c.value for c in at.caption)
    assert not at.exception


# --- Analyst Lens ------------------------------------------------------------------------

def test_analyst_rail_has_log_explanation_and_notes_that_seek_the_replay():
    at = app()
    button(at, "Goal moment").click().run()
    at.radio[0].set_value("Analyst").run()
    titles = " ".join(m.value for m in at.markdown)
    for title in ("📋 Key moments log", "📋 Analyst · explanation", "📝 Analyst notes", "📊 Match stats",
                  "Tide of the game", "Proxy leaders", "👥 Lineups"):
        assert title in titles
    at.text_area(key="note_text").input("Novak arrives late at the back post")  # form: sent with the submit
    button(at, "Add note at Min 20:21").click().run()
    assert [n["clock"] for n in at.session_state["notes"]] == ["20:21"]
    assert at.session_state["note_text"] == ""  # cleared on submit
    button(at, "Momentum swing").click().run()
    assert at.session_state["replay_state"].clock == 610
    button(at, "Min 20:21").click().run()
    assert at.session_state["replay_state"].clock == 1221 and not at.session_state["replay_state"].playing
    note_id = at.session_state["notes"][0]["id"]
    at.button(key=f"note_del_{note_id}").click().run()
    assert at.session_state["notes"] == []
    assert not at.exception


def test_empty_note_is_not_added():
    at = app()
    at.radio[0].set_value("Analyst").run()
    button(at, "Add note at Min").click().run()
    assert at.session_state["notes"] == [] if "notes" in at.session_state else True
    assert any("Write something first." in c.value for c in at.caption)
