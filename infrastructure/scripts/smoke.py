"""Functional smoke test against a running API and migrated PostgreSQL database."""

import os

import httpx

base = os.environ.get("SMOKE_API_URL", "http://127.0.0.1:8000")
with httpx.Client(base_url=base, timeout=30) as client:
    health = client.get("/health")
    health.raise_for_status()
    assert health.json()["live_trading_enabled"] is False
    response = client.post("/api/backtests", json={})
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["data"]["bars"] == 506
    assert result["metrics"]["completed_trades"] == 5
    assert len(result["equity_curve"]) == 506
    fetched = client.get(f"/api/backtests/{result['id']}")
    fetched.raise_for_status()
    assert fetched.json() == result
    assert any(r["id"] == result["id"] for r in client.get("/api/backtests").json())
    invalid = client.post("/api/backtests", json={"fast": 50, "slow": 20})
    assert invalid.status_code == 422
    assert client.post("/api/orders", json={}).status_code == 404
    spec = {
        "name": "Manual smoke-test version",
        "description": "Daily AAPL SMA 20/50 crossover.",
        "symbol": "AAPL",
        "timeframe": "1Day",
        "indicator": "SMA",
        "fast": 20,
        "slow": 50,
        "entry": "fast_crosses_above_slow",
        "exit": "fast_crosses_below_slow",
        "direction": "long_only",
    }
    saved = client.post("/api/strategy-drafts", json={"specification": spec})
    assert saved.status_code == 201, saved.text
    draft = saved.json()
    path = f"/api/strategy-drafts/{draft['id']}"
    assert client.post(f"{path}/backtests", json={}).status_code == 409
    approved = client.post(f"{path}/approve", json={})
    approved.raise_for_status()
    assert approved.json()["approved_at"]
    run = client.post(f"{path}/backtests", json={})
    assert run.status_code == 201, run.text
    assert run.json()["strategy_draft"]["specification"] == spec
    assert run.json()["strategy_draft"]["id"] == draft["id"]
print(
    "PASS: historical simulation, PostgreSQL persistence, draft approval gate, versioned backtest, "
    "validation, no orders. AI generation is covered separately by mocked tests."
)
