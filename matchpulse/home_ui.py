"""Home landing view and the Quick Tour (onboarding). Rendering only: navigation goes through the `mode` lens key,
and a tour step's "Try it" only switches lens and jumps the replay to a known demo moment (paused)."""
from __future__ import annotations

from collections.abc import Callable

import streamlit as st

from .i18n import t

TOUR = (  # (key, lens to open, demo moment to jump to)
    ("replay", "Fan", "Momentum swing"),
    ("evidence", "Analyst", "Goal moment"),
    ("hypothesis", "Analyst", "Goal moment"),
)


def _open(mode: str) -> None:
    st.session_state["mode"] = mode


def _tour_step(delta: int) -> None:
    st.session_state["tour_step"] = max(0, min(len(TOUR) - 1, st.session_state.get("tour_step", 0) + delta))


def _try(mode: str, jump: Callable[[], None]) -> None:
    jump()
    st.session_state["mode"] = mode


def render_home(logo_html: str, moments: dict[str, int], jump_to: Callable[[int], None]) -> None:
    with st.container(border=True, key="home_hero"):
        st.markdown(f'<div class="sl-home">{logo_html}'
                    f'<h2 class="sl-home-claim">{t("home.claim")}</h2>'
                    f'<p class="sl-home-sub">{t("home.sub")}</p>'
                    f'<span class="sl-chip">{t("chip.synthetic")}</span></div>', unsafe_allow_html=True)
    cols = st.columns(3, gap="medium")
    for col, (mode, icon) in zip(cols, (("Fan", "📺"), ("Analyst", "📋"), ("Capture", "🎬"))):
        with col, st.container(border=True, key=f"home_card_{mode.lower()}"):
            st.markdown(f"#### {icon} {t('lens.' + mode)}")
            st.markdown(t(f"home.{mode.lower()}"))
            st.button(t(f"home.open.{mode.lower()}"), key=f"home_open_{mode.lower()}", on_click=_open, args=(mode,),
                      type="primary" if mode == "Fan" else "secondary", width="stretch")
    render_tour(moments, jump_to)


def render_tour(moments: dict[str, int], jump_to: Callable[[int], None]) -> None:
    step = st.session_state.setdefault("tour_step", 0)
    key, mode, moment = TOUR[step]
    with st.container(border=True, key="home_tour"):
        st.markdown(f"### {t('tour.title')}")
        st.caption(t("tour.progress", n=step + 1, total=len(TOUR)))
        st.progress((step + 1) / len(TOUR))
        st.markdown(f"**{t('tour.' + key + '.title')}**")
        st.markdown(t("tour." + key + ".body"))
        c_back, c_try, c_next = st.columns([1, 2, 1])
        c_back.button(t("tour.back"), key="tour_back", on_click=_tour_step, args=(-1,), disabled=step == 0,
                      width="stretch")
        seconds = moments.get(moment, 0)
        c_try.button(t("tour.try", lens=t("lens." + mode)), key="tour_try", type="primary", width="stretch",
                     on_click=_try, args=(mode, lambda: jump_to(seconds)), icon=":material/play_circle:")
        c_next.button(t("tour.next"), key="tour_next", on_click=_tour_step, args=(1,),
                      disabled=step == len(TOUR) - 1, width="stretch")
