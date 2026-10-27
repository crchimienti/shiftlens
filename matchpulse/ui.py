"""Single-page Streamlit UI. Rendering only: state lives in ReplayState, numbers in metrics."""
from __future__ import annotations

from html import escape
from pathlib import Path

import streamlit as st
import streamlit.components.v2 as components_v2

from . import analytics as A
from .anim import LABEL as ANIM_LABEL
from .anim import animation_figure
from .explain import (
    ExplanationCache,
    build_request,
    cached_explain,
    data_limits,
    explain,
    explain_guard,
    traceability_rows,
)
from .foundry_client import online_generator_from_env
from .lineups import lineup_slots, load_lineups, team_lineup, team_lineup_figure
from .metrics import event_time
from .pitch import (
    AWAY_COLOR,
    HOME_COLOR,
    all_moves,
    chain_summary,
    momentum_figure,
    momentum_trend,
    move_events,
    move_points,
    move_stats,
    pitch_figure,
    pressure_bar_figure,
)
from .presentation import (
    EVIDENCE_LEVELS,
    SUMMARY_ROWS,
    friendly_trace_rows,
    friendly_value,
    match_summary,
    metric_label,
    momentum_cue,
    nice,
    window_label,
)
from .replay import DEMO_MOMENTS, Replay, clock_label
from . import i18n as I
from . import lab_ui as LUI
from . import notes as N
from .capture_ui import render_capture
from .home_ui import render_home
from .i18n import t as tr
from . import threat as T
from .story import DEFAULT_SPEED, SPEEDS, event_focus, match_read, speed_step, state_arc, story_moments
from .validator import CONFIG_PATH, load_json, load_match

PRODUCT_NAME = "ShiftLens"
PRODUCT_SUBTITLE = "Evidence-backed match intelligence for every turning point."
TICK_SECONDS = 1.0  # real seconds between automatic steps while playing; the speed sets simulated seconds per tick

MOMENTUM_HELP = ("Who is producing more of the recent attacking actions. Each action is weighted by type "
                 "and pitch zone, and older actions fade (half-life 1 min, last 3 min). "
                 "+1 = all home team, −1 = all away team, 0 = balanced.")
IMPACT_HELP = ("Impact = weighted sum of a move's actions: passes, carries, crosses, entries into the final "
               "third and box, shots and goals, each weighted by action type and pitch zone. "
               "Higher means more dangerous. It is a simple index, not xG.")
SQI_HELP = ("Shot Quality Index: a transparent 0–1 proxy from the shot's zone, lane and the action that set it up. "
            "Synthetic and explainable. Not xG and not a probability.")
THREAT_HELP = ("Zone Threat: a fixed, published 0–1 grid over the 5 zones × 3 lanes (higher near goal and "
               "centrally). Threat gain = grid value where the team's next action happens − where this action "
               "happened, for passes, crosses, set pieces, carries and dribbles in the same move. Hand-set, not "
               "learned: a grid proxy, not xT and not a probability.")
THREAT_VIEW_NOTES = {
    T.VIEW_GAINS: "Gains of this move: path colour shows how much each action raised the danger of where the ball "
                  "is (redder = bigger gain, grey = none or backwards).",
    T.VIEW_DANGER: "Danger map: how dangerous each zone is for the attacking team; brighter cell = more dangerous, "
                   "numbers = cell value. Paths keep their team colours.",
    T.VIEW_OFF: "Threat layer off.",
}
PITCH_NOTE = "Schematic: zone × lane positions, not tracking data; curves show the action type."
TACTICAL_NOTE = "Five-lane grid (wing · half-space · centre) is a reference overlay; events carry three lanes."
PLOT_CONFIG = {"displayModeBar": False}
PITCH_VIEWS = ("Static", "Animated")
LENSES = ["Home", "Fan", "Analyst", "Capture"]
# Reports the browser's prefers-reduced-motion setting (no other data leaves the page).
MOTION = components_v2.component(
    "shiftlens_motion",
    js="export default function(c){ const q = window.matchMedia('(prefers-reduced-motion: reduce)');"
       " c.setStateValue('reduce', !!q.matches); }")
SUMMARY_ICONS = {"Shots": "⚽", "On target": "🎯", "Saves": "🧤", "Corners": "🚩", "Fouls": "⚠️",
                 "Yellow cards": "🟨", "Red cards": "🟥", "Passes": "↗️", "Unsuccessful passes": "✖️",
                 "Attacking actions": "🔥"}
HOME_RGB, AWAY_RGB = "37,99,235", "234,88,12"

# The hackathon's five-stage value chain, shown in the header so the product story is visible on screen.
VALUE_CHAIN = (("Ingest", "Synthetic match events, schema-validated and fingerprinted"),
               ("Interpret", "Deterministic metrics, turning point and synthetic proxies"),
               ("Explain", "Validated explanations and a live match read; Python owns the numbers"),
               ("Render", "Pitch, pressure flow, lineups and analyst maps"),
               ("Personalize", "Fan Lens for viewers, Analyst Lens for the studio desk"))

# --- brand + theme -------------------------------------------------------------
# Logo files are the official ShiftLens assets, served unchanged from ./static/brand (Streamlit static
# serving). Lockups are shown by cropping the brand sheet with CSS background positioning: no redrawing.
BRAND_URL = "app/static/brand/"
# (file, x0, y0, width, height) in the SVG's 1500×1500 viewBox units.
BRAND_CROPS = {
    "lockup_dark": ("brand-sheet.svg", 70, 930, 760, 250),
    "lockup_light": ("brand-sheet.svg", 30, 1225, 680, 240),
    "icon_dark": ("brand-sheet.svg", 1085, 935, 225, 225),
    "icon_light": ("brand-sheet.svg", 95, 1245, 260, 135),
}

THEMES = {
    "dark": {"text": "#f1f5fb", "muted": "#b9c6d8", "home_text": "#7fb0ff", "away_text": "#ff9e5e", "label": "#a9b8cc", "card": "rgba(19,35,61,0.92)", "border": "rgba(148,163,184,0.18)",
             "bar": "linear-gradient(100deg, rgba(10,22,40,0.97) 0%, rgba(19,35,61,0.97) 100%)",
             "banner": "linear-gradient(100deg, #0a1628 0%, #0f2440 60%, #0b3b3a 100%)", "ink": "#cbd5e1",
             "row": "rgba(148,163,184,0.08)", "shadow": "0 14px 30px -16px rgba(0,0,0,0.85)"},
    "light": {"text": "#0b1a33", "muted": "#475569", "home_text": "#2563eb", "away_text": "#c2410c", "label": "#64748b", "card": "#ffffff", "border": "rgba(15,23,42,0.10)",
              "bar": "linear-gradient(100deg, rgba(255,255,255,0.98) 0%, rgba(240,246,251,0.98) 100%)",
              "banner": "linear-gradient(100deg, #f0f2f5 0%, #ffffff 60%, #e6f4ef 100%)", "ink": "#334155",
              "row": "rgba(148,163,184,0.12)", "shadow": "0 12px 26px -16px rgba(15,23,42,0.45)"},
}
LENS_ACCENT = {("fan", "dark"): "#2dd4a7", ("fan", "light"): "#0f8a6f",
               ("analyst", "dark"): "#60a5fa", ("analyst", "light"): "#1e40af"}

