"""Final pass: synthetic analytics proxies, badges, vertical lineups, branding/theme config, Analyst workspace."""
import hashlib
import tomllib

import pytest
from streamlit.testing.v1 import AppTest

from matchpulse import analytics as A
from matchpulse.lineups import badge_text, load_lineups, team_lineup, team_lineup_figure, vertical_slots
from matchpulse.replay import Replay
from matchpulse.validator import CONFIG_PATH, ROOT, load_json, load_match


@pytest.fixture(scope="module")
def replay():
    match, _ = load_match()
    return Replay(match, load_json(CONFIG_PATH))


@pytest.fixture(scope="module")
def events(replay):
    return replay.snapshot(1320)["events"]


@pytest.fixture(scope="module")
def shot_list(events):
    return A.shots(events, "NBR")


# --- Shot Quality Index -----------------------------------------------------------

@pytest.mark.parametrize("zone, lane, setup, expected", [
    ("opp_box", "center", None, 0.45), ("opp_box", "center", "cross", 0.53), ("opp_box", "right", None, 0.34),
    ("opp_box", "center", "pass", 0.51), ("attacking_third", "center", None, 0.18),
    ("middle_third", "left", "dribble", 0.1),
])
def test_shot_quality_index_is_transparent(zone, lane, setup, expected):
    assert A.shot_quality(zone, lane, setup) == expected


def test_shot_quality_is_bounded():
    assert all(0 <= A.shot_quality(z, l, s) <= A.SQI_CAP
               for z in A.SQI_ZONE_BASE for l in ("left", "center", "right", None)
               for s in (None, *A.SQI_SETUP_BONUS))


def test_shots_cover_every_shot_and_goal(events, shot_list):
    assert len(shot_list) == sum(1 for e in events if e["type"] in ("shot", "goal")) == 16
    assert [s["outcome"] for s in shot_list].count("goal") == 3
    winner = next(s for s in shot_list if s["event_id"] == "E095")
    assert (winner["setup_player_id"], winner["setup_type"], winner["sqi"]) == ("NBR-07", "pass", 0.51)
    saved = next(s for s in shot_list if s["clock"] == "03:13")
    assert saved["keeper_id"] == "HBC-01"


def test_team_summary_and_proxies(shot_list):
    summary = A.team_shot_summary(shot_list, ("NBR", "HBC"))
    assert summary["NBR"] == {"shots": 8, "goals": 2, "sqi_total": 3.37, "sqi_avg": 0.42, "best": 0.53}
    cci = A.chance_creation(shot_list)
    assert cci["NBR-07"] == {"cci": 2.07, "chances": 4, "assists": 1}
    assert A.prevented_danger(shot_list) == {"HBC-01": {"saves": 2, "prevented": 0.98},
                                             "NBR-01": {"saves": 3, "prevented": 1.08}}


def test_proxies_are_deterministic(events):
    assert A.shots(events, "NBR") == A.shots(events, "NBR")


# --- badges --------------------------------------------------------------------

def test_player_badges_from_event_chain(events):
    b = A.player_badges(events)
    assert b["NBR-09"]["goals"] == 1 and b["NBR-10"]["goals"] == 1 and b["HBC-09"]["goals"] == 1
    assert b["NBR-11"]["assists"] == 1 and b["NBR-07"]["assists"] == 1 and b["HBC-07"]["assists"] == 1
    assert all(v["yellow"] == v["red"] == 0 for v in b.values())


def test_badges_respect_the_clock(replay):
    assert A.player_badges(replay.snapshot(400)["events"]) == {}
    assert A.player_badges(replay.snapshot(414)["events"])["NBR-09"]["goals"] == 1


def test_card_badges_when_present():
    fake = [{"type": "yellow_card", "team_id": "NBR", "player_id": "NBR-06", "sequence_id": "S1"}]
    assert A.player_badges(fake)["NBR-06"]["yellow"] == 1
    assert badge_text({"goals": 1, "assists": 1, "yellow": 1, "red": 0}) == "⚽ 🅰️ 🟨"
    assert badge_text(None) == "" and badge_text({"goals": 0, "assists": 0, "yellow": 0, "red": 0}) == ""


# --- zone activity, defensive actions, pass links ----------------------------------

def test_zone_activity_counts_every_team_action(events):
    act = A.zone_activity(events, "HBC")
    assert sum(act.values()) == sum(1 for e in events if e["team_id"] == "HBC")


def test_cell_rect_mirrors_for_the_away_team():
    assert A.cell_rect("opp_box", "left", True) == (84, 66.7, 100, 100)
    assert A.cell_rect("opp_box", "left", False) == (0, 0, 16, 33.3)


