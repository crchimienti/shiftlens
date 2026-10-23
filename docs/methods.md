# ShiftLens methods contract

ShiftLens computes every number in Python, deterministically, from the synthetic event data
(`data/match_demo.json`) and the versioned config (`config/metrics_config.json`, version 0.2.0).
The explanation layer only rephrases those numbers. **The model never owns the numbers.**

The data is a synthetic, football-realistic Premier League-style broadcast scenario with fictional clubs
and players. No real Premier League match data or official competition data is used. The metrics are
chosen for broadcast storytelling: who has the pressure (momentum, danger), where the game is being played
(territorial control, pass share), when it turned (turning point), and how much evidence there is (data sufficiency).
They are simple, transparent indices, not official or licensed statistics.

## Shared conventions

- **Clock.** `t = minute × 60 + second` on the simulated replay clock (0–1320 s for the 22-minute
  demo match). It does not reset at half-time. Metrics are recomputed for whatever second the replay is on.
- **Window.** Inclusive `[max(0, t − length), t]`. Events after `t` are never used.
- **Event weight.** `weights.event[type] × weights.zone[zone]`. Types without a weight (save,
  clearance, foul, offside, kickoff) count 0. Outcome is ignored.
  - Event: pass 0.1 · carry 0.2 · dribble 0.4 · cross 0.5 · shot 1.0 · goal 2.0 · corner 0.6 ·
    free_kick 0.3 · interception 0.3 · tackle 0.3
  - Zone: own_box 0.2 · defensive_third 0.4 · middle_third 0.7 · attacking_third 1.0 · opp_box 1.5

- **Output envelope (every metric).** `metric_name`, `value`, `window {start_seconds, end_seconds,
  length_seconds}`, `formula_version` (all 1.0), `config_version`, `source_event_ids`, `team_id`,
  `notes`, `details`. Team-level values are keyed by team id (`NBR`, `HBC`).
- **Traceability in the app.** The Traceability panel lists every metric. Fan Lens shows
  metric, value, window and the number of source events. Analyst Lens adds `formula_version`,
  `config_version`, `team_id` and the full `source_event_ids`.

## Metrics

### Score (`score`)
- **Purpose:** the scoreline at the current second.
- **Inputs / window:** `goal` events from kick-off to `t`.
- **Calculation:** count goals per team.
- **Output:** `value {team: goals}`; `source_event_ids` = the goal events.
- **Interpretation:** authoritative within the dataset; the declared `final_score` is validated against it on load.
- **Limits:** no own goals, penalties or disallowed goals are modelled.

### Pass share (`pass_share`)
- **Purpose:** which team is moving the ball more right now.
- **Inputs / window:** `pass` events, last 300 s.
- **Calculation:** each team's passes ÷ all passes × 100, rounded to 2 decimals; `null` when there are no passes.
- **Output:** `value {team: % | null}`; `details.pass_counts`; sources = the passes counted.
- **Interpretation:** a share of pass *events*. We call it pass share everywhere; it is **not possession**
  (no time on the ball, no carries, no completion rate).
- **Limits:** incomplete passes count the same as complete ones; small windows swing quickly.

### Danger (`danger_score`)
- **Purpose:** how threatening each team's recent actions are.
- **Inputs / window:** all events, last 180 s.
- **Calculation:** sum of event weights per team, rounded to 4 decimals.
- **Output:** `value {team: number}`; sources = events with weight > 0.
- **Interpretation:** a simple weighted index. Higher means more, and more advanced, attacking actions.
- **Limits:** **not xG** and not a probability; ignores outcome, shot quality and defenders.

### Momentum (`momentum`)
- **Purpose:** which side is on top right now, on one bounded scale.
- **Inputs / window:** weighted events, last 180 s, half-life 60 s.
- **Calculation:** each event's weight decays by `0.5^(age / 60)`.
  `momentum = (home − away) / (home + away)`, rounded to 4 decimals; 0 when there are no weighted events.
- **Output:** `value` in [−1, +1] (positive favours the home team); `team_id` = leading side or `null`
  on a tie; `details.half_life_seconds`; sources = weighted events in the window.
- **Interpretation:** relative, not absolute. +0.8 means the home side produced most of the recent weighted activity.
- **Limits:** depends on the window and half-life; saturates near ±1 when one side dominates.