# Isolated styling.
# - The control bar is a keyed container (class `st-key-control_bar`); `position: sticky` goes on its layout
#   wrapper via `:has()`. Compact-on-scroll uses a CSS scroll-driven animation on a named timeline declared on
#   Streamlit's page scroller (Chromium); other browsers keep the full-size bar.
# - Colours come from THEMES / LENS_ACCENT; Streamlit's own widgets follow .streamlit/config.toml.
CSS = """
<style>
:root { --sl-accent: %(accent)s; --sl-home: %(home)s; --sl-away: %(away)s; --sl-text: %(text)s; --sl-muted: %(muted)s;
  --sl-card: %(card)s; --sl-border: %(border)s; --sl-bar: %(bar)s; --sl-banner: %(banner)s; --sl-row: %(row)s;
  --sl-shadow: %(shadow)s; }
/* scroll-padding keeps anything scrolled into view below the header + compact sticky bar */
[data-testid="stMain"] { scroll-timeline: --sl-page block; scroll-padding-top: 8.5rem; }
/* Top padding clears Streamlit's own fixed header (3.75rem), so nothing starts underneath it. */
[data-testid="stMainBlockContainer"] { padding-top: 4.2rem; padding-bottom: 1.5rem; }
[data-testid="stMainBlockContainer"] [data-testid="stVerticalBlock"] { gap: 0.6rem; }
h1 { position: absolute !important; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
.sl-crop { display: inline-block; background-repeat: no-repeat; vertical-align: middle; }
.sl-banner { display: flex; align-items: center; justify-content: space-between; gap: 1rem; padding: 0.3rem 0.9rem;
  border-radius: 0.9rem; background: var(--sl-banner); border: 1px solid var(--sl-border); box-shadow: var(--sl-shadow); }
.sl-banner .tag { color: var(--sl-muted); font-size: 0.82rem; }
.sl-banner > div:last-child { min-width: 0; } .sl-banner .sl-chip { white-space: normal; }
.sl-chip { display: inline-block; padding: 0.15rem 0.6rem; margin-left: 0.35rem; border-radius: 999px; font-size: 0.74rem;
  border: 1px solid var(--sl-border); color: var(--sl-text); background: var(--sl-row); white-space: nowrap; }
.sl-chip.lens { border-color: var(--sl-accent); color: var(--sl-accent); font-weight: 700; }
/* Sticky essentials only (score, clock, half, play state, lens; play / pause / reset). Sticky, not fixed: it keeps
   its place in the flow, so nothing starts underneath it. Its small size is structural (no animation needed); the
   scroll-driven compaction below is an optional enhancement where the browser supports it. */
[data-testid="stLayoutWrapper"]:has(> .st-key-control_bar) { position: sticky; top: 3.75rem; z-index: 990; }
.st-key-control_bar { background: var(--sl-bar); border: 1px solid var(--sl-border); border-left: 6px solid var(--sl-accent);
  border-radius: 0.8rem; padding: 0.35rem 0.8rem 0.3rem; box-shadow: var(--sl-shadow); backdrop-filter: blur(6px);
  animation: sl-compact linear both; animation-timeline: --sl-page; animation-range: 0 160px; }
@keyframes sl-compact { to { padding-top: 0.1rem; padding-bottom: 0.1rem; } }
.st-key-control_bar button { min-height: 2.25rem; }
.st-key-control_bar [data-testid="stMarkdownContainer"] { margin-bottom: 0 !important; }  /* keep the clock inside */
.st-key-clock_strip { padding: 0 0.8rem; margin-top: -0.25rem; }
.st-key-brand_row [data-testid="stWidgetLabel"] { margin-bottom: -0.25rem; }
.st-key-control_bar [data-testid="stWidgetLabel"], .st-key-control_bar .sl-clock .extra {
  max-height: 2rem; overflow: hidden;
  animation: sl-hide linear both; animation-timeline: --sl-page; animation-range: 0 180px; }
@keyframes sl-hide { to { max-height: 0; opacity: 0; margin: 0; padding: 0; } }
.st-key-control_bar .sl-score .goals { animation: sl-goals linear both; animation-timeline: --sl-page; animation-range: 0 180px; }
@keyframes sl-goals { to { font-size: 1.3rem; } }
.sl-score { display: flex; align-items: center; justify-content: center; gap: 0.7rem; }
/* Product mark: its own slot with a divider, so it never reads as one team's crest. It does not shrink on scroll. */
.sl-brandmark { display: flex; align-items: center; justify-content: center; padding-right: 0.7rem;
  border-right: 1px solid var(--sl-border); min-height: 2.6rem; }
.sl-score .team { font-weight: 700; font-size: 1.0rem; }
.sl-score .home { color: var(--sl-home); } .sl-score .away { color: var(--sl-away); }
.sl-score .goals { font-size: 1.7rem; font-weight: 800; letter-spacing: 0.05em; color: var(--sl-text); }
.sl-clock { text-align: center; font-size: 0.78rem; color: var(--sl-muted); margin-top: -0.2rem; }
.sl-kpi { border: 1px solid var(--sl-border); border-top: 3px solid var(--sl-accent); border-radius: 0.7rem;
  padding: 0.35rem 0.7rem; height: 72px; display: flex; flex-direction: column; justify-content: space-between;
  background: var(--sl-card); overflow: hidden; box-shadow: var(--sl-shadow); }
.sl-kpi .lbl { font-size: 0.72rem; color: var(--sl-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sl-kpi .lbl span { cursor: help; opacity: 0.7; }
.sl-kpi .val { font-size: 1.18rem; font-weight: 700; line-height: 1.1; color: var(--sl-text); }
.sl-kpi .val.small { font-size: 0.92rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sl-kpi .sub { font-size: 0.66rem; color: var(--sl-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
/* Metric layouts. margin-bottom cancels Streamlit's -1rem pull on HTML blocks so cards never touch what follows. */
.sl-kpi-stack { display: flex; flex-direction: column; gap: 0.45rem; margin-bottom: 1rem; }
.sl-kpi-stack .sl-kpi { height: auto; min-height: 60px; gap: 0.1rem; }
.sl-kpi-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 0.5rem;
  margin-bottom: 1rem; }  /* auto-fill keeps empty tracks, so hidden cards never stretch the rest */
.sl-kpi-grid .sl-kpi { height: 66px; }
.st-key-goal_cheer { display: none; }
.sl-panel-title { font-weight: 700; font-size: 0.95rem; color: var(--sl-text); margin-bottom: 0.2rem; }
.sl-panel-title .acc { color: var(--sl-accent); font-weight: 500; font-size: 0.8rem; }
table.sl-stats { width: 100%%; border-collapse: collapse; font-size: 0.88rem; color: var(--sl-text); }
table.sl-stats td, table.sl-stats th { border: none !important; padding: 0.12rem 0.4rem; text-align: center; }
table.sl-stats tr:nth-child(even) { background: var(--sl-row); }
table.sl-stats .lbl { color: var(--sl-muted); font-size: 0.78rem; white-space: nowrap; }
table.sl-stats .lead { font-weight: 800; color: var(--sl-accent); }
table.sl-stats th.home { color: var(--sl-home); } table.sl-stats th.away { color: var(--sl-away); }
.sl-moment { font-size: 0.85rem; line-height: 1.35; color: var(--sl-text); }
.st-key-motion_probe { position: absolute !important; height: 0 !important; overflow: hidden !important; }
.sl-home { text-align: center; padding: 0.6rem 0 0.4rem; }
.sl-home-claim { margin: 0.6rem 0 0.2rem; }
.sl-home-sub { max-width: 46rem; margin: 0 auto 0.5rem !important; color: var(--sl-muted); }
.sl-flow { display: flex; flex-wrap: wrap; align-items: stretch; gap: 0.4rem; }
.sl-flow .arrow { align-self: center; color: var(--sl-accent); font-weight: 700; }
.sl-flow-step { flex: 1 1 160px; border: 1px solid var(--sl-accent); border-radius: 10px; padding: 0.5rem 0.65rem; font-size: 0.85rem; line-height: 1.3; }
ol.sl-trace { font-size: 0.78rem; line-height: 1.3; padding-left: 1.1rem; margin: 0; overflow-wrap: anywhere; }
ol.sl-trace li { margin-bottom: 0.3rem; } ol.sl-trace code { font-size: 0.72rem; }
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p { color: var(--sl-muted) !important; }
.sl-chain { display: flex; gap: 0.25rem; align-items: center; flex-wrap: wrap; justify-content: flex-end; margin-top: 0.3rem; }
.sl-chain .step { font-size: 0.7rem; padding: 0.1rem 0.5rem; border-radius: 0.4rem; color: var(--sl-text);
  border: 1px solid var(--sl-border); background: var(--sl-row); cursor: help; }
.sl-chain .step b { color: var(--sl-accent); }
.sl-chain .arrow { color: var(--sl-muted); font-size: 0.7rem; }
.sl-read { border-left: 3px solid var(--sl-accent); padding: 0.35rem 0.6rem; margin-bottom: 0.35rem; background: var(--sl-row);
  border-radius: 0.4rem; color: var(--sl-text); font-size: 0.9rem; }
.sl-read ul { margin: 0.25rem 0 0 1rem; padding: 0; font-size: 0.84rem; }
[data-testid="stTabs"] [data-baseweb="tab-list"] { gap: 0.6rem; }
/* Analyst move controls: one dominant picker, a quieter secondary row */
.st-key-move_primary [data-testid="stWidgetLabel"] p { font-weight: 700; font-size: 0.86rem; color: var(--sl-text); }
.st-key-move_primary button { min-height: 2.4rem; font-weight: 600; }
.st-key-move_secondary [data-testid="stWidgetLabel"] p { font-size: 0.7rem; color: var(--sl-muted);
  text-transform: uppercase; letter-spacing: 0.04em; }
.st-key-move_secondary button, .st-key-move_secondary [data-baseweb="select"] { font-size: 0.8rem; min-height: 2rem; }
.st-key-move_secondary { margin-top: -0.2rem; }
/* map boards (dark pitch cards) get rounded corners like the panels around them */
[data-testid="stPlotlyChart"] .bglayer rect { rx: 8px; }
[data-testid="stTabs"] [data-baseweb="tab-panel"] { padding-top: 0.5rem; }

/* Phones: one column, story order kept, a slim two-line sticky bar, tappable controls. */
@media (max-width: 640px) {
  [data-testid="stMainBlockContainer"] { padding-left: 0.6rem; padding-right: 0.6rem; padding-top: 4rem; }
  [data-testid="stMain"] { scroll-padding-top: 11.5rem; }  /* header 3.75rem + pinned bar (~7rem) + margin */
  /* Streamlit pulls HTML blocks up by 1rem; on stacked phone rows that makes cards overlap. */
  .sl-banner { padding: 0.25rem 0.6rem; }
  .sl-banner > div:last-child { display: none; }  /* chips and value chain: the lens is named in the clock line */
  .st-key-brand_row [data-testid="stHorizontalBlock"] { flex-wrap: wrap; flex-direction: row; gap: 0.35rem; }
  .st-key-brand_row [data-testid="stColumn"] { min-width: 0 !important; width: auto !important; flex: 1 1 100%% !important; }
  .st-key-brand_row [data-testid="stWidgetLabel"] { display: none; }
  .st-key-control_bar { padding: 0.3rem 0.5rem; border-left-width: 4px; }
  .st-key-control_bar [data-testid="stHorizontalBlock"] { flex-wrap: wrap; flex-direction: row; gap: 0.35rem; }
  .st-key-control_bar [data-testid="stColumn"] { min-width: 0 !important; width: auto !important; flex: 1 1 28%% !important; }
  .st-key-control_bar [data-testid="stColumn"]:first-child { flex: 0 0 auto !important; }
  .st-key-control_bar [data-testid="stColumn"]:nth-child(2) { flex: 1 1 70%% !important; }
  .sl-brandmark { padding-right: 0.45rem; min-height: 2.2rem; }
  .st-key-control_bar button { min-height: 2.6rem; }
  .sl-score { gap: 0.45rem; } .sl-score .team { font-size: 0.9rem; } .sl-score .goals { font-size: 1.4rem; }
  .sl-clock { margin-top: 0; }
  .st-key-clock_strip { padding: 0 0.2rem; }
  .st-key-clock_strip [data-testid="stHorizontalBlock"] { flex-wrap: wrap; flex-direction: row; gap: 0.35rem; }
  .st-key-clock_strip [data-testid="stColumn"] { min-width: 0 !important; width: auto !important; flex: 1 1 30%% !important; }
  .st-key-clock_strip [data-testid="stColumn"]:first-child { flex-basis: 100%% !important; }
  .st-key-clock_strip button { min-height: 2.8rem; padding: 0.2rem 0.3rem; }
  .st-key-clock_strip button p { white-space: normal; font-size: 0.78rem; line-height: 1.15; }
  .sl-kpi-stack { display: grid; grid-template-columns: 1fr 1fr; gap: 0.4rem; }
  .sl-kpi-grid { grid-template-columns: 1fr 1fr; }
  .sl-kpi, .sl-kpi-grid .sl-kpi { height: auto; min-height: 62px; }
  .st-key-story_rail, .st-key-analyst_log { height: auto !important; max-height: none !important; overflow: visible !important; }
  button { min-height: 2.5rem; }
}
</style>
"""


def _theme() -> str:
    try:
        return "dark" if st.context.theme.type == "dark" else "light"
    except Exception:  # bare mode / older runtimes
        return "light"


