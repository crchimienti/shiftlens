import copy
import json

import pytest
from streamlit.testing.v1 import AppTest

from matchpulse.explain import (
    PAUSE_REQUIRED,
    build_request,
    explain,
    explain_guard,
    fallback,
    traceability_rows,
    validate_explanation,
)
from matchpulse.llm import AzureChatGenerator, online_generator_from_env
from matchpulse.replay import Replay
from matchpulse.validator import CONFIG_PATH, ROOT, load_json, load_match


@pytest.fixture(scope="module")
def replay():
    match, _ = load_match()
    return Replay(match, load_json(CONFIG_PATH))


def req(replay, at, mode):
    return build_request(replay.match, replay.snapshot(at), mode)


# --- request ----------------------------------------------------------------

def test_request_contains_only_visible_events(replay):
    r = req(replay, 300, "fan")
    assert r["clock"] == {"at_seconds": 300, "label": "05:00", "minute": 5, "period": 1}
    assert r["allowed_event_ids"][-1] == replay.snapshot(300)["events"][-1]["event_id"]
    assert len(r["recent_events"]) <= 12 and set(r["metrics"]) == set(replay.snapshot(300)["metrics"])
    json.dumps(r)


def test_request_rejects_unknown_mode(replay):
    with pytest.raises(ValueError):
        req(replay, 300, "pundit")


# --- fallback: fan ----------------------------------------------------------

def test_fan_fallback_valid_short_and_serializable(replay):
    r = req(replay, 674, "fan")
    out = fallback(r)
    assert validate_explanation(out, r) == []
    assert out["mode"] == "fan" and out["minute"] == 11 and out["source"] == "fallback"
    assert len(out["key_points"]) <= 3 and len(out["narrative"]) <= 300
    assert out["headline"] == "All square at 1–1"
    json.dumps(out)


def test_fan_fallback_at_kickoff_flags_low_data(replay):
    out = fallback(req(replay, 0, "fan"))
    assert out["headline"] == "All square at 0–0"
    assert out["data_sufficiency"] == "low"
    assert any("few events" in t for t in out["limitations"])


def test_fan_fallback_names_latest_scorer(replay):
    out = fallback(req(replay, 1290, "fan"))  # calm spell after the winner: no fresh goal or shot
    assert out["headline"] == "Northbridge FC lead 2–1"
    assert any("Adrian Novak" in p["text"] for p in out["key_points"])


def test_fan_fallback_calls_a_fresh_goal_with_the_setup(replay):
    r = req(replay, 1221, "fan")  # the winner, just scored
    out = fallback(r)
    assert out["headline"] == "⚽ GOAL! Northbridge FC lead 2–1"
    assert out["narrative"].startswith("Adrian Novak scores for Northbridge FC, set up by Samuel Adeyemi's pass!")
    assert validate_explanation(out, r) == []


def test_fan_fallback_calls_a_big_chance(replay):
    r = req(replay, 194, "fan")  # 03:14, shot saved at 03:13
    out = fallback(r)
    assert "Big chance for Northbridge FC! Adrian Novak's shot is saved." in out["narrative"]
    assert validate_explanation(out, r) == []


# --- fallback: analyst ------------------------------------------------------

def test_analyst_fallback_detail_refs_and_limits(replay):
    r = req(replay, 674, "analyst")
    out = fallback(r)
    assert validate_explanation(out, r) == []
    assert 3 <= len(out["key_points"]) <= 6
    assert all(p["metric_refs"] for p in out["key_points"])
    assert any(p["event_refs"] for p in out["key_points"])
    assert any("not possession" in t for t in out["limitations"])
    assert len(out["narrative"]) > len(fallback(req(replay, 674, "fan"))["narrative"])


@pytest.mark.parametrize("mode", ["fan", "analyst"])
def test_fallback_valid_across_whole_match(replay, mode):
    for at in range(0, 1321, 10):
        r = req(replay, at, mode)
        assert validate_explanation(fallback(r), r) == [], at


