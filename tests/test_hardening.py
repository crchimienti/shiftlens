"""MVP hardening: claim attribution, explanation cache, data limits, demo moments."""
import copy

import pytest
from streamlit.testing.v1 import AppTest

from matchpulse.explain import (
    EXPLANATION_VERSION,
    STANDARD_LIMITS,
    ExplanationCache,
    build_request,
    cached_explain,
    data_limits,
    explain,
    fallback,
    validate_explanation,
)
from matchpulse.metrics import event_time
from matchpulse.replay import DEMO_MOMENTS, Replay, ReplayState
from matchpulse.validator import CONFIG_PATH, ROOT, load_json, load_match

AT = 2400  # 40:00 - score 1-1, pass share NBR 45.83 / HBC 54.17, danger NBR 0.86 / HBC 4.31


@pytest.fixture(scope="module")
def replay():
    match, _ = load_match()
    return Replay(match, load_json(CONFIG_PATH))


@pytest.fixture
def analyst(replay):
    r = build_request(replay.match, replay.snapshot(AT), "analyst")
    return r, fallback(r)


def with_point(out, text, metric_refs, event_refs=()):
    out = copy.deepcopy(out)
    out["key_points"][0] = {"text": text, "metric_refs": list(metric_refs), "event_refs": list(event_refs)}
    return out


def test_snapshot_values_assumed_by_these_tests(analyst):
    m = analyst[0]["metrics"]
    assert m["danger_score"]["value"] == {"NBR": 0.86, "HBC": 4.31}
    assert m["pass_share"]["value"] == {"NBR": 45.83, "HBC": 54.17}
    assert m["score"]["value"] == {"NBR": 1, "HBC": 1}


# --- claim-to-metric validation ---------------------------------------------

def test_valid_metric_backed_claim(analyst):
    r, out = analyst
    out = with_point(out, "Danger score: Northbridge FC 0.86, Harbor City 4.31.", ["danger_score"], ["E0460"])
    assert validate_explanation(out, r) == []


def test_number_from_unrelated_metric_rejected(analyst):
    r, out = analyst
    out = with_point(out, "Harbor City are pushing, danger 4.31.", ["momentum"])
    errors = validate_explanation(out, r)
    assert any("'4.31' is not attributable to ['momentum']" in e for e in errors), errors


def test_team_values_swapped_within_metric_rejected(analyst):
    r, out = analyst
    out = with_point(out, "Danger score: Northbridge FC 4.31, Harbor City 0.86.", ["danger_score", "pass_share"])
    errors = validate_explanation(out, r)
    assert any("'4.31' is written for Northbridge FC but belongs to Harbor City" in e for e in errors), errors
    assert any("'0.86' is written for Harbor City but belongs to Northbridge FC" in e for e in errors), errors


def test_team_value_swapped_across_referenced_metrics_rejected(analyst):
    r, out = analyst
    out = with_point(out, "Harbor City have 45.83% of passes and danger 0.86.", ["pass_share", "danger_score"])
    errors = validate_explanation(out, r)
    assert any("'45.83' is written for Harbor City" in e for e in errors), errors


def test_valid_score_and_minute_claim(analyst):
    r, out = analyst
    out = with_point(out, "Northbridge FC and Harbor City are level at 1–1 in minute 40.", ["score"])
    assert validate_explanation(out, r) == []


def test_valid_text_without_numbers(analyst):
    r, out = analyst
    out = with_point(out, "Harbor City are pressing high.", ["momentum"])
    out["narrative"] = "Harbor City are on top and Northbridge FC are defending deep."
    assert validate_explanation(out, r) == []


def test_invalid_metric_and_event_refs_rejected(analyst):
    r, out = analyst
    out = with_point(out, "Harbor City are pressing.", ["xg"], ["E1000", "E9999"])
    errors = validate_explanation(out, r)
    assert any("unknown metric 'xg'" in e for e in errors)
    assert any("needs at least one metric_ref that is a valid metric" in e for e in errors)
    assert any("'E1000' is not a visible event" in e for e in errors)   # future
    assert any("'E9999' is not a visible event" in e for e in errors)   # nonexistent


def test_fan_key_point_needs_metric_ref(replay):
    r = build_request(replay.match, replay.snapshot(AT), "fan")
    out = with_point(fallback(r), "Harbor City are on top.", [])
    assert any("needs at least one metric_ref" in e for e in validate_explanation(out, r))


def test_unverifiable_online_claim_retries_then_falls_back(analyst):
    r, out = analyst
    swapped = with_point(out, "Danger score: Northbridge FC 4.31, Harbor City 0.86.", ["danger_score"])
    calls = []
    gen = lambda req, prev: calls.append(prev) or swapped
    result = explain(r, gen)
    assert result["source"] == "fallback" and len(calls) == 2
    assert any("is written for" in e for e in calls[1])


# --- cache ------------------------------------------------------------------

class CountingGenerator:
    def __init__(self, replay):
        self.replay, self.calls = replay, 0

    def __call__(self, request, previous_errors=None):
        self.calls += 1
        return fallback(request)  # a valid "online" answer


def req(replay, at, mode):
    return build_request(replay.match, replay.snapshot(at), mode)