def _crop(name: str, height: int) -> str:
    """HTML span showing one region of an official logo file, scaled to `height` px (no redrawing)."""
    file, x0, y0, w, h = BRAND_CROPS[name]
    s = height / h
    return (f'<span class="sl-crop" role="img" aria-label="ShiftLens logo" style="width:{w * s:.0f}px;height:{height}px;'
            f'background-image:url({BRAND_URL}{file});background-size:{1500 * s:.1f}px {1500 * s:.1f}px;'
            f'background-position:-{x0 * s:.1f}px -{y0 * s:.1f}px"></span>')


@st.cache_resource
def get_replay(dataset_path: str) -> tuple[Replay | None, list[str]]:
    match, errors = load_match(dataset_path)
    if errors:
        return None, errors
    return Replay(match, load_json(CONFIG_PATH)), []


@st.cache_resource
def get_lineups() -> dict:
    return load_lineups()


@st.cache_resource
def get_generator():
    """Optional online generator; None (offline fallback only) unless explicitly configured."""
    return online_generator_from_env()


# --- callbacks (run before the script reruns) --------------------------------

def _state():
    return st.session_state["replay_state"]


def _cache() -> ExplanationCache:
    """Per-session, server-side, in-memory explanation cache (no browser storage)."""
    return st.session_state.setdefault("explain_cache", ExplanationCache())


def _clear_explanation() -> None:
    for key in ("explanation", "explain_notice"):
        st.session_state.pop(key, None)


def _clear_focus() -> None:
    for key in ("selected_move", "selected_event"):
        st.session_state.pop(key, None)


def _mode() -> str:
    return st.session_state.get("mode", "Home").lower()


def on_play():
    st.session_state.pop("explain_notice", None)
    _state().play()


def on_pause():
    st.session_state.pop("explain_notice", None)
    _state().pause()


def on_reset():
    _clear_explanation()
    _cache().clear()
    _clear_focus()
    _state().reset()


def on_demo(seconds: int):
    _clear_explanation()
    _clear_focus()
    _state().jump_to(seconds)


def on_jump_move(sequence_id: str, seconds: int):
    """Pause the replay at the end of the selected move and keep it selected."""
    _clear_explanation()
    _state().jump_to(seconds)
    st.session_state["selected_move"] = sequence_id


def on_focus(sequence_id: str | None, event_id: str | None):
    """'Show on pitch': select the move and ring the event (no clock change; it is already played)."""
    if sequence_id:
        st.session_state["selected_move"] = sequence_id
        st.session_state["selected_event"] = event_id


def on_story_moment(sequence_id: str | None, event_id: str | None, seconds: int):
    """Story feed: jump to the moment (paused) and show it on the pitch; the live story then explains it."""
    _clear_explanation()
    _state().jump_to(seconds)
    on_focus(sequence_id, event_id)


def on_event_row():
    rows = st.session_state.get("event_table", {}).get("selection", {}).get("rows", [])
    ids = st.session_state.get("_event_row_ids", [])
    if rows and rows[0] < len(ids):
        event_id = ids[rows[0]]
        on_focus(event_focus(st.session_state["replay"].snapshot(_state().clock), event_id), event_id)


def on_breakdown_row():
    """Move breakdown: selecting a row selects that action (ring on the pitch + selected-action card)."""
    rows = st.session_state.get("breakdown_table", {}).get("selection", {}).get("rows", [])
    ids = st.session_state.get("_breakdown_ids", [])
    if rows and rows[0] < len(ids):
        st.session_state["selected_event"] = ids[rows[0]]


DISPLAY_DEFAULTS = {"disp_labels": True, "disp_counts": True, "disp_guides": True}


def _display() -> dict:
    """Analyst display options (overlay density): labels, counts, guides. Defaults on."""
    return {k[5:]: st.session_state.get(k, v) for k, v in DISPLAY_DEFAULTS.items()}


def render_display_controls() -> None:
    """One small popover instead of a settings panel; applies to the move pitch and every map."""
    with st.popover("Display", icon=":material/tune:", width="stretch"):
        st.toggle("Player labels", value=True, key="disp_labels",
                  help="Names next to the move's step numbers; the six most involved players on the pass network.")
        st.toggle("Count badges", value=True, key="disp_counts",
                  help="Counts on the busiest pass-network links and on activity-map cells.")
        st.toggle("Zone & lane guides", value=True, key="disp_guides",
                  help="Five-lane grid, third lines and their labels.")
        st.caption("Overlay density only. Positions stay schematic (zone × lane), never tracking.")


GOAL_CHEER = Path(__file__).parent / "assets" / "goal_cheer.wav"


@st.cache_resource
def goal_cheer_wav() -> bytes:
    """1.5 s crowd-cheer excerpt (Pixabay Content License), trimmed to the eruption with short fades; bundled."""
    return GOAL_CHEER.read_bytes()


def _notes() -> list[dict]:
    return st.session_state.setdefault("notes", [])


def on_add_note():
    text = (st.session_state.get("note_text") or "").strip()
    if not text:
        st.session_state["notes_notice"] = "Write something first."
        return
    seq = st.session_state.get("note_seq", 0) + 1
    st.session_state["note_seq"] = seq
    note = N.make_note(seq, _state().clock, text, _mode(), st.session_state.get("selected_move"))
    st.session_state["notes"] = N.merge(_notes(), [note])
    st.session_state["note_text"] = ""
    st.session_state.pop("notes_notice", None)


def on_note_jump(note_id: int):
    """Seek the replay to the note's exact second (paused) and reselect the move it was written on."""
    note = next((n for n in _notes() if n["id"] == note_id), None)
    if note:
        _clear_explanation()
        _state().jump_to(note["seconds"])
        if note["move_id"]:
            st.session_state["selected_move"] = note["move_id"]
            st.session_state.pop("selected_event", None)


def on_note_delete(note_id: int):
    st.session_state["notes"] = [n for n in _notes() if n["id"] != note_id]


def on_import_notes():
    upload = st.session_state.get("notes_upload")
    if upload is None:
        return
    replay = st.session_state["replay"]
    seq = st.session_state.get("note_seq", 0) + 1
    incoming, errors = N.parse_import(upload.getvalue(), replay.match["match_id"], replay.duration, seq)
    st.session_state["note_seq"] = seq + len(incoming)
    before = len(_notes())
    st.session_state["notes"] = N.merge(_notes(), incoming)
    added = len(st.session_state["notes"]) - before
    st.session_state["notes_notice"] = (f"Imported {added} note(s)." + (f" Skipped: {' '.join(errors[:3])}"
                                                                       if errors else ""))


def on_featured_move():
    if st.session_state.get("featured_move"):
        st.session_state["selected_move"] = st.session_state["featured_move"]
        st.session_state.pop("selected_event", None)


def on_any_move():
    st.session_state["selected_move"] = st.session_state["any_move"]
    st.session_state.pop("selected_event", None)


def on_explain():
    """Generate only while paused; otherwise leave a notice instead."""
    state = _state()
    notice = explain_guard(state.playing)
    if notice:
        st.session_state["explain_notice"] = notice
        return
    st.session_state.pop("explain_notice", None)
    replay = st.session_state["replay"]
    request = build_request(replay.match, replay.snapshot(state.clock), _mode())
    result = cached_explain(_cache(), request, get_generator())
    st.session_state["explanation"] = {"at": state.clock, "mode": _mode(), **result}


def on_seek():
    _state().seek(st.session_state["seek_clock"])


def _tick():
    """Timer fragment, registered only while playing. Advances the clock by the chosen speed and reruns.

    A fragment also executes inline during the full page run; that pass must not tick,
    otherwise every page run would immediately trigger another one.
    """
    if st.session_state.pop("_inline_pass", False):
        return
    _state().tick(speed_step(st.session_state.get("speed")))
    st.rerun()


# --- helpers -----------------------------------------------------------------

def _pal() -> dict:
    """Theme-aware text colours for Plotly annotations."""
    t = THEMES[st.session_state.get("_theme", "light")]
    return {"label": t["label"], "home_text": t["home_text"], "away_text": t["away_text"]}


def _teams(replay: Replay):
    return replay.match["home_team"], replay.match["away_team"]


def _names(replay: Replay) -> dict[str, str]:
    return {t["id"]: t["name"] for t in _teams(replay)}


def _colors(replay: Replay) -> dict[str, str]:
    home, away = _teams(replay)
    return {home["id"]: HOME_COLOR, away["id"]: AWAY_COLOR}


def _split(value: dict, home: str, away: str, fmt: str, suffix: str = "") -> str:
    show = lambda v: "–" if v is None else f"{format(v, fmt)}{suffix}"
    return f"{show(value[home])} – {show(value[away])}"


def _kpi(label: str, value: str, sub: str, help_text: str, small: bool = False) -> str:
    return (f'<div class="sl-kpi"><div class="lbl">{escape(label)} <span title="{escape(help_text)}">ⓘ</span></div>'
            f'<div class="val{" small" if small else ""}">{escape(value)}</div>'
            f'<div class="sub">{escape(sub)}</div></div>')


def _title(text: str, accent: str = "") -> None:
    st.markdown(f'<div class="sl-panel-title">{text}' + (f' <span class="acc">{accent}</span>' if accent else "")
                + "</div>", unsafe_allow_html=True)


def _move_label(move: dict, names: dict) -> str:
    goal = " ⚽" if move["has_goal"] else ""
    return f"{clock_label(move['start_seconds'])} · {names[move['team_id']]}{goal} · impact {move['score']:.2f}"


def _selected_move(replay: Replay, snap: dict) -> tuple[dict | None, list[dict], list[dict]]:
    """Canonical selection (`selected_move`) over all moves so far; defaults to the top key move."""
    featured = snap["metrics"]["highlighted_sequences"]["value"]
    everything = all_moves(snap, replay.match, replay.config)
    by_id = {m["sequence_id"]: m for m in everything}
    if not featured:
        _clear_focus()
        return None, featured, everything
    if st.session_state.get("selected_move") not in by_id:
        st.session_state["selected_move"] = featured[0]["sequence_id"]
        st.session_state.pop("selected_event", None)
    return by_id[st.session_state["selected_move"]], featured, everything


# --- sections ----------------------------------------------------------------