@pytest.mark.parametrize("mode", ["fan", "analyst"])
def test_fallback_deterministic(replay, mode):
    a = json.dumps(explain(req(replay, 900, mode)), sort_keys=True)
    b = json.dumps(explain(req(replay, 900, mode)), sort_keys=True)
    assert a == b


# --- validator --------------------------------------------------------------

@pytest.fixture
def valid(replay):
    r = req(replay, 674, "analyst")
    return r, fallback(r)


def errors_for(valid, mutate):
    r, out = valid
    out = copy.deepcopy(out)
    mutate(out)
    return validate_explanation(out, r)


@pytest.mark.parametrize("mutate, fragment", [
    (lambda o: o.pop("headline"), "'headline' is a required property"),
    (lambda o: o.update(extra=1), "Additional properties"),
    (lambda o: o.update(limitations=[]), "limitations"),
    (lambda o: o.update(mode="fan"), "does not match request"),
    (lambda o: o.update(minute=3), "does not match snapshot"),
    (lambda o: o.update(data_sufficiency="low"), "data_sufficiency"),
    (lambda o: o["key_points"][0]["metric_refs"].append("xg"), "unknown metric 'xg'"),
    (lambda o: o["key_points"][0]["event_refs"].append("E104"), "'E104' is not a visible event"),
    (lambda o: o["key_points"][0]["event_refs"].append("E999"), "'E999' is not a visible event"),
    (lambda o: o.update(narrative="Northbridge FC had 99 shots."), "number '99'"),
    (lambda o: o.update(headline="Goal at 15:15"), "clock '15:15'"),
    (lambda o: o.update(narrative="See E100 for details."), "event 'E100'"),
    (lambda o: o["key_points"][0].update(metric_refs=[]), "needs at least one metric_ref"),
    (lambda o: o.update(key_points=o["key_points"][:2]), "at least 3 key points"),
])
def test_validator_rejects(valid, mutate, fragment):
    errors = errors_for(valid, mutate)
    assert any(fragment in e for e in errors), errors


def test_validator_fan_rules(replay):
    r = req(replay, 674, "fan")
    out = fallback(r)
    out["key_points"] = out["key_points"] * 2
    out["narrative"] = "x" * 301
    errors = validate_explanation(out, r)
    assert any("at most 3" in e for e in errors) and any("longer than 300" in e for e in errors)


def test_validator_rejects_non_object(valid):
    assert "expected a JSON object" in validate_explanation(["nope"], valid[0])[0]


def test_validator_accepts_reformatted_snapshot_numbers(valid):
    r, out = valid
    out = copy.deepcopy(out)
    out["narrative"] = "Harbor City carried 46.1% of their events into attacking zones."
    assert validate_explanation(out, r) == []


# --- retry then fallback ----------------------------------------------------

class FakeGenerator:
    """Returns scripted outputs; records the previous_errors it was given."""

    def __init__(self, *outputs):
        self.outputs, self.calls = list(outputs), []

    def __call__(self, request, previous_errors=None):
        self.calls.append(previous_errors)
        out = self.outputs.pop(0)
        if isinstance(out, Exception):
            raise out
        return out


def test_no_generator_uses_fallback(valid):
    result = explain(valid[0])
    assert result["source"] == "fallback" and result["attempts"] == []


def test_valid_online_output_accepted_first_time(valid):
    r, good = valid
    gen = FakeGenerator(json.dumps({**good, "source": "fallback"}))  # model cannot claim to be fallback
    result = explain(r, gen)
    assert result["source"] == "llm" and result["explanation"]["source"] == "llm"
    assert len(gen.calls) == 1 and gen.calls[0] is None


