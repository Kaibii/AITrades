"""Functional smoke test against a running API and migrated PostgreSQL database."""

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

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
    replay = client.post(
        "/api/paper/sessions",
        json={
            "backtest_id": run.json()["id"],
            "limits": {"max_daily_loss_pct": 90, "max_drawdown_pct": 90},
        },
    )
    assert replay.status_code == 201, replay.text
    paper_path = f"/api/paper/sessions/{replay.json()['id']}"
    for cursor in (0, 100):

        def duplicate_advance(_, expected=cursor):
            return client.post(
                f"{paper_path}/advance", json={"expected_cursor": expected, "bars": 100}
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(duplicate_advance, range(2)))
        assert all(r.status_code == 200 for r in responses), [r.text for r in responses]
        assert all(r.json()["cursor"] == cursor + 100 for r in responses)
        assert responses[0].json()["orders"] == responses[1].json()["orders"]
    advanced = client.get(paper_path).json()
    assert len(advanced["orders"]) == 1 and float(advanced["quantity"]) > 0
    client.post(f"{paper_path}/start", json={}).raise_for_status()
    subprocess.run([sys.executable, "-m", "app.paper_worker", "--once"], check=True)
    paused = client.post(f"{paper_path}/pause", json={}).json()
    assert paused["cursor"] > 200
    stopped = client.post(f"{paper_path}/stop", json={}).json()
    assert stopped["status"] == "stopped" and stopped["quantity"] == paused["quantity"]
    assert stopped["orders"] == paused["orders"]
    assert (
        client.post(
            f"{paper_path}/advance", json={"expected_cursor": stopped["cursor"]}
        ).status_code
        == 409
    )
print(
    "PASS: historical simulation, PostgreSQL persistence, draft approval gate, versioned backtest, "
    "concurrent replay idempotency, worker restart, emergency stop. No brokerage orders. "
    "AI generation is covered separately by mocked tests."
)
