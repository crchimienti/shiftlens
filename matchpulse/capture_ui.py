"""ShiftLens Capture: a planned space (roadmap + interactive wireframe). Nothing here processes video, calls a
model or stores data: the upload control is disabled, the proposals are invented for the synthetic match and the
review queue lives in the session only."""
from __future__ import annotations

from html import escape

import streamlit as st

from .i18n import t
from .replay import clock_label

FLOW = ("cap.step1", "cap.step2", "cap.step3", "cap.step4")
# Invented proposals for the synthetic match (mock data for the wireframe; not derived from any video).
MOCK_PROPOSALS = (
    {"id": "P1", "video_s": 912, "type": "pass", "team": "NBR", "player": "NBR-08", "confidence": 0.93},
    {"id": "P2", "video_s": 925, "type": "pressure", "team": "HBC", "player": "HBC-06", "confidence": 0.71},
    {"id": "P3", "video_s": 941, "type": "shot", "team": "NBR", "player": "NBR-09", "confidence": 0.88},
    {"id": "P4", "video_s": 944, "type": "save", "team": "HBC", "player": "HBC-01", "confidence": 0.64},
    {"id": "P5", "video_s": 980, "type": "corner", "team": "NBR", "player": "NBR-07", "confidence": 0.52},
)
CONTRACT = {
    "matches": ("match_id, competition, kickoff_utc, home/away club ids, rights_status, source_video_ids",
                "One row per match; `rights_status` must be `authorized` before any video is linked."),
    "videos": ("video_id, match_id, uri (private storage), duration_s, kickoff_offset_s, second_half_offset_s, "
               "license_ref, uploaded_by",
               "Offsets map video time to the match clock used by every event."),
    "events": ("event_id, match_id, minute, second, period, team_id, player_id, type, outcome, x, y, end_x, end_y, "
               "sequence_id + provenance {origin: manual / ai_proposal, video_id, video_s, model_version, confidence}",
               "Same fields as today's schema 1.1.0 match file, plus where each event came from."),
    "reviews": ("review_id, event_id, reviewer_id, decision: accepted / edited / rejected, changes, reviewed_at, note",
                "Only accepted or edited proposals become events; every decision is kept for audit."),
}


def _queue() -> dict:
    return st.session_state.setdefault("capture_queue", {p["id"]: "pending" for p in MOCK_PROPOSALS})


def _decide(pid: str, status: str) -> None:
    _queue()[pid] = status


def _reset_queue() -> None:
    st.session_state.pop("capture_queue", None)


def render_capture(replay) -> None:
    with st.container(border=True, key="capture_head"):
        st.markdown(f"### {t('cap.title')} <span class='sl-chip lens'>{t('cap.badge')}</span>", unsafe_allow_html=True)
        st.markdown(t("cap.intro"))

    with st.container(border=True, key="capture_flow"):
        st.markdown(f"**{t('cap.flow')}**")
        cells = '<span class="arrow">→</span>'.join(
            f'<div class="sl-flow-step"><b>{i}. {escape(t(k))}</b><br><small>{escape(t(k + ".d"))}</small></div>'
            for i, k in enumerate(FLOW, 1))
        st.markdown(f'<div class="sl-flow">{cells}</div>', unsafe_allow_html=True)

    with st.container(border=True, key="capture_mock"):
        st.markdown(f"**{t('cap.mock')}** · <span class='sl-chip'>{t('cap.badge')}</span>", unsafe_allow_html=True)
        st.caption(t("cap.mock_note"))
        c_video, c_queue = st.columns([1, 1.25], gap="medium")
        with c_video:
            st.file_uploader(t("cap.upload"), type=["mp4", "mov"], disabled=True, key="capture_upload")
            st.markdown(f"**{t('cap.sync')}**")
            offset = st.number_input(t("cap.offset"), 0, 600, 120, step=1, key="capture_offset")
            video_s = st.slider(t("cap.video_t"), 0, 1200, 945, key="capture_video_s")
            match_s = max(0, min(video_s - offset, replay.duration))
            st.markdown(f'<div class="sl-moment">🎞️ {escape(t("cap.synced", video=clock_label(video_s), clock=clock_label(match_s)))}</div>',
                        unsafe_allow_html=True)
        with c_queue:
            st.markdown(f"**{t('cap.queue')}**")
            queue = _queue()
            for p in MOCK_PROPOSALS:
                status = queue[p["id"]]
                player = replay.players.get(p["player"], {}).get("name", p["player"])
                clock = clock_label(max(0, p["video_s"] - offset))
                with st.container(border=True):
                    c_txt, c_ok, c_no = st.columns([3, 1, 1], vertical_alignment="center")
                    c_txt.markdown(f"**{p['id']}** · {clock} · {p['type']} · {escape(player)} ({p['team']})  \n"
                                   f"<small>conf. {p['confidence']:.2f} · video {clock_label(p['video_s'])} · "
                                   f"{t('cap.status.' + status)}</small>", unsafe_allow_html=True)
                    c_ok.button(t("cap.accept"), key=f"cap_ok_{p['id']}", on_click=_decide, args=(p["id"], "accepted"),
                                disabled=status != "pending", width="stretch")
                    c_no.button(t("cap.reject"), key=f"cap_no_{p['id']}", on_click=_decide, args=(p["id"], "rejected"),
                                disabled=status != "pending", width="stretch")
            st.button(t("cap.reset"), on_click=_reset_queue, key="cap_reset")

    with st.container(border=True, key="capture_contract"):
        st.markdown(f"**{t('cap.contract')}** · <span class='sl-chip'>{t('cap.badge')}</span>", unsafe_allow_html=True)
        st.caption(t("cap.contract_note"))
        st.markdown("\n".join(["| Entity | Fields | Rule |", "|:--|:--|:--|"]
                              + [f"| `{name}` | {fields} | {rule} |" for name, (fields, rule) in CONTRACT.items()]))