def render_banner(theme: str, analyst: bool) -> None:
    """Brand row (scrolls away): logo, lens chip, value chain, and the session settings: language, replay speed,
    lens (Fan / Analyst / Capture · planned) and goal sound."""
    lens = tr({"analyst": "chip.analyst", "capture": "chip.capture", "home": "chip.home"}.get(_mode(), "chip.fan"))
    chain = '<span class="arrow">→</span>'.join(
        f'<span class="step" title="{escape(tip)}"><b>{i}</b> {name}</span>'
        for i, (name, tip) in enumerate(VALUE_CHAIN, 1))
    with st.container(key="brand_row"):
        c_brand, c_speed, c_lens, c_lang = st.columns([3.5, 1.9, 2.3, 1.3], vertical_alignment="center")
        c_sound = c_lang  # language and goal sound share the last column (stacked)
        c_brand.markdown(
            f'<div class="sl-banner"><div>{_crop("lockup_dark" if theme == "dark" else "lockup_light", 48)}</div>'
            f'<div style="text-align:right"><div><span class="sl-chip lens">{lens}</span>'
            f'<span class="sl-chip">{tr("chip.synthetic")}</span>'
            f'</div><div class="sl-chain">{chain}</div></div></div>',
            unsafe_allow_html=True)
        if not st.session_state.get("speed"):  # default, and re-select 1x if the active option was clicked off
            st.session_state["speed"] = DEFAULT_SPEED
        I.render_switcher(c_lang)
        c_speed.segmented_control(tr("speed.label"), list(SPEEDS), key="speed", help=tr("speed.help"))
        if st.session_state.get("mode") not in LENSES:
            st.session_state["mode"] = "Home"
        c_lens.radio(tr("lens.label"), LENSES, key="mode", horizontal=True,
                     format_func=lambda m: tr(f"lens.{m}"), help=tr("lens.help"))
        c_sound.toggle(tr("sound.label"), key="goal_sound", value=False,
                       help="Play a short crowd cheer when a goal happens in the replay. Off by default; some browsers "
                            "only allow sound after you have clicked on the page.")


def render_control_bar(replay: Replay, snap: dict, state, analyst: bool, theme: str) -> None:
    """Sticky bar with the essentials (score, clock, half, play state and lens, play/pause/reset), then a
    non-sticky clock strip (match-clock slider and jump-to moments) that scrolls away with the page. Speed and lens
    are set in the brand row above, so the pinned part stays small in every browser."""
    home, away = _teams(replay)
    score = snap["metrics"]["score"]["value"]
    half = tr(f"half.{snap['period']}")
    status = tr("status.playing" if state.playing else "status.full_time" if state.clock >= state.duration
                else "status.paused")
    with st.container(key="control_bar"):
        c_logo, c_score, c_play, c_pause, c_reset = st.columns([0.75, 3.6, 1, 1, 1], vertical_alignment="center")
        c_logo.markdown(f'<div class="sl-brandmark" title="ShiftLens">'
                        f'{_crop("icon_dark" if theme == "dark" else "icon_light", 36)}</div>', unsafe_allow_html=True)
        c_score.markdown(
            f'<div class="sl-score">'
            f'<span class="team home">{escape(home["name"])}</span>'
            f'<span class="goals">{score[home["id"]]} – {score[away["id"]]}</span>'
            f'<span class="team away">{escape(away["name"])}</span></div>'
            f'<div class="sl-clock"><b>⏱ {snap["clock"]}</b> / {clock_label(replay.duration)} · {half} · {status}'
            f'<span class="extra"> · {tr("lens.Analyst" if analyst else "lens.Fan")}</span></div>', unsafe_allow_html=True)
        c_play.button(tr("ctl.play"), icon=":material/play_arrow:", on_click=on_play, width="stretch",
                      disabled=state.playing or state.clock >= state.duration)
        c_pause.button(tr("ctl.pause"), icon=":material/pause:", on_click=on_pause, disabled=not state.playing,
                       width="stretch")
        c_reset.button(tr("ctl.reset"), icon=":material/replay:", on_click=on_reset, width="stretch")
    with st.container(key="clock_strip"):  # not sticky: scrubbing and jumps live here and scroll away
        moments = DEMO_MOMENTS.get(replay.match["match_id"], ())
        c_clock, *c_moments = st.columns([3.4] + [1.25] * len(moments), vertical_alignment="center")
        st.session_state["seek_clock"] = state.clock
        c_clock.select_slider("Match clock", options=range(replay.duration + 1), key="seek_clock",
                              format_func=clock_label, on_change=on_seek, label_visibility="collapsed")
        icons = {"Momentum swing": ":material/swap_horiz:", "Goal moment": "⚽", "Late pressure": ":material/trending_up:"}
        for col, (label, seconds) in zip(c_moments, moments):
            col.button(f"{tr('moment.' + label)} ({clock_label(seconds)})", icon=icons.get(label), on_click=on_demo,
                       args=(seconds,), width="stretch", help=tr("moment.help", clock=clock_label(seconds)))


KPI_LABELS = {"pressure": "Pressure", "pass_share": "Pass share", "danger": "Danger index",
              "territory": "Territory", "evidence": "Evidence level", "shot_quality": "Shot Quality",
              "turning": "Turning point"}
# Analyst defaults: everything except evidence level, which every explanation's status line already reports.
ANALYST_KPI_DEFAULT = {"pressure", "pass_share", "danger", "territory", "shot_quality", "turning"}


def _kpi_visible(key: str) -> bool:
    return st.session_state.get(f"kpi_{key}", key in ANALYST_KPI_DEFAULT)


def _kpi_order() -> list[str]:
    """Analyst card order (session). Unknown or missing keys fall back to the default order."""
    order = [k for k in st.session_state.get("kpi_order", []) if k in KPI_LABELS]
    return order + [k for k in KPI_LABELS if k not in order]


def on_kpi_move(key: str, step: int) -> None:
    order = _kpi_order()
    i = order.index(key)
    j = i + step
    if 0 <= j < len(order):
        order[i], order[j] = order[j], order[i]
    st.session_state["kpi_order"] = order


def on_kpi_reset_order() -> None:
    st.session_state.pop("kpi_order", None)


def render_kpi_menu() -> None:
    """Analyst: one small popover to show or hide each metric card (visibility only, no reordering)."""
    shown = sum(_kpi_visible(k) for k in KPI_LABELS)
    order = _kpi_order()
    with st.popover(f"Metrics {shown}/{len(KPI_LABELS)}", icon=":material/view_column:", width="stretch"):
        st.caption("Show or hide a card; ↑ ↓ change its place in the strip.")
        for i, key in enumerate(order):
            c_box, c_up, c_down = st.columns([4, 1, 1], vertical_alignment="center")
            c_box.checkbox(KPI_LABELS[key], value=key in ANALYST_KPI_DEFAULT, key=f"kpi_{key}")
            c_up.button("↑", key=f"kpi_up_{key}", on_click=on_kpi_move, args=(key, -1), disabled=i == 0,
                        help=f"Move {KPI_LABELS[key]} left")
            c_down.button("↓", key=f"kpi_down_{key}", on_click=on_kpi_move, args=(key, 1),
                          disabled=i == len(order) - 1, help=f"Move {KPI_LABELS[key]} right")
        st.button("Reset order", key="kpi_reset_order", on_click=on_kpi_reset_order, width="stretch",
                  disabled="kpi_order" not in st.session_state)
        st.caption("Hidden cards only leave the strip; the metrics still drive the explanation and traceability.")


def render_kpis(replay: Replay, snap: dict, analyst: bool) -> None:
    """Fan: a compact vertical stack (placed beside the key content by the caller). Analyst: a fixed-width card
    grid with only the cards chosen in the Metrics menu; hiding cards never stretches the others."""
    cards = _kpi_cards(replay, snap, analyst)
    if not analyst:
        st.markdown(f'<div class="sl-kpi-stack">{"".join(cards.values())}</div>', unsafe_allow_html=True)
        return
    visible = [cards[key] for key in _kpi_order() if key in cards and _kpi_visible(key)]
    if visible:
        st.markdown(f'<div class="sl-kpi-grid">{"".join(visible)}</div>', unsafe_allow_html=True)
    else:
        st.caption("All metric cards are hidden. Use Metrics to show them again.")


def _kpi_cards(replay: Replay, snap: dict, analyst: bool) -> dict[str, str]:
    m = snap["metrics"]
    home, away = _teams(replay)
    h, a = home["id"], away["id"]
    mom = m["momentum"]["value"]
    suf = m["data_sufficiency"]
    tc = m["territorial_control"]
    cards = {
        "pressure": _kpi("🌊 Pressure", momentum_cue(mom, home["name"], away["name"]),
                         f"{mom:+.2f} · −1 {a} … +1 {h}", MOMENTUM_HELP, small=True),
        "pass_share": _kpi(f"↗️ Pass share · {h}–{a}", _split(m["pass_share"]["value"], h, a, ".0f", "%"),
                           window_label(m["pass_share"]["window"]), "Share of pass events. Not possession."),
        "danger": _kpi(f"🔥 Danger index · {h}–{a}", _split(m["danger_score"]["value"], h, a, ".1f"),
                       window_label(m["danger_score"]["window"]), "Weighted attacking actions. A simple index, not xG."),
        "territory": _kpi(f"🗺️ Territory · {h}–{a}", _split(tc["value"], h, a, ".0f", "%"),
                          f"in attacking areas, {window_label(tc['window'])}",
                          "Share of each team's actions in the attacking third or box."),
        "evidence": _kpi("📊 Evidence level", EVIDENCE_LEVELS.get(suf["value"], suf["value"]),
                         f"{suf['details']['event_count']} events, {window_label(suf['window'])}",
                         "How much data is behind the numbers. Low = treat them with caution."),
    }
    if analyst:
        inf = m["inflection_point"]
        v = inf["value"]
        sqi = A.team_shot_summary(A.shots(snap["events"], h), (h, a))
        cards["shot_quality"] = _kpi(f"🎯 Shot Quality · {h}–{a}",
                                     f"{sqi[h]['sqi_total']:.2f} – {sqi[a]['sqi_total']:.2f}",
                                     f"{sqi[h]['shots']} – {sqi[a]['shots']} shots · proxy, not xG", SQI_HELP)
        cards["turning"] = _kpi("🔄 Turning point",
                                f"{clock_label(v['to_seconds'])} → {inf['team_id']}" if v else "None yet",
                                f"change {v['delta']:+.2f}" if v else "no swing above 0.8 yet",
                                "Largest momentum swing so far (above 0.8 within 2 minutes).")
    return cards


