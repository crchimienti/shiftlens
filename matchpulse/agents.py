"""Multi-agent orchestration over deterministic tools (Microsoft AI / Azure AI Foundry-aligned shape).

Three roles, each a small class with named tools and a trace of what it did:

- FanStoryAgent: orchestrates the story tools (match read, story moments, fan explanation) into one contextual
  summary of the moment.
- TacticalAnalystAgent: evaluates the session's hypotheses and decisions (Hypothesis Lab / Decision Journal) and
  audits the raw events behind every metric its explanation references.
- EvidenceGuardrail: a deterministic validator, not a model. Every explanation must pass `validate_explanation`
  (numbers, clocks and event IDs must come from the snapshot), and every lab/journal number is recomputed from the
  raw events its evidence IDs point to. Anything that fails is rejected.

Honesty rules: by default (offline) every tool is a Python rule and no model is called; `generator` is the optional
Azure AI Foundry path from `foundry_client` and only ever drafts wording, which the guardrail still checks. Nothing
here reads events after the replay clock.
"""
from __future__ import annotations

from . import lab as L
from .explain import build_request, cached_explain, explain, validate_explanation
from .metrics import event_time
from .story import match_read, story_moments


def _step(agent: str, tool: str, detail: str, ok: bool = True) -> dict:
    return {"agent": agent, "tool": tool, "detail": detail, "ok": ok}


def _visible(snap: dict) -> dict[str, dict]:
    return {e["event_id"]: e for e in snap["events"]}


class EvidenceGuardrail:
    name = "EvidenceGuardrail"
    tools = ("validate_explanation", "recompute_from_event_ids", "check_event_refs")

    def check_event_refs(self, event_ids, snap: dict) -> list[str]:
        seen = _visible(snap)
        return [f"event '{e}' is not a visible event at {snap['clock']}" for e in event_ids if e not in seen]

    def check_explanation(self, output: dict, request: dict) -> list[str]:
        return validate_explanation(output, request)

    def check_lab_result(self, result: dict, snap: dict) -> list[str]:
        """Recompute both window values from the raw events behind the evidence IDs (pending results pass)."""
        if result["verdict"] == "pending":
            return []
        errors = self.check_event_refs(result["evidence_event_ids"], snap)
        seen = _visible(snap)
        cited = [seen[e] for e in result["evidence_event_ids"] if e in seen]
        for key, window in (("value_a", result["window_a"]), ("value_b", result["window_b"])):
            events = [e for e in cited if window[0] <= event_time(e) <= window[1]]
            if result["measure"] == "pass_share":  # needs every pass in the window, cited or not
                events = L.window_events(snap["events"], *window)
            value, _ = L.measure(events, result["team_id"], result["measure"])
            if value != result[key]:
                errors.append(f"{key} {result[key]} does not match {value} recomputed from its event IDs")
        return errors


class FanStoryAgent:
    name = "FanStoryAgent"
    tools = ("match_read", "story_moments", "fan_explanation")

    def __init__(self, guardrail: EvidenceGuardrail):
        self.guardrail = guardrail

    def run(self, replay, snap: dict, generator=None, cache=None) -> dict:
        trace = []
        read = match_read(snap, replay.match, replay.config)
        trace.append(_step(self.name, "match_read", f"state '{read['state']}': {read['headline']}"))
        moments = story_moments(snap, replay.match, replay.players)[:3]
        trace.append(_step(self.name, "story_moments", f"{len(moments)} latest moment(s) selected"))
        request = build_request(replay.match, snap, "fan")
        result = cached_explain(cache, request, generator) if cache is not None else explain(request, generator)
        exp = result["explanation"]
        trace.append(_step(self.name, "fan_explanation", f"source: {result['source']} · '{exp['headline']}'"))
        errors = self.guardrail.check_explanation(exp, request)
        trace.append(_step(self.guardrail.name, "validate_explanation",
                           "every number, clock and event ID traced to the snapshot" if not errors else "; ".join(errors),
                           ok=not errors))
        return {"agent": self.name, "read": read, "moments": moments, "explanation": exp, "source": result["source"],
                "trace": trace, "ok": not errors}


class TacticalAnalystAgent:
    name = "TacticalAnalystAgent"
    tools = ("evaluate_hypotheses", "review_decisions", "analyst_explanation", "audit_evidence")

    def __init__(self, guardrail: EvidenceGuardrail):
        self.guardrail = guardrail

    def run(self, replay, snap: dict, hypotheses=(), decisions=(), generator=None, cache=None) -> dict:
        trace, results = [], []
        clock = snap["at_seconds"]
        review = lambda d, events, at: L.review_decision(d, events, at, replay.duration)
        for kind, records, evaluate in (("hypothesis", hypotheses, L.evaluate_hypothesis),
                                        ("decision", decisions, review)):
            for rec in records:
                res = evaluate(rec, replay.match["events"], clock)
                errors = self.guardrail.check_lab_result(res, snap)
                results.append({"record": rec, "result": res, "ok": not errors})
                trace.append(_step(self.name, "evaluate_hypotheses" if kind == "hypothesis" else "review_decisions",
                                   f"{kind} #{rec['id']}: {res['verdict']} ({len(res['evidence_event_ids'])} events)"))
                trace.append(_step(self.guardrail.name, "recompute_from_event_ids",
                                   "values recomputed from raw events" if not errors else "; ".join(errors),
                                   ok=not errors))
        if not results:
            trace.append(_step(self.name, "evaluate_hypotheses", "no hypotheses or decisions in this session yet"))
        request = build_request(replay.match, snap, "analyst")
        result = cached_explain(cache, request, generator) if cache is not None else explain(request, generator)
        exp = result["explanation"]
        trace.append(_step(self.name, "analyst_explanation", f"source: {result['source']} · '{exp['headline']}'"))
        refs = sorted({m for p in exp["key_points"] for m in p["metric_refs"]})
        audit = {m: snap["metrics"][m]["source_event_ids"] for m in refs if m in snap["metrics"]}
        missing = [e for ids in audit.values() for e in self.guardrail.check_event_refs(ids, snap)]
        trace.append(_step(self.name, "audit_evidence",
                           f"{len(refs)} metric(s) referenced, {sum(len(v) for v in audit.values())} source events "
                           "checked" + ("" if not missing else f"; {len(missing)} missing"), ok=not missing))
        errors = self.guardrail.check_explanation(exp, request)
        trace.append(_step(self.guardrail.name, "validate_explanation",
                           "every number, clock and event ID traced to the snapshot" if not errors else "; ".join(errors),
                           ok=not errors))
        ok = not errors and not missing and all(r["ok"] for r in results)
        return {"agent": self.name, "results": results, "explanation": exp, "audit": audit,
                "source": result["source"], "trace": trace, "ok": ok}


def run_agents(replay, snap: dict, lens: str, hypotheses=(), decisions=(), generator=None, cache=None) -> dict:
    """The lens decides which agent leads; the guardrail checks every output either way."""
    guard = EvidenceGuardrail()
    if lens == "fan":
        return FanStoryAgent(guard).run(replay, snap, generator, cache)
    return TacticalAnalystAgent(guard).run(replay, snap, hypotheses, decisions, generator, cache)
