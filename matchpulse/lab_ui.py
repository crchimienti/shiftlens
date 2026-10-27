"""Analyst panels added for the hackathon build: Hypothesis Lab, Decision Journal, agent trace, xG evolution and the
workspace layout editor. Rendering only; the logic lives in lab.py, agents.py and xg.py. Records live in the
session (st.session_state) and can be downloaded as JSON; nothing is written to disk."""
from __future__ import annotations

import json
from html import escape

import streamlit as st

from . import lab as L
from .agents import run_agents
from .i18n import t
from .replay import clock_label
from .xg import xg_figure, xg_totals

PLOT_CONFIG = {"displayModeBar": False}
VERDICT_ICON = {"supported": "✅", "not_supported": "❌", "inconclusive": "➖", "pending": "⏳"}
PANELS = ("log", "explain", "notes", "lab", "journal", "agents")
DEFAULT_LAYOUT = {"left": ["log", "notes"], "right": ["explain", "lab", "journal", "agents"]}


def _records() -> dict:
    return st.session_state.setdefault("lab_records", {"hypotheses": [], "decisions": [], "seq": 0})


def _next_id() -> int:
    rec = _records()
    rec["seq"] += 1
    return rec["seq"]


def _team_name(teams, team_id: str) -> str:
    return next(tm["name"] for tm in teams if tm["id"] == team_id)


def _minutes(pair) -> str:
    return f"{clock_label(pair[0])}–{clock_label(pair[1])}"


def _fmt(name: str, value) -> str:
    if value is None:
        return "—"
    return f"{value:.1f}%" if name == "pass_share" else f"{value:.2f}" if name == "xg" else f"{value:g}"


def _verdict_line(res: dict) -> str:
    icon = VERDICT_ICON[res["verdict"]]
    head = f"{icon} **{t('verdict.' + res['verdict'])}**"
    if res["verdict"] == "pending":
        return head
    return head + " · " + t("lab.result", a=_fmt(res["measure"], res["value_a"]), b=_fmt(res["measure"], res["value_b"]),
                            delta=f"{res['delta']:+g}", n=len(res["evidence_event_ids"]))


# --- Hypothesis Lab ---------------------------------------------------------------------------------------------

def render_lab(replay, teams, clock: int) -> None:
    st.markdown(f"**{t('lab.title')}** · <small>{t('lab.sub')}</small>", unsafe_allow_html=True)
    ids = [tm["id"] for tm in teams]
    span = replay.duration // 60
    with st.form("lab_form", clear_on_submit=False, border=False):
        c1, c2 = st.columns(2)
        team = c1.selectbox(t("lab.team"), ids, format_func=lambda i: _team_name(teams, i), key="lab_team")
        measure = c2.selectbox(t("lab.measure"), L.MEASURES, format_func=lambda m: t("measure." + m), key="lab_measure")
        direction = st.radio(t("lab.direction"), ("higher", "lower"), horizontal=True, key="lab_dir",
                             format_func=lambda d: t("lab.dir." + d))
        a = st.slider(t("lab.window_a"), 0, span, (30, 45), key="lab_a")
        b = st.slider(t("lab.window_b"), 0, span, (45, 60), key="lab_b")
        statement = st.text_input(t("lab.statement"), key="lab_statement", max_chars=160)
        submitted = st.form_submit_button(t("lab.test"), icon=":material/science:")
    if submitted:
        if a[0] >= a[1] or b[0] >= b[1]:
            st.warning(t("lab.bad_windows"))
        else:
            win_a, win_b = (a[0] * 60, a[1] * 60), (b[0] * 60, b[1] * 60)
            text = statement or f"{_team_name(teams, team)}: {t('measure.' + measure)} {t('lab.dir.' + direction)}"
            _records()["hypotheses"].append(
                L.make_hypothesis(_next_id(), text, team, measure, win_a, win_b, direction, clock))
    hyps = _records()["hypotheses"]
    if not hyps:
        st.caption(t("lab.empty"))
    for h in reversed(hyps):
        res = L.evaluate_hypothesis(h, replay.match["events"], clock)
        with st.container(border=True):
            st.markdown(f"**#{h['id']}** {escape(h['statement'])}  \n"
                        f"<small>{_team_name(teams, h['team_id'])} · {t('measure.' + h['measure'])} · "
                        f"A {_minutes(h['window_a'])} → B {_minutes(h['window_b'])}</small>", unsafe_allow_html=True)
            st.markdown(_verdict_line(res))
            if res["verdict"] == "pending":
                st.caption(t("lab.future"))
            elif res["evidence_event_ids"]:
                st.caption("Evidence: " + ", ".join(res["evidence_event_ids"][:12])
                           + (" …" if len(res["evidence_event_ids"]) > 12 else ""))