COMPACT_ROWS = ("Shots", "On target", "Corners", "Fouls", "Passes", "Attacking actions")


def render_summary(replay: Replay, snap: dict, compact: bool = False) -> None:
    """Broadcast-style match stats: home value · stat · away value, leader highlighted.
    Compact (Fan Lens): the six rows a viewer scans first; card rows only appear once cards exist."""
    home, away = _teams(replay)
    counts = match_summary(snap["events"], (home["id"], away["id"]), replay.config["attacking_zones"])
    rows = []
    cards = any(counts[r][t["id"]] for r in ("Yellow cards", "Red cards") for t in (home, away))
    shown = COMPACT_ROWS + (("Yellow cards", "Red cards") if cards else ()) if compact else SUMMARY_ROWS
    for row in shown:
        hv, av = counts[row][home["id"]], counts[row][away["id"]]
        lead_h = ' class="lead"' if hv > av else ""
        lead_a = ' class="lead"' if av > hv else ""
        rows.append(f"<tr><td{lead_h}>{hv}</td><td class='lbl'>{SUMMARY_ICONS.get(row, '')} {row}</td>"
                    f"<td{lead_a}>{av}</td></tr>")
    _title("📊 Match stats")
    st.markdown(f'<table class="sl-stats"><tr><th class="home">{escape(home["name"])}</th><th></th>'
                f'<th class="away">{escape(away["name"])}</th></tr>{"".join(rows)}</table>', unsafe_allow_html=True)
    if not compact:
        st.caption("Event counts so far. No card events in this synthetic match.")


def render_pressure(replay: Replay, snap: dict, analyst: bool, theme: str, compact: bool = False) -> None:
    m = snap["metrics"]
    home, away = _teams(replay)
    value = m["momentum"]["value"]
    _title("🌊 Tide of the game" if analyst else "🌊 Pressure", "pressure over time · home above, away below")
    if m["momentum"]["source_event_ids"]:
        st.plotly_chart(pressure_bar_figure(value, home, away), config=PLOT_CONFIG, key="pressure_bar")
    else:
        st.caption("No attacking actions in the last 3 minutes.")
    goals = [(event_time(ev), ev["team_id"]) for ev in snap["events"] if ev["type"] == "goal"]
    inf = m["inflection_point"]
    turning = (inf["value"]["from_seconds"], inf["value"]["to_seconds"], inf["team_id"]) if inf["value"] else None
    trend = momentum_trend(replay.match, replay.config, snap["at_seconds"], step=15 if analyst else 30)
    tide = momentum_figure(trend, home, away, goals=goals, turning=turning, ink=THEMES[theme]["ink"])
    if compact:
        tide.update_layout(height=115)
    st.plotly_chart(tide, config=PLOT_CONFIG, key="pressure_trend")
    if compact:
        return
    caption = f":blue[{home['name']}] above the line, :orange[{away['name']}] below · ⚽ goals"
    if turning:
        team = home if inf["team_id"] == home["id"] else away
        caption += (f" · turning point {clock_label(turning[0])} → {clock_label(turning[1])} "
                    f"towards {team['name']} (change {inf['value']['delta']:+.2f})")
    st.caption(caption)


def render_key_moves(replay: Replay, snap: dict, analyst: bool):
    """Move pickers and the schematic pitch. Returns (move, events, points) for the side panel."""
    names = _names(replay)
    home, away = _teams(replay)
    move, featured, everything = _selected_move(replay, snap)
    if move is None:
        st.caption("No moves yet. Press Play or jump to a moment.")
        return None, [], []
    featured_ids = [m["sequence_id"] for m in featured]
    by_feat = {m["sequence_id"]: m for m in featured}
    sel = st.session_state["selected_move"]
    st.session_state["featured_move"] = sel if sel in featured_ids else None
    st.session_state["any_move"] = sel
    feat_label = lambda sid: (f"{'⚽ ' if by_feat[sid]['has_goal'] else ''}{names[by_feat[sid]['team_id']]} · "
                              f"{clock_label(by_feat[sid]['start_seconds'])}")
    by_id = {m["sequence_id"]: m for m in everything}
    if analyst:  # one dominant move picker; the any-move list and the threat view sit on a quieter row below
        with st.container(key="move_primary"):
            st.segmented_control("Key moves · highest impact", featured_ids, key="featured_move",
                                 on_change=on_featured_move, format_func=feat_label)
        with st.container(key="move_secondary"):
            c_any, c_view_col = st.columns([1.15, 1], vertical_alignment="bottom")
        c_view = [c_view_col]
    else:
        c_feat, c_any = st.columns([3, 2], vertical_alignment="bottom")
        c_feat.segmented_control("Featured moves (highest impact)", featured_ids, key="featured_move",
                                 on_change=on_featured_move, format_func=feat_label)
    c_any.selectbox(f"{'Any move' if analyst else 'All moves so far'} ({len(everything)})", list(by_id),
                    key="any_move", on_change=on_any_move, format_func=lambda sid: _move_label(by_id[sid], names))
    events = move_events(snap, move["sequence_id"])
    points = move_points(events, home["id"], replay.players, replay.config)
    gains = underlay = labels = attack = None
    view = None
    if analyst:
        if not st.session_state.get("threat_view"):  # default, and re-select if the active option was clicked off
            st.session_state["threat_view"] = T.VIEW_GAINS
        short = {T.VIEW_GAINS: "Move gains", T.VIEW_DANGER: "Danger map", T.VIEW_OFF: "Off"}
        c_view[0].segmented_control("Threat view", list(T.THREAT_VIEWS), key="threat_view", format_func=short.get,
                                    help="Move gains = Gains of this move (default). " + THREAT_HELP)
        view = st.session_state["threat_view"]
        right = move["team_id"] == home["id"]
        if view == T.VIEW_GAINS:
            gains = T.threat_gains(snap["events"])
        elif view == T.VIEW_DANGER:
            underlay, labels = T.threat_underlay(right), T.threat_cell_labels(right)
        attack = {"team": names[move["team_id"]], "target": (away if right else home)["name"], "right": right,
                  "color": HOME_COLOR if right else AWAY_COLOR}
    disp = _display()
    if st.session_state.get("pitch_view") not in PITCH_VIEWS:  # default, and re-select if clicked off
        st.session_state["pitch_view"] = "Static"
    st.segmented_control(tr("pitch.view"), PITCH_VIEWS, key="pitch_view", format_func=lambda v: tr("pitch." + v),
                         help=tr("pitch.view_help"))
    if st.session_state["pitch_view"] == "Animated":
        render_animation(replay, events)
        return move, events, points
    st.plotly_chart(pitch_figure(points, home, away, detailed=analyst, highlight=st.session_state.get("selected_event"),
                                 palette=_pal(), threat=gains, underlay=underlay, cell_labels=labels, attack=attack,
                                 guides=disp["guides"] if analyst else True, names=analyst and disp["labels"]),
                    config=PLOT_CONFIG, key="pitch")
    st.caption((THREAT_VIEW_NOTES[view] + " Zone Threat is a fixed grid, not xT. " + TACTICAL_NOTE + " "
                if analyst else "") + PITCH_NOTE)
    return move, events, points


def render_animation(replay: Replay, events: list[dict]) -> None:
    """The selected move as an animated sequence (chart-side controls only; the match clock never moves)."""
    home, away = _teams(replay)
    ids = [e["event_id"] for e in events if e.get("x") is not None]
    sel = st.session_state.get("selected_event")
    start = ids.index(sel) + 1 if sel in ids else 1
    reduce = bool(st.session_state.get("reduce_motion"))
    st.plotly_chart(animation_figure(events, replay.players, home, away, start_step=start, reduce_motion=reduce),
                    config=PLOT_CONFIG, key="pitch_anim")
    st.caption(ANIM_LABEL + (" · " + tr("pitch.reduced") if reduce else "") + " · " + tr("pitch.anim_note"))


def render_motion_probe() -> None:
    with st.container(key="motion_probe", height=1, border=False):
        res = MOTION(key="motion", on_reduce_change=lambda: None)
        st.session_state["reduce_motion"] = bool(getattr(res, "reduce", False))


def render_move_card(replay: Replay, snap: dict, move: dict, events: list[dict], analyst: bool) -> None:
    names = _names(replay)
    featured_ids = [m["sequence_id"] for m in snap["metrics"]["highlighted_sequences"]["value"]]
    stats = move_stats(events, move["team_id"], replay.config["attacking_zones"])
    with st.container(border=True):
        outcome = ":green-badge[⚽ Goal]" if move["has_goal"] else ":gray-badge[No goal]"
        rank = (f":blue-badge[#{featured_ids.index(move['sequence_id']) + 1} key move]"
                if move["sequence_id"] in featured_ids else "")
        st.markdown(f"**{names[move['team_id']]}** · {clock_label(move['start_seconds'])}–"
                    f"{clock_label(move['end_seconds'])} &nbsp; {outcome} {rank}")
        st.markdown(chain_summary(events))
        detail = (f"**Impact {move['score']:.2f}** · {stats['actions']} actions · {stats['attacking_actions']} in "
                  f"attacking areas · {stats['passes']} passes · {stats['shots']} shot{'s' if stats['shots'] != 1 else ''}"
                  f" · {stats['duration_seconds']} s")
        if analyst:
            detail += f" · {stats['players']} players"
        st.caption(detail, help=IMPACT_HELP)
        if analyst:
            own = [ev for ev in snap["events"] if ev["sequence_id"] == move["sequence_id"]
                   and ev["team_id"] == move["team_id"]]
            mt = T.move_threat(own)
            st.caption(f"**Threat gain {mt['net_gain']:+.2f}** · most dangerous cell reached {mt['peak']:.2f} · "
                       f"{mt['measured_actions']} measured actions · grid proxy, not xT", help=THREAT_HELP)
        st.button(f"Jump replay to {clock_label(move['end_seconds'])}", icon=":material/fast_forward:",
                  on_click=on_jump_move, args=(move["sequence_id"], move["end_seconds"]), width="stretch",
                  help="Pause the replay at the end of this move so you can explain that moment.")


