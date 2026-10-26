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
print("PASS: health, 506-bar simulation, 5 completed trades, persistence, validation, no orders")
