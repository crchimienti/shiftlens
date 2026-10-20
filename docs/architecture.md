# ShiftLens architecture

ShiftLens turns a synthetic Premier League-style match into explainable, audience-aware match
intelligence: turning points, pressure swings and territorial control, told for fans (Fan Lens) and
for studio and broadcast use (Analyst Lens). No real Premier League data, clubs or players are used.

The UI keeps a sticky control bar using isolated CSS: `position: sticky` on the layout wrapper of a keyed
container, selected with `:has()`, which needs a current Chromium, Safari or Firefox. Otherwise the bar simply scrolls.
Compact-on-scroll uses a CSS scroll-driven animation on a named timeline declared on Streamlit's page scroller
(Chromium only); other browsers keep the full-size bar.

It is a local, single-process Streamlit app running a simulated replay. There is no live feed, no
production ingestion, no server-side database, no background workers and no cloud dependency. The
optional model call is the only network path, and the app works without it.

## Components

| Component | File | Responsibility |
|---|---|---|
| Data contract | `config/match_schema.json`, `matchpulse/validator.py` | Load the synthetic match JSON, validate schema and cross-field rules, normalize, fingerprint (SHA-256) |
| Metrics engine | `matchpulse/metrics.py`, `config/metrics_config.json` | 8 deterministic metrics at any clock second, each with traceability fields |
| Replay | `matchpulse/replay.py` | Play / pause / reset / seek state, one cached snapshot per second, demo moments |
| Explanation layer | `matchpulse/explain.py`, `config/explanation_schema.json` | Build the request, validate output, deterministic fallback, one retry, cache, traceability rows |
| Optional model | `matchpulse/foundry_client.py` | Microsoft Foundry / Azure OpenAI chat completions over HTTPS (stdlib only), structured output, evidence package; off by default |
| Analytics proxies | `matchpulse/analytics.py` | Shot Quality / Chance Creation / Prevented Danger proxies, lineup badges, zone activity, defensive actions, pass links, Analyst map figures |
| Brand & themes | `static/brand/`, `.streamlit/config.toml`, `ui.THEMES` | Official logo files served unchanged (static serving) and cropped with CSS; native light/dark theme config; small isolated CSS for panels |
| Story & lineups | `matchpulse/story.py`, `matchpulse/lineups.py`, `config/lineups.json` | Replay speed steps, factual story feed, card counts, event → move focus; synthetic presentation-only lineups and formations |
| Presentation | `matchpulse/presentation.py`, `matchpulse/pitch.py` | Plain-language labels, match-summary counts, schematic pitch positions (zone × lane), key-move chain and stats, Plotly figures. No new metrics |
| UI | `matchpulse/ui.py`, `streamlit_app.py` | Single page: scoreboard + summary, controls, KPIs, pressure, territory, key move on the pitch, explanation, event list, traceability (Fan Lens: behind an expander) |

`matchpulse/` modules other than `ui.py` have no Streamlit dependency and are unit-tested directly.

## Data flow

```
data/match_demo.json ──► validator: schema + rules ──► normalized match (fingerprinted)
                                                              │
config/metrics_config.json ──► validate_config ───────────────┤
                                                              ▼
                 ReplayState.clock (t) ──► Replay.snapshot(t) = compute_metrics(match, config, t)
                                              + events up to t (cached per second)
                                                              │
                         ┌────────────────────────────────────┼─────────────────────┐
                         ▼                                    ▼                     ▼
                  KPIs, momentum, territory,          Traceability panel     Explain (paused only)
                  sequences, event list               (from metric outputs)  build_request(snapshot, mode)
                                                                                    ▼
                                                                           cached_explain → UI
```

The clock is simulated: Play advances 10 simulated seconds per real second using Streamlit's
`st.fragment(run_every=1s)`, registered only while playing. The same second always produces the
same snapshot.

## Explanation path

```
Explain pressed ──► playing? ──yes──► message: "Pause the replay…" (nothing generated)
                       │ no
                       ▼
               cache hit for (match_id, second, mode, version)? ──yes──► show cached result
                       │ no
                       ▼
        generator configured? ──no──► deterministic fallback ──► validate ──► cache ──► show
                       │ yes
                       ▼
  Foundry answer (strict JSON Schema) ──► validate ──ok──► cache ──► show (source: Foundry)
                           │ fail / network error
                           ▼
        invalid answer: retry once with the errors ──ok──► cache ──► show
        timeout / auth / network / HTTP error: no retry
                           │ fail
                           ▼
                deterministic fallback ──► validate ──► cache ──► show
```

- **Offline-first.** With `MATCHPULSE_OFFLINE` unset or `1` (the default), no generator is created
  and every explanation is the deterministic fallback. No network access is attempted.
- **Optional Microsoft Foundry / Azure OpenAI.** Enabled only when `MATCHPULSE_OFFLINE=0` and the four
  `AZURE_OPENAI_*` connection variables are set (shell or a local `.env`, loaded by `python-dotenv`).
  Timeout `AZURE_OPENAI_TIMEOUT_SECONDS` (default 15 s). The client sends an **evidence package** (lens, minute,
  clock, teams, score, metric snapshot, last 12 events, data sufficiency, limitations) and requires a
  strict JSON Schema response. Foundry writes the language; Python owns the numbers.
  **Not validated against a live deployment**: covered by mocked tests and a browser test against a
  local mock endpoint. It is considered validated only after a real deployment test.
- **Isolation.** All Azure-specific code is in `foundry_client.py`. The UI only calls
  `online_generator_from_env()`; metrics and replay never touch it, so an online failure cannot affect them.
- **Validation.** See [methods.md](methods.md#explanation-contract). The deterministic fallback goes
  through the same validator as model output.
- **Cache.** In-memory, per browser session, keyed by `(match_id, second, mode, explanation_version)`.
  Repeated presses do not call the model again. Changing mode is a separate entry. Reset clears it.
  No browser storage is used.

## Traceability path

Each metric output carries `window`, `formula_version`, `config_version` and `source_event_ids`.
The Traceability panel renders them directly, with more columns in Analyst Lens. Each explanation
key point carries `metric_refs` and `event_refs`, which are validated against the same snapshot. The
status line shows the source (deterministic fallback, Foundry, or cached), the validated status, the number
of metric and event references, attempts and latency.

## Demo moments

Three buttons jump to known timestamps in the demo match and pause there: Momentum swing (10:10),
Goal moment (20:21) and Late pressure (19:40). They only call `ReplayState.jump_to` and clear any
explanation already on screen. Metrics are unchanged, and tests check that each moment shows what its
label claims. The match has no genuine comeback, so the third button is "Late pressure".

## Non-goals for the MVP

Real match data or live feeds · real-time ingestion · predictions, betting or win probabilities ·
xG or tracking data · free-form chat or continuous narration · accounts, auth or multi-user state ·
databases · cloud hosting (App Service, Container Apps, AKS) · agents or multi-agent orchestration ·
Fabric / Eventstream · charts (planned, see the [README roadmap](../README.md#roadmap)).
