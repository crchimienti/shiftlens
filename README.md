# ShiftLens

**Evidence-backed match intelligence for every turning point.**

ShiftLens turns football match events into explainable, audience-aware intelligence for studio, streaming
and fan experiences. A synthetic, football-realistic match plays as a simulated replay. Python computes
every number deterministically, and every explanation is validated against those numbers before it
reaches the screen.

> **Synthetic-data hackathon demo.** The match, clubs and players are fictional: a Premier League-style
> broadcast scenario built for this project. No real match data, clubs, players, competition data or
> licensed assets are used. ShiftLens is not affiliated with or endorsed by the Premier League.

## Live demo
[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://shiftlens.streamlit.app/)

**https://shiftlens.streamlit.app/**: the synthetic demo, no sign-in or keys needed.

## Overview
- **Ingest:** a versioned synthetic match file, schema-validated and fingerprinted.
- **Interpret:** 8 deterministic metrics (pressure/momentum, pass share, danger index, territory, key moves,
  turning point, evidence level, score), a match-state read, and transparent synthetic proxies.
- **Explain:** grounded, validated explanations, plus a live match story.
- **Render:** a pressure tide, a schematic pitch, lineups, analyst maps and full traceability.
- **Personalize:** **Fan Lens** for viewers and **Analyst Lens** for the studio desk.

The app header shows the same five-stage chain.

## Why it matters
A match's story lives in its shifts: who has the pressure, where the game is played, and when it turned.
Broadcast stats usually arrive as bare numbers with no explanation, and AI summaries can invent figures.
ShiftLens keeps numbers and language separate: **Python owns the numbers; explanations only rephrase them**,
cite the metrics and events behind each claim, and are rejected if they don't check out.

## Fan Lens vs Analyst Lens
| | 📺 Fan Lens: broadcaster companion | 📋 Analyst Lens: tactical desk |
|---|---|---|
| **For** | fans, viewers, presenters | analysts, coaches, scouts, studio producers |
| **First on screen** | the key move on the pitch, compact stats, pressure | tactical workspace and proxy leaders |
| **Story** | Match Story (who presses, has the ball, connects, threatens; how the game evolved) and Live Story (explains each paused moment) | tactical read with a coaching takeaway, plus a key-moments log |
| **Visuals** | clean pitch, goal emphasis, lineups one tab away | five-lane tactical board with threat-coloured paths, activity map (team or player), threat-coloured pass network, shot map, defensive actions |
| **Layout** | key move · stats & pressure · xG evolution · lineups as tabs; Match Story, Live Story and the agent trace in the right rail | three columns: tactical workspace (move · maps · stats, tide & xG · proxy leaders · lineups) in the centre; key moments log, explanation, notes, **Hypothesis Lab**, **Decision Journal** and agent trace either side, placed with the layout editor |
| **Evidence** | one click away | summary first, full evidence table on demand |

The app opens on **Home**: the logo, the claim *From moments to evidence. From evidence to insight.*, quick starts
to Fan Lens, Analyst Lens and Capture, and a three-step **Quick tour** (replay controls, evidence trace, hypothesis
testing) whose *Try it* buttons open the right lens at the right moment. In both lenses the pitch can switch between
**Static** and **Animated**: the selected move replayed step by step with the chart's own Play / Pause / Restart and
step slider (it never moves the match clock; with the browser's reduced-motion setting, steps are shown in place).

Both lenses switch between **English and Spanish** (navigation, controls, section titles and the new spaces;
generated narratives and chart text stay English in this version). A third space, **🎬 ShiftLens Capture**, is
badged *Planned · Future Architecture*: the product flow (authorized video → manual annotation → AI-assisted
proposals → human-in-the-loop review), an interactive wireframe (disabled upload, video-time ↔ match-clock sync,
validation queue with invented proposals) and the planned data contract (matches, videos, events, reviews). It
processes nothing today.

Hypotheses, decisions and notes live in the browser session only (JSON download to keep them); nothing is written to
the server.

## Architecture
```
synthetic match JSON ──► validator (schema + rules + fingerprint)
        │
        ▼
ReplayState (play / pause / seek / speed) ──► Replay.snapshot(t) = 8 deterministic metrics at second t
        │
        ├──► story & proxies (match read, key moments, shot quality, chance creation, progression, zone threat)
        ├──► Hypothesis Lab / Decision Journal: window comparisons over recorded events (no look-ahead)
        ├──► agents: FanStoryAgent · TacticalAnalystAgent → EvidenceGuardrail (deterministic validator)
        │        → explanation layer: deterministic fallback (default) or optional Azure AI Foundry draft
        │        → strict schema + grounding validator → one retry → fallback → cache
        └──► Streamlit UI (EN / ES): Fan Lens / Analyst Lens / Capture (planned), pitch, tide, xG, traceability
```
- **Offline-first:** the default path needs no network and no keys.
- **Optional model path:** Azure OpenAI chat completions, which can be managed in Microsoft Foundry. Its output
  is untrusted until it passes the same validator. **This path has not been validated against a live
  deployment**, and nothing in the demo was produced by a model.
## Agent architecture (Microsoft AI / Azure AI Foundry-aligned)
`matchpulse/agents.py` organises the explanation work as three named agents with explicit tools and a visible trace
(the **🤖 Agent architecture** panel shows who did what for the paused second):

| Agent | Tools it orchestrates | What it returns |
|---|---|---|
| **FanStoryAgent** | `match_read`, `story_moments`, fan explanation | one contextual summary of the moment for the Fan Lens |
| **TacticalAnalystAgent** | Hypothesis Lab evaluation, Decision Journal review, analyst explanation, evidence audit | verdicts, the analyst read and the source events behind every referenced metric |
| **EvidenceGuardrail** | `validate_explanation`, recompute-from-event-IDs, event-reference check | pass / reject; rejected drafts are retried once, then replaced by the deterministic fallback |

- **Deterministic by default.** Offline, every tool is a Python rule and no model is called; the UI says
  "Deterministic mode". The guardrail is a validator, not AI.
- **Optional Azure AI Foundry path.** When `MATCHPULSE_OFFLINE=0` and the Azure variables are set, agents may draft
  wording with the model (`foundry_client.py`); every draft still has to pass the EvidenceGuardrail, which checks each
  number, clock and event ID against the snapshot and recomputes lab values from their raw event IDs.
- **No look-ahead.** Agents only see events up to the replay clock; lab and journal windows that end later are pending.
- More: [docs/wiki/Architecture.md](docs/wiki/Architecture.md) ·
  [docs/architecture.md](docs/architecture.md) · [docs/methods.md](docs/methods.md)

## Synthetic data
`data/match_demo.json` is a synthetic 90-minute match between fictional clubs: Northbridge FC 2–1 Harbor
City. It has about 1,000 events (passes, carries, shots, pressures, saves…) in 200+ sequences, built by a seeded
generator (`python tools/build_match.py`) from a scripted storyline: Northbridge control and lead (23'), Harbor City
equalise from a corner (38') and push after the break, Northbridge's late winner (84'). Each event carries
synthetic x/y coordinates (consistent with its zone and lane), and shots carry a **synthetic xG** from a published
distance/angle formula, not a provider model. Squads are 16 fictional players per club. Nothing is tracking data, and
the other advanced numbers are documented synthetic proxies, **not xA or xT**. Details: [docs/wiki/Data-Model.md](docs/wiki/Data-Model.md).

## Quick start
Python 3.11+.
```bash
python -m venv .venv && .venv\Scripts\python -m pip install -r requirements.txt
```
```bash
.venv\Scripts\python -m streamlit run streamlit_app.py
```
Then open http://localhost:8501. On macOS/Linux use `.venv/bin/python`. To pick a theme, open ⋮ → Settings →
Theme; dark is the hero look. No `.env` is needed for the demo. Copy `.env.example` only if you want to try the
optional model path.

## Demo flow (about 2 minutes)
1. **Fan Lens → Momentum swing (16:40):** the Match Story calls a *shifting* game, and the pitch shows the move behind it.
2. **Pause:** the Live Story explains the moment by itself, validated ✓, with data limits in one line.
3. **Goal moment (84:20):** "⚽ GOAL!" with the scorer and who set it up. The lineups tab shows the badges.
4. **Analyst Lens:** the tactical workspace (shot map, pass network, activity map), proxy leaders, the tide of
   the game, and a tactical read ending in a coaching takeaway.
5. **Traceability:** the formula, window and source events behind every number.

Full script: [docs/wiki/Demo-Guide.md](docs/wiki/Demo-Guide.md) · [docs/demo_runbook.md](docs/demo_runbook.md)

## Repository structure
```
streamlit_app.py      entry point (UI; `python streamlit_app.py` = CLI dataset check)
matchpulse/           validator · metrics · replay · story · analytics · explain · foundry_client · pitch · lineups ·
                      agents · lab · xg · anim · i18n · ui · lab_ui · home_ui · capture_ui
tools/                build_match.py (seeded generator of the synthetic 90-minute match)
config/               match / explanation schemas · metrics config · synthetic lineups
data/                 match_demo.json (synthetic)
docs/                 methods · architecture · data contract · demo runbook · wiki/ (long-form pages) · assets/
static/brand/         ShiftLens logo files (served by Streamlit static serving)
logos-dashboard-examples/  original brand exports; tests check static/brand/ matches them
.streamlit/           light / dark theme config
tests/                pytest suite
```
The Python package and `MATCHPULSE_*` environment variables keep the project's original internal name.

## Validation & testing
```bash
.venv\Scripts\python -m pytest
```
343 tests cover:
- **Data:** dataset rules, determinism and the fingerprint.
- **Metrics and proxies:** every metric and the synthetic proxies.
- **Replay:** speed and state handling.
- **Explanations:**
  - Fan Lens and Analyst Lens explanations at every second of the match
  - the grounding validator: invented numbers, swapped team values, future events
  - the optional model path with mocks: retry, fallback, timeouts, cache
- **Hackathon build:** the seeded 90-minute generator, Hypothesis Lab / Decision Journal verdicts (no look-ahead),
  agent traces and the EvidenceGuardrail rejecting tampered numbers, future events and invented model drafts, the
  EN/ES catalog, the layout editor, the Capture wireframe, the animated player (paths, mirroring, reduced
  motion), Home and the Quick tour.
- **UI:** flows through Streamlit's test runner.

`python streamlit_app.py` prints the dataset fingerprint. Methods and limits:
[docs/methods.md](docs/methods.md).

## Roadmap
- **Live model verification:** test the optional Azure OpenAI / Microsoft Foundry path against a real deployment.
- **ShiftLens Capture (planned):** authorized video, manual annotation and AI-assisted event proposals with
  human-in-the-loop review, feeding the same event contract. Shown as a badged wireframe in the app today.
- **Richer real-data deployments:** licensed event and tracking databases or APIs could unlock fuller real-data
  versions, adding real xG, player tracking and fuller event streams through a separate adapter. The synthetic
  demo stays the default. See [docs/wiki/Future-Real-Data-Integrations.md](docs/wiki/Future-Real-Data-Integrations.md).
- **Product:**
  - card events in the data model
  - clickable charts
  - a precomputed match timeline for smoother autoplay
  - a mobile layout

## Limitations
- A single synthetic match, shown as a simulated replay; not a live feed or a production deployment.
- Pass share is not possession, and the danger index and proxies are not xG, xA or xT. The xG field is synthetic
  (a published distance/angle formula on invented coordinates), not a provider model.
- Spanish covers navigation, controls and the new spaces; generated narratives and chart text are English.
- Momentum depends on its time window.
- The grounding validator is deterministic text checking, not language understanding.

## Technology & license
- **Stack:** Python, Streamlit, Plotly, jsonschema.
- **Development:** built with Claude Code (Anthropic) as the AI coding assistant.
- **Microsoft:** an optional Azure OpenAI / Microsoft Foundry integration path (not validated live). No Azure
  hosting, databases, Entra ID, Key Vault or agents are used.
- **Goal sound (optional, off by default):** a 1.5 s excerpt of a crowd-cheering clip from Pixabay
  (Pixabay Content License), trimmed and faded; it plays only when switched on.
- **Brand assets:** the ShiftLens logo files were created specifically for ShiftLens using an AI-assisted design
  workflow. They use no third-party, club, league or broadcaster branding. No exclusive copyright is claimed over
  purely AI-generated elements.
- **License:** MIT, see [LICENSE](LICENSE). Contributions: [CONTRIBUTING.md](CONTRIBUTING.md).
