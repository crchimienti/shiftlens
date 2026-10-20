"""Optional Microsoft Foundry / Azure OpenAI explanation generator (stdlib HTTPS, no SDK).

Off unless MATCHPULSE_OFFLINE=0 and the AZURE_OPENAI_* variables are set. The model receives a
minimal evidence package and must return JSON matching a structured-output schema derived from
config/explanation_schema.json. Its output stays untrusted: `explain.explain` runs the full
validator, retries once on an invalid response, and otherwise uses the deterministic fallback.
Python owns every number; the model only writes language around them.
"""
from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.request

from .explain import EXPLANATION_SCHEMA_PATH, EXPLANATION_VERSION, STANDARD_LIMITS
from .validator import load_json

REQUIRED_ENV = ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_DEPLOYMENT", "AZURE_OPENAI_API_VERSION")
DEFAULT_TIMEOUT_SECONDS = 15.0
RESPONSE_FORMATS = ("json_schema", "json_object")
MODEL_FIELDS = ("mode", "minute", "headline", "narrative", "key_points", "limitations", "data_sufficiency")

SYSTEM_PROMPT = """You write one explanation of one moment of a SYNTHETIC football match.
You receive an evidence package computed by Python. Python owns every number.
Rules:
- Use ONLY numbers, clock times (mm:ss), team names, player names and event ids that appear in the evidence.
- Never calculate new metrics or numbers. Never estimate xG, probabilities, predictions or betting information.
- Never invent events, players, causes, outcomes or real-world facts. This is not a real match.
- Every key point must list at least one metric name from evidence.metrics in metric_refs, and only
  event ids from the evidence in event_refs. A number in a key point must come from a metric it lists
  (or the clock/score), written right after the team it belongs to.
- "mode" must equal evidence.lens, "minute" must equal evidence.minute, "data_sufficiency" must equal
  evidence.data_sufficiency. Include at least one limitation.
- fan: simple words, narrative <= 300 characters, 1 to 3 key points.
- analyst: 3 to 6 key points, mention the time windows; keep the stated limitations.
- pass_share is pass share, never possession. Return only the JSON object."""


class FoundryError(RuntimeError):
    """A failed online call. `retryable` is False for timeout/auth/network: fall back at once."""

    def __init__(self, kind: str, message: str, retryable: bool):
        super().__init__(f"{kind}: {message}")
        self.kind, self.retryable = kind, retryable


# --- evidence package -------------------------------------------------------

def evidence_package(request: dict) -> dict:
    """Only what the model needs: lens, minute, score, metric snapshot, recent events, sufficiency, limits."""
    metrics = request["metrics"]
    players = request.get("players", {})
    recent = [{**ev, "player_name": players.get(ev["player_id"])} for ev in request["recent_events"]]
    return {
        "lens": request["mode"],
        "minute": request["clock"]["minute"],
        "clock": {"label": request["clock"]["label"], "period": request["clock"]["period"]},
        "teams": {"home": request["match"]["home"], "away": request["match"]["away"]},
        "score": metrics["score"]["value"],
        "metrics": metrics,
        "recent_events": recent,
        "data_sufficiency": metrics["data_sufficiency"]["value"],
        "limitations": [sentence for _, sentence in STANDARD_LIMITS],
    }


# --- structured output schema -----------------------------------------------

_UNSUPPORTED = {"$schema", "$id", "title", "minLength", "maxLength", "minItems", "maxItems",
                "uniqueItems", "minimum", "maximum", "pattern"}


def _strict(node, defs):
    if isinstance(node, list):
        return [_strict(n, defs) for n in node]
    if not isinstance(node, dict):
        return node
    if "$ref" in node:
        return _strict(defs[node["$ref"].split("/")[-1]], defs)
    out = {k: _strict(v, defs) for k, v in node.items() if k not in _UNSUPPORTED and k != "$defs"}
    if "const" in out:
        out["enum"] = [out.pop("const")]
    if "enum" in out and "type" not in out:
        out["type"] = "integer" if all(isinstance(v, int) for v in out["enum"]) else "string"
    return out


def model_output_schema() -> dict:
    """Strict JSON Schema for the model: the app schema minus app-owned fields and unsupported keywords."""
    schema = load_json(EXPLANATION_SCHEMA_PATH)
    strict = _strict(schema, schema.get("$defs", {}))
    strict["properties"] = {k: strict["properties"][k] for k in MODEL_FIELDS}
    strict["required"] = list(MODEL_FIELDS)
    return strict


