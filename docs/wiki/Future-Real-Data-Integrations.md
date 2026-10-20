# Future real-data integrations

ShiftLens is a synthetic-data demo. Richer, **licensed** event and tracking databases or APIs could unlock fuller
real-data deployments. This page describes how that would work without weakening the demo's guarantees.

## Principles
- **The synthetic demo stays the default.** A real-data path would sit behind an explicit opt-in flag.
- **Adapter, not rewrite:** a provider adapter maps external payloads into ShiftLens structures. Metrics,
  explanations and the validator stay the same, and a real-data path gets its own schema rather than loosening
  the synthetic one.
- **Keep the raw data:** keep the provider's original payloads for debugging, never invent missing fields (use
  null), and record the provider's coordinate conventions.
- **Licensing first:** use only data you are licensed to process and display.

## What maps easily from typical match-data APIs
- **Match header:** teams, score, status and kickoff.
- **Lineups:** formations, starting XI and bench.
- **Team statistics:** shots, passes, cards and similar totals feed the match-stats panel.
- **Shots with provider xG and coordinates:** a real shot map in place of the synthetic Shot Quality Index.
- **Pressure / momentum time series:** an alternative tide of the game.
- **Average positions:** real nodes for the pass network and player maps.

## What the full ShiftLens experience needs
- **An action-by-action event stream:** passes, carries, tackles and so on, each with pitch location, timestamp
  and possession sequence. Pass share, danger index, territory, key moves, the story feed and the validated
  explanations are all built on that stream.
- **Tracking data (optional):** real positional heat maps and off-ball analysis, beyond today's schematic zones.
- **Pass links with receivers:** a measured pass network rather than the schematic one.

## Validation stays mandatory
Real data does not relax grounding: explanations still only rephrase computed numbers and must still pass the validator.
