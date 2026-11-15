import json

import httpx
import pytest
from audit_copilot.config import Settings
from audit_copilot.models import EvidenceReport
from audit_copilot.providers import LLM, Budget


@pytest.fixture(autouse=True)
def keys(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-not-real")
    monkeypatch.setenv("GEMINI_API_KEY", "test-not-real")


@pytest.mark.parametrize("provider", ["openai", "gemini"])
async def test_provider_contract(provider):
    def handle(req):
        body = json.loads(req.content)
        text = json.dumps({"facts": [], "summary": "No evidence"})
        assert "test-not-real" not in req.url.query.decode()
        if provider == "openai":
            assert body["response_format"]["type"] == "json_object"
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": text}}],
                    "usage": {"total_tokens": 42},
                },
            )
        assert req.headers["x-goog-api-key"] == "test-not-real"
        return httpx.Response(
            200,
            json={
                "candidates": [{"content": {"parts": [{"text": text}]}}],
                "usageMetadata": {"totalTokenCount": 42},
            },
        )

    llm = LLM(Settings(provider=provider), transport=httpx.MockTransport(handle))
    assert (await llm.generate("Evidence", [], EvidenceReport)).summary == "No evidence"
    assert llm.budget.calls == 1
    assert llm.budget.usage[0]["cost_usd"] is None


async def test_transient_failover():
    counts = {"openai": 0, "gemini": 0}

    def handle(req):
        if req.url.host == "api.openai.com":
            counts["openai"] += 1
            return httpx.Response(429, json={})
        counts["gemini"] += 1
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": '{"facts":[],"summary":"Fallback"}'}]
                        }
                    }
                ]
            },
        )

    llm = LLM(Settings(fallback="gemini"), transport=httpx.MockTransport(handle))
    assert (await llm.generate("Evidence", [], EvidenceReport)).summary == "Fallback"
    assert counts == {"openai": 2, "gemini": 1}


async def test_auth_and_schema_failures_not_retried():
    for status in (400, 401, 403):
        llm = LLM(
            Settings(fallback="gemini"),
            transport=httpx.MockTransport(
                lambda r, status=status: httpx.Response(status, json={})
            ),
        )
        with pytest.raises(httpx.HTTPStatusError):
            await llm.generate("Evidence", [], EvidenceReport)
        assert llm.budget.calls == 1
    llm = LLM(
        Settings(),
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                200, json={"choices": [{"message": {"content": '{"unexpected":true}'}}]}
            )
        ),
    )
    with pytest.raises(ValueError):
        await llm.generate("Evidence", [], EvidenceReport)
    assert llm.budget.calls == 1


def test_budget():
    b = Budget(max_calls=1, max_input_chars=10)
    b.spend(5)
    with pytest.raises(ValueError):
        b.spend(1)
    with pytest.raises(ValueError):
        Budget(max_input_chars=1).spend(2)


def test_cost_requires_explicit_rates(monkeypatch):
    from audit_copilot.providers import cost_for

    monkeypatch.delenv("COPILOT_PRICES_JSON", raising=False)
    assert cost_for("openai", {"prompt_tokens": 100, "completion_tokens": 50}) is None
    monkeypatch.setenv(
        "COPILOT_PRICES_JSON",
        '{"openai":{"input_per_million":1,"output_per_million":2}}',
    )
    assert cost_for("openai", {"prompt_tokens": 100, "completion_tokens": 50}) == 0.0002
