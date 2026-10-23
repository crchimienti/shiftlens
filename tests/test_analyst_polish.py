"""Analyst polish: map boards keep their pitch, display options, spread pass-network nodes, quieter controls."""
import math

import pytest
from streamlit.testing.v1 import AppTest

from matchpulse import analytics as A
from matchpulse import threat as T
from matchpulse.pitch import FIVE_LANES, MAP_CARD, MAP_GRASS, move_events, move_points, pitch_figure
from matchpulse.replay import Replay
from matchpulse.validator import CONFIG_PATH, ROOT, load_json, load_match


@pytest.fixture(scope="module")
def replay():
    match, _ = load_match()
    return Replay(match, load_json(CONFIG_PATH))


@pytest.fixture(scope="module")
def events(replay):
    return replay.snapshot(replay.duration)["events"]


def test_activity_map_keeps_its_pitch_under_the_cells(replay, events):
    home = replay.match["home_team"]
    fig = A.zone_heatmap_figure(events, home, True, "37,99,235")
    shapes = list(fig.layout.shapes)
    cells = [s for s in shapes if str(s.fillcolor).startswith("rgba(37,99,235")]
    assert shapes[0].fillcolor == MAP_GRASS  # grass first (it used to be overwritten by the cells)
    assert len(cells) == len(A.zone_activity(events, home["id"]))  # each cell once, not merged / duplicated
    last_cell = max(i for i, s in enumerate(shapes) if s in cells)
    assert any(s.type == "line" for s in shapes[last_cell:])  # pitch lines drawn above the cells
    assert fig.layout.plot_bgcolor == MAP_CARD and fig.layout.xaxis.constrain == "domain"
    assert len([a for a in fig.layout.annotations]) == len(cells)  # count chips
    assert not A.zone_heatmap_figure(events, home, True, "37,99,235", show_counts=False).layout.annotations


def test_guides_toggle_removes_lane_and_third_lines(replay, events):
    home = replay.match["home_team"]
    dashed = lambda f: [s for s in f.layout.shapes if s.type == "line" and s.line.dash in ("dot", "dash")]
    assert dashed(A.zone_heatmap_figure(events, home, True, "0,0,255"))
    assert not dashed(A.zone_heatmap_figure(events, home, True, "0,0,255", guides=False))
    full = replay.snapshot(replay.duration)
    pts = move_points(move_events(full, "S09"), "NBR", replay.players, replay.config)
    with_grid = pitch_figure(pts, home, replay.match["away_team"], detailed=True)
    clean = pitch_figure(pts, home, replay.match["away_team"], detailed=True, guides=False)
    assert sorted(s.y0 for s in dashed(with_grid) if s.x0 == 0) == list(FIVE_LANES[1:-1])
    assert not dashed(clean) and not any(a.text == "Half-space" for a in clean.layout.annotations)


def test_player_labels_toggle_adds_names_to_step_numbers(replay):
    full = replay.snapshot(replay.duration)
    home, away = replay.match["home_team"], replay.match["away_team"]
    pts = move_points(move_events(full, "S09"), "NBR", replay.players, replay.config)
    named = next(t for t in pitch_figure(pts, home, away, detailed=True, names=True).data if t.name == home["name"])
    plain = next(t for t in pitch_figure(pts, home, away, detailed=True).data if t.name == home["name"])
    assert plain.text[0] == "1" and named.text[0].startswith("1 ") and len(named.text[0]) > 2


def test_spread_positions_are_stable_separated_and_keep_the_mean(events):
    rows = A.average_action_positions(events, "NBR", True)
    a, b = A.spread_positions(rows), A.spread_positions(rows)
    assert a == b  # deterministic (hash of the player id, not random)
    for r, s in zip(rows, a):
        assert (s["mean_x"], s["mean_y"]) == (r["x"], r["y"]) and 2 <= s["x"] <= 98 and 2 <= s["y"] <= 98
        assert math.hypot(s["x"] - r["x"], s["y"] - r["y"]) < 12  # a nudge, not a new position
    gaps = [math.hypot(p["x"] - q["x"], (p["y"] - q["y"]) * 0.68) for i, p in enumerate(a) for q in a[i + 1:]]
    raw = [math.hypot(p["x"] - q["x"], (p["y"] - q["y"]) * 0.68) for i, p in enumerate(rows) for q in rows[i + 1:]]
    assert min(gaps) > min(raw) and min(gaps) >= 6.5


