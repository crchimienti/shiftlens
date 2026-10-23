# Product vision

## The problem
A football match is a story of shifts: who has the pressure, where the game is played, when it turns.
Broadcast stats rarely tell that story. They arrive as bare numbers ("momentum +0.82", "60% of passes") with
no explanation and no way to check where they came from. Generative summaries can make this worse by sounding
confident about figures that were never measured.

## The idea
Separate **numbers** from **language**:
1. Compute every number deterministically from the match events.
2. Let explanations only rephrase numbers that exist, citing the metrics and events behind each claim.
3. Validate every explanation before display, and fall back to a deterministic, validated template if it fails.

The result is match intelligence a presenter can say on air and an analyst can check.

## Two audiences, two lenses
### 📺 Fan Lens: broadcaster companion
For fans, streaming viewers and presenters who need a fast, engaging read.
- **Key moments first:** the key move on a schematic pitch, compact match stats, a pressure summary.
- **Match Story:** who is pressing, who controls the ball, who connects passes better, who threatens the box,
  and how the game state has evolved (controlled → shifting → pressing …).
- **Live Story:** whenever the replay is paused, a validated explanation of that exact moment. Fresh goals and
  big chances get a broadcast tone, using only facts from the events.

### 📋 Analyst Lens: tactical desk
For analysts, coaches, scouts and studio producers who need compact tactical insight.
- **Tactical workspace:** the move on a five-lane board, an activity map (team or single player), a pass network,
  a shot map and defensive actions.
- **Proxy leaders:** chance creation, ball progression, threat added and prevented danger.
- **Tactical read:** how momentum, ball, threat and territory line up, ending with a coaching takeaway.
- **Traceability:** a summary first, with the full evidence (formula and config versions, source event ids) on demand.

## Principles
- **Honest data:** synthetic and labelled as synthetic; schematic positions; proxies are never called xG/xA/xT.
- **Offline-first:** the demo needs no network.
- **Deterministic:** the same second always shows the same numbers.
- **Evidence over eloquence:** an explanation that cannot be verified is not shown.
