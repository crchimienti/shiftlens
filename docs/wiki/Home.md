# ShiftLens

**Evidence-backed match intelligence for every turning point.**

ShiftLens is a synthetic-data hackathon demo. It shows how football match events can be turned into
explainable, audience-aware intelligence for studio, streaming and fan experiences. Every number is computed
deterministically in Python, and every explanation is grounded in those numbers and validated before it is shown.

> All match data is synthetic: a fictional Premier League-style scenario. No real clubs, players, competition
> data or licensed assets are used.

## Pages
| Page | What it covers |
|---|---|
| [Product vision](Product-Vision.md) | The problem, the audiences, and why Fan Lens and Analyst Lens exist |
| [Architecture](Architecture.md) | Components, data flow, offline-first design, optional model path |
| [Data model](Data-Model.md) | The synthetic match format, schema, rules and provenance |
| [Synthetic replay engine](Synthetic-Replay-Engine.md) | Replay state, speed, snapshots, metrics and proxies |
| [Explainability approach](Explainability.md) | Grounding, validation, deterministic fallback, traceability |
| [Future real-data integrations](Future-Real-Data-Integrations.md) | How licensed data could plug in, and what it would need |
| [Demo guide](Demo-Guide.md) | A 2-minute walkthrough and talking points |

## The five-stage chain
**Ingest → Interpret → Explain → Render → Personalize.** The app header shows the same chain, and each page
above maps to one or more stages.

## Quick start
```bash
python -m venv .venv && .venv\Scripts\python -m pip install -r requirements.txt
```
```bash
.venv\Scripts\python -m streamlit run streamlit_app.py
```