def test_defensive_actions_and_pass_links(events):
    pts = A.defensive_actions(events, "NBR")
    assert {p["type"] for p in pts} <= set(A.DEFENSIVE_TYPES)
    assert len(pts) == sum(1 for e in events if e["type"] in A.DEFENSIVE_TYPES)
    assert len({(p["x"], p["y"]) for p in pts if p["team_id"] == "NBR"}) > 1
    links = A.pass_links(events, "NBR")
    assert links[("NBR-08", "NBR-07")] == 2 and all(a.startswith("NBR") and b.startswith("NBR") for a, b in links)


def test_analyst_figures_build(replay, events, shot_list):
    home, away = replay.match["home_team"], replay.match["away_team"]
    colors = {"NBR": "#00f", "HBC": "#f80"}
    assert len(A.shot_map_figure(shot_list, home, away, colors, replay.players).data) == 2
    assert len(A.zone_heatmap_figure(events, home, True, "0,0,255").layout.shapes) > 10
    assert len(A.defensive_map_figure(A.defensive_actions(events, "NBR"), home, away, colors, replay.players).data) == 2
    from matchpulse.lineups import lineup_slots
    slots = lineup_slots(team_lineup(replay.match, home, load_lineups()), True)
    net = A.pass_network_figure(A.pass_links(events, "NBR"), slots, home, "#00f", replay.players)
    assert net.data[-1].mode == "markers+text" and len(net.data[-1].x) == 11


# --- vertical lineups --------------------------------------------------------------

def test_vertical_slots_spread_players_without_overlap(replay):
    for team in (replay.match["home_team"], replay.match["away_team"]):
        slots = vertical_slots(team_lineup(replay.match, team, load_lineups()))
        assert len(slots) == 11 and slots[0]["x"] == 50 and slots[0]["y"] == 10
        pos = [(s["x"], s["y"]) for s in slots]
        assert len(set(pos)) == 11
        same_line = {}
        for s in slots:
            same_line.setdefault(s["y"], []).append(s["x"])
        assert all(min(abs(a - b) for a in xs for b in xs if a != b) >= 20 for xs in same_line.values() if len(xs) > 1)


def test_team_lineup_figure_with_badges(replay, events):
    home = replay.match["home_team"]
    fig = team_lineup_figure(home, team_lineup(replay.match, home, load_lineups()), "#00f", replay.players,
                             A.player_badges(events), detailed=True)
    assert len(fig.data) == 3  # markers, names, badges
    assert "⚽" in "".join(fig.data[2].text) and "4-3-3" in fig.layout.annotations[0].text
    assert any("· FW" in t for t in fig.data[1].text)  # analyst labels show positions


# --- branding + themes -------------------------------------------------------------

def test_theme_config_has_light_and_dark():
    cfg = tomllib.loads((ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
    assert cfg["server"]["enableStaticServing"] is True
    for mode in ("light", "dark"):
        assert {"primaryColor", "backgroundColor", "secondaryBackgroundColor", "textColor"} <= set(cfg["theme"][mode])


@pytest.mark.parametrize("served, original", [("logo-light.svg", "4.svg"), ("logo-dark.svg", "5.svg"),
                                              ("mark.svg", "6.svg"), ("brand-sheet.svg", "7.svg")])
def test_brand_assets_are_the_official_files_unchanged(served, original):
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    assert digest(ROOT / "static" / "brand" / served) == digest(ROOT / "logos-dashboard-examples" / original)


def test_theme_tokens_and_logo_crops():
    from matchpulse import ui
    assert set(ui.THEMES["dark"]) == set(ui.THEMES["light"])
    assert {(lens, t) for lens in ("fan", "analyst") for t in ("dark", "light")} == set(ui.LENS_ACCENT)
    span = ui._crop("lockup_dark", 58)
    assert "app/static/brand/brand-sheet.svg" in span and "height:58px" in span
    for name, (file, x0, y0, w, h) in ui.BRAND_CROPS.items():
        assert (ROOT / "static" / "brand" / file).exists() and x0 + w <= 1500 and y0 + h <= 1500


# --- UI ------------------------------------------------------------------------

def test_ui_analyst_workspace_and_fan_layout():
    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=30)
    at.run()
    assert any("Fan Lens · broadcaster companion" in m.value for m in at.markdown)
    next(b for b in at.button if b.label.startswith("Goal moment")).click().run()
    at.radio[0].set_value("Analyst").run()
    assert [t.label for t in at.tabs] == ["🎯 Move on pitch", "🔥 Activity map", "🔗 Pass network", "🥅 Shot map",
                                          "🛡️ Defensive actions"]
    assert any("Chance Creation Index" in m.value for m in at.markdown)
    assert any("Shot Quality" in m.value for m in at.markdown)
    assert "formula_version" in at.dataframe[-1].value.columns
    assert not at.exception
