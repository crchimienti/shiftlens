"""Single-page Streamlit UI. Rendering only: state lives in ReplayState, numbers in metrics."""
from __future__ import annotations

from html import escape

import streamlit as st

from . import analytics as A
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
from . import notes as N
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
[data-testid="stMain"] { scroll-timeline: --sl-page block; }
[data-testid="stMainBlockContainer"] { padding-top: 2.2rem; padding-bottom: 2rem; }
h1 { position: absolute !important; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
.sl-crop { display: inline-block; background-repeat: no-repeat; vertical-align: middle; }
.sl-banner { display: flex; align-items: center; justify-content: space-between; gap: 1rem; padding: 0.5rem 1rem;
  border-radius: 0.9rem; background: var(--sl-banner); border: 1px solid var(--sl-border); box-shadow: var(--sl-shadow); }
.sl-banner .tag { color: var(--sl-muted); font-size: 0.82rem; }
.sl-chip { display: inline-block; padding: 0.15rem 0.6rem; margin-left: 0.35rem; border-radius: 999px; font-size: 0.74rem;
  border: 1px solid var(--sl-border); color: var(--sl-text); background: var(--sl-row); white-space: nowrap; }
.sl-chip.lens { border-color: var(--sl-accent); color: var(--sl-accent); font-weight: 700; }
[data-testid="stLayoutWrapper"]:has(> .st-key-control_bar) { position: sticky; top: 3.75rem; z-index: 990; }
.st-key-control_bar { background: var(--sl-bar); border: 1px solid var(--sl-border); border-left: 6px solid var(--sl-accent);
  border-radius: 0.8rem; padding: 0.4rem 0.8rem 0.1rem; box-shadow: var(--sl-shadow); backdrop-filter: blur(6px);
  animation: sl-compact linear both; animation-timeline: --sl-page; animation-range: 0 180px; }
@keyframes sl-compact { to { padding-top: 0.12rem; padding-bottom: 0; } }
.st-key-control_bar [data-testid="stWidgetLabel"], .st-key-control_bar .sl-clock .extra {
  max-height: 2rem; overflow: hidden;
  animation: sl-hide linear both; animation-timeline: --sl-page; animation-range: 0 180px; }
@keyframes sl-hide { to { max-height: 0; opacity: 0; margin: 0; padding: 0; } }
.st-key-control_bar .sl-score .goals { animation: sl-goals linear both; animation-timeline: --sl-page; animation-range: 0 180px; }
@keyframes sl-goals { to { font-size: 1.3rem; } }
.sl-score { display: flex; align-items: center; justify-content: center; gap: 0.7rem; }
.sl-score .team { font-weight: 700; font-size: 1.0rem; }
.sl-score .home { color: var(--sl-home); } .sl-score .away { color: var(--sl-away); }
.sl-score .goals { font-size: 1.7rem; font-weight: 800; letter-spacing: 0.05em; color: var(--sl-text); }
.sl-clock { text-align: center; font-size: 0.78rem; color: var(--sl-muted); margin-top: -0.2rem; }
.sl-kpi { border: 1px solid var(--sl-border); border-top: 3px solid var(--sl-accent); border-radius: 0.7rem;
  padding: 0.4rem 0.7rem; height: 84px; display: flex; flex-direction: column; justify-content: space-between;
  background: var(--sl-card); overflow: hidden; box-shadow: var(--sl-shadow); }
.sl-kpi .lbl { font-size: 0.72rem; color: var(--sl-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sl-kpi .lbl span { cursor: help; opacity: 0.7; }
.sl-kpi .val { font-size: 1.18rem; font-weight: 700; line-height: 1.1; color: var(--sl-text); }
.sl-kpi .val.small { font-size: 0.96rem; }
.sl-kpi .sub { font-size: 0.66rem; color: var(--sl-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sl-panel-title { font-weight: 700; font-size: 0.95rem; color: var(--sl-text); margin-bottom: 0.2rem; }
.sl-panel-title .acc { color: var(--sl-accent); font-weight: 500; font-size: 0.8rem; }
table.sl-stats { width: 100%%; border-collapse: collapse; font-size: 0.88rem; color: var(--sl-text); }
table.sl-stats td, table.sl-stats th { border: none !important; padding: 0.12rem 0.4rem; text-align: center; }
table.sl-stats tr:nth-child(even) { background: var(--sl-row); }
table.sl-stats .lbl { color: var(--sl-muted); font-size: 0.78rem; white-space: nowrap; }
table.sl-stats .lead { font-weight: 800; color: var(--sl-accent); }
table.sl-stats th.home { color: var(--sl-home); } table.sl-stats th.away { color: var(--sl-away); }
.sl-moment { font-size: 0.85rem; line-height: 1.35; color: var(--sl-text); }
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p { color: var(--sl-muted) !important; }
.sl-chain { display: flex; gap: 0.25rem; align-items: center; flex-wrap: wrap; justify-content: flex-end; margin-top: 0.3rem; }
.sl-chain .step { font-size: 0.7rem; padding: 0.1rem 0.5rem; border-radius: 0.4rem; color: var(--sl-text);
  border: 1px solid var(--sl-border); background: var(--sl-row); cursor: help; }
.sl-chain .step b { color: var(--sl-accent); }
.sl-chain .arrow { color: var(--sl-muted); font-size: 0.7rem; }
.sl-read { border-left: 3px solid var(--sl-accent); padding: 0.35rem 0.6rem; margin-bottom: 0.35rem; background: var(--sl-row);
  border-radius: 0.4rem; color: var(--sl-text); font-size: 0.9rem; }
.sl-read ul { margin: 0.25rem 0 0 1rem; padding: 0; font-size: 0.84rem; }
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
    return st.session_state.get("mode", "Fan").lower()


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
    lens = "📋 Analyst Lens · tactical desk" if analyst else "📺 Fan Lens · broadcaster companion"
    chain = '<span class="arrow">→</span>'.join(
        f'<span class="step" title="{escape(tip)}"><b>{i}</b> {name}</span>'
        for i, (name, tip) in enumerate(VALUE_CHAIN, 1))
    st.markdown(
        f'<div class="sl-banner"><div>{_crop("lockup_dark" if theme == "dark" else "lockup_light", 64)}</div>'
        f'<div style="text-align:right"><div><span class="sl-chip lens">{lens}</span>'
        f'<span class="sl-chip">Synthetic Premier League-style scenario · simulated replay · fictional clubs</span></div>'
        f'<div class="sl-chain">{chain}</div></div></div>',
        unsafe_allow_html=True)


def render_control_bar(replay: Replay, snap: dict, state, analyst: bool, theme: str) -> None:
    """Sticky bar: score, clock, play/pause/reset, speed, lens, match clock and jump-to moments."""
    home, away = _teams(replay)
    score = snap["metrics"]["score"]["value"]
    half = "1st half" if snap["period"] == 1 else "2nd half"
    status = "▶ Playing" if state.playing else ("🏁 Full time" if state.clock >= state.duration else "⏸ Paused")
    with st.container(key="control_bar"):
        c_score, c_play, c_pause, c_reset, c_speed, c_lens = st.columns(
            [3.1, 0.9, 0.9, 0.9, 1.9, 1.8], vertical_alignment="center")
        c_score.markdown(
            f'<div class="sl-score">{_crop("icon_dark" if theme == "dark" else "icon_light", 30)}'
            f'<span class="team home">{escape(home["name"])}</span>'
            f'<span class="goals">{score[home["id"]]} – {score[away["id"]]}</span>'
            f'<span class="team away">{escape(away["name"])}</span></div>'
            f'<div class="sl-clock"><b>⏱ {snap["clock"]}</b> / {clock_label(replay.duration)} · {half} · {status}'
            f'<span class="extra"> · {"Analyst Lens" if analyst else "Fan Lens"}</span></div>', unsafe_allow_html=True)
        c_play.button("Play", icon=":material/play_arrow:", on_click=on_play, width="stretch",
                      disabled=state.playing or state.clock >= state.duration)
        c_pause.button("Pause", icon=":material/pause:", on_click=on_pause, disabled=not state.playing,
                       width="stretch")
        c_reset.button("Reset", icon=":material/replay:", on_click=on_reset, width="stretch")
        if not st.session_state.get("speed"):  # default, and re-select 1x if the active option was clicked off
            st.session_state["speed"] = DEFAULT_SPEED
        c_speed.segmented_control("Speed", list(SPEEDS), key="speed",
                                  help="Replay speed. 1x = 10 simulated seconds per real second.")
        c_lens.radio("Lens", ["Fan", "Analyst"], key="mode", horizontal=True, format_func=lambda m: f"{m} Lens",
                     help="Fan Lens: a broadcaster companion. Analyst Lens: a tactical desk with references, "
                          "move breakdowns, proxy analytics and full traceability.")
        moments = DEMO_MOMENTS.get(replay.match["match_id"], ())
        c_clock, *c_moments = st.columns([3.4] + [1.25] * len(moments), vertical_alignment="bottom")
        st.session_state["seek_clock"] = state.clock
        c_clock.select_slider("Match clock", options=range(replay.duration + 1), key="seek_clock",
                              format_func=clock_label, on_change=on_seek)
        icons = {"Momentum swing": ":material/swap_horiz:", "Goal moment": "⚽", "Late pressure": ":material/trending_up:"}
        for col, (label, seconds) in zip(c_moments, moments):
            col.button(f"{label} ({clock_label(seconds)})", icon=icons.get(label), on_click=on_demo,
                       args=(seconds,), width="stretch", help=f"Jump to {clock_label(seconds)} and pause")


def render_kpis(replay: Replay, snap: dict, analyst: bool) -> None:
    m = snap["metrics"]
    home, away = _teams(replay)
    h, a = home["id"], away["id"]
    mom = m["momentum"]["value"]
    suf = m["data_sufficiency"]
    tc = m["territorial_control"]
    cards = [
        _kpi("🌊 Pressure", momentum_cue(mom, home["name"], away["name"]), f"{mom:+.2f} · −1 {a} … +1 {h}",
             MOMENTUM_HELP, small=True),
        _kpi(f"↗️ Pass share · {h}–{a}", _split(m["pass_share"]["value"], h, a, ".0f", "%"),
             window_label(m["pass_share"]["window"]), "Share of pass events. Not possession."),
        _kpi(f"🔥 Danger index · {h}–{a}", _split(m["danger_score"]["value"], h, a, ".1f"),
             window_label(m["danger_score"]["window"]), "Weighted attacking actions. A simple index, not xG."),
        _kpi(f"🗺️ Territory · {h}–{a}", _split(tc["value"], h, a, ".0f", "%"),
             f"in attacking areas, {window_label(tc['window'])}",
             "Share of each team's actions in the attacking third or box."),
        _kpi("📊 Evidence level", EVIDENCE_LEVELS.get(suf["value"], suf["value"]),
             f"{suf['details']['event_count']} events, {window_label(suf['window'])}",
             "How much data is behind the numbers. Low = treat them with caution."),
    ]
    if analyst:
        inf = m["inflection_point"]
        v = inf["value"]
        sqi = A.team_shot_summary(A.shots(snap["events"], h), (h, a))
        cards.append(_kpi(f"🎯 Shot Quality · {h}–{a}", f"{sqi[h]['sqi_total']:.2f} – {sqi[a]['sqi_total']:.2f}",
                          f"{sqi[h]['shots']} – {sqi[a]['shots']} shots · proxy, not xG", SQI_HELP))
        cards.append(_kpi("🔄 Turning point", f"{clock_label(v['to_seconds'])} → {inf['team_id']}" if v else "None yet",
                          f"change {v['delta']:+.2f}" if v else "no swing above 0.8 yet",
                          "Largest momentum swing so far (above 0.8 within 2 minutes)."))
    for col, card in zip(st.columns(len(cards)), cards):
        col.markdown(card, unsafe_allow_html=True)


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
    c_feat, c_any = st.columns([3, 2], vertical_alignment="bottom")
    c_feat.segmented_control(
        "Featured moves (highest impact)", featured_ids, key="featured_move", on_change=on_featured_move,
        format_func=lambda sid: f"{'⚽ ' if by_feat[sid]['has_goal'] else ''}{names[by_feat[sid]['team_id']]} · "
                                f"{clock_label(by_feat[sid]['start_seconds'])}")
    by_id = {m["sequence_id"]: m for m in everything}
    c_any.selectbox(f"All moves so far ({len(everything)})", list(by_id), key="any_move", on_change=on_any_move,
                    format_func=lambda sid: _move_label(by_id[sid], names))
    events = move_events(snap, move["sequence_id"])
    points = move_points(events, home["id"], replay.players, replay.config)
    gains = underlay = labels = attack = None
    view = None
    if analyst:
        if not st.session_state.get("threat_view"):  # default, and re-select if the active option was clicked off
            st.session_state["threat_view"] = T.VIEW_GAINS
        st.segmented_control("Threat view", list(T.THREAT_VIEWS), key="threat_view", help=THREAT_HELP)
        view = st.session_state["threat_view"]
        right = move["team_id"] == home["id"]
        if view == T.VIEW_GAINS:
            gains = T.threat_gains(snap["events"])
        elif view == T.VIEW_DANGER:
            underlay, labels = T.threat_underlay(right), T.threat_cell_labels(right)
        attack = {"team": names[move["team_id"]], "target": (away if right else home)["name"], "right": right,
                  "color": HOME_COLOR if right else AWAY_COLOR}
    st.plotly_chart(pitch_figure(points, home, away, detailed=analyst, highlight=st.session_state.get("selected_event"),
                                 palette=_pal(), threat=gains, underlay=underlay, cell_labels=labels, attack=attack),
                    config=PLOT_CONFIG, key="pitch")
    st.caption((THREAT_VIEW_NOTES[view] + " Zone Threat is a fixed grid, not xT. " + TACTICAL_NOTE + " "
                if analyst else "") + PITCH_NOTE)
    return move, events, points


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
    _title("📝 Analyst notes", "attached to the match clock · kept for this session")
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
                col.plotly_chart(A.zone_heatmap_figure(events, team, right, rgb), config=PLOT_CONFIG,
                                 key=f"heat_{team['id']}")
        else:
            team = home if pick.startswith(home["id"]) else away
            right = team["id"] == home["id"]
            n = sum(A.zone_activity(events, team["id"], pick).values())
            st.markdown(f"**{replay.players[pick]['name']}** · {n} actions so far")
            st.plotly_chart(A.zone_heatmap_figure(events, team, right, HOME_RGB if right else AWAY_RGB, player_id=pick),
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
                slots = A.average_action_positions(events, team["id"], right)
            col.markdown(f"**{team['name']}** · {sum(links.values())} links")
            col.plotly_chart(A.pass_network_figure(links, slots, team, colors[team["id"]], replay.players,
                                                   threat=T.link_threat(events, team["id"]),
                                                   player_threat=p_threat, label_top=3),
                             config=PLOT_CONFIG, key=f"net_{team['id']}")
            top = sorted(A.merged_links(links, T.link_threat(events, team["id"])).items(),
                         key=lambda kv: (-kv[1]["n"], kv[0]))[:3]
            col.caption(" · ".join(f"{replay.players[a]['name'].split()[-1]}–{replay.players[b]['name'].split()[-1]} "
                                   f"{r['n']}× ({r['gain']:+.2f})" for (a, b), r in top) or "No links yet.")
        st.caption("Schematic pass network: a link = a pass, cross, corner or free kick followed by a team-mate's "
                   "next action in the same move. Line width = links; line colour = threat gain moved along the link "
                   "(Zone Threat grid, grey = none); the busiest links show their count. Players sit at the average "
                   "of their zone × lane cells or at their formation slots, never at measured positions.")
    with maps[2]:
        shot_list = A.shots(events, home["id"])
        summary = A.team_shot_summary(shot_list, (home["id"], away["id"]))
        c_map, c_tab = st.columns([3, 2], gap="medium")
        c_map.plotly_chart(A.shot_map_figure(shot_list, home, away, colors, replay.players), config=PLOT_CONFIG,
                           key="shot_map")
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
        st.plotly_chart(A.defensive_map_figure(pts, home, away, colors, replay.players), config=PLOT_CONFIG,
                        key="def_map")
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
    snap = replay.snapshot(state.clock)

    # 1. Brand, match state and controls (sticky), headline cards
    render_banner(theme, analyst)
    render_control_bar(replay, snap, state, analyst, theme)
    render_kpis(replay, snap, analyst)

    if analyst:
        # 2. Tactical workspace = the analytical surface (move, maps, stats & tide, proxy leaders, lineups);
        #    the right rail holds the story: key moments log, analyst explanation, notes
        c_work, c_rail = st.columns([2.45, 1.55], gap="medium")
        with c_work, st.container(border=True):
            _title("📋 Tactical workspace", "schematic · proxy-based · synthetic data")
            render_workspace(replay, snap, theme)
        with c_rail:
            with st.container(border=True, height=430):  # scrolls inside, so the rail keeps its shape
                render_match_story(replay, snap, "📋 Key moments log", 8, "Moments")
            with st.container(border=True):
                render_explanation(replay, snap, state)
            with st.container(border=True):
                render_notes(replay, state)
    else:
        # 2. Pictures and numbers on the left (key move · stats & pressure · lineups), the story on the right
        c_main, c_rail = st.columns([3, 2], gap="medium")
        with c_main, st.container(border=True):
            _title("⚽ Key moments")
            tab_move, tab_stats, tab_line = st.tabs(["⚽ Key move", "📊 Stats & pressure", "👥 Lineups"])
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
            with tab_line:
                render_lineups(replay, snap, analyst=False)
        with c_rail:
            with st.container(border=True):
                render_match_story(replay, snap, "📰 Match Story", 3, "Key moments")
            with st.container(border=True):
                render_explanation(replay, snap, state)
    # 4. Evidence
    render_timeline(replay, snap, analyst)
    render_traceability(replay, snap)

    if state.playing:
        st.session_state["_inline_pass"] = True
        st.fragment(_tick, run_every=TICK_SECONDS)()
