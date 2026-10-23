"""Zone Threat grid, threat gain, the analyst pitch upgrade and the stronger pass network (all synthetic)."""
import pytest
from streamlit.testing.v1 import AppTest

from matchpulse import analytics as A
from matchpulse import threat as T
from matchpulse.explain import build_request
from matchpulse.pitch import THREAT_LEGEND, move_events, move_points, pitch_figure, schematic_xy
from matchpulse.replay import Replay
from matchpulse.validator import CONFIG_PATH, ROOT, load_json, load_match

ZONES = ("own_box", "defensive_third", "middle_third", "attacking_third", "opp_box")


@pytest.fixture(scope="module")
def replay():
    match, _ = load_match()
    return Replay(match, load_json(CONFIG_PATH))


@pytest.fixture(scope="module")
def full(replay):
    return replay.snapshot(replay.duration)


# --- the grid ----------------------------------------------------------------------

def test_grid_rises_towards_goal_and_the_centre():
    for lane in ("left", "center", "right"):
        values = [T.ZONE_THREAT[z][lane] for z in ZONES]
        assert values == sorted(values) and len(set(values)) > 1
    for zone in ZONES:
        lanes = T.ZONE_THREAT[zone]
        assert lanes["center"] >= lanes["left"] == lanes["right"]
    assert all(0 < v < 1 for lanes in T.ZONE_THREAT.values() for v in lanes.values())
    assert T.cell_threat("opp_box", None) == T.ZONE_THREAT["opp_box"]["center"]


# --- threat gain --------------------------------------------------------------------

def test_gain_is_destination_minus_origin_within_one_team_and_move(full):
    events = full["events"]
    gains = T.threat_gains(events)
    by_id = {ev["event_id"]: ev for ev in events}
    assert gains
    for g in gains.values():
        a, b = by_id[g["event_id"]], by_id[g["to_event_id"]]
        assert a["type"] in T.THREAT_TYPES
        assert (a["team_id"], a["sequence_id"]) == (b["team_id"], b["sequence_id"])
        assert events.index(b) == events.index(a) + 1  # the very next event, never a later one
        assert g["gain"] == round(T.cell_threat(b["zone"], b["lane"]) - T.cell_threat(a["zone"], a["lane"]), 2)
    shots = [ev["event_id"] for ev in events if ev["type"] in ("shot", "goal", "save")]
    assert not set(shots) & set(gains)  # shots and saves have no destination to measure
    assert gains == T.threat_gains(events)  # deterministic


def test_goal_move_gains_threat_mostly_through_the_cross(full):
    s09 = [ev for ev in full["events"] if ev["sequence_id"] == "S09"]
    gains = T.threat_gains(full["events"])
    cross = next(ev for ev in s09 if ev["type"] == "cross")
    assert gains[cross["event_id"]]["gain"] == max(gains[ev["event_id"]]["gain"] for ev in s09 if ev["event_id"] in gains)
    mt = T.move_threat(s09)
    assert mt["net_gain"] > 0 and mt["peak"] == T.ZONE_THREAT["opp_box"]["center"]


def test_player_threat_adds_only_positive_gains(full):
    gains = T.threat_gains(full["events"]).values()
    for pid, row in T.player_threat(full["events"]).items():
        own = [g["gain"] for g in gains if g["player_id"] == pid]
        assert row["added"] == round(sum(max(g, 0) for g in own), 2) >= row["net"] == round(sum(own), 2)
        assert row["forward"] == sum(g > 0 for g in own)


def test_link_threat_matches_pass_links(full):
    assert T.LINK_TYPES == A.PASS_LIKE
    for team in ("NBR", "HBC"):
        assert set(T.link_threat(full["events"], team)) <= set(A.pass_links(full["events"], team))


def test_carries_never_create_a_link():
    ev = lambda i, kind, player, zone: {"event_id": f"E{i}", "minute": 0, "second": i, "period": 1, "team_id": "NBR",
                                        "player_id": player, "type": kind, "outcome": None, "zone": zone,
                                        "lane": "center", "sequence_id": "S1"}
    events = [ev(1, "carry", "NBR-01", "middle_third"), ev(2, "shot", "NBR-02", "opp_box")]
    assert T.threat_gains(events)["E1"]["gain"] > 0  # the carry still gains threat ...
    assert T.link_threat(events, "NBR") == {} == A.pass_links(events, "NBR")  # ... but is not a pass link


def test_threat_colours_are_grey_for_no_gain_and_warm_for_gain():
    assert T.threat_color(None) == T.threat_color(0) == T.threat_color(-0.2) == T.NO_GAIN
    assert T.threat_color(0.05) != T.threat_color(0.35) and T.threat_color(1.0) == T.threat_color(0.35)


def test_threat_stays_out_of_metrics_and_explanations(replay, full):
    assert "threat" not in " ".join(full["metrics"])
    request = build_request(replay.match, full, "analyst")
    assert "threat" not in str(request).lower()


