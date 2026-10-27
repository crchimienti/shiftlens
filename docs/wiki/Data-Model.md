# Data model

## The synthetic match
`data/match_demo.json` (schema version 1.1.0) is a synthetic, football-realistic 90-minute match:
**Northbridge FC 2–1 Harbor City**, with about 1,000 events in 200+ sequences across 2 halves and 16 players per
side (11 starters, 5 substitutes).

- **Fictional:** the clubs and players are invented, and any resemblance to real people or clubs is coincidental.
- **Scripted, then generated:** the storyline (Northbridge control and lead at 23', Harbor City equalise from a
  corner at 38' and press high after the break, Northbridge's late winner at 84') is scripted;
  `tools/build_match.py` fills the possessions in between from the recorded `seed`.
- **Reproducible:** the same seed rebuilds a byte-identical file (a test checks it); `python streamlit_app.py`
  prints its fingerprint.
- **Synthetic coordinates and xG:** x/y (0–100, acting team's frame) are invented positions consistent with each
  event's zone and lane; xG on shots is a transparent distance/angle formula. Neither is tracking or provider data.

## Event fields
| Field | Meaning |
|---|---|
| `event_id` | unique id |
| `minute`, `second`, `period` | match clock 0–90 (does not reset at half-time; period 2 starts at 45:00) |
| `team_id`, `player_id` | acting team and player (the player must belong to the team) |
| `type` | kickoff, pass, carry, dribble, cross, shot, goal, save, tackle, interception, clearance, foul, free_kick, corner, offside, pressure |
| `outcome` | complete, incomplete, saved, off_target, blocked, won, lost, success, fail |
| `zone` | own_box, defensive_third, middle_third, attacking_third, opp_box, from the acting team's view |
| `lane` | left, center, right |
| `sequence_id` | groups the actions of one move |
| `x`, `y`, `end_x`, `end_y` | synthetic coordinates (optional pairs), consistent with zone and lane |
| `xg` | synthetic shot quality, shots and goals only |

## Rules checked on load
- unique ids
- strict time order
- valid team and player references
- non-blank sequences
- enum-only types and zones
- the final score equals the goals in the events
- deterministic normalization

## Presentation-only configuration
- `config/lineups.json`: authored formations and slots, used for display only and never read by metrics.
- `config/metrics_config.json`: versioned weights and windows behind every metric.

## What the data deliberately excludes
- tracking coordinates (pitch positions are schematic zone × lane cells)
- xG
- substitutions, cards, injuries, stoppage time
- odds and predictions

Full field reference: [docs/data_contract.md](../data_contract.md).