def test_pass_network_curves_links_and_limits_names(replay, events):
    home = replay.match["home_team"]
    links = A.pass_links(events, "NBR")
    slots = A.spread_positions(A.average_action_positions(events, "NBR", True))
    fig = A.pass_network_figure(links, slots, home, "#00f", replay.players, threat=T.link_threat(events, "NBR"),
                                label_top=3, name_top=6)
    assert all(len(t.x) > 2 for t in fig.data[:-1])  # curves, not straight two-point lines
    assert sum(1 for t in fig.data[-1].text if t) == 6 and len(fig.layout.annotations) == 3
    bare = A.pass_network_figure(links, slots, home, "#00f", replay.players, label_top=0, name_top=0)
    assert not any(bare.data[-1].text) and not bare.layout.annotations
    assert all("links" in h for h in bare.data[-1].hovertext)  # everyone still named on hover


def test_display_popover_and_quiet_secondary_controls():
    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=30)
    at.run()
    next(b for b in at.button if b.label.startswith("Goal moment")).click().run()
    at.radio(key="mode").set_value("Analyst").run()
    assert at.segmented_control(key="featured_move").label == "Key moves · highest impact"
    assert at.selectbox(key="any_move").label.startswith("Any move")
    for key in ("disp_labels", "disp_counts", "disp_guides"):
        assert at.toggle(key=key).value is True
        at.toggle(key=key).set_value(False).run()
        assert not at.exception
    at.radio(key="mode").set_value("Fan").run()  # Fan Lens untouched
    assert at.segmented_control(key="featured_move").label == "Featured moves (highest impact)"
    assert at.selectbox(key="any_move").label.startswith("All moves so far") and not at.exception


# --- metric cards: Fan stack, Analyst visibility -------------------------------------------------

def _kpi_blocks(at):
    stack = [m.value for m in at.markdown if 'class="sl-kpi-stack"' in m.value]
    grid = [m.value for m in at.markdown if 'class="sl-kpi-grid"' in m.value]
    return stack, grid


def test_fan_metrics_are_a_vertical_stack_beside_the_key_content():
    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=30)
    at.run()
    stack, grid = _kpi_blocks(at)
    assert len(stack) == 1 and not grid and stack[0].count('class="sl-kpi"') == 5
    assert not any(p.label.startswith("Metrics") for p in at.get("popover"))  # no menu in Fan Lens


def test_analyst_metric_visibility_defaults_and_hiding():
    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=30)
    at.run()
    at.radio(key="mode").set_value("Analyst").run()
    stack, grid = _kpi_blocks(at)
    assert not stack and grid[0].count('class="sl-kpi"') == 6 and "Evidence level" not in grid[0]
    at.checkbox(key="kpi_pressure").uncheck().run()
    _, grid = _kpi_blocks(at)
    assert grid[0].count('class="sl-kpi"') == 5 and "Pressure" not in grid[0]
    at.checkbox(key="kpi_evidence").check().run()
    assert "Evidence level" in _kpi_blocks(at)[1][0]
    for key in ("pass_share", "danger", "territory", "evidence", "shot_quality", "turning"):
        at.checkbox(key=f"kpi_{key}").uncheck().run()
    assert not _kpi_blocks(at)[1] and any("All metric cards are hidden" in c.value for c in at.caption)
    assert not at.exception


def test_metric_grid_keeps_card_width_when_cards_are_hidden():
    from matchpulse import ui

    assert "repeat(auto-fill, minmax(150px, 1fr))" in ui.CSS  # empty tracks stay; cards never stretch