# --- Decision Journal -------------------------------------------------------------------------------------------

def render_journal(replay, teams, clock: int) -> None:
    st.markdown(f"**{t('dj.title')}** · <small>{t('dj.sub')}</small>", unsafe_allow_html=True)
    ids = [tm["id"] for tm in teams]
    with st.form("dj_form", clear_on_submit=True, border=False):
        c1, c2 = st.columns(2)
        team = c1.selectbox(t("lab.team"), ids, format_func=lambda i: _team_name(teams, i), key="dj_team")
        kind = c2.selectbox(t("dj.kind"), L.DECISION_KINDS, format_func=lambda k: t("dj.kind." + k), key="dj_kind")
        c3, c4 = st.columns(2)
        measure = c3.selectbox(t("dj.expect"), L.MEASURES, format_func=lambda m: t("measure." + m), key="dj_measure")
        direction = c4.radio(t("lab.direction"), ("higher", "lower"), horizontal=True, key="dj_dir",
                             format_func=lambda d: t("dj.dir." + d))
        review = st.slider(t("dj.review"), 5, 20, 10, key="dj_review")
        rationale = st.text_area(t("dj.rationale"), key="dj_rationale", max_chars=280, height=68)
        submitted = st.form_submit_button(t("dj.log", clock=clock_label(clock)), icon=":material/edit_note:")
    if submitted:
        _records()["decisions"].append(
            L.make_decision(_next_id(), clock, team, kind, rationale, measure, direction, review))
    decisions = _records()["decisions"]
    if not decisions:
        st.caption(t("dj.empty"))
    for d in reversed(decisions):
        res = L.review_decision(d, replay.match["events"], clock, replay.duration)
        with st.container(border=True):
            st.markdown(f"**#{d['id']} · {clock_label(d['at'])}** {_team_name(teams, d['team_id'])} · "
                        f"{t('dj.kind.' + d['decision'])}" + (f"  \n_{escape(d['rationale'])}_" if d["rationale"] else ""))
            if res["verdict"] == "pending":
                st.markdown(f"{VERDICT_ICON['pending']} " + t("dj.pending", clock=clock_label(L.review_end(d, replay.duration))))
            else:
                st.markdown(_verdict_line(res) + "  \n" + t("dj.compare", before=_fmt(d["measure"], res["value_a"]),
                                                            after=_fmt(d["measure"], res["value_b"])))
    if decisions:
        st.caption(t("dj.caveat"))


def render_download(replay, clock: int) -> None:
    rec = _records()
    if not (rec["hypotheses"] or rec["decisions"]):
        return
    events = replay.match["events"]
    payload = {"match_id": replay.match["match_id"], "clock": clock, "version": L.VERSION,
               "hypotheses": [{**h, "result": L.evaluate_hypothesis(h, events, clock)} for h in rec["hypotheses"]],
               "decisions": [{**d, "review": L.review_decision(d, events, clock, replay.duration)} for d in rec["decisions"]]}
    st.download_button(t("lab.download"), json.dumps(payload, indent=1, ensure_ascii=False),
                       file_name=f"shiftlens_{replay.match['match_id']}_records.json", mime="application/json",
                       icon=":material/download:", key="lab_download")
    st.caption(t("lab.session_note"))


