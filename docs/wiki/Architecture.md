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
| Render | `matchpulse/ui.py`, `pitch.py`, `lineups.py`, `presentation.py` | Fan Lens / Analyst Lens layouts, pitch, tide, lineups, labels |
| Config | `config/*.json`, `.streamlit/config.toml` | Schemas, metric weights and windows, synthetic lineups, light/dark themes |

## Data flow
```
data/match_demo.json ─► validator ─► normalized match ─► Replay.snapshot(t) ─► metrics + story + proxies
                                                                         │
                                       Explain (paused only) ◄───────────┤
                                       request → fallback | model → validate → retry → fallback → cache
                                                                         ▼
                                                     Streamlit UI (Fan Lens | Analyst Lens)
```

## Key design choices
- **Determinism:** snapshots depend only on (dataset, config, second), so they are cached and reproducible.
- **Autoplay:** a Streamlit fragment with `run_every=1s`, registered only while playing. The speed setting changes
  how many simulated seconds each tick advances (5 / 10 / 15 / 20). There are no threads and no async code.
- **Optional model path:** enabled only by explicit environment settings. It sends an evidence package (no
  hidden data), requires a strict JSON schema, and then runs the same validator as the fallback. Timeouts and
  auth/network errors fall back at once; invalid answers get one retry. **Not validated against a live deployment.**
- **Isolation:** no external provider code is imported by the app. Any future real-data adapter must sit behind
  an explicit opt-in flag that defaults to the synthetic demo.

## Further reading
[docs/architecture.md](../architecture.md) (detailed flow diagrams) · [docs/methods.md](../methods.md) (every formula)
