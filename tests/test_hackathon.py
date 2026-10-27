"""Hackathon build: EN/ES catalog, Hypothesis Lab and Decision Journal (no look-ahead), agent orchestration with the
deterministic EvidenceGuardrail, Analyst three-column layout editor, xG evolution and the planned Capture space."""
import copy
import re
import string

import pytest
from streamlit.testing.v1 import AppTest

from matchpulse import agents as AG
from matchpulse import i18n
from matchpulse import lab as L
from matchpulse.replay import Replay
from matchpulse.validator import CONFIG_PATH, ROOT, load_json, load_match
from matchpulse.xg import xg_timeline, xg_totals


@pytest.fixture(scope="module")
def replay():
    match, _ = load_match()
    return Replay(match, load_json(CONFIG_PATH))


def app(**state):
    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=60)
    for k, v in {"mode": "Fan", **state}.items():  # Home is the landing view
        at.session_state[k] = v
    at.run()
    assert not at.exception, at.exception
    return at


def button(at, prefix):
    return next(b for b in at.button if b.label.startswith(prefix))


# --- i18n -------------------------------------------------------------------------------------------------------

def test_every_catalog_entry_has_spanish_with_the_same_placeholders():
    fields = lambda s: sorted(f for _, f, _, _ in string.Formatter().parse(s) if f)
    for key, (en, es) in i18n.CATALOG.items():
        assert es, key
        if en:
            assert fields(en) == fields(es), key


def test_unknown_keys_fail_loudly():
    with pytest.raises(KeyError):
        i18n.t("no.such.key")


def test_spanish_switch_translates_navigation_and_controls():
    at = app(lang="es")
    assert [b.label for b in at.button][:3] == ["Reproducir", "Pausa", "Reiniciar"]
    assert at.radio(key="mode").options == ["Inicio", "Lente Aficionado", "Lente Analista",
                                             "Capture · planificado"]
    assert any("Las narraciones generadas" in c.value for c in at.caption)  # says what stays English
    assert at.session_state["replay_state"].clock == 0  # switching language moves nothing


# --- Hypothesis Lab / Decision Journal ----------------------------------------------------------------------------

def test_hypothesis_verdicts_follow_the_recorded_arc(replay):
    ev = replay.match["events"]
    after_break = L.compare(ev, "HBC", "shots", (1800, 2700), (2700, 3600), "higher", 3600)
    assert after_break["verdict"] == "supported" and after_break["value_b"] > after_break["value_a"]
    assert L.compare(ev, "HBC", "shots", (1800, 2700), (2700, 3600), "lower", 3600)["verdict"] == "not_supported"
    tiny = L.compare(ev, "NBR", "shots", (100, 110), (120, 130), "higher", 3600)
    assert tiny["verdict"] == "inconclusive"  # too few events to say anything


def test_lab_never_looks_ahead(replay):
    ev = replay.match["events"]
    res = L.compare(ev, "HBC", "shots", (1800, 2700), (2700, 3600), "higher", 3599)
    assert res["verdict"] == "pending" and res["evidence_event_ids"] == []
    d = L.make_decision(1, 3000, "NBR", "drop_deeper", " protect the lead ", "shots", "lower", 10)
    assert d["rationale"] == "protect the lead" and L.review_decision(d, ev, 3599)["verdict"] == "pending"
    assert L.review_decision(d, ev, 3600)["verdict"] != "pending"
    with pytest.raises(ValueError):
        L.make_decision(2, 3000, "NBR", "sack_the_manager", "", "shots", "lower", 10)
    late = L.make_decision(3, 5060, "NBR", "drop_deeper", "", "shots", "lower", 10)  # 84:20, ten-minute review
    assert L.review_end(late, 5400) == 5400  # cut at full time, so it can still be reviewed
    assert L.review_decision(late, ev, 5400, 5400)["verdict"] != "pending"


def test_lab_evidence_ids_are_the_counted_events(replay):
    ev = replay.match["events"]
    res = L.compare(ev, "NBR", "pressures", (2700, 3600), (3600, 4500), "higher", 4500)
    counted = [e for e in ev if e["event_id"] in res["evidence_event_ids"]]
    assert all(e["type"] == "pressure" and e["team_id"] == "NBR" for e in counted)
    assert len(counted) == res["value_a"] + res["value_b"]


# --- agents and guardrail -----------------------------------------------------------------------------------------

def test_agents_orchestrate_tools_and_the_guardrail_passes_honest_output(replay):
    snap = replay.snapshot(3600)
    h = L.make_hypothesis(1, "HBC shoot more after the break", "HBC", "shots", (1800, 2700), (2700, 3600), "higher", 3600)
    out = AG.run_agents(replay, snap, "analyst", [h], [])
    assert out["ok"] and out["agent"] == "TacticalAnalystAgent" and out["source"] == "fallback"
    tools = [(s["agent"], s["tool"]) for s in out["trace"]]
    assert ("TacticalAnalystAgent", "evaluate_hypotheses") in tools
    assert ("EvidenceGuardrail", "recompute_from_event_ids") in tools
    assert tools[-1] == ("EvidenceGuardrail", "validate_explanation")
    fan = AG.run_agents(replay, snap, "fan")
    assert fan["ok"] and [s["tool"] for s in fan["trace"]][:3] == ["match_read", "story_moments", "fan_explanation"]