### Territorial control (`territorial_control`)
- **Purpose:** how much each team plays in the opponent's half.
- **Inputs / window:** all events, last 300 s; attacking zones = `attacking_third`, `opp_box`.
- **Calculation:** a team's events in attacking zones ÷ that team's events × 100, rounded to 2 decimals;
  `null` if the team has no events.
- **Output:** `value {team: % | null}`; `details.counts`, `details.attacking_zones`; sources = all events in the window.
- **Interpretation:** the two values are independent and do not add up to 100.
- **Limits:** zones are coarse (5 zones, 3 lanes); there is no positional tracking.

### Highlighted sequences (`highlighted_sequences`)
- **Purpose:** the most dangerous moves so far.
- **Inputs / window:** all events from kick-off to `t`, grouped by `sequence_id`.
- **Calculation:** sequence score = sum of its event weights. Top 3 by score; ties go to the earlier
  sequence, then to `sequence_id`. Sequence team = the team with the larger weighted contribution
  (on a tie, the team of its first event).
- **Output:** `value` = list of `{sequence_id, score, team_id, start_seconds, end_seconds, event_ids, has_goal}`;
  sources = the events of the listed sequences.
- **Interpretation:** "where the danger came from", not "best chances" in an xG sense.
- **Limits:** sequence boundaries are authored in the data, not detected.

### Turning point (`inflection_point`, shown as "Biggest swing so far")
- **Purpose:** the biggest shift in momentum so far.
- **Inputs / window:** momentum sampled every 10 s from kick-off to `t`; samples with fewer than 8
  weighted events are skipped.
- **Calculation:** the largest |Δmomentum| greater than 0.8 between two samples at most 120 s apart;
  ties go to the earliest.
- **Output:** `value {from_seconds, to_seconds, from_momentum, to_momentum, delta}` or `null`; `team_id` =
  the side it swung towards; `details {threshold, span_seconds, step_seconds, samples_used}`;
  sources = events in `(from_seconds, to_seconds]`.
- **Interpretation:** "when the game turned", for one swing only.
- **Limits:** reports the largest swing, not the latest one or all of them; inherits momentum's limits.

### Data sufficiency (`data_sufficiency`)
- **Purpose:** how much evidence sits behind the current numbers.
- **Inputs / window:** all events, last 300 s.
- **Calculation:** fewer than 10 events → `low`; 10–19 → `med`; 20 or more → `high`.
- **Output:** `value` (low / med / high); `details {event_count, med_from, high_from}`; sources = events counted.
- **Interpretation:** treat other metrics with caution when this is `low` (e.g. the first minutes).
- **Limits:** counts events; it does not judge their quality.

## Visual layer (no new metrics)
- **Schematic pitch:** each event is placed at the centre of its zone × lane cell, seen from the acting team
  (home attacks left → right, away is mirrored). Repeated cells inside one move step slightly towards goal.
  These are approximate positions, not coordinates.
- **Schematic paths:** curves, dashes and the gold line into the net show the *type* of action (pass, cross,
  carry, dribble, goal). They are not ball trajectories.
- **Match flow:** the existing momentum value sampled every 15–30 s and drawn as a smoothed spline (visual
  only; hover shows the sampled values). Goals and the turning-point window are marked. The tug-of-war bar
  shows the current value as a home/away split, `(m + 1) / 2`.
- **All moves:** every sequence so far, with impact computed exactly as for the featured key moves.
- **Move card and breakdown:** plain counts from the move's events. Per-event weights are the existing event weights
  and add up to the move's impact.

## Lineups and formations (presentation only)
`config/lineups.json` holds synthetic, authored lineups: a formation label and the players' slots, line by line
from goalkeeper to forwards, each line listed left → right as the team attacks. `matchpulse/lineups.py` validates
them (every roster player appears exactly once, a single goalkeeper line, the formation matches the line sizes)
and places each line evenly between its own goal and halfway (home team mirrored to attack right). If a match has
no entry, players are grouped by listed position (GK / DF / MF / FW). Lineups are never read by metrics or
explanations and do not describe real positioning.

## Tactical pitch (Analyst Lens)
The Analyst Lens pitch draws five vertical lanes as a reference grid: wing, half-space, centre, half-space, wing.
The half-spaces are the lanes between the central lane and the wide lanes; their boundaries follow the
penalty-box and six-yard-box edges. The event data has three lanes (left / centre / right), so events still sit
in their three-lane positions. The grid is a reading aid, not extra data.

## Story feed and auto story
- **Story so far** restates events: goals (with the previous action of the same team in the move as the setup),
  shots with their outcome (and the goalkeeper when a save follows), and the turning point. No generated text.