def render_action_card(replay: Replay, snap: dict, move: dict, points: list[dict]) -> None:
    """Selected-action card (Analyst): the selected action, or by default the move's biggest threat gain, with
    where the ball went and what that did on the Zone Threat grid. Display only."""
    gains = T.threat_gains(snap["events"])
    ids = [p["event_id"] for p in points]
    measured = sorted((gains[e] for e in ids if e in gains), key=lambda g: (-g["gain"], ids.index(g["event_id"])))
    chosen = st.session_state.get("selected_event")
    picked = chosen in ids
    if not picked:
        chosen = measured[0]["event_id"] if measured else ids[-1]
    by_id = {ev["event_id"]: ev for ev in snap["events"]}
    ev, point = by_id[chosen], next(p for p in points if p["event_id"] == chosen)
    gain = gains.get(chosen)
    rank = next((i for i, g in enumerate(measured, 1) if g["event_id"] == chosen), None)
    where = lambda e: f"{nice(e['zone']).lower()} · {nice(e['lane'] or 'center').lower()}"
    with st.container(border=True):
        _title("🎯 Selected action" if picked else "🎯 Biggest threat gain in this move",
               "select a breakdown row to change it")
        st.markdown(f"**{point['time']} · {point['action']}" + (f" · {point['player']}" if point["player"] else "")
                    + f"** ({_names(replay)[ev['team_id']]})")
        if gain:
            nxt = by_id[gain["to_event_id"]]
            receiver = replay.players[nxt["player_id"]]["name"] if nxt.get("player_id") else _names(replay)[nxt["team_id"]]
            st.caption(f"From {where(ev)} → {where(nxt)} · next: {receiver} ({nice(nxt['type']).lower()})")
        st.markdown(T.describe_gain(gain, rank, len(measured)))
        st.caption("Zone Threat grid proxy, not xT. Not used by the validated explanations.", help=THREAT_HELP)


def render_move_breakdown(replay: Replay, snap: dict, move: dict, points: list[dict]) -> None:
    names = _names(replay)
    m = snap["metrics"]
    st.markdown("**Move breakdown**")
    gains = T.threat_gains(snap["events"])
    st.session_state["_breakdown_ids"] = [p["event_id"] for p in points]
    rows = [{"#": p["step"], "Time": p["time"], "Team": names[p["team_id"]], "Player": p["player"],
             "Action": p["action"], "Outcome": nice(p["outcome"]), "Weight": p["weight"],
             "Threat Δ": gains[p["event_id"]]["gain"] if p["event_id"] in gains else None, "Event ID": p["event_id"]}
            for p in points]
    st.dataframe(rows, hide_index=True, width="stretch", key="breakdown_table", on_select=on_breakdown_row,
                 selection_mode="single-row",
                 column_config={"Weight": st.column_config.NumberColumn(
                     "Weight", format="%.2f", help="Event-type weight × zone weight; the weights add up to the impact."),
                     "Threat Δ": st.column_config.NumberColumn(
                         "Threat Δ", format="%+.2f", help=THREAT_HELP + " Empty = no measured destination.")})
    ids = set(move["event_ids"])
    related = []
    if ids & set(m["score"]["source_event_ids"]):
        related.append("contains a goal counted in the score")
    if ids & set(m["inflection_point"]["source_event_ids"]):
        related.append("part of the turning-point window")
    if ids & set(m["momentum"]["source_event_ids"]):
        related.append("still counts towards current momentum")
    st.caption("Select a row to ring that action on the pitch and explain its threat gain.")
    st.caption(f"Source events: {', '.join(move['event_ids'])} · impact {move['score']:.2f} = sum of weights"
               + (f" · Related: {'; '.join(related)}" if related else ""))


def render_story_feed(replay: Replay, snap: dict, limit: int, title: str) -> None:
    """Factual key moments so far (from the events). 'Show' jumps there, paused, and shows it on the pitch."""
    moments = story_moments(snap, replay.match, replay.players)
    _title(title)
    if not moments:
        st.caption("Nothing yet: the story starts with the first chance.")
        return
    for i, mo in enumerate(moments[:limit]):
        c_txt, c_btn = st.columns([5, 1], vertical_alignment="center")
        c_txt.markdown(f'<div class="sl-moment"><b>{mo["clock"]}</b> {mo["icon"]} {escape(mo["text"])}</div>',
                       unsafe_allow_html=True)
        c_btn.button("Show", key=f"story_{i}_{mo['event_id']}", on_click=on_story_moment,
                     args=(mo["sequence_id"], mo["event_id"], mo["seconds"]),
                     help="Jump to this moment (paused) and show it on the pitch", disabled=mo["sequence_id"] is None)
    if len(moments) > limit:
        st.caption(f"+ {len(moments) - limit} earlier moments")


def render_match_read(replay: Replay, snap: dict) -> None:
    """Broadcaster-style read of the current state (story.match_read): state + who presses, keeps the ball,
    connects passes and gets near the box. Derived from metrics and recent event counts only."""
    read = match_read(snap, replay.match, replay.config)
    items = "".join(f"<li>{escape(line)}</li>" for line in read["lines"])
    st.markdown(f'<div class="sl-read"><b>{read["icon"]} {escape(read["headline"])}</b><ul>{items}</ul></div>',
                unsafe_allow_html=True)


def render_state_arc(replay: Replay, snap: dict, step: int = 60) -> None:
    """How the game has evolved: match_read sampled every `step` seconds, consecutive phases merged."""
    t = snap["at_seconds"]
    reads = [(s, match_read(replay.snapshot(s), replay.match, replay.config)) for s in range(0, t + 1, step)]
    arc = [a for a in state_arc(reads) if a["state"] != "settling"][-5:]
    if not arc:
        return
    names = _names(replay)
    words = {"controlled": "in control", "pressing": "pressing", "building": "building", "shifting": "shifting",
             "chaotic": "scrappy", "even": "even"}
    steps = [f"{a['icon']} {clock_label(a['from_seconds'])} " + (f"{names[a['team']]} " if a["team"] else "")
             + words[a["state"]] for a in arc]
    st.markdown(f'<div class="sl-moment"><b>How it has evolved:</b> {" → ".join(escape(x) for x in steps)}</div>',
                unsafe_allow_html=True)


def render_match_story(replay: Replay, snap: dict, title: str, feed_limit: int, feed_title: str) -> None:
    _title(title, "who presses, who has the ball, who connects, who threatens")
    render_match_read(replay, snap)
    render_state_arc(replay, snap)
    render_story_feed(replay, snap, limit=feed_limit, title=feed_title)


def render_lineups(replay: Replay, snap: dict, analyst: bool) -> None:
    lineups = get_lineups()
    badges = A.player_badges(snap["events"])
    forms = " · ".join(f"{t['name']} {team_lineup(replay.match, t, lineups)['formation']}" for t in _teams(replay))
    _title(f"👥 Lineups · {forms}", "⚽ goal · 🅰️ assist · 🟨 🟥 cards")
    cols = st.columns(2)
    pal = _pal()
    for col, team, color, text in zip(cols, _teams(replay), (HOME_COLOR, AWAY_COLOR), (pal["home_text"], pal["away_text"])):
        lineup = team_lineup(replay.match, team, lineups)
        col.plotly_chart(team_lineup_figure(team, lineup, color, replay.players, badges, detailed=analyst,
                                            title_color=text), config=PLOT_CONFIG, key=f"lineup_{team['id']}")
    st.caption("Synthetic lineups (config/lineups.json), not measured positions. Badges follow the event chain.")


def render_timeline(replay: Replay, snap: dict, analyst: bool) -> None:
    """Event list linked to the pitch: select a row to show its move and ring the action."""
    names = _names(replay)
    selected = st.session_state.get("selected_move")
    events = list(reversed(snap["events"]))
    st.session_state["_event_row_ids"] = [ev["event_id"] for ev in events]
    with st.expander(f"🔎 Explore match events ({len(events)}) · select a row to show it on the pitch",
                     expanded=analyst):
        rows = [{"": "●" if ev["sequence_id"] == selected else "",
                 "Time": clock_label(ev["minute"] * 60 + ev["second"]), "Team": names[ev["team_id"]],
                 "Player": replay.players[ev["player_id"]]["name"] if ev["player_id"] else "",
                 "Action": ("⚽ " if ev["type"] == "goal" else "") + nice(ev["type"]), "Outcome": nice(ev["outcome"]),
                 "Zone": nice(ev["zone"]), "Lane": nice(ev["lane"]), "Move": ev["sequence_id"]}
                for ev in events]
        st.dataframe(rows, hide_index=True, width="stretch", height=220, key="event_table",
                     on_select=on_event_row, selection_mode="single-row")
        st.caption("● = action in the selected move. The selected action is ringed in gold on the pitch.")


def _render_fan(exp: dict) -> None:
    st.markdown(f"### {exp['headline']}")
    st.write(exp["narrative"])
    st.markdown("\n".join(f"- {p['text']}" for p in exp["key_points"]))


def _render_analyst(exp: dict) -> None:
    st.markdown(f"#### {exp['headline']}")
    st.write(exp["narrative"])
    for p in exp["key_points"]:
        refs = "Evidence: " + ", ".join(metric_label(m) for m in p["metric_refs"])
        if p["event_refs"]:
            refs += f" · events {', '.join(p['event_refs'])}"
        st.markdown(f"- {p['text']}")
        st.caption(refs)


def _status_line(result: dict) -> str:
    origin = "Foundry" if result["source"] == "llm" else "deterministic fallback"
    source = f"cached ({origin})" if result["cache_hit"] else origin
    failed = sum(1 for a in result["attempts"] if not a["ok"])
    if failed:
        source += f" after {failed} rejected online attempt(s)"
    status = "grounded ✓ validated" if result["validated"] else "NOT validated"
    latency = "cache hit" if result["cache_hit"] else f"{result['latency_ms']} ms"
    return (f"Source: {source} · {status} · {len(result['metric_refs'])} metric refs · "
            f"{len(result['event_refs'])} event refs · attempts: {len(result['attempts'])} · latency: {latency}")


def _turning_context(replay: Replay, snap: dict) -> str | None:
    """A turning-point banner while the clock is inside (or just after) the swing window."""
    inf = snap["metrics"]["inflection_point"]
    if not inf["value"]:
        return None
    v, t = inf["value"], snap["at_seconds"]
    if v["from_seconds"] <= t <= v["to_seconds"] + 60:
        return (f"🔄 Turning point: the game swung towards {_names(replay)[inf['team_id']]} between "
                f"{clock_label(v['from_seconds'])} and {clock_label(v['to_seconds'])}.")
    return None