def test_guardrail_rejects_tampered_numbers_and_future_events(replay):
    snap = replay.snapshot(3600)
    guard = AG.EvidenceGuardrail()
    res = L.compare(replay.match["events"], "HBC", "shots", (1800, 2700), (2700, 3600), "higher", 3600)
    assert guard.check_lab_result(res, snap) == []
    inflated = {**res, "value_b": res["value_b"] + 3}
    assert any("does not match" in e for e in guard.check_lab_result(inflated, snap))
    future = {**res, "evidence_event_ids": res["evidence_event_ids"] + ["E1000"]}
    assert any("not a visible event" in e for e in guard.check_lab_result(future, snap))
    out = AG.FanStoryAgent(guard).run(replay, snap)["explanation"]
    bad = copy.deepcopy(out)
    bad["narrative"] = "Harbor City have 97.3% of the ball."
    from matchpulse.explain import build_request
    assert guard.check_explanation(bad, build_request(replay.match, snap, "fan"))


def test_a_model_draft_with_an_invented_number_never_reaches_the_user(replay):
    snap = replay.snapshot(1500)
    calls = []

    def generator(request, previous):  # stands in for the optional Azure AI Foundry path
        calls.append(previous)
        from matchpulse.explain import fallback
        draft = fallback(request)
        draft["narrative"] = "Northbridge FC have 97.3% of the ball."
        return draft

    out = AG.run_agents(replay, snap, "fan", generator=generator)
    assert len(calls) == 2 and calls[1]  # one retry with the guardrail's errors
    assert out["source"] == "fallback" and out["ok"] and "97.3" not in out["explanation"]["narrative"]
    assert AG.run_agents(replay, snap, "fan")["source"] == "fallback"  # offline default: no generator at all


# --- xG evolution -------------------------------------------------------------------------------------------------

def test_xg_timeline_is_cumulative_and_respects_the_clock(replay):
    ev = replay.match["events"]
    tl = xg_timeline(ev, ("NBR", "HBC"), 2700)
    for pts in tl.values():
        assert pts[0] == (0, 0.0) and pts[-1][0] == 2700
        assert all(b[1] >= a[1] for a, b in zip(pts, pts[1:]))
    totals = xg_totals(ev, ("NBR", "HBC"), 2700)
    assert totals["NBR"]["xg"] == tl["NBR"][-1][1]
    assert xg_totals(ev, ("NBR", "HBC"), 0) == {"NBR": {"xg": 0, "shots": 0}, "HBC": {"xg": 0, "shots": 0}}


# --- Analyst layout, lab and journal in the app ------------------------------------------------------------------

def test_analyst_three_columns_with_lab_journal_and_layout_editor():
    at = app(mode="Analyst")
    titles = " ".join(m.value for m in at.markdown)
    for title in ("Tactical Hypothesis Lab", "Decision Journal", "Agent architecture", "📝 Analyst notes"):
        assert title in titles
    assert at.session_state["layout_left"] == ["log", "notes"]
    at.multiselect(key="layout_left").set_value(["log", "notes", "lab"]).run()
    assert "lab" not in at.session_state["layout_right"]  # a panel lives in one column
    assert sum("Tactical Hypothesis Lab" in m.value for m in at.markdown) == 1


def test_lab_and_journal_record_and_review_in_the_session():
    at = app(mode="Analyst")
    button(at, "Goal moment").click().run()  # 84:20
    at.selectbox(key="lab_team").set_value("NBR")
    at.selectbox(key="lab_measure").set_value("shots")
    at.slider(key="lab_a").set_value((60, 70))
    at.slider(key="lab_b").set_value((70, 84))
    button(at, "Test hypothesis").click().run()
    assert len(at.session_state["lab_records"]["hypotheses"]) == 1
    assert any(re.search(r"(Supported|Not supported|Inconclusive)", m.value) for m in at.markdown)
    at.text_area(key="dj_rationale").input("Protect the lead")
    button(at, "Log decision at 84:20").click().run()
    d = at.session_state["lab_records"]["decisions"][0]
    assert (d["at"], d["rationale"]) == (5060, "Protect the lead")
    assert any("Review at" in m.value for m in at.markdown)  # pending: the review window is still ahead
    assert at.session_state["replay_state"].clock == 5060  # logging moves nothing


def test_agents_run_only_while_paused_and_show_the_trace():
    at = app(mode="Analyst")
    button(at, "Momentum swing").click().run()
    button(at, "Run agents for this moment").click().run()
    trace = " ".join(m.value for m in at.markdown if "sl-trace" in m.value)
    assert "TacticalAnalystAgent" in trace and "EvidenceGuardrail" in trace
    assert any("Deterministic mode" in c.value for c in at.caption)
    button(at, "Play").click().run()
    assert button(at, "Run agents for this moment").disabled


# --- Capture (planned) --------------------------------------------------------------------------------------------

def test_capture_is_a_badged_wireframe_with_no_replay_and_a_session_queue():
    at = app(mode="Capture")
    text = " ".join(m.value for m in at.markdown)
    assert "Planned · Future Architecture" in text and "Human-in-the-loop review" in text
    assert not any(b.label == "Play" for b in at.button)  # no replay controls in a planned space
    assert at.get("file_uploader")[0].proto.disabled  # upload is disabled
    for entity in ("`matches`", "`events`", "`videos`", "`reviews`"):
        assert entity in text
    at.button(key="cap_ok_P1").click().run()
    assert at.session_state["capture_queue"]["P1"] == "accepted" and at.button(key="cap_ok_P1").disabled
    at.button(key="cap_reset").click().run()
    assert at.session_state["capture_queue"]["P1"] == "pending"