# --- client -----------------------------------------------------------------

def _timeout(env) -> float:
    try:
        value = float(env.get("AZURE_OPENAI_TIMEOUT_SECONDS") or DEFAULT_TIMEOUT_SECONDS)
        return value if value > 0 else DEFAULT_TIMEOUT_SECONDS
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS


def online_generator_from_env(env=None):
    """Return a FoundryClient, or None when offline / not configured (the default)."""
    env = os.environ if env is None else env
    if env.get("MATCHPULSE_OFFLINE", "1") != "0":
        return None
    if not all(env.get(k) for k in REQUIRED_ENV):
        return None
    fmt = env.get("AZURE_OPENAI_RESPONSE_FORMAT") or "json_schema"
    return FoundryClient(*(env[k] for k in REQUIRED_ENV), timeout=_timeout(env),
                         response_format=fmt if fmt in RESPONSE_FORMATS else "json_schema")


class FoundryClient:
    """Callable generator: (request, previous_errors) -> explanation dict, or raises FoundryError."""

    def __init__(self, endpoint: str, api_key: str, deployment: str, api_version: str,
                 timeout: float = DEFAULT_TIMEOUT_SECONDS, response_format: str = "json_schema"):
        self.url = (f"{endpoint.rstrip('/')}/openai/deployments/{deployment}/chat/completions"
                    f"?api-version={api_version}")
        self._api_key = api_key
        self.timeout = timeout
        self.response_format = response_format

    def __repr__(self) -> str:  # never print the key
        return f"FoundryClient(url={self.url!r}, timeout={self.timeout}, response_format={self.response_format!r})"

    def messages(self, evidence: dict, previous_errors: list[str] | None) -> list[dict]:
        msgs = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps({"evidence": evidence}, ensure_ascii=False)}]
        if previous_errors:
            msgs.append({"role": "user", "content": "Your previous answer was rejected:\n- "
                         + "\n- ".join(previous_errors[:10]) + "\nReturn a corrected JSON object."})
        return msgs

    def body(self, evidence: dict, previous_errors: list[str] | None) -> dict:
        if self.response_format == "json_schema":
            fmt = {"type": "json_schema",
                   "json_schema": {"name": "shiftlens_explanation", "strict": True, "schema": model_output_schema()}}
        else:
            fmt = {"type": "json_object"}
        return {"messages": self.messages(evidence, previous_errors), "temperature": 0, "response_format": fmt}

    def _post(self, payload: dict) -> dict:
        req = urllib.request.Request(self.url, data=json.dumps(payload).encode("utf-8"), method="POST",
                                     headers={"Content-Type": "application/json", "api-key": self._api_key})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise FoundryError("authentication", f"HTTP {e.code}", retryable=False) from None
            raise FoundryError("http", f"HTTP {e.code}", retryable=False) from None
        except (TimeoutError, socket.timeout):
            raise FoundryError("timeout", f"no response within {self.timeout:g}s", retryable=False) from None
        except urllib.error.URLError as e:
            if isinstance(e.reason, (TimeoutError, socket.timeout)):
                raise FoundryError("timeout", f"no response within {self.timeout:g}s", retryable=False) from None
            raise FoundryError("network", str(e.reason), retryable=False) from None
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise FoundryError("response", "provider returned a non-JSON body", retryable=True) from None

    def __call__(self, request: dict, previous_errors: list[str] | None = None) -> dict:
        payload = self._post(self.body(evidence_package(request), previous_errors))
        try:
            message = payload["choices"][0]["message"]
        except (KeyError, IndexError, TypeError):
            raise FoundryError("response", "no choices in provider response", retryable=True) from None
        if message.get("refusal"):
            raise FoundryError("refusal", "model refused to answer", retryable=False)
        try:
            output = json.loads(message.get("content") or "")
        except json.JSONDecodeError:
            raise FoundryError("malformed_json", "model content is not valid JSON", retryable=True) from None
        if not isinstance(output, dict):
            raise FoundryError("malformed_json", "model content is not a JSON object", retryable=True)
        return {**output, "explanation_version": EXPLANATION_VERSION}