def test_cache_hit_does_not_call_generator_again(replay):
    cache, gen = ExplanationCache(), CountingGenerator(replay)
    first = cached_explain(cache, req(replay, AT, "fan"), gen)
    second = cached_explain(cache, req(replay, AT, "fan"), gen)
    assert gen.calls == 1
    assert first["cache_hit"] is False and second["cache_hit"] is True
    assert second["explanation"] == first["explanation"] and second["source"] == "llm"


def test_cache_separates_modes_and_seconds(replay):
    cache, gen = ExplanationCache(), CountingGenerator(replay)
    for at, mode in [(AT, "fan"), (AT, "analyst"), (AT + 1, "fan"), (AT, "fan")]:
        cached_explain(cache, req(replay, at, mode), gen)
    assert gen.calls == 3 and len(cache) == 3


def test_cache_clear_forces_regeneration(replay):
    cache, gen = ExplanationCache(), CountingGenerator(replay)
    cached_explain(cache, req(replay, AT, "fan"), gen)
    cache.clear()
    assert cached_explain(cache, req(replay, AT, "fan"), gen)["cache_hit"] is False
    assert gen.calls == 2


def test_cache_works_offline_and_reports_metadata(replay):
    cache = ExplanationCache()
    r = req(replay, AT, "analyst")
    result = cached_explain(cache, r, None, clock=iter([1.0, 1.25]).__next__)
    assert result["source"] == "fallback" and result["validated"] is True
    assert result["latency_ms"] == 250.0
    assert result["metric_refs"] and result["event_refs"]
    assert set(result["event_refs"]) <= set(r["allowed_event_ids"])
    assert ExplanationCache.key(r) == ("MP-DEMO-001", AT, "analyst", EXPLANATION_VERSION)
    assert cached_explain(cache, r)["cache_hit"] is True


# --- data limits ------------------------------------------------------------

def test_data_limits_cover_required_topics_without_duplicates(replay):
    limits = data_limits(fallback(req(replay, AT, "analyst")))
    text = " ".join(limits).lower()
    for word in ("synthetic", "not real possession", "not xg", "window", "no predictions", "no continuous player tracking"):
        assert word in text, word
    assert sum("synthetic" in t.lower() for t in limits) == 1
    assert sum("possession" in t.lower() for t in limits) == 1
    assert any("outcomes are ignored" in t for t in limits)          # kept from explanation
    assert any(t.startswith("Evidence level is") for t in limits)  # kept from explanation
    assert len(limits) == len(STANDARD_LIMITS) + 2


def test_data_limits_keep_low_data_warning(replay):
    limits = data_limits(fallback(req(replay, 0, "fan")))
    assert any("few events" in t for t in limits)


# --- demo moments -----------------------------------------------------------

def test_demo_moment_labels_are_honest(replay):
    labels = [label for label, _ in DEMO_MOMENTS["MP-DEMO-001"]]
    assert labels == ["Momentum swing", "Goal moment", "Late pressure"]
    # No genuine comeback: no team ever leads after having trailed.
    score, trailed = {"NBR": 0, "HBC": 0}, set()
    for ev in replay.match["events"]:
        if ev["type"] == "goal":
            score[ev["team_id"]] += 1
            for team, other in (("NBR", "HBC"), ("HBC", "NBR")):
                if score[team] < score[other]:
                    trailed.add(team)
                assert not (team in trailed and score[team] > score[other])


def test_demo_moments_point_at_what_they_claim(replay):
    moments = dict(DEMO_MOMENTS["MP-DEMO-001"])
    swing = replay.snapshot(moments["Momentum swing"])["metrics"]["inflection_point"]
    assert swing["team_id"] == "HBC" and swing["value"]["to_seconds"] <= moments["Momentum swing"]
    goal_at = moments["Goal moment"]
    goals = [e for e in replay.snapshot(goal_at)["events"] if e["type"] == "goal"]
    assert event_time(goals[-1]) == goal_at
    late = replay.snapshot(moments["Late pressure"])["metrics"]
    assert late["score"]["value"] == {"NBR": 1, "HBC": 1} and late["momentum"]["value"] > 0.5


def test_jump_to_pauses_and_is_deterministic(replay):
    state = ReplayState(duration=5400, clock=100, playing=True)
    state.jump_to(1000)
    assert (state.clock, state.playing) == (1000, False)
    assert replay.snapshot(1000) == replay.snapshot(state.clock)


# --- UI (AppTest, offline) --------------------------------------------------

def button(at, prefix):
    return next(b for b in at.button if b.label.startswith(prefix))


def test_ui_demo_moment_cache_and_reset():
    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=30)
    at.session_state["mode"] = "Fan"  # Home is the landing view; these flows start in Fan Lens
    at.run()
    button(at, "Play").click().run()
    button(at, "Momentum swing").click().run()
    state = at.session_state["replay_state"]
    assert (state.clock, state.playing) == (1000, False)
    assert "explanation" not in at.session_state

    button(at, "Explain this moment").click().run()
    assert at.session_state["explanation"]["cache_hit"] is False
    assert any("deterministic fallback · grounded ✓ validated" in c.value for c in at.caption)
    button(at, "Explain this moment").click().run()
    assert at.session_state["explanation"]["cache_hit"] is True
    assert any("cached (deterministic fallback)" in c.value for c in at.caption)

    button(at, "Goal moment").click().run()
    assert at.session_state["replay_state"].clock == 5060 and "explanation" not in at.session_state

    button(at, "Reset").click().run()
    assert len(at.session_state["explain_cache"]) == 0
    assert at.session_state["replay_state"].clock == 0
    assert not at.exception