def render_explanation(replay: Replay, snap: dict, state) -> None:
    """Fan Lens: a live story that explains itself whenever the replay is paused (deterministic fallback,
    validated), with Explain for the full cached / Foundry version. Analyst Lens: Explain on demand."""
    fan = _mode() == "fan"
    _title("🎙️ Live story" if fan else "📋 Analyst · explanation")
    notice = st.session_state.get("explain_notice")
    if notice and state.playing:
        st.warning(notice)
    context = _turning_context(replay, snap)
    if fan and context:
        st.info(context)
    st.button("Explain this moment", on_click=on_explain, type="primary", icon=":material/record_voice_over:")
    result = st.session_state.get("explanation")
    if result and result["at"] == state.clock and result["mode"] == _mode():
        exp = result["explanation"]
        (_render_fan if fan else _render_analyst)(exp)
        level = EVIDENCE_LEVELS.get(exp["data_sufficiency"], exp["data_sufficiency"])
        st.caption(_status_line(result) + f" · minute {exp['minute']} · evidence level {level.lower()}")
    elif fan and not state.playing and snap["events"]:
        exp = explain(build_request(replay.match, snap, "fan"))["explanation"]  # offline, validated, not cached
        _render_fan(exp)
        st.caption("Auto story · deterministic fallback · validated ✓ · press Explain for the full version")
    elif fan and state.playing:
        latest = story_moments(snap, replay.match, replay.players)
        if latest:
            st.markdown(f'<div class="sl-moment"><b>Latest · {latest[0]["clock"]}</b> {latest[0]["icon"]} '
                        f'{escape(latest[0]["text"])}</div>', unsafe_allow_html=True)
        st.caption("The full story pauses with the replay: pause to hear this moment explained.")
        return
    else:
        st.caption("Pause, then press Explain for a referenced explanation of this second.")
        return
    limits = data_limits(exp)
    if fan:
        st.caption("Data limits: " + " · ".join(limits))
    else:
        with st.expander(f"Data limits ({len(limits)})"):
            st.markdown("**Data limits**")
            st.caption("\n".join(f"- {t}" for t in limits))


def render_notes(replay: Replay, state) -> None:
    """Analyst notes attached to the exact match clock; click a time to seek there (paused)."""
    notes = N.ordered(_notes())
    _title(tr("notes.title"), "attached to the match clock · kept for this session")
    with st.form("note_form", clear_on_submit=True, border=False):  # text and click are submitted together
        st.text_area("Note", key="note_text", height=68, max_chars=N.MAX_TEXT, label_visibility="collapsed",
                     placeholder=f"What do you see at Min {clock_label(state.clock)}?")
        st.form_submit_button(f"Add note at Min {clock_label(state.clock)}", on_click=on_add_note,
                              icon=":material/add:", width="stretch")
    notice = st.session_state.get("notes_notice")
    if notice:
        st.caption(notice)
    for n in notes:
        c_time, c_text, c_del = st.columns([1.9, 3.4, 0.7], vertical_alignment="center")
        c_time.button(f"Min {n['clock']}", key=f"note_go_{n['id']}", on_click=on_note_jump, args=(n["id"],),
                      help="Jump the replay to this second (paused)", width="stretch")
        c_text.markdown(escape(n["text"]))
        c_del.button("✕", key=f"note_del_{n['id']}", on_click=on_note_delete, args=(n["id"],), help="Delete note")
    if not notes:
        st.caption("No notes yet. Pause on a moment, write, then Add.")
    c_json, c_md = st.columns(2)
    c_json.download_button("Export .json", N.to_json(notes, replay.match["match_id"]), "shiftlens_notes.json",
                           "application/json", disabled=not notes, width="stretch", key="notes_json")
    title = " vs ".join(t["name"] for t in _teams(replay))
    c_md.download_button("Export .md", N.to_markdown(notes, title), "shiftlens_notes.md", "text/markdown",
                         disabled=not notes, width="stretch", key="notes_md")
    with st.expander("Import notes (.json export)"):
        st.file_uploader("Notes file", type=["json"], key="notes_upload", on_change=on_import_notes,
                         label_visibility="collapsed")
        st.caption("Notes stay in this browser session only; export them to keep them. They are never sent to "
                   "the explanation layer.")


def render_proxies(replay: Replay, snap: dict) -> None:
    """Analyst leaderboard of the synthetic proxies (chance creation, prevented danger)."""
    shot_list = A.shots(snap["events"], replay.match["home_team"]["id"])
    players = replay.players
    _title("🧪 Proxy leaders", "synthetic · explainable · not xG / xA")
    cci = sorted(A.chance_creation(shot_list).items(), key=lambda kv: (-kv[1]["cci"], kv[0]))[:3]
    keep = sorted(A.prevented_danger(shot_list).items(), key=lambda kv: (-kv[1]["prevented"], kv[0]))
    lines = ["**Chance Creation Index** (sum of SQI of shots set up)"]
    lines += [f"- {players[p]['name']} · {r['cci']:.2f} from {r['chances']} chance(s)"
              + (f" · {r['assists']} 🅰️" if r["assists"] else "") for p, r in cci] or ["- none yet"]
    prog = sorted(A.progressive_actions(snap["events"]).items(), key=lambda kv: (-kv[1]["progressive"], kv[0]))[:3]
    lines += ["", "**Ball Progression** (actions that move the ball into a more advanced zone)"]
    lines += [f"- {players[p]['name']} · {r['progressive']} progressive action(s)" for p, r in prog] or ["- none yet"]
    added = sorted(T.player_threat(snap["events"]).items(), key=lambda kv: (-kv[1]["added"], kv[0]))[:3]
    lines += ["", "**Threat Added** (sum of positive threat gains, Zone Threat grid · not xT)"]
    lines += [f"- {players[p]['name']} · +{r['added']:.2f} from {r['forward']} forward action(s)"
              for p, r in added if r["added"] > 0] or ["- none yet"]
    lines += ["", "**Prevented Danger** (sum of SQI of shots saved)"]
    lines += [f"- {players[p]['name']} · {r['prevented']:.2f} from {r['saves']} save(s)" for p, r in keep] or ["- none yet"]
    st.markdown("\n".join(lines))


def render_workspace(replay: Replay, snap: dict, theme: str) -> None:
    """Analyst tactical workspace: tabs inspired by pro dashboards, all schematic or proxy-based."""
    home, away = _teams(replay)
    colors = _colors(replay)
    events = snap["events"]
    disp = _display()
    tabs = st.tabs(["🎯 Move", "🗺️ Maps", "📊 Stats & tide", "🧪 Proxy leaders", "👥 Lineups"])
    maps = tabs[1].tabs(["🔥 Activity map", "🔗 Pass network", "🥅 Shot map", "🛡️ Defensive actions"])
    with tabs[0]:  # the pitch gets the full workspace width; the two cards sit side by side below it
        move, mv_events, points = render_key_moves(replay, snap, analyst=True)
        if move:
            c_move, c_action = st.columns(2, gap="medium")
            with c_move:
                render_move_card(replay, snap, move, mv_events, analyst=True)
            with c_action:
                render_action_card(replay, snap, move, points)
        if move:
            render_move_breakdown(replay, snap, move, points)
    with maps[0]:
        active = sorted({ev["player_id"] for ev in events if ev.get("player_id")},
                        key=lambda pid: (pid[:3] != home["id"], replay.players[pid]["number"]))
        options = ["Both teams"] + active
        pick = st.selectbox("Activity of", options, key="heat_player",
                            format_func=lambda o: o if o == "Both teams" else
                            f"{replay.players[o]['name']} ({o[:3]} · {replay.players[o]['position']})")
        if pick == "Both teams":
            cols = st.columns(2)
            for col, team, rgb, right in zip(cols, (home, away), (HOME_RGB, AWAY_RGB), (True, False)):
                col.markdown(f"**{team['name']}** · actions per zone × lane")
                col.plotly_chart(A.zone_heatmap_figure(events, team, right, rgb, show_counts=disp["counts"],
                                                       guides=disp["guides"]), config=PLOT_CONFIG,
                                 key=f"heat_{team['id']}")
        else:
            team = home if pick.startswith(home["id"]) else away
            right = team["id"] == home["id"]
            n = sum(A.zone_activity(events, team["id"], pick).values())
            st.markdown(f"**{replay.players[pick]['name']}** · {n} actions so far")
            st.plotly_chart(A.zone_heatmap_figure(events, team, right, HOME_RGB if right else AWAY_RGB, player_id=pick,
                                                  show_counts=disp["counts"], guides=disp["guides"]),
                            config=PLOT_CONFIG, key="heat_player_map")
        st.caption("Counts of actions per zone × lane cell so far: a schematic heat map of cells, not coordinates.")
    with maps[1]:
        lineups = get_lineups()
        layout = st.segmented_control("Players placed at", ["Average action cell", "Formation slot"],
                                      default="Average action cell", key="net_layout")
        p_threat = T.player_threat(events)
        cols = st.columns(2)
        for col, team, right in zip(cols, (home, away), (True, False)):
            links = A.pass_links(events, team["id"])
            if layout == "Formation slot":
                slots = lineup_slots(team_lineup(replay.match, team, lineups), attacks_right=right)
            else:
                slots = A.spread_positions(A.average_action_positions(events, team["id"], right))
            col.markdown(f"**{team['name']}** · {sum(links.values())} links")
            col.plotly_chart(A.pass_network_figure(links, slots, team, colors[team["id"]], replay.players,
                                                   threat=T.link_threat(events, team["id"]),
                                                   player_threat=p_threat, label_top=3 if disp["counts"] else 0,
                                                   name_top=6 if disp["labels"] else 0, guides=disp["guides"]),
                             config=PLOT_CONFIG, key=f"net_{team['id']}")
            top = sorted(A.merged_links(links, T.link_threat(events, team["id"])).items(),
                         key=lambda kv: (-kv[1]["n"], kv[0]))[:3]
            col.caption(" · ".join(f"{replay.players[a]['name'].split()[-1]}–{replay.players[b]['name'].split()[-1]} "
                                   f"{r['n']}× ({r['gain']:+.2f})" for (a, b), r in top) or "No links yet.")
        st.caption("Schematic pass network: a link = a pass, cross, corner or free kick followed by a team-mate's "
                   "next action in the same move. Line width = links; line colour = threat gain moved along the link "
                   "(Zone Threat grid, grey = none); the busiest links show their count. Players sit at the average "
                   "of their zone × lane cells, nudged apart so they don't stack (or at their formation slots), never "
                   "at measured positions. The six most involved players are named; hover for everyone.")
    with maps[2]:
        shot_list = A.shots(events, home["id"])
        summary = A.team_shot_summary(shot_list, (home["id"], away["id"]))
        c_map, c_tab = st.columns([3, 2], gap="medium")
        c_map.plotly_chart(A.shot_map_figure(shot_list, home, away, colors, replay.players, guides=disp["guides"]),
                           config=PLOT_CONFIG, key="shot_map")
        c_map.caption("Schematic shot map: zone × lane positions, marker size = Shot Quality Index, ★ goal · ● saved "
                      "· ○ off target · ✕ blocked. Not real shot coordinates and not xG.")
        with c_tab:
            st.markdown("\n".join(
                [f"| | {home['id']} | {away['id']} |", "|:--|:-:|:-:|"]
                + [f"| {label} | {summary[home['id']][k]} | {summary[away['id']][k]} |"
                   for label, k in (("Shots", "shots"), ("Goals", "goals"), ("SQI total", "sqi_total"),
                                    ("SQI per shot", "sqi_avg"), ("Best chance (SQI)", "best"))]))
            st.caption(SQI_HELP)
    with maps[3]:
        pts = A.defensive_actions(events, home["id"])
        st.plotly_chart(A.defensive_map_figure(pts, home, away, colors, replay.players, guides=disp["guides"]),
                        config=PLOT_CONFIG, key="def_map")
        counts = {t["id"]: {k: sum(1 for p in pts if p["team_id"] == t["id"] and p["type"] == k)
                            for k in A.DEFENSIVE_TYPES} for t in (home, away)}
        st.caption(" · ".join(f"{t['name']}: " + ", ".join(f"{n} {k}s" for k, n in counts[t["id"]].items() if n)
                              for t in (home, away))
                   + " · ✕ tackle · ⬡ interception · ▲ clearance · ■ save. Schematic positions (zone × lane).")
    with tabs[2]:
        c_stats, c_flow = st.columns([2, 3], gap="medium")
        with c_stats:
            render_summary(replay, snap)
        with c_flow:
            render_pressure(replay, snap, True, theme)
        st.markdown(f"**{tr('xg.title')}**")
        LUI.render_xg(replay, (home, away), colors, snap["at_seconds"], key="xg_analyst")
    with tabs[3]:
        render_proxies(replay, snap)
    with tabs[4]:
        render_lineups(replay, snap, analyst=True)