- **Auto story (Fan Lens, paused only)** is the deterministic fallback explanation for the current second, passed
  through the same validator. It is not cached and makes no online call. **Explain this moment** still produces the
  cached / optional-Foundry version.

## Replay speed
Speeds 0.5x / 1x / 1.5x / 2x advance the clock by 5 / 10 / 15 / 20 simulated seconds per one-second tick. The same
second always shows the same numbers at any speed.

## Advanced proxies (Analyst Lens)
Display-only, deterministic and synthetic. They never feed the 8 core metrics or the explanation validator, and
none of them is xG, xA or xT. Code: `matchpulse/analytics.py`.

- **Shot Quality Index (SQI, 0–1).** `zone base × lane factor + setup bonus`, capped at 0.95. Zone base: opp_box
  0.45, attacking_third 0.18, middle_third 0.05, deeper 0.02. Lane factor: centre 1.0, wide 0.75. Setup bonus from
  the previous action of the same team in the same move: cross +0.08, dribble +0.06, corner +0.05, free kick +0.04,
  pass +0.03 (+0.03 more for a pass inside the box). A goal counts as a shot. It describes how promising the
  *situation* was from the fields we have. It is not a probability.
- **Chance Creation Index.** For each player, the sum of the SQI of shots they set up (the setup action, as above).
  An **assist** is the setup of a goal.
- **Prevented Danger.** For each goalkeeper, the sum of the SQI of shots they saved (a shot immediately followed
  by a save in the same move).
- **Activity map.** Counts of a team's (or one selected player's) actions per zone × lane cell (5 × 3), drawn as
  shaded cells. These are counts, not coordinates.
- **Defensive actions.** Tackles, interceptions, clearances and saves at schematic zone × lane positions.
- **Shot map (schematic).** Shots at schematic positions (fixed offsets within a cell); marker size = SQI,
  symbol = outcome. These are not real shot locations.
- **Pass network (schematic).** A link is a pass, cross, corner or free kick followed by a team-mate's next
  action in the same move. Players are drawn at the *average of their zone × lane cells* (default) or at their
  *formation slots* (see Lineups), never at measured positions. Line width = number of links; line colour = the
  summed threat gain moved along the link (Zone Threat, below); the three busiest links show their count.
- **Lineup badges.** ⚽ goals, 🅰️ assists (as above), 🟨 🟥 cards if the data has card events (schema 1.0.0 has
  none), all from the event chain up to the current second.

## Match read (Fan Lens)
`story.match_read` describes the current state from the metrics and counts in the last 300 s. It is not
generated text and is not part of the validated explanation.
- **Lines:**
  - **Pressure:** momentum ≥ 0.6 → "on the front foot"; ≥ 0.2 → "edging"; otherwise "neither side".
  - **Ball:** the pass-share leader, when ahead by more than 5 points.
  - **Connecting:** pass completion (complete ÷ all passes, at least 3 passes per team), when ahead by more than 5 points.
  - **Closer to goal:** each team's action count in the opponent's box.
- **States** (the first match wins):
  - *settling*: fewer than 10 recent events.
  - *shifting*: the turning point ended in the last 90 s, or momentum changed sign vs 2 min ago (both ≥ 0.2).
  - *controlled*: momentum ≥ 0.6, and the ball and territory leaders agree with it.
  - *pressing*: momentum ≥ 0.6 otherwise ("possession without penetration" when the other side has more of the ball).
  - *building*: momentum ≥ 0.2, same sign as 2 min ago, and at least 0.15 stronger.
  - *chaotic*: momentum < 0.3 and at least 35% of recent events are turnovers.
  - *even*: anything else.

## Analyst tactical read
Each pattern ends with a one-line **coaching takeaway**: an interpretation with no numbers.
The Analyst deterministic fallback compares the leaders of momentum, pass share (more than 5 points), danger
index (more than 0.5) and territory (more than 5 points):
- **Ball and threat split:** "X carry the threat, Y keep the ball".
- **Territory vs momentum split:** "X hold the momentum, Y the territory".
- **Aligned:** "X in control" (momentum ≥ 0.6).
- **Momentum below 0.2:** "an even phase".
- **Otherwise:** "X edging it".

It adds the latest chance (zone and outcome, no numbers) and the turning point. Every number it uses comes from
the snapshot and passes the unchanged validator; "suggests" marks interpretation.