# --- analyst pitch -----------------------------------------------------------------------

def test_analyst_pitch_colours_paths_by_threat_and_shows_a_legend(replay, full):
    home, away = replay.match["home_team"], replay.match["away_team"]
    pts = move_points(move_events(full, "S09"), "NBR", replay.players, replay.config)
    gains = T.threat_gains(full["events"])
    fig = pitch_figure(pts, home, away, detailed=True, threat=gains, underlay=T.threat_underlay(True))
    paths = [s for s in fig.layout.shapes if s.type == "path"]
    assert len(paths) == len(pts) - 1
    for a, path in zip(pts, paths):
        expected = T.threat_color(gains[a["event_id"]]["gain"]) if a["event_id"] in gains else None
        if expected:
            assert path.line.color == expected
    assert len([a for a in fig.layout.annotations if a.showarrow]) == len(pts) - 1
    assert any(a.text == THREAT_LEGEND for a in fig.layout.annotations)
    gold = [s for s in fig.layout.shapes if s.type == "rect" and str(s.fillcolor).startswith("rgba(250,204,21")]
    assert len(gold) == 15  # the 5 × 3 grid
    hovers = [c[6] for t in fig.data if t.customdata is not None for c in t.customdata]
    assert any("Threat" in h and "grid proxy" in h for h in hovers)


def test_fan_pitch_has_no_threat_layer(replay, full):
    home, away = replay.match["home_team"], replay.match["away_team"]
    pts = move_points(move_events(full, "S09"), "NBR", replay.players, replay.config)
    fig = pitch_figure(pts, home, away)
    assert not any(a.text == THREAT_LEGEND for a in fig.layout.annotations)
    assert all(p.line.color in ("#2563eb", "#ea580c") for p in fig.layout.shapes if p.type == "path")


def test_focus_dims_the_rest_and_labels_the_selected_action(replay, full):
    home, away = replay.match["home_team"], replay.match["away_team"]
    pts = move_points(move_events(full, "S09"), "NBR", replay.players, replay.config)
    fig = pitch_figure(pts, home, away, detailed=True, highlight="E040")
    team = next(t for t in fig.data if t.name == "Northbridge FC")
    opacities = dict(zip(team.customdata[:, 5] if hasattr(team.customdata, "shape") else [c[5] for c in team.customdata],
                         team.marker.opacity))
    assert opacities["E040"] == 1.0 and min(opacities.values()) < 1.0
    assert any("Goal" in str(a.text) and a.bgcolor for a in fig.layout.annotations if not a.showarrow)


# --- pass network ---------------------------------------------------------------------------

def test_average_action_positions_are_means_of_schematic_cells(full):
    events = full["events"]
    for team, right in (("NBR", True), ("HBC", False)):
        for row in A.average_action_positions(events, team, right):
            own = [ev for ev in events if ev["team_id"] == team and ev.get("player_id") == row["player_id"]]
            xs = [schematic_xy(ev["zone"], ev["lane"], right)[0] for ev in own]
            assert row["n"] == len(own) and row["x"] == round(sum(xs) / len(xs), 2)
    mirrored = A.average_action_positions(events, "HBC", True)  # the away side is drawn mirrored
    for a, b in zip(A.average_action_positions(events, "HBC", False), mirrored):
        assert a["player_id"] == b["player_id"] and a["x"] == round(100 - b["x"], 2)


def test_pass_network_colours_links_by_threat_and_labels_the_busiest(replay, full):
    events = full["events"]
    home = replay.match["home_team"]
    links = A.pass_links(events, "NBR")
    slots = A.average_action_positions(events, "NBR", True)
    fig = A.pass_network_figure(links, slots, home, "#00f", replay.players, threat=T.link_threat(events, "NBR"),
                                player_threat=T.player_threat(events), label_top=3)
    pairs = A.merged_links(links, T.link_threat(events, "NBR"))
    drawn = [k for k in pairs if k[0] in {s["player_id"] for s in slots} and k[1] in {s["player_id"] for s in slots}]
    assert len(fig.data) == len(drawn) + 1
    assert {t.line.color for t in fig.data[:-1]} <= {T.threat_color(r["gain"]) for r in pairs.values()}
    assert len(fig.layout.annotations) == 3
    assert any("threat added" in h for h in fig.data[-1].hovertext)


# --- UI -----------------------------------------------------------------------------------

def test_analyst_workspace_shows_threat_surfaces():
    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=30)
    at.run()
    next(b for b in at.button if b.label.startswith("Goal moment")).click().run()
    at.radio[0].set_value("Analyst").run()
    assert not at.exception
    assert any("Threat Added" in m.value for m in at.markdown)
    assert any("Threat gain" in c.value for c in at.caption)
    assert at.toggle(key="threat_grid").value is True
    at.toggle(key="threat_grid").set_value(False).run()
    at.segmented_control(key="net_layout").set_value("Formation slot").run()
    assert not at.exception
    assert any("never at measured positions" in c.value for c in at.caption)