TRACE_COLUMNS = {
    "metric": st.column_config.TextColumn("Metric"),
    "value": st.column_config.TextColumn("Value", width="large"),
    "window": st.column_config.TextColumn("Time window"),
    "sources": st.column_config.NumberColumn("Evidence events", help="Number of source events behind the value"),
    "formula_version": st.column_config.TextColumn("Formula"),
    "config_version": st.column_config.TextColumn("Config"),
    "team_id": st.column_config.TextColumn("Team"),
    "source_event_ids": st.column_config.TextColumn("Source event IDs", width="medium"),
}


def _trace_table(replay: Replay, snap: dict, mode: str) -> None:
    rows = friendly_trace_rows(traceability_rows(snap["metrics"], mode), snap["metrics"], _names(replay))
    st.dataframe(rows, hide_index=True, width="stretch", column_config=TRACE_COLUMNS)


def render_traceability(replay: Replay, snap: dict) -> None:
    if _mode() == "fan":  # hidden by default for fans, one click away
        with st.expander("See the evidence behind this explanation"):
            st.caption("Where every number comes from: its time window and how many events are behind it.")
            _trace_table(replay, snap, "fan")
            st.caption("Switch to Analyst Lens for formula/config versions, team and source event IDs.")
        return
    names = _names(replay)
    with st.container(border=True):
        _title("📋 Analyst · traceability", "summary first")
        lines = [f"- **{metric_label(n)}**: {friendly_value(n, m, names)} · {window_label(m['window'])} · "
                 f"{len(m['source_event_ids'])} evidence events" for n, m in snap["metrics"].items()]
        st.markdown("\n".join(lines))
        with st.expander("Full evidence: formula and config versions, team, source event IDs"):
            _trace_table(replay, snap, "analyst")


# --- page --------------------------------------------------------------------

def render_panel(panel: str, replay: Replay, snap: dict, state) -> None:
    """One side panel of the Analyst workspace (see lab_ui.PANELS)."""
    teams = _teams(replay)
    if panel == "log":
        with st.container(border=True, height=330, key="analyst_log"):  # scrolls inside; full height on phones
            render_match_story(replay, snap, "📋 Key moments log", 8, "Moments")
        return
    with st.container(border=True, key=f"panel_{panel}"):
        if panel == "explain":
            render_explanation(replay, snap, state)
        elif panel == "notes":
            render_notes(replay, state)
        elif panel == "lab":
            LUI.render_lab(replay, teams, state.clock)
            LUI.render_download(replay, state.clock)
        elif panel == "journal":
            LUI.render_journal(replay, teams, state.clock)
        elif panel == "agents":
            LUI.render_agents(replay, snap, "analyst", state.playing, get_generator(), _cache())

def render(dataset_path: str) -> None:
    st.set_page_config(page_title=PRODUCT_NAME, page_icon="⚽", layout="wide")
    analyst = _mode() == "analyst"
    theme = _theme()
    st.session_state["_theme"] = theme
    st.markdown(CSS % {**THEMES[theme], "accent": LENS_ACCENT[("analyst" if analyst else "fan", theme)],
                       "home": THEMES[theme]["home_text"], "away": THEMES[theme]["away_text"]}, unsafe_allow_html=True)
    st.title(PRODUCT_NAME)  # visually hidden; the banner shows the official logo
    replay, errors = get_replay(dataset_path)
    if errors:
        st.error(f"Dataset invalid ({len(errors)} error(s))")
        for e in errors:
            st.write(f"- {e}")
        st.stop()

    st.session_state["replay"] = replay
    if "replay_state" not in st.session_state:
        st.session_state["replay_state"] = replay.new_state()
    state = _state()
    render_motion_probe()
    if _mode() == "home":  # landing view: logo, value proposition, quick starts and the quick tour
        state.pause()
        render_banner(theme, analyst)
        if I.lang() == "es":
            st.caption(tr("i18n.note"))
        render_home(_crop("lockup_dark" if theme == "dark" else "lockup_light", 120),
                    dict(DEMO_MOMENTS.get(replay.match["match_id"], ())), on_demo)
        return
    if _mode() == "capture":  # planned space: no replay controls, nothing processed
        state.pause()
        render_banner(theme, analyst)
        if I.lang() == "es":
            st.caption(tr("i18n.note"))
        render_capture(replay)
        return
    snap = replay.snapshot(state.clock)
    goals_now = sum(1 for ev in snap["events"] if ev["type"] == "goal")
    goals_seen = st.session_state.get("_goals_seen")
    st.session_state["_goals_seen"] = goals_now

    # 1. Brand, match state and controls (sticky), headline cards
    render_banner(theme, analyst)
    render_control_bar(replay, snap, state, analyst, theme)
    if I.lang() == "es":
        st.caption(tr("i18n.note"))

    if analyst:
        # 2a. Metric strip: only the cards the analyst keeps visible, with the menu at its right end
        c_cards, c_menu = st.columns([8.6, 1.4], vertical_alignment="center")
        with c_cards:
            render_kpis(replay, snap, analyst)
        with c_menu:
            render_kpi_menu()
        # 2. Three columns: the tactical workspace (move, maps, stats & tide, proxy leaders, lineups) in the centre,
        #    panels either side (key moments log, explanation, notes, Hypothesis Lab, Decision Journal, agents),
        #    placed with the layout editor (session only)
        sides = LUI.layout()
        c_left, c_work, c_right = st.columns([1.2, 2.5, 1.3], gap="small")
        with c_work, st.container(border=True):
            c_title, c_lay, c_disp = st.columns([2.6, 1.3, 1.3], vertical_alignment="center")
            with c_title:
                _title(tr("sec.workspace"), tr("sec.workspace_sub"))
            with c_lay:
                LUI.render_layout_editor()
            with c_disp:
                render_display_controls()
            render_workspace(replay, snap, theme)
        for col, side in ((c_left, "left"), (c_right, "right")):
            with col:
                for panel in sides[side]:
                    render_panel(panel, replay, snap, state)
    else:
        # 2. Metrics as a slim stack on the left, pictures and numbers in the middle (key move · stats & pressure ·
        #    lineups), the story on the right; on phones the stack becomes a two-column grid above the pitch
        c_kpi, c_main, c_rail = st.columns([1.05, 3, 2], gap="small")
        with c_kpi:
            render_kpis(replay, snap, analyst)
        with c_main, st.container(border=True):
            _title(tr("sec.key_moments"))
            tab_move, tab_stats, tab_xg, tab_line = st.tabs([tr("tab.key_move"), tr("tab.stats_pressure"),
                                                             tr("tab.xg"), tr("tab.lineups")])
            with tab_move:
                move, events, points = render_key_moves(replay, snap, analyst=False)
                if move:
                    render_move_card(replay, snap, move, events, analyst=False)
            with tab_stats:
                c_stats, c_flow = st.columns([1, 1.25], gap="medium")
                with c_stats:
                    render_summary(replay, snap, compact=True)
                with c_flow:
                    render_pressure(replay, snap, analyst, theme, compact=True)
            with tab_xg:
                LUI.render_xg(replay, _teams(replay), _colors(replay), snap["at_seconds"], key="xg_fan")
            with tab_line:
                render_lineups(replay, snap, analyst=False)
        with c_rail:
            with st.container(border=True, height=340, key="story_rail"):  # Live Story stays on the first screen
                render_match_story(replay, snap, "📰 Match Story", 4, "Key moments")
            with st.container(border=True):
                render_explanation(replay, snap, state)
            with st.expander(tr("ag.title")):
                LUI.render_agents(replay, snap, "fan", state.playing, get_generator(), _cache())
    if st.session_state.get("goal_sound") and goals_seen is not None and goals_now > goals_seen:
        with st.container(key="goal_cheer"):  # hidden player; rendered only in the run where a goal appears
            st.audio(goal_cheer_wav(), format="audio/wav", autoplay=True)
    # 4. Evidence
    render_timeline(replay, snap, analyst)
    render_traceability(replay, snap)

    if state.playing:
        st.session_state["_inline_pass"] = True
        st.fragment(_tick, run_every=TICK_SECONDS)()