## Ball Progression (proxy)
A pass, carry, dribble or cross counts as progressive when the same team's next action in the same move is in a
more advanced zone (own box → defensive third → middle third → attacking third → opponent box). It is a count,
not a threat value.

## Zone Threat and threat gain (proxy)
Code: `matchpulse/threat.py` (version 1.0). Display-only: it never feeds the 8 core metrics, the explanation
request or the validator.
- **Zone Threat grid.** A fixed, hand-set 0–1 value per zone × lane cell, as seen by the acting team:

  | Zone | Left | Centre | Right |
  |---|---|---|---|
  | own box | 0.01 | 0.01 | 0.01 |
  | defensive third | 0.02 | 0.03 | 0.02 |
  | middle third | 0.05 | 0.07 | 0.05 |
  | attacking third | 0.10 | 0.16 | 0.10 |
  | opponent box | 0.24 | 0.40 | 0.24 |

- **Threat gain** of a pass, cross, corner, free kick, carry or dribble = grid value of the cell where the same
  team's *very next* action in the same move happens − grid value of the action's own cell. Turnovers, shots,
  saves and the last action of a move get no value (no destination to measure).
- **Threat Added** (Proxy leaders) = a player's sum of positive gains. **Move threat** = net gain of the move's
  actions plus the most dangerous cell it reached.
- **Honest limits.** The grid is not learned from data and is **not xT** or a probability: it only ranks cells
  (closer to goal and more central = higher). With 15 cells the values are coarse, so they are used to colour
  paths and rank actions, not to claim precise threat. An earlier version of this document rejected a grid for
  that false-precision risk; it was added once it could be shown as a published, fixed ranking with these
  limits stated next to it.

## Explanation contract

**Input (request).** `build_request` sends: mode, the two teams, the clock (seconds, label, minute,
half), all 8 metric outputs exactly as computed, the last 12 events, every goal so far, the IDs of all
events played so far, and player names. Nothing after the current second is included.

**Output.** `config/explanation_schema.json`: `explanation_version`, `mode`, `minute`, `headline`,
`narrative`, `key_points[] {text, metric_refs, event_refs}`, `limitations[]`, `data_sufficiency`, `source`.

| | Fan Lens (`fan`) | Analyst Lens (`analyst`) |
|---|---|---|
| Key points | 1–3 | 3–6 |
| Narrative | ≤ 300 characters, broadcast tone (fresh goal / big chance calls) | up to 1200 characters, numbers with windows |
| References | required on every key point; not shown in the UI | required on every key point; metric and event references shown under each one |
| Limitations | shared "Data limits" panel | shared "Data limits" panel plus metric-specific caveats |

**Validation rules** (`validate_explanation`; all must pass before anything is shown):
1. The output matches the schema.
2. `mode`, `minute` and `data_sufficiency` match the request.
3. Every metric reference is a real metric, and every event reference is an event already played.
4. Every key point has at least one valid metric reference.
5. Every number, mm:ss time and event ID in any text must come from the request (rounded forms are allowed).
6. Every number in a key point must belong to one of its referenced metrics, or to the clock or score.
7. A team-specific number must belong to the nearest team name written before it, which rejects swapped team values.

Rules 5–7 are deterministic text checks, not language understanding. They are deliberately strict:
an answer that cannot be verified is rejected.

**Deterministic fallback.** Fixed templates over the same request produce Fan Lens and Analyst
Lens explanations offline. They pass the same validator; a template that ever failed would raise an
error instead of being shown.

**Optional Foundry path.** Off by default. When enabled, the model receives only an evidence package
(lens, minute, clock, team names, score, metric snapshot, last 12 events, data sufficiency, standard
limitations) and must answer in a strict JSON Schema derived from the explanation schema. The app adds
`explanation_version` and `source`. Structured output does not replace validation: rules 1–7 above
still apply. An invalid answer gets one retry with the validation errors; a timeout, authentication,
network or HTTP error falls back immediately. Either way the result is the deterministic fallback.
Only validated output is cached, per (match, second, lens, explanation version), and Reset clears the
cache. Not validated against a live deployment yet.

**What the model may do:** choose which of the supplied numbers to highlight, rephrase them for Fan Lens
or Analyst Lens readers, and cite metric and event references from the request.

**What the model may not do:** compute or estimate new numbers or metrics, invent players, teams, events,
outcomes, causes or real-world facts, reference future events, give xG, predictions, outcome probabilities
or betting information, run while the replay is playing, or take free-form questions.
