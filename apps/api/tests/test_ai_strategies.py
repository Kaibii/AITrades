import json

import httpx
import pytest
from app.main import app
from app.strategy_routes import get_generator
from pydantic import SecretStr, ValidationError
from quantpilot.ai import GenerationError, OpenAIStrategyGenerator, Proposal, StrategySpec

SPEC = {
    "name": "AAPL daily crossover",
    "description": "Buy the 20/50 bullish crossover; exit on bearish.",
    "symbol": "AAPL",
    "timeframe": "1Day",
    "indicator": "SMA",
    "fast": 20,
    "slow": 50,
    "entry": "fast_crosses_above_slow",
    "exit": "fast_crosses_below_slow",
    "direction": "long_only",
}
PROMPT = "Buy AAPL when its daily 20-day SMA crosses above the 50-day SMA and sell on the reverse."


class FixedGenerator:
    def generate(self, prompt):
        assert prompt == PROMPT
        return Proposal(
            status="supported",
            explanation="Daily long-only SMA crossover.",
            specification=StrategySpec(**SPEC),
        )


@pytest.mark.parametrize(
    "change",
    [
        {"indicator": "RSI"},
        {"timeframe": "1Min"},
        {"fast": 50},
        {"fast": 20.1},
        {"direction": "short"},
        {"entry": "eval(user_code)"},
        {"execute_live": True},
        {"allocation": 1},
        {"stop_loss": 0.1},
        {"symbol": "AAPL,SPY"},
    ],
)
def test_restricted_schema_rejects_unsupported_or_risk_fields(change):
    with pytest.raises(ValidationError):
        StrategySpec(**{**SPEC, **change})


def test_provider_uses_structured_outputs_without_tools_or_storage():
    def respond(request):
        body = json.loads(request.content)
        assert request.url == "https://api.openai.com/v1/responses"
        assert body["store"] is False
        assert body["text"]["format"]["type"] == "json_schema"
        assert body["text"]["format"]["strict"] is True
        assert not body.get("tools")
        assert body["input"] == [{"role": "user", "content": PROMPT}]
        return httpx.Response(
            200,
            json={
                "id": "resp_test",
                "object": "response",
                "created_at": 1,
                "status": "completed",
                "model": "gpt-4.1-mini",
                "error": None,
                "incomplete_details": None,
                "output": [
                    {
                        "type": "message",
                        "id": "msg_test",
                        "status": "completed",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(
                                    {
                                        "status": "supported",
                                        "explanation": "Supported SMA.",
                                        "specification": SPEC,
                                    }
                                ),
                                "annotations": [],
                            }
                        ],
                    }
                ],
            },
        )

    provider = OpenAIStrategyGenerator(
        "test-only", "gpt-4.1-mini", httpx.Client(transport=httpx.MockTransport(respond))
    )
    assert provider.generate(PROMPT).specification.fast == 20


def test_provider_errors_do_not_expose_credentials_or_response_body():
    provider = OpenAIStrategyGenerator(
        "test-only",
        "gpt-4.1-mini",
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    401,
                    json={
                        "error": {
                            "message": "sensitive-provider-details",
                            "type": "invalid_api_key",
                        }
                    },
                )
            )
        ),
    )
    with pytest.raises(GenerationError) as exc:
        provider.generate(PROMPT)
    assert "sensitive" not in str(exc.value)
    assert "test-only" not in str(exc.value)


def test_real_generation_requires_key_and_never_fakes_a_draft(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "ai_api_key", SecretStr(""))
    response = client.post("/api/strategy-drafts/generate", json={"prompt": PROMPT})
    assert response.status_code == 503
    assert client.get("/api/strategy-drafts").json() == []


def test_generate_review_approve_and_backtest_exact_version(client):
    app.dependency_overrides[get_generator] = lambda: FixedGenerator()
    result = client.post("/api/strategy-drafts/generate", json={"prompt": PROMPT})
    assert result.status_code == 200, result.text
    draft = result.json()["draft"]
    assert draft["origin"] == "ai" and draft["approved_at"] is None
    path = f"/api/strategy-drafts/{draft['id']}"
    assert client.post(f"{path}/backtests", json={}).status_code == 409
    approved = client.post(f"{path}/approve", json={}).json()
    assert approved["approved_at"]
    assert client.post(f"{path}/approve", json={}).json() == approved
    result = client.post(f"{path}/backtests", json={})
    assert result.status_code == 201, result.text
    backtest = result.json()
    assert backtest["configuration"]["fast"] == 20
    assert backtest["strategy_draft"]["id"] == draft["id"]
    assert backtest["strategy_draft"]["specification"] == SPEC
    assert client.get(f"/api/backtests/{backtest['id']}").json() == backtest
    assert client.post(f"{path}/backtests", json={"fast": 10}).status_code == 422
    assert client.post(f"{path}/backtests", json={"execute_live": True}).status_code == 422


def test_edit_creates_unapproved_version_preserving_approved_parent(client):
    original = client.post("/api/strategy-drafts", json={"specification": SPEC}).json()
    path = f"/api/strategy-drafts/{original['id']}"
    client.post(f"{path}/approve", json={})
    edited = client.post(
        "/api/strategy-drafts",
        json={
            "specification": {**SPEC, "fast": 10},
            "parent_id": original["id"],
        },
    ).json()
    assert edited["id"] != original["id"]
    assert edited["parent_id"] == original["id"] and edited["approved_at"] is None
    assert client.post(f"/api/strategy-drafts/{edited['id']}/backtests", json={}).status_code == 409
    assert client.get(path).json()["specification"]["fast"] == 20
    assert len(client.get("/api/strategy-drafts").json()) == 2
    assert client.patch(path, json={"specification": SPEC}).status_code == 405


def test_unsupported_generation_does_not_persist_or_run(client):
    class UnsupportedGenerator:
        def generate(self, prompt):
            return Proposal(
                status="unsupported", explanation="RSI is not supported yet.", specification=None
            )

    app.dependency_overrides[get_generator] = lambda: UnsupportedGenerator()
    result = client.post("/api/strategy-drafts/generate", json={"prompt": "Create an RSI strategy"})
    assert result.json()["status"] == "unsupported" and result.json()["draft"] is None
    assert client.get("/api/strategy-drafts").json() == []
    assert client.get("/api/backtests").json() == []


def test_invalid_provider_output_does_not_persist(client):
    class InvalidGenerator:
        def generate(self, prompt):
            return Proposal(
                status="supported",
                explanation="Invalid RSI",
                specification={**SPEC, "indicator": "RSI"},
            )

    app.dependency_overrides[get_generator] = lambda: InvalidGenerator()
    assert client.post("/api/strategy-drafts/generate", json={"prompt": PROMPT}).status_code == 502
    assert client.get("/api/strategy-drafts").json() == []


def test_draft_input_and_unknown_ids(client):
    assert (
        client.post(
            "/api/strategy-drafts", json={"specification": {**SPEC, "indicator": "RSI"}}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/strategy-drafts", json={"specification": SPEC, "approved_at": "2020-01-01"}
        ).status_code
        == 422
    )
    path = "/api/strategy-drafts/00000000-0000-0000-0000-000000000000"
    assert client.get(path).status_code == 404
    assert client.post(f"{path}/approve", json={}).status_code == 404
