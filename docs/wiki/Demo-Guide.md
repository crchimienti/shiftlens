# Demo guide (about 2 minutes)

**Setup:** run `.venv\Scripts\python -m streamlit run streamlit_app.py` and open http://localhost:8501. Choose
⋮ → Settings → Theme → Dark for the hero look. No network or keys are needed.

| Step | Click | Say |
|---|---|---|
| 1 | — | "ShiftLens turns match events into explainable intelligence: Python owns the numbers, and every explanation is checked." |
| 2 | **Fan Lens**, **Play**, then **Momentum swing (10:10)** | "This is a synthetic, Premier League-style match with fictional clubs. Match Story says the game is shifting; the pitch shows the move behind it." |
| 3 | (paused) | "Live Story explains this moment by itself, validated ✓. Data limits are one line below." |
| 4 | **Goal moment (20:21)** | "⚽ GOAL!, with the scorer and who set it up, straight from the event chain. The lineups tab shows the badges." |
| 5 | **Analyst Lens** | "The tactical desk: shot map, pass network, a team or player activity map, proxy leaders and the tide of the game." |
| 6 | **Explain this moment** | "A tactical read: who carries the threat, who keeps the ball, and a coaching takeaway, with every number referenced." |
| 7 | Traceability | "Formula, window and source events behind every number. Nothing is made up." |
| 8 | **Reset** | "Deterministic: the same second always gives the same numbers." |

## Talking points
- **Synthetic:** fictional clubs and players; schematic positions; proxies, not xG.
- **Deterministic:** metrics are computed in Python from the events and a versioned config.
- **Validated:** any explanation that fails the checks is replaced by the deterministic fallback.
- **Optional model path:** wired to Azure OpenAI / Microsoft Foundry, but not validated live, so don't claim it ran.

## Don't say
- "official data", "real clubs or players", "partner app", "real-time feed" or "production deployment"

Detailed script: [docs/demo_runbook.md](../demo_runbook.md).
