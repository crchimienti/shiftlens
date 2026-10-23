# Synthetic replay engine

## Replay
- **State:** clock and playing flag, with play, pause, reset, seek and jump-to-moment controls.
- **Speed:** 0.5x / 1x / 1.5x / 2x advance the clock 5 / 10 / 15 / 20 simulated seconds per real second.
- **Snapshots:** `Replay.snapshot(t)` returns the events played so far and all metrics at second `t`. Snapshots are
  cached per second, so the same second always shows the same numbers, at any speed.

## The 8 core metrics
| Metric | In one line |
|---|---|
| Score | goals from goal events only |
| Pass share | each team's share of pass events in the last 5 minutes (not possession) |
| Danger index | sum of event-type × zone weights in the last 3 minutes (not xG) |
| Momentum / pressure | time-decayed weighted activity, home − away, scaled to −1…+1 |
| Territory | share of each team's actions in the attacking third or box |
| Key moves | top moves ranked by impact (summed action weights) |
| Turning point | the largest momentum swing above a threshold within 2 minutes |
| Evidence level | low / medium / high from the event count |

Every metric carries its window, formula version, config version and source event ids.

## Interpretation layers
- **Match read:** settling / controlled / pressing / building / shifting / chaotic / even, plus who presses,
  who has the ball, who connects better and who gets closer to goal.
- **Story so far:** goals with who set them up, chances with the goalkeeper who saved them, and the turning point.
- **Synthetic proxies (Analyst Lens):** Shot Quality Index, Chance Creation Index, Ball Progression,
  Prevented Danger and Zone Threat (a fixed 5 × 3 grid; threat gain = where the next team-mate action happens
  minus where this one did). These are transparent formulas over the event fields, never called xG, xA or xT.

Every formula and threshold: [docs/methods.md](../methods.md).
