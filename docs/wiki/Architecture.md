# Architecture

A local, single-process Streamlit app. There is no database, no background worker and no cloud dependency.
The optional model call is the only network path, and the app works without it.

## Components
| Layer | Module | Responsibility |
|---|---|---|
| Ingest | `matchpulse/validator.py` | Load the match JSON; schema and cross-field rules; normalize; SHA-256 fingerprint |
| Interpret | `matchpulse/metrics.py` | 8 deterministic metrics at any second, each with window, formula/config version and source events |
| Interpret | `matchpulse/story.py`, `matchpulse/analytics.py` | Match read, key moments, speed steps; synthetic proxies and analyst maps |
| Replay | `matchpulse/replay.py` | Play / pause / seek / speed state; one cached snapshot per second; demo moments |
| Explain | `matchpulse/explain.py` | Request building, deterministic fallback, strict validator, retry, cache, traceability rows |
| Explain (optional) | `matchpulse/foundry_client.py` | Azure OpenAI chat completions with structured output; off by default |
| Agents | `matchpulse/agents.py` | **FanStoryAgent** (story tools → contextual summary), **TacticalAnalystAgent** (hypothesis evaluation, decision review, evidence audit) and **EvidenceGuardrail** (deterministic validator: numbers, clocks and event IDs must trace to the snapshot; lab values recomputed from raw event IDs) |
| Analyse | `matchpulse/lab.py`, `matchpulse/xg.py` | Hypothesis Lab and Decision Journal window comparisons (no look-ahead); cumulative synthetic xG |
| Render | `matchpulse/ui.py`, `lab_ui.py`, `capture_ui.py`, `i18n.py`, `pitch.py`, `lineups.py`, `presentation.py` | Fan Lens / Analyst Lens (three-column workspace, layout editor) / Capture (planned wireframe), EN / ES labels, pitch, tide, xG, lineups |
| Data | `tools/build_match.py` | Seeded generator of the synthetic 90-minute match (byte-reproducible) |
| Config | `config/*.json`, `.streamlit/config.toml` | Schemas, metric weights and windows, synthetic lineups, light/dark themes |

## Data flow
```
data/match_demo.json ─► validator ─► normalized match ─► Replay.snapshot(t) ─► metrics + story + proxies
                                                                         │
                     FanStoryAgent | TacticalAnalystAgent (paused only) ◄┤ Hypothesis Lab · Decision Journal
                                       request → fallback | model draft
                                       → EvidenceGuardrail → retry → fallback → cache
                                                                         ▼
                                     Streamlit UI, EN / ES (Fan Lens | Analyst Lens | Capture · planned)
```

## Key design choices
- **Determinism:** snapshots depend only on (dataset, config, second), so they are cached and reproducible.
- **Autoplay:** a Streamlit fragment with `run_every=1s`, registered only while playing. The speed setting changes
  how many simulated seconds each tick advances (5 / 10 / 15 / 20 / 40). There are no threads and no async code.
- **Optional model path:** enabled only by explicit environment settings. It sends an evidence package (no
  hidden data), requires a strict JSON schema, and then runs the same validator as the fallback. Timeouts and
  auth/network errors fall back at once; invalid answers get one retry. **Not validated against a live deployment.**
- **Agents without overclaiming:** offline, every agent tool is a Python rule and the UI says "Deterministic
  mode"; a configured Azure AI Foundry model may only draft wording, which the EvidenceGuardrail still checks.
- **Session-only records:** hypotheses, decisions and notes stay in the browser session (JSON download).
- **Isolation:** no external provider code is imported by the app. Any future real-data adapter must sit behind
  an explicit opt-in flag that defaults to the synthetic demo.

## Further reading
[docs/architecture.md](../architecture.md) (detailed flow diagrams) · [docs/methods.md](../methods.md) (every formula)
