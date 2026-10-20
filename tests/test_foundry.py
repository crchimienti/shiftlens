"""Mocked Foundry / Azure OpenAI path. No test makes a real network call: urlopen is replaced."""
import io
import json
import socket
import urllib.error

import pytest

from matchpulse import foundry_client
from matchpulse.explain import ExplanationCache, build_request, cached_explain, explain, fallback
from matchpulse.foundry_client import (
    MODEL_FIELDS,
    FoundryClient,
    evidence_package,
    model_output_schema,
    online_generator_from_env,
)
from matchpulse.replay import Replay
from matchpulse.validator import CONFIG_PATH, load_json, load_match

AT = 674  # 11:14, 1-1
SECRET = "test-key-do-not-log"


@pytest.fixture(scope="module")
def replay():
    match, _ = load_match()
    return Replay(match, load_json(CONFIG_PATH))


@pytest.fixture
def request_(replay):
    return build_request(replay.match, replay.snapshot(AT), "analyst")


@pytest.fixture
def client():
    return FoundryClient("https://unit-test.invalid", SECRET, "dep", "2024-10-21", timeout=2)


def model_answer(request, **changes):
    """A model-shaped answer: the deterministic text without app-owned fields, plus changes."""
    out = {k: v for k, v in fallback(request).items() if k not in ("explanation_version", "source")}
    out.update(changes)
    return out


def chat_response(content):
    body = {"choices": [{"message": {"role": "assistant", "content": content}}]}
    return io.BytesIO(json.dumps(body).encode("utf-8"))


class FakeUrlopen:
    """Scripted replies: bytes streams are returned, exceptions are raised. Records every request."""

    def __init__(self, *replies):
        self.replies, self.requests = list(replies), []

    def __call__(self, req, timeout):
        self.requests.append({"url": req.full_url, "headers": dict(req.header_items()),
                              "body": json.loads(req.data), "timeout": timeout})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


@pytest.fixture
def fake(monkeypatch):
    def install(*replies):
        f = FakeUrlopen(*replies)
        monkeypatch.setattr(foundry_client.urllib.request, "urlopen", f)
        return f
    return install


# --- happy path and request shape -------------------------------------------

def test_valid_foundry_response_is_accepted(fake, client, request_):
    f = fake(chat_response(json.dumps(model_answer(request_))))
    result = explain(request_, client)
    assert result["source"] == "llm" and [a["ok"] for a in result["attempts"]] == [True]
    assert result["explanation"]["explanation_version"] == "1.0"
    assert len(f.requests) == 1


def test_request_sends_only_the_evidence_package(fake, client, request_):
    f = fake(chat_response(json.dumps(model_answer(request_))))
    explain(request_, client)
    sent = f.requests[0]
    evidence = json.loads(sent["body"]["messages"][1]["content"])["evidence"]
    assert set(evidence) == {"lens", "minute", "clock", "teams", "score", "metrics", "recent_events",
                             "data_sufficiency", "limitations"}
    assert evidence["lens"] == "analyst" and evidence["minute"] == 11 and evidence["score"] == {"NBR": 1, "HBC": 1}
    assert len(evidence["recent_events"]) <= 12 and evidence["limitations"]
    raw = json.dumps(sent["body"])
    assert "allowed_event_ids" not in raw and "match_id" not in raw and SECRET not in raw
    assert sent["headers"]["Api-key"] == SECRET and sent["timeout"] == 2
    assert sent["url"] == "https://unit-test.invalid/openai/deployments/dep/chat/completions?api-version=2024-10-21"
    assert sent["body"]["temperature"] == 0
    assert SECRET not in repr(client)


