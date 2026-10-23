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
| **Layout** | key move · stats & pressure · lineups as tabs; Match Story and Live Story in the right rail | tactical workspace (move · maps · stats & tide · proxy leaders · lineups); key moments log, explanation and timestamped notes in the right rail |
| **Evidence** | one click away | summary first, full evidence table on demand |

## Architecture
```
synthetic match JSON ──► validator (schema + rules + fingerprint)
        │
        ▼
ReplayState (play / pause / seek / speed) ──► Replay.snapshot(t) = 8 deterministic metrics at second t
        │
        ├──► story & proxies (match read, key moments, shot quality, chance creation, progression, zone threat)
        ├──► explanation layer: request → deterministic fallback (default) or optional model
        │        → strict schema + grounding validator → one retry → fallback → cache
        └──► Streamlit UI: Fan Lens / Analyst Lens, pitch, tide, lineups, traceability
```
- **Offline-first:** the default path needs no network and no keys.
- **Optional model path:** Azure OpenAI chat completions, which can be managed in Microsoft Foundry. Its output
  is untrusted until it passes the same validator. **This path has not been validated against a live
  deployment**, and nothing in the demo was produced by a model.
- More: [docs/wiki/Architecture.md](docs/wiki/Architecture.md) ·
  [docs/architecture.md](docs/architecture.md) · [docs/methods.md](docs/methods.md)

## Synthetic data
`data/match_demo.json` is a synthetic 22-minute match: Northbridge FC 2–1 Harbor City. It has 104 events
in 26 sequences, each event carrying a zone, a lane and a sequence id. The storyline (control, goal,
equaliser against the run of play, pressure, late winner) was designed by hand. Positions on the pitch are
schematic (zone × lane), not tracking coordinates. Every advanced number is a documented synthetic proxy,
**not xG, xA or xT**. Details: [docs/wiki/Data-Model.md](docs/wiki/Data-Model.md).

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
1. **Fan Lens → Momentum swing (10:10):** the Match Story calls a *shifting* game, and the pitch shows the move behind it.
2. **Pause:** the Live Story explains the moment by itself, validated ✓, with data limits in one line.
3. **Goal moment (20:21):** "⚽ GOAL!" with the scorer and who set it up. The lineups tab shows the badges.
4. **Analyst Lens:** the tactical workspace (shot map, pass network, activity map), proxy leaders, the tide of
   the game, and a tactical read ending in a coaching takeaway.
5. **Traceability:** the formula, window and source events behind every number.

Full script: [docs/wiki/Demo-Guide.md](docs/wiki/Demo-Guide.md) · [docs/demo_runbook.md](docs/demo_runbook.md)

## Repository structure
```
streamlit_app.py      entry point (UI; `python streamlit_app.py` = CLI dataset check)
matchpulse/           validator · metrics · replay · story · analytics · explain · foundry_client · pitch · lineups · ui
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
296 tests cover:
- **Data:** dataset rules, determinism and the fingerprint.
- **Metrics and proxies:** every metric and the synthetic proxies.
- **Replay:** speed and state handling.
- **Explanations:**
  - Fan Lens and Analyst Lens explanations at every second of the match
  - the grounding validator: invented numbers, swapped team values, future events
  - the optional model path with mocks: retry, fallback, timeouts, cache
- **UI:** flows through Streamlit's test runner.

`python streamlit_app.py` prints the dataset fingerprint. Methods and limits:
[docs/methods.md](docs/methods.md).

## Roadmap
- **Live model verification:** test the optional Azure OpenAI / Microsoft Foundry path against a real deployment.
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
- Pass share is not possession, and the danger index and proxies are not xG, xA or xT.
- Momentum depends on its time window.
- The grounding validator is deterministic text checking, not language understanding.

## Technology & license
- **Stack:** Python, Streamlit, Plotly, jsonschema.
- **Development:** built with Claude Code (Anthropic) as the AI coding assistant.
- **Microsoft:** an optional Azure OpenAI / Microsoft Foundry integration path (not validated live). No Azure
  hosting, databases, Entra ID, Key Vault or agents are used.
- **Brand assets:** the ShiftLens logo files were created specifically for ShiftLens using an AI-assisted design
  workflow. They use no third-party, club, league or broadcaster branding. No exclusive copyright is claimed over
  purely AI-generated elements.
- **License:** MIT, see [LICENSE](LICENSE). Contributions: [CONTRIBUTING.md](CONTRIBUTING.md).
