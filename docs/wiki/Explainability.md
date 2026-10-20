# Explainability approach

**Python owns the numbers; explanations only rephrase them.**

## Grounding
An explanation request carries only an evidence package:
- the lens
- the clock
- the metric snapshot
- recent events and goals
- the ids of events already played

Nothing from the future is included.

## Validation (every explanation, every time)
1. A strict JSON schema: headline, narrative, key points with metric and event references, limitations, evidence level.
2. Mode, minute and evidence level must match the request.
3. Metric references must be real metrics, and event references must point to events already played.
4. Every number, clock time and event id in the text must come from the snapshot.
5. Each key point's numbers must belong to a metric it references, or to the clock or score.
6. Team values must sit next to the right team name, so swapped values are rejected.

## Deterministic fallback
Fixed templates produce both lenses offline and pass the same validator:
- **Fan Lens:** a broadcast tone. Fresh goals are called with who set them up, and recent shots become "Big chance!" moments.
- **Analyst Lens:** a tactical read of how momentum, ball, threat and territory line up, the latest chance, the
  turning point, and a coaching takeaway.

## Optional model path
A model can phrase the explanation instead, but its output is untrusted: it goes through the same validator,
gets one retry on failure, and otherwise falls back. The status line always shows the source (deterministic
fallback, cached or model), the validated status, the reference counts, the attempts and the latency.

## Traceability
Every number on screen links back to its window, formula version, config version and source events. Fan Lens
keeps this one click away; Analyst Lens shows a summary first, with the full table on demand.
