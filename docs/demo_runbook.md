# ShiftLens demo runbook (90–120 s)

ShiftLens demonstrates how synthetic Premier League-style match events can be turned into explainable,
audience-aware football intelligence for studio, streaming, and fan experiences.

**Before you start**
- Pick the theme: ⋮ → Settings → Theme. Use **Dark** for the hero Analyst Lens look, or **Light** for a bright room.
- Start offline (this is the safe path; it needs no network, keys or Wi-Fi):
  `.venv\Scripts\python -m streamlit run streamlit_app.py`
- Open http://localhost:8501, use a wide window, press **Reset**, select **Fan Lens**.

## Script

| Time | Click | Say |
|---|---|---|
| 0:00 | — | "ShiftLens: evidence-backed match intelligence for every turning point. It turns a Premier League-style match into explanations a studio can put on air and fans can follow on a second screen, and every number can be traced." |
| 0:10 | **Play** | "This is **synthetic** data: a football-realistic 22-minute match we designed as a Premier League-style broadcast scenario, with fictional clubs and players. No real Premier League data, clubs or players. This is a simulated replay, not a live feed." |
| 0:20 | **Explain this moment** (while playing) | "Explanations only run while paused, so nothing is narrated while play is running." |
| 0:25 | **Pause** | "Every metric is computed in Python, **deterministically**: same second, same numbers, every time." |
| 0:30 | **Momentum swing (10:10)** | "This jumps to the turning point: right after the equaliser, the pressure swung towards Harbor City. Territorial control shows where the game is being played." |
| 0:33 | Point at **📰 Match read** | "The match read calls the state of the game: here it is shifting, Harbor City on the front foot, Northbridge FC still with more of the ball." |
| 0:35 | **Explain this moment** | Read the Fan Lens headline and one key point. "Short and plain for fans and streaming viewers." |
| 0:50 | Point at the status line | "Source: deterministic fallback, validated ✓, with metric and event references and latency." |
| 0:55 | **Analyst Lens** → **Explain this moment** | "Analyst Lens is for the studio: each claim names the metric and events behind it, plus its limits, so a presenter can say it on air with confidence." |
| 1:05 | Tactical workspace tabs: **🥅 Shot map** → **🔗 Pass network** | "Shot Quality Index and the pass network are synthetic proxies built from zone, lane and the event chain. We say not xG, because it isn't." |
| 1:10 | Scroll to **Traceability** | "Formula version, config version, window and the exact source event IDs for each number." |
| 1:20 | Point at **Data limits** | "Pass share is not possession, danger is not xG, there are no predictions or betting advice." |
| 1:30 | **Late pressure (19:40)** → **Goal moment (20:21)** → **Explain this moment** | "Late pressure from Northbridge, then the winner. Same validation on every explanation." |
| 1:45 | **Reset** | "Reset clears the replay and the explanation cache." |

## What to say about the optional Foundry path
"There's an optional Microsoft Foundry / Azure OpenAI path. It receives an evidence package and must
answer in a strict JSON schema. Python owns the numbers. Any model output goes through the same validator: wrong
numbers, wrong team values, unknown metrics or future events get one retry, then we use
the deterministic fallback. It's off by default and **we have not validated it against a live
deployment**, so everything in this demo is the offline path."

## Fallback-safe path (no network)
- Keep `MATCHPULSE_OFFLINE` unset or `1`. The status line should read **deterministic fallback**.
- If the app misbehaves: **Reset**, then use the demo-moment buttons; they always pause at the same
  timestamps and show the same numbers.
- Pressing **Explain** twice at the same moment shows **cached** (no extra work).
- Never claim a Microsoft or Azure service ran live during the demo unless you have actually tested a real
  deployment. If you have, the status line will read **Foundry**.

## Foundry live verification
This is optional and manual. The path is **not validated** until these steps succeed against a real deployment.
1. Copy `.env.example` to `.env` (git-ignored). Set `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`,
   `AZURE_OPENAI_DEPLOYMENT` and `AZURE_OPENAI_API_VERSION` (`2024-10-21` or later for structured outputs).
   Never paste the key into chat, docs or screenshots.
2. Turn offline mode off: `MATCHPULSE_OFFLINE=0` in `.env`.
3. Launch: `.venv\Scripts\python -m streamlit run streamlit_app.py`.
4. Click **Momentum swing (10:10)**, select **Fan Lens**, then press **Explain this moment**.
5. Confirm the status line reads **Source: Foundry · grounded ✓ validated**. If it reads *deterministic
   fallback after N rejected online attempt(s)*, the call failed or was rejected: check the endpoint, key,
   deployment and API version.
6. Select **Analyst Lens** and press **Explain this moment** again. Confirm **Foundry** again.
7. Record, for each lens: source, latency, attempts (1 = accepted first time, 2 = retried), and whether it
   fell back. Press Explain once more and confirm **cached (Foundry)** with no new call.
8. For the main demo, switch back to offline if needed: `MATCHPULSE_OFFLINE=1`, then restart.
9. Only after steps 4–7 succeed, update the README validation status, with the date and API version.

## Do not say
- "Official Premier League data", "real clubs or players", or "Premier League partner app". The match and
  clubs are synthetic, and the project is not affiliated with the Premier League.
- "Real-time live feed" or "production deployment". It is a simulated replay running locally.
