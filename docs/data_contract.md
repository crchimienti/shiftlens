# Data contract — schema_version 1.1.0

Source of truth: `config/match_schema.json`. Rules the schema cannot express live in
`matchpulse/validator.py::rule_errors`.

## Match
| Field | Type | Notes |
|---|---|---|
| match_id | id | `[A-Za-z0-9_-]+` |
| schema_version | `"1.1.0"` | bump on any shape change |
| seed | int ≥ 0 | seed of `tools/build_match.py` (same seed → byte-identical file) |
| description | string, optional | narrative arc in one line |
| duration_minutes | int 18–120 | match clock; the demo match is 90 |
| home_team / away_team | team | `id`, `name`, `players[]` (`id`, `name`, `number`, `position` GK/DF/MF/FW, optional `starter`) |
| final_score | `{home, away}` | must equal goal events |
| events | event[] | in strict time order |

## Event
| Field | Required | Values |
|---|---|---|
| event_id | yes | unique |
| minute, second | yes | match clock, `minute < duration_minutes`, not reset per period |
| period | yes | 1 or 2; for 90-minute matches period 1 ⇔ minute < 45 |
| team_id | yes | acting team |
| player_id | no | must belong to `team_id`; required for `goal` |
| type | yes | kickoff, pass, carry, dribble, cross, shot, goal, save, tackle, interception, clearance, foul, free_kick, corner, offside, pressure |
| outcome | no | complete, incomplete, saved, off_target, blocked, won, lost, success, fail |
| zone | yes | own_box, defensive_third, middle_third, attacking_third, opp_box — relative to the acting team's attack |
| lane | no | left, center, right |
| sequence_id | yes | non-blank; groups one possession/phase |
| x, y | no (pair) | synthetic 0–100 in the acting team's frame: x towards the goal it attacks, y = 100 on its left touchline. When present, `zone` and `lane` must equal the values derived from them (`validator.zone_of`, `lane_of`) |
| end_x, end_y | no (pair) | synthetic end point of a pass, carry, cross or shot, same frame |
| xg | no | 0–1, shots and goals only. Synthetic: a transparent distance/angle formula in `tools/build_match.py`, not a provider model |

A `goal` is the scoring shot itself (no separate `shot` event). A `pressure` is attributed to the pressing team, at its own coordinates. A `foul` is attributed to the
fouling team. A `save` is attributed to the goalkeeper's team.

The demo dataset is produced by `python tools/build_match.py` (fictional clubs and players, scripted arc, synthetic
coordinates and xG). Coordinates are invented positions for presentation and analysis practice, never tracking.

## Rules checked
Unique team/player/event IDs · strict `(period, minute, second)` order · events inside duration ·
valid `team_id` / `player_id` and membership · non-blank `sequence_id` · enum-only types/zones ·
`final_score` == goals derived from events · x/y and end_x/end_y in pairs · zone/lane consistent with x/y · `xg` only on shots and goals · period matches the half (90-minute matches) · deterministic normalization (same input → same
canonical JSON and SHA-256 fingerprint).

## Metrics (formula 1.0, config 0.3.0)
Computed by `matchpulse/metrics.py` at clock `t` (seconds). Windows are inclusive
`[max(0, t - length), t]`. Event weight = `weights.event[type] x weights.zone[zone]` (missing → 0).
Team-level values are keyed by `team_id`.

| Metric | Value | Window |
|---|---|---|
| score | goals per team (goal events only) | match start → t |
| pass_share | % of pass events per team; null if no passes. Not possession | `pass_share_seconds` |
| danger_score | sum of event weights per team | `danger_seconds` |
| momentum | (home − away) / total of weights decayed by `0.5^(age / half_life)`; [-1, 1], + = home | `momentum_seconds` |
| territorial_control | % of team events in `attacking_zones`; null if no team events | `territorial_seconds` |
| highlighted_sequences | top `top_n` sequences by summed weight; ties → earlier, then id | match start → t |
| inflection_point | largest \|Δmomentum\| > `threshold` between samples ≤ `span_seconds` apart (grid `step_seconds`, samples need ≥ `min_window_events`); ties → earliest | match start → t |
| data_sufficiency | low / med / high from event count vs `med_from`, `high_from` | `sufficiency_seconds` |
