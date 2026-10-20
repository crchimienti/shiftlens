"""Submission polish: Fan match read, Analyst tactical synthesis, progression proxy, player activity, badges."""
import pytest
from streamlit.testing.v1 import AppTest

from matchpulse import analytics as A
from matchpulse.explain import build_request, fallback, validate_explanation
from matchpulse.lineups import badge_text
from matchpulse.replay import Replay
from matchpulse.story import STATE_ICONS, match_read
from matchpulse.validator import CONFIG_PATH, ROOT, load_json, load_match


@pytest.fixture(scope="module")
def replay():
    match, _ = load_match()
    return Replay(match, load_json(CONFIG_PATH))


def read(replay, t):
    return match_read(replay.snapshot(t), replay.match, replay.config)


# --- Fan Lens match read --------------------------------------------------------------

@pytest.mark.parametrize("t, state", [(0, "settling"), (414, "controlled"), (610, "shifting"), (900, "pressing"),
                                      (1320, "even")])
def test_match_read_states_follow_the_match_arc(replay, t, state):
    r = read(replay, t)
    assert r["state"] == state and r["icon"] == STATE_ICONS[state]


def test_match_read_interprets_pressure_ball_passing_and_box(replay):
    r = read(replay, 414)
    text = " ".join(r["lines"])
    assert "Northbridge FC are on the front foot" in text
    assert "seeing more of the ball (56% of passes" in text
    assert "connecting their passes better (100% completed vs 75%)" in text
    assert "getting closer to goal: 3 actions in the opponent's box to 0" in text


def test_match_read_names_possession_without_penetration(replay):
    assert read(replay, 900)["headline"] == ("Harbor City are pressing hard while Northbridge FC keep more of the "
                                             "ball: possession without penetration for Northbridge FC.")


def test_match_read_is_deterministic_and_never_looks_ahead(replay):
    assert read(replay, 700) == read(replay, 700)
    early = read(replay, 120)
    assert not any("GOAL" in line for line in early["lines"])


# --- Analyst tactical synthesis -------------------------------------------------------------

def test_analyst_explanation_reads_like_an_analyst(replay):
    r = build_request(replay.match, replay.snapshot(610), "analyst")
    out = fallback(r)
    assert out["headline"] == "10:10 · 1–1 · Harbor City carry the threat, Northbridge FC keep the ball"
    assert "The pattern suggests Northbridge FC are circulating in front of the opposition" in out["narrative"]
    assert "The latest chance was the goal for Harbor City, scored inside the box." in out["narrative"]
    assert validate_explanation(out, r) == []


@pytest.mark.parametrize("t, phrase", [(414, "Northbridge FC in control"), (1320, "an even phase")])
def test_analyst_headline_patterns(replay, t, phrase):
    assert fallback(build_request(replay.match, replay.snapshot(t), "analyst"))["headline"].endswith(phrase)


# --- progression proxy, player activity, badges ------------------------------------------

def test_ball_progression(replay):
    events = replay.snapshot(1320)["events"]
    prog = A.progressive_actions(events)
    assert prog["NBR-08"] == {"progressive": 5, "zones_gained": 5}
    assert A.team_progression(events, ("NBR", "HBC")) == {"NBR": 14, "HBC": 17}
    early = A.progressive_actions(replay.snapshot(60)["events"])
    assert sum(r["progressive"] for r in early.values()) <= sum(r["progressive"] for r in prog.values())


def test_player_activity_is_a_subset_of_team_activity(replay):
    events = replay.snapshot(1320)["events"]
    team = A.zone_activity(events, "NBR")
    player = A.zone_activity(events, "NBR", "NBR-07")
    assert sum(player.values()) == sum(1 for e in events if e.get("player_id") == "NBR-07")
    assert all(player[k] <= team[k] for k in player)


def test_badges_are_compact_for_repeat_events():
    assert badge_text({"goals": 2, "assists": 1, "yellow": 0, "red": 0}) == "⚽×2 🅰️"
    assert badge_text({"goals": 3, "assists": 0, "yellow": 1, "red": 1}) == "⚽×3 🟨 🟥"


# --- UI -----------------------------------------------------------------------------------

def test_ui_value_chain_match_read_and_player_heat_map():
    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=30)
    at.run()
    banner = next(m.value for m in at.markdown if 'class="sl-chain"' in m.value)
    for step in ("Ingest", "Interpret", "Explain", "Render", "Personalize"):
        assert step in banner
    next(b for b in at.button if b.label.startswith("Momentum swing")).click().run()
    assert any('class="sl-read"' in m.value and "shifting" in m.value for m in at.markdown)
    at.radio[0].set_value("Analyst").run()
    at.selectbox(key="heat_player").set_value("NBR-07").run()
    assert any("Samuel Adeyemi" in m.value and "actions so far" in m.value for m in at.markdown)
    assert any("Ball Progression" in m.value for m in at.markdown)
    assert not at.exception


# --- last polish: state arc, coaching takeaway, clearer analyst charts -------------------

from matchpulse.story import state_arc  # noqa: E402


def test_state_arc_merges_phases_and_follows_the_story(replay):
    reads = [(t, read(replay, t)) for t in range(0, 1321, 60)]
    arc = state_arc(reads)
    assert all((a["state"], a["team"]) != (b["state"], b["team"]) for a, b in zip(arc, arc[1:]))
    assert arc[0]["state"] == "settling" and arc[0]["from_seconds"] == 0
    assert ("pressing", "HBC") in [(a["state"], a["team"]) for a in arc]
    assert state_arc(reads) == arc


def test_analyst_explanation_ends_with_a_coaching_takeaway(replay):
    out = fallback(build_request(replay.match, replay.snapshot(610), "analyst"))
    assert out["narrative"].endswith("Coaching takeaway: Northbridge FC need more penetration from their possession; "
                                     "Harbor City can keep looking to break quickly after regains.")


def test_pass_network_merges_directions_and_labels_players(replay):
    from matchpulse.lineups import lineup_slots, load_lineups, team_lineup
    events = replay.snapshot(1320)["events"]
    home = replay.match["home_team"]
    links = A.pass_links(events, "NBR")
    slots = lineup_slots(team_lineup(replay.match, home, load_lineups()), True)
    fig = A.pass_network_figure(links, slots, home, "#00f", replay.players)
    undirected = {tuple(sorted(k)) for k in links}
    assert len(fig.data) == len(undirected) + 1  # one line per pair + the player layer
    assert "Moreau" in fig.data[-1].text and max(fig.data[-1].marker.size) <= 18


def test_shot_map_marks_goals_gold_and_scales_with_quality(replay):
    events = replay.snapshot(1320)["events"]
    shot_list = A.shots(events, "NBR")
    home, away = replay.match["home_team"], replay.match["away_team"]
    fig = A.shot_map_figure(shot_list, home, away, {"NBR": "#00f", "HBC": "#f80"}, replay.players)
    nbr = fig.data[0]
    goals = [i for i, s in enumerate([s for s in shot_list if s["team_id"] == "NBR"]) if s["outcome"] == "goal"]
    assert all(nbr.marker.color[i] == "#facc15" for i in goals) and max(nbr.marker.size) <= 9 + 16 * 0.95 + 6
    assert "set up by" in " ".join(nbr.hovertext)