# --- agents -----------------------------------------------------------------------------------------------------

def render_agents(replay, snap: dict, lens: str, playing: bool, generator, cache) -> None:
    st.markdown(f"**{t('ag.title')}** · <small>{t('ag.sub')}</small>", unsafe_allow_html=True)
    st.caption(t("ag.mode.online" if generator is not None else "ag.mode.offline"))
    for name in (("FanStoryAgent",) if lens == "fan" else ("TacticalAnalystAgent",)) + ("EvidenceGuardrail",):
        st.markdown(f"- **{name}** · {t('ag.' + name)}")
    key = f"agents_{lens}"
    if st.button(t("ag.run"), key=f"{key}_run", disabled=playing, icon=":material/account_tree:"):
        rec = _records()
        st.session_state[key] = {"at": snap["at_seconds"], "out": run_agents(
            replay, snap, lens, rec["hypotheses"], rec["decisions"], generator, cache)}
    if playing:
        st.caption(t("ag.paused"))
    last = st.session_state.get(key)
    if last and last["at"] == snap["at_seconds"]:
        out = last["out"]
        rows = "".join(f"<li>{'✓' if s['ok'] else '✗'} <b>{escape(s['agent'])}</b> · <code>{escape(s['tool'])}</code>"
                       f"<br>{escape(s['detail'])}</li>" for s in out["trace"])
        st.markdown(f"**{t('ag.trace')}** · {clock_label(last['at'])} · "
                    f"{t('ag.verdict.pass') if out['ok'] else t('ag.verdict.fail')}", unsafe_allow_html=True)
        st.markdown(f'<ol class="sl-trace">{rows}</ol>', unsafe_allow_html=True)


# --- xG evolution -----------------------------------------------------------------------------------------------

def render_xg(replay, teams, colors: dict, clock: int, key: str) -> None:
    events = replay.match["events"]
    st.plotly_chart(xg_figure(events, teams, colors, clock), config=PLOT_CONFIG, key=key)
    totals = xg_totals(events, (teams[0]["id"], teams[1]["id"]), clock)
    st.caption(" · ".join(t("xg.total", team=tm["name"], xg=f"{totals[tm['id']]['xg']:.2f}",
                                shots=totals[tm["id"]]["shots"]) for tm in teams))
    st.caption(t("xg.caption"))


# --- layout editor ----------------------------------------------------------------------------------------------

def layout() -> dict:
    for side in ("left", "right"):
        st.session_state.setdefault(f"layout_{side}", list(DEFAULT_LAYOUT[side]))
    return {side: [p for p in st.session_state[f"layout_{side}"] if p in PANELS] for side in ("left", "right")}


def _reset_layout() -> None:
    for side in ("left", "right"):
        st.session_state[f"layout_{side}"] = list(DEFAULT_LAYOUT[side])


def _dedupe(changed: str) -> None:
    """A panel lives in one column: picking it on one side removes it from the other."""
    other = "right" if changed == "left" else "left"
    picked = st.session_state[f"layout_{changed}"]
    st.session_state[f"layout_{other}"] = [p for p in st.session_state[f"layout_{other}"] if p not in picked]


def render_layout_editor() -> None:
    layout()
    with st.popover(t("layout.button"), icon=":material/dashboard_customize:", width="stretch"):
        st.markdown(f"**{t('layout.title')}**")
        st.caption(t("layout.help"))
        for side in ("left", "right"):
            st.multiselect(t(f"layout.{side}"), PANELS, key=f"layout_{side}", format_func=lambda p: t("panel." + p),
                           on_change=_dedupe, args=(side,))
        st.button(t("layout.reset"), on_click=_reset_layout, key="layout_reset")