def test_structured_output_schema_is_strict(fake, client, request_):
    f = fake(chat_response(json.dumps(model_answer(request_))))
    explain(request_, client)
    fmt = f.requests[0]["body"]["response_format"]
    assert fmt["type"] == "json_schema" and fmt["json_schema"]["strict"] is True
    schema = fmt["json_schema"]["schema"]
    assert schema == model_output_schema() and list(schema["required"]) == list(MODEL_FIELDS)

    def walk(node):
        if isinstance(node, dict):
            assert not {"$ref", "minLength", "maxLength", "minItems", "maxItems", "uniqueItems", "const"} & set(node)
            if node.get("type") == "object":
                assert node["additionalProperties"] is False and set(node["required"]) == set(node["properties"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(schema)


def test_json_object_mode_is_available(monkeypatch):
    env = {"MATCHPULSE_OFFLINE": "0", "AZURE_OPENAI_ENDPOINT": "https://x.invalid", "AZURE_OPENAI_API_KEY": "k",
           "AZURE_OPENAI_DEPLOYMENT": "d", "AZURE_OPENAI_API_VERSION": "v", "AZURE_OPENAI_RESPONSE_FORMAT": "json_object",
           "AZURE_OPENAI_TIMEOUT_SECONDS": "7.5"}
    gen = online_generator_from_env(env)
    assert gen.response_format == "json_object" and gen.timeout == 7.5
    assert gen.body({"lens": "fan"}, None)["response_format"] == {"type": "json_object"}
    assert online_generator_from_env({**env, "AZURE_OPENAI_TIMEOUT_SECONDS": "soon"}).timeout == 15.0


def test_offline_by_default():
    assert online_generator_from_env({}) is None


# --- invalid responses: retry once, then deterministic fallback -------------

def test_malformed_json_retries_then_falls_back(fake, client, request_):
    f = fake(chat_response("Sure! Here is the JSON: {"), chat_response("still not json"))
    result = explain(request_, client)
    assert result["source"] == "fallback" and len(f.requests) == 2
    assert "malformed_json" in result["attempts"][0]["errors"][0]
    assert "rejected" in f.requests[1]["body"]["messages"][-1]["content"]  # errors fed back on retry


def test_schema_invalid_response_retries_then_falls_back(fake, client, request_):
    bad = model_answer(request_)
    del bad["headline"]
    f = fake(chat_response(json.dumps(bad)), chat_response(json.dumps(bad)))
    result = explain(request_, client)
    assert result["source"] == "fallback" and len(f.requests) == 2
    assert any("'headline' is a required property" in e for e in result["attempts"][0]["errors"])


def test_invented_number_is_rejected_then_retry_succeeds(fake, client, request_):
    invented = model_answer(request_, narrative="Harbor City have an xG of 2.7 and 99 shots.")
    f = fake(chat_response(json.dumps(invented)), chat_response(json.dumps(model_answer(request_))))
    result = explain(request_, client)
    assert result["source"] == "llm" and [a["ok"] for a in result["attempts"]] == [False, True]
    assert any("'2.7'" in e for e in result["attempts"][0]["errors"])
    assert len(f.requests) == 2


def test_invalid_event_reference_falls_back(fake, client, request_):
    bad = model_answer(request_)
    bad["key_points"][0]["event_refs"] = ["E104"]  # a future event at 11:14
    f = fake(chat_response(json.dumps(bad)), chat_response(json.dumps(bad)))
    result = explain(request_, client)
    assert result["source"] == "fallback" and len(f.requests) == 2
    assert any("'E104' is not a visible event" in e for e in result["attempts"][1]["errors"])


def test_refusal_falls_back_without_retry(fake, client, request_):
    body = {"choices": [{"message": {"role": "assistant", "content": None, "refusal": "no"}}]}
    f = fake(io.BytesIO(json.dumps(body).encode()))
    result = explain(request_, client)
    assert result["source"] == "fallback" and len(f.requests) == 1


# --- transport failures: deterministic fallback at once ----------------------

@pytest.mark.parametrize("error, kind", [
    (socket.timeout("timed out"), "timeout"),
    (urllib.error.URLError(socket.timeout("timed out")), "timeout"),
    (urllib.error.HTTPError("u", 401, "Unauthorized", {}, None), "authentication"),
    (urllib.error.HTTPError("u", 403, "Forbidden", {}, None), "authentication"),
    (urllib.error.URLError(ConnectionRefusedError("refused")), "network"),
    (urllib.error.HTTPError("u", 500, "Server error", {}, None), "http"),
])
def test_transport_errors_fall_back_without_retry(fake, client, request_, error, kind):
    f = fake(error)
    result = explain(request_, client)
    assert result["source"] == "fallback" and len(f.requests) == 1
    assert f"FoundryError: {kind}:" in result["attempts"][0]["errors"][0]
    assert SECRET not in json.dumps(result)


# --- cache --------------------------------------------------------------------

def test_successful_online_response_is_served_from_cache(fake, client, replay):
    f = fake(chat_response(json.dumps(model_answer(build_request(replay.match, replay.snapshot(AT), "fan")))))
    cache = ExplanationCache()
    first = cached_explain(cache, build_request(replay.match, replay.snapshot(AT), "fan"), client)
    second = cached_explain(cache, build_request(replay.match, replay.snapshot(AT), "fan"), client)
    assert len(f.requests) == 1
    assert (first["source"], first["cache_hit"], second["cache_hit"]) == ("llm", False, True)
    assert second["explanation"] == first["explanation"] and second["attempts"] == first["attempts"]


def test_invalid_online_output_is_never_cached(fake, client, request_):
    bad = model_answer(request_, narrative="Harbor City have 99 shots.")
    fake(chat_response(json.dumps(bad)), chat_response(json.dumps(bad)))
    cache = ExplanationCache()
    result = cached_explain(cache, request_, client)
    cached = cache.get(request_)
    assert result["source"] == "fallback" and cached["explanation"]["source"] == "fallback"
    assert "99" not in json.dumps(cached["explanation"])
