# Data model

## The synthetic match
`data/match_demo.json` (schema version 1.0.0) is a synthetic, football-realistic 22-minute summary match:
**Northbridge FC 2–1 Harbor City**, with 104 events in 26 sequences across 2 halves and 11 players per side.

- **Fictional:** the clubs and players are invented, and any resemblance to real people or clubs is coincidental.
- **Designed by hand:** the storyline (home control, home goal, away equaliser against the run of play, away
  pressure after the break, late home winner) and each sequence's actions.
- **Reproducible:** loading the file twice gives identical normalized data; `python streamlit_app.py` prints its
  fingerprint. The `seed` field is recorded for a future generator; no randomness is used.

## Event fields
| Field | Meaning |
|---|---|
| `event_id` | unique id |
| `minute`, `second`, `period` | summary clock (does not reset at half-time) |
| `team_id`, `player_id` | acting team and player (the player must belong to the team) |
| `type` | kickoff, pass, carry, dribble, cross, shot, goal, save, tackle, interception, clearance, foul, free_kick, corner, offside |
| `outcome` | complete, incomplete, saved, off_target, blocked, won, lost, success, fail |
| `zone` | own_box, defensive_third, middle_third, attacking_third, opp_box, from the acting team's view |
| `lane` | left, center, right |
| `sequence_id` | groups the actions of one move |

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
