"""English / Spanish display text. Canonical data, metric names, validation and stored records stay English;
only labels change with the language. `t(key)` fails loudly on unknown keys so a missing entry is caught in tests.

Coverage: navigation, replay controls, section titles and tabs, notes, Hypothesis Lab, Decision Journal, agent
architecture and ShiftLens Capture. Generated match narratives, chart text and metric tooltips are English in this
version; the Spanish view says so (`i18n.note`).
"""
from __future__ import annotations

import streamlit as st

LANGS = ("en", "es")
LANG_LABELS = {"en": "English", "es": "Español"}

CATALOG: dict[str, tuple[str, str]] = {
    # navigation and chrome
    "lang.label": ("Language", "Idioma"),
    "lens.label": ("Lens", "Lente"),
    "lens.Home": ("Home", "Inicio"),
    "lens.Fan": ("Fan Lens", "Lente Aficionado"),
    "lens.Analyst": ("Analyst Lens", "Lente Analista"),
    "lens.Capture": ("Capture · planned", "Capture · planificado"),
    "lens.help": ("Fan Lens: a broadcaster companion. Analyst Lens: a tactical desk with references, move breakdowns, "
                  "proxy analytics and full traceability. Capture: the planned video-annotation space (roadmap).",
                  "Lente Aficionado: un acompañante tipo retransmisión. Lente Analista: una mesa táctica con referencias, "
                  "desglose de jugadas, analítica proxy y trazabilidad completa. Capture: el espacio planificado de "
                  "anotación de vídeo (hoja de ruta)."),
    "chip.home": ("🏠 Home", "🏠 Inicio"),
    "chip.fan": ("📺 Fan Lens · broadcaster companion", "📺 Lente Aficionado · acompañante de retransmisión"),
    "chip.analyst": ("📋 Analyst Lens · tactical desk", "📋 Lente Analista · mesa táctica"),
    "chip.capture": ("🎬 ShiftLens Capture · planned", "🎬 ShiftLens Capture · planificado"),
    "chip.synthetic": ("Synthetic Premier League-style scenario · simulated replay · fictional clubs",
                       "Escenario sintético estilo Premier League · repetición simulada · clubes ficticios"),
    "speed.label": ("Speed", "Velocidad"),
    "speed.help": ("Replay speed. 1x = 10 simulated seconds per real second.",
                   "Velocidad de la repetición. 1x = 10 segundos simulados por segundo real."),
    "sound.label": ("🔔 Goal", "🔔 Gol"),
    "ctl.play": ("Play", "Reproducir"),
    "ctl.pause": ("Pause", "Pausa"),
    "ctl.reset": ("Reset", "Reiniciar"),
    "half.1": ("1st half", "1.ª parte"),
    "half.2": ("2nd half", "2.ª parte"),
    "status.playing": ("▶ Playing", "▶ En juego"),
    "status.full_time": ("🏁 Full time", "🏁 Final"),
    "status.paused": ("⏸ Paused", "⏸ En pausa"),
    "moment.Momentum swing": ("Momentum swing", "Cambio de inercia"),
    "moment.Goal moment": ("Goal moment", "Momento del gol"),
    "moment.Late pressure": ("Late pressure", "Presión final"),
    "moment.help": ("Jump to {clock} and pause", "Ir al {clock} y pausar"),
    "i18n.note": ("", "Vista en español: navegación, controles y nuevos espacios traducidos. Las narraciones generadas, "
                      "los textos de gráficos y las ayudas de métricas siguen en inglés en esta versión."),
    # sections
    "sec.key_moments": ("⚽ Key moments", "⚽ Momentos clave"),
    "tab.key_move": ("⚽ Key move", "⚽ Jugada clave"),
    "tab.stats_pressure": ("📊 Stats & pressure", "📊 Estadísticas y presión"),
    "tab.lineups": ("👥 Lineups", "👥 Alineaciones"),
    "tab.xg": ("📈 xG evolution", "📈 Evolución del xG"),
    "sec.workspace": ("📋 Tactical workspace", "📋 Espacio táctico"),
    "sec.workspace_sub": ("schematic · proxy-based · synthetic data", "esquemático · basado en proxies · datos sintéticos"),
    "sec.match_story": ("📰 Match Story", "📰 Relato del partido"),
    "sec.moments_log": ("📋 Key moments log", "📋 Registro de momentos clave"),
    # home and quick tour
    "home.claim": ("From moments to evidence. From evidence to insight.",
                   "De los momentos a la evidencia. De la evidencia al conocimiento."),
    "home.sub": ("ShiftLens replays a match second by second and explains every turning point with numbers you can "
                 "trace back to the events behind them. This demo uses one synthetic 90-minute match between fictional "
                 "clubs.",
                 "ShiftLens repite un partido segundo a segundo y explica cada punto de inflexión con números que puedes "
                 "rastrear hasta los eventos que los originan. Esta demo usa un partido sintético de 90 minutos entre "
                 "clubes ficticios."),
    "home.fan": ("Follow the match like a broadcast: the key move on the pitch (static or animated), pressure, xG and "
                 "a live story that explains each paused moment.",
                 "Sigue el partido como una retransmisión: la jugada clave en el campo (estática o animada), presión, xG y "
                 "un relato que explica cada momento en pausa."),
    "home.analyst": ("A tactical desk: maps, evidence trace, Hypothesis Lab, Decision Journal and the agent trace, in a "
                     "three-column workspace you can rearrange.",
                     "Una mesa táctica: mapas, traza de evidencia, laboratorio de hipótesis, diario de decisiones y traza de "
                     "agentes, en un espacio de tres columnas que puedes reorganizar."),
    "home.capture": ("The planned video-annotation space: product flow, interactive wireframe and data contract. "
                     "Roadmap only.",
                     "El espacio planificado de anotación de vídeo: flujo del producto, wireframe interactivo y contrato de "
                     "datos. Solo hoja de ruta."),
    "home.open.fan": ("Open Fan Lens", "Abrir Lente Aficionado"),
    "home.open.analyst": ("Open Analyst Lens", "Abrir Lente Analista"),
    "home.open.capture": ("Open Capture (planned)", "Abrir Capture (planificado)"),
    "tour.title": ("🧭 Quick tour", "🧭 Recorrido rápido"),
    "tour.progress": ("Step {n} of {total}", "Paso {n} de {total}"),
    "tour.back": ("‹ Back", "‹ Atrás"),
    "tour.next": ("Next ›", "Siguiente ›"),
    "tour.try": ("Try it in {lens}", "Pruébalo en {lens}"),
    "tour.replay.title": ("1 · Replay controls", "1 · Controles de la repetición"),
    "tour.replay.body": ("The sticky bar plays, pauses and resets the match; the clock strip seeks to any second and the "
                         "moment buttons jump to known turning points. Everything you see uses only events up to the "
                         "clock: nothing later is ever shown. On the pitch, switch Static / Animated to replay a move "
                         "step by step.",
                         "La barra fija reproduce, pausa y reinicia el partido; la franja del reloj salta a cualquier "
                         "segundo y los botones de momentos van a puntos de inflexión conocidos. Todo usa solo eventos "
                         "hasta el reloj: nunca se muestra nada posterior. En el campo, cambia Estática / Animada para ver "
                         "una jugada paso a paso."),
    "tour.evidence.title": ("2 · Evidence trace", "2 · Traza de evidencia"),
    "tour.evidence.body": ("Pause and press Explain this moment: every number in the explanation must come from a metric "
                           "with a time window and source event IDs. The traceability table at the bottom lists them, "
                           "and the agent trace shows the EvidenceGuardrail checking each output.",
                           "Pausa y pulsa Explain this moment: cada número de la explicación debe salir de una métrica con "
                           "su ventana de tiempo e IDs de eventos de origen. La tabla de trazabilidad los enumera y la "
                           "traza de agentes muestra a EvidenceGuardrail comprobando cada salida."),
    "tour.hypothesis.title": ("3 · Hypothesis testing", "3 · Prueba de hipótesis"),
    "tour.hypothesis.body": ("In the Analyst Lens, the Hypothesis Lab compares one team's measure (pressures, shots, xG…) "
                             "in two windows and returns supported, not supported, inconclusive or pending, with the "
                             "event IDs it counted. The Decision Journal reviews a decision before and after.",
                             "En la Lente Analista, el laboratorio de hipótesis compara una medida de un equipo (presiones, "
                             "tiros, xG…) en dos ventanas y responde respaldada, no respaldada, no concluyente o pendiente, "
                             "con los IDs de eventos contados. El diario de decisiones revisa una decisión antes y después."),
    # pitch view
    "pitch.view": ("Pitch view", "Vista del campo"),
    "pitch.Static": ("Static", "Estática"),
    "pitch.Animated": ("Animated", "Animada"),
    "pitch.view_help": ("Static: the whole move with numbered steps. Animated: the move replayed step by step with the "
                        "chart's own Play / Pause / Restart and step slider; it starts at the selected action and "
                        "never moves the match clock.",
                        "Estática: la jugada completa con pasos numerados. Animada: la jugada paso a paso con los "
                        "controles del gráfico (Reproducir / Pausa / Reiniciar y deslizador); empieza en la acción "
                        "seleccionada y nunca mueve el reloj del partido."),
    "pitch.anim_note": ("The chart's controls replay this move only; the match clock does not move.",
                        "Los controles del gráfico repiten solo esta jugada; el reloj del partido no se mueve."),
    "pitch.reduced": ("reduced motion: steps shown in place", "movimiento reducido: pasos sin desplazamiento"),
    # xG evolution
    "xg.title": ("📈 xG evolution", "📈 Evolución del xG"),
    "xg.caption": ("Cumulative synthetic xG per team up to the replay clock (a transparent distance/angle formula in "
                   "the synthetic dataset, not a provider model). ⚽ marks goals.",
                   "xG sintético acumulado por equipo hasta el reloj de la repetición (fórmula transparente de distancia y "
                   "ángulo del conjunto de datos sintético, no un modelo de proveedor). ⚽ marca los goles."),
    "xg.total": ("{team}: {xg} xG from {shots} shots", "{team}: {xg} xG en {shots} tiros"),
    # layout editor
    "layout.button": ("Layout", "Diseño"),
    "layout.title": ("Analyst workspace layout", "Diseño del espacio del analista"),
    "layout.left": ("Left column", "Columna izquierda"),
    "layout.right": ("Right column", "Columna derecha"),
    "layout.help": ("Choose which panels sit beside the workspace. Saved for this session only.",
                    "Elige qué paneles van junto al espacio de trabajo. Se guarda solo en esta sesión."),
    "layout.reset": ("Reset layout", "Restablecer diseño"),
    "panel.log": ("Key moments log", "Registro de momentos clave"),
    "panel.explain": ("Explanation", "Explicación"),
    "panel.notes": ("Observation notes", "Notas de observación"),
    "panel.lab": ("Hypothesis Lab", "Laboratorio de hipótesis"),
    "panel.journal": ("Decision Journal", "Diario de decisiones"),
    "panel.agents": ("Agent architecture", "Arquitectura de agentes"),
    # Hypothesis Lab
    "lab.title": ("🧪 Tactical Hypothesis Lab", "🧪 Laboratorio de hipótesis tácticas"),
    "lab.sub": ("test a claim against two windows of recorded events", "contrasta una idea con dos ventanas de eventos"),
    "lab.team": ("Team", "Equipo"),
    "lab.measure": ("Measure", "Medida"),
    "lab.direction": ("Expected change", "Cambio esperado"),
    "lab.dir.higher": ("higher in B", "mayor en B"),
    "lab.dir.lower": ("lower in B", "menor en B"),
    "lab.window_a": ("Window A (minutes)", "Ventana A (minutos)"),
    "lab.window_b": ("Window B (minutes)", "Ventana B (minutos)"),
    "lab.statement": ("Hypothesis (optional wording)", "Hipótesis (texto opcional)"),
    "lab.test": ("Test hypothesis", "Probar hipótesis"),
    "lab.empty": ("No hypotheses tested yet in this session.", "Aún no has probado hipótesis en esta sesión."),
    "lab.future": ("Window B ends after the replay clock: move the clock forward to test it (no look-ahead).",
                   "La ventana B termina después del reloj: avanza la repetición para probarla (sin mirar al futuro)."),
    "lab.bad_windows": ("Each window needs a start before its end.", "Cada ventana necesita un inicio anterior a su final."),
    "lab.download": ("Download session records (JSON)", "Descargar registros de la sesión (JSON)"),
    "lab.session_note": ("Session only: nothing is stored on the server; download to keep a copy.",
                         "Solo en esta sesión: nada se guarda en el servidor; descarga una copia para conservarla."),
    "verdict.supported": ("Supported", "Respaldada"),
    "verdict.not_supported": ("Not supported", "No respaldada"),
    "verdict.inconclusive": ("Inconclusive", "No concluyente"),
    "verdict.pending": ("Pending", "Pendiente"),
    "lab.result": ("{a} → {b} ({delta}) · {n} events in evidence", "{a} → {b} ({delta}) · {n} eventos como evidencia"),
    "measure.pressures": ("Pressures applied", "Presiones realizadas"),
    "measure.shots": ("Shots", "Tiros"),
    "measure.xg": ("Synthetic xG", "xG sintético"),
    "measure.attacking": ("Actions in attacking zones", "Acciones en zonas de ataque"),
    "measure.pass_share": ("Pass share (%)", "Cuota de pases (%)"),
    "measure.box": ("Actions in the opponent's box", "Acciones en el área rival"),
    # Decision Journal
    "dj.title": ("📓 Decision Journal", "📓 Diario de decisiones"),
    "dj.sub": ("log a decision now, review its effect later", "registra una decisión ahora y revisa su efecto después"),
    "dj.kind": ("Decision", "Decisión"),
    "dj.kind.substitution": ("Substitution", "Cambio"),
    "dj.kind.press_higher": ("Press higher", "Presionar más arriba"),
    "dj.kind.drop_deeper": ("Drop deeper", "Replegarse"),
    "dj.kind.switch_flank": ("Attack the other flank", "Atacar por la otra banda"),
    "dj.kind.other": ("Other", "Otra"),
    "dj.rationale": ("Rationale", "Motivo"),
    "dj.expect": ("Expected effect on", "Efecto esperado en"),
    "dj.dir.higher": ("higher after", "mayor después"),
    "dj.dir.lower": ("lower after", "menor después"),
    "dj.review": ("Review after (minutes)", "Revisar tras (minutos)"),
    "dj.log": ("Log decision at {clock}", "Registrar decisión en el {clock}"),
    "dj.empty": ("No decisions logged yet in this session.", "Aún no hay decisiones en esta sesión."),
    "dj.pending": ("Review at {clock}: the replay has not reached the end of the review window.",
                   "Revisión en el {clock}: la repetición aún no ha llegado al final de la ventana."),
    "dj.compare": ("{before} before → {after} after", "{before} antes → {after} después"),
    "dj.caveat": ("Before/after comparison of recorded events only; it does not prove the decision caused the change.",
                  "Comparación antes/después de eventos registrados; no demuestra que la decisión causara el cambio."),
    # notes
    "notes.title": ("📝 Analyst notes", "📝 Notas del analista"),
    # agents
    "ag.title": ("🤖 Agent architecture", "🤖 Arquitectura de agentes"),
    "ag.sub": ("who did what for this moment", "quién hizo qué en este momento"),
    "ag.mode.offline": ("Deterministic mode (offline default): every step below is a Python rule, no model is called.",
                        "Modo determinista (por defecto, sin conexión): cada paso es una regla en Python; no se llama a "
                        "ningún modelo."),
    "ag.mode.online": ("Azure AI Foundry configured: the agents may draft wording with the model; every draft still "
                       "passes the EvidenceGuardrail or is replaced by the deterministic fallback.",
                       "Azure AI Foundry configurado: los agentes pueden redactar con el modelo; cada borrador pasa por "
                       "EvidenceGuardrail o se sustituye por la versión determinista."),
    "ag.run": ("Run agents for this moment", "Ejecutar agentes en este momento"),
    "ag.paused": ("Pause the replay to run the agents.", "Pausa la repetición para ejecutar los agentes."),
    "ag.trace": ("Agent trace", "Traza de agentes"),
    "ag.tool": ("tool", "herramienta"),
    "ag.verdict.pass": ("✓ passed", "✓ superado"),
    "ag.verdict.fail": ("✗ rejected", "✗ rechazado"),
    "ag.FanStoryAgent": ("Orchestrates the story tools (match read, story moments, fan explanation) into one "
                         "contextual summary for the moment.",
                         "Orquesta las herramientas de relato (lectura del partido, momentos, explicación para "
                         "aficionados) en un resumen del momento."),
    "ag.TacticalAnalystAgent": ("Evaluates the session's hypotheses and decisions and audits the raw events behind "
                                "every referenced metric.",
                                "Evalúa las hipótesis y decisiones de la sesión y audita los eventos de origen de cada "
                                "métrica citada."),
    "ag.EvidenceGuardrail": ("Deterministic validator: every number, clock and event ID in an output must trace back "
                             "to the snapshot and its raw event IDs, or the output is rejected.",
                             "Validador determinista: cada número, minuto e ID de evento de una salida debe remontarse "
                             "al estado del partido y a sus eventos de origen, o la salida se rechaza."),
    # capture
    "cap.title": ("🎬 ShiftLens Capture", "🎬 ShiftLens Capture"),
    "cap.badge": ("Planned · Future Architecture", "Planificado · Arquitectura futura"),
    "cap.intro": ("A roadmap space: how ShiftLens could turn authorized match video into evidence-backed events, with "
                  "people in charge of every accepted event. Nothing here processes video today.",
                  "Un espacio de hoja de ruta: cómo ShiftLens podría convertir vídeo autorizado en eventos con evidencia, "
                  "con personas a cargo de cada evento aceptado. Hoy nada aquí procesa vídeo."),
    "cap.flow": ("Product flow", "Flujo del producto"),
    "cap.step1": ("Authorized video", "Vídeo autorizado"),
    "cap.step1.d": ("Club-owned or licensed footage, with rights recorded per match.",
                    "Imágenes propias del club o con licencia, con los derechos registrados por partido."),
    "cap.step2": ("Manual annotation", "Anotación manual"),
    "cap.step2.d": ("Analysts tag events on a clock synced to the video.",
                    "Los analistas etiquetan eventos con un reloj sincronizado con el vídeo."),
    "cap.step3": ("AI-assisted proposals", "Propuestas asistidas por IA"),
    "cap.step3.d": ("A model proposes candidate events with confidence and the frame they come from.",
                    "Un modelo propone eventos candidatos con su confianza y el fotograma de origen."),
    "cap.step4": ("Human-in-the-loop review", "Revisión con persona en el circuito"),
    "cap.step4.d": ("Every proposal is accepted, edited or rejected by a person before it becomes data.",
                    "Cada propuesta se acepta, edita o rechaza por una persona antes de convertirse en dato."),
    "cap.mock": ("Interactive wireframe", "Wireframe interactivo"),
    "cap.mock_note": ("Mockup with invented proposals for the synthetic match. Upload is disabled; nothing is stored.",
                      "Maqueta con propuestas inventadas para el partido sintético. La subida está desactivada; nada se guarda."),
    "cap.upload": ("Match video (disabled in this demo)", "Vídeo del partido (desactivado en esta demo)"),
    "cap.sync": ("Video time ↔ match clock", "Tiempo de vídeo ↔ reloj del partido"),
    "cap.offset": ("Kick-off at video time (s)", "Saque inicial en el tiempo de vídeo (s)"),
    "cap.video_t": ("Video time (s)", "Tiempo de vídeo (s)"),
    "cap.synced": ("Video {video} ↔ match clock {clock}", "Vídeo {video} ↔ reloj del partido {clock}"),
    "cap.queue": ("Validation queue", "Cola de validación"),
    "cap.accept": ("Accept", "Aceptar"),
    "cap.reject": ("Reject", "Rechazar"),
    "cap.status.pending": ("pending review", "pendiente de revisión"),
    "cap.status.accepted": ("accepted by reviewer", "aceptada por revisor"),
    "cap.status.rejected": ("rejected by reviewer", "rechazada por revisor"),
    "cap.reset": ("Reset mock queue", "Reiniciar cola de la maqueta"),
    "cap.contract": ("Planned data contract", "Contrato de datos planificado"),
    "cap.contract_note": ("Draft schema for the roadmap; not implemented. Accepted events would use the same event "
                          "fields as today's match file, plus provenance.",
                          "Esquema borrador de la hoja de ruta; no implementado. Los eventos aceptados usarían los mismos "
                          "campos que el archivo de partido actual, más su procedencia."),
}


def lang() -> str:
    value = st.session_state.get("lang", "en")
    return value if value in LANGS else "en"


def t(key: str, **kw) -> str:
    if key not in CATALOG:
        raise KeyError(f"i18n: unknown key '{key}'")
    text = CATALOG[key][LANGS.index(lang())] or CATALOG[key][0]
    return text.format(**kw) if kw else text


def render_switcher(container) -> None:
    """EN / ES control; a click that deselects keeps the current language."""
    if st.session_state.get("lang") not in LANGS:
        st.session_state["lang"] = "en"
    st.session_state["_lang_last"] = st.session_state["lang"]
    container.segmented_control(t("lang.label"), LANGS, key="lang", format_func=LANG_LABELS.get,
                                label_visibility="collapsed", on_change=_keep_lang)


def _keep_lang() -> None:
    if st.session_state.get("lang") not in LANGS:
        st.session_state["lang"] = st.session_state.get("_lang_last", "en")
    st.session_state["_lang_last"] = st.session_state["lang"]