def test_invalid_then_valid_retries_once_with_errors(valid):
    r, good = valid
    bad = {**good, "narrative": "They had 99 shots."}
    gen = FakeGenerator(bad, good)
    result = explain(r, gen)
    assert result["source"] == "llm"
    assert [a["ok"] for a in result["attempts"]] == [False, True]
    assert any("'99'" in e for e in gen.calls[1])


def test_invalid_twice_falls_back(valid):
    r, good = valid
    gen = FakeGenerator("not json", {**good, "minute": 20})
    result = explain(r, gen)
    assert result["source"] == "fallback" and result["explanation"] == fallback(r)
    assert len(gen.calls) == 2 and [a["ok"] for a in result["attempts"]] == [False, False]
    assert "invalid JSON" in result["attempts"][0]["errors"][0]


def test_generator_exceptions_fall_back(valid):
    gen = FakeGenerator(TimeoutError("network down"), ConnectionError("still down"))
    result = explain(valid[0], gen)
    assert result["source"] == "fallback" and "TimeoutError" in result["attempts"][0]["errors"][0]


# --- guard, traceability, optional online config ----------------------------

def test_explain_guard():
    assert explain_guard(playing=True) == PAUSE_REQUIRED
    assert explain_guard(playing=False) is None


def test_traceability_rows_by_mode(replay):
    metrics = replay.snapshot(674)["metrics"]
    fan, analyst = traceability_rows(metrics, "fan"), traceability_rows(metrics, "analyst")
    assert [r["metric"] for r in fan] == list(metrics)
    assert set(fan[0]) == {"metric", "value", "window", "sources"}
    assert {"formula_version", "config_version", "team_id", "source_event_ids"} <= set(analyst[0])
    mom = next(r for r in analyst if r["metric"] == "momentum")
    assert mom["source_event_ids"] == ", ".join(metrics["momentum"]["source_event_ids"])
    assert mom["window"] == "08:14–11:14"


FULL_ENV = {"MATCHPULSE_OFFLINE": "0", "AZURE_OPENAI_ENDPOINT": "https://example.invalid",
            "AZURE_OPENAI_API_KEY": "test", "AZURE_OPENAI_DEPLOYMENT": "d", "AZURE_OPENAI_API_VERSION": "v"}


@pytest.mark.parametrize("env", [{}, {**FULL_ENV, "MATCHPULSE_OFFLINE": "1"},
                                 {**FULL_ENV, "AZURE_OPENAI_API_KEY": ""}])
def test_online_generator_disabled_by_default(env):
    assert online_generator_from_env(env) is None


def test_online_generator_built_only_when_configured():
    gen = online_generator_from_env(FULL_ENV)
    assert isinstance(gen, AzureChatGenerator)
    msgs = gen.messages({"mode": "fan"}, ["number '99' does not come from the snapshot"])
    assert "rejected" in msgs[-1]["content"]


# --- UI flow (AppTest, offline) ---------------------------------------------

def button(at, label):
    return next(b for b in at.button if b.label == label)


def test_ui_explain_guard_then_fan_then_analyst():
    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=30)
    at.run()
    at.select_slider[0].set_value(600).run()
    button(at, "Play").click().run()
    button(at, "Explain this moment").click().run()
    assert any(PAUSE_REQUIRED in w.value for w in at.warning)
    assert "explanation" not in at.session_state

    button(at, "Pause").click().run()
    button(at, "Explain this moment").click().run()
    fan = at.session_state["explanation"]
    assert fan["mode"] == "fan" and fan["source"] == "fallback"
    assert any(fan["explanation"]["headline"] in m.value for m in at.markdown)
    assert "formula_version" not in at.dataframe[-1].value.columns

    at.radio[0].set_value("Analyst").run()
    assert "formula_version" in at.dataframe[-1].value.columns
    button(at, "Explain this moment").click().run()
    assert at.session_state["explanation"]["mode"] == "analyst"
    assert any(m.value == "**Data limits**" for m in at.markdown)

    button(at, "Reset").click().run()
    assert "explanation" not in at.session_state
    assert not at.exception
