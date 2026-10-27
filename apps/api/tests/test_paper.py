from datetime import date, timedelta
from decimal import Decimal

import pytest
from app.database import BacktestRun, PaperOrder, PaperSession, StrategyDraft
from app.paper import advance
from app.paper_worker import process_once
from pydantic import ValidationError
from quantpilot.backtesting import BacktestConfig, run_backtest
from quantpilot.market_data import Bar, Dataset
from quantpilot.risk import RiskLimits, order_breach, portfolio_breach
from sqlalchemy import select

SPEC = {
    "name": "Replay test",
    "description": "Daily SMA 2/3 crossover",
    "symbol": "AAPL",
    "timeframe": "1Day",
    "indicator": "SMA",
    "fast": 2,
    "slow": 3,
    "entry": "fast_crosses_above_slow",
    "exit": "fast_crosses_below_slow",
    "direction": "long_only",
}


def seed(client, database, closes=(10, 9, 8, 9, 11, 12, 9, 7), opens=None, **limits):
    opens = opens or closes
    data = Dataset(
        [
            Bar(
                date=date(2020, 1, 1) + timedelta(days=i),
                open=opens[i],
                close=close,
                high=max(opens[i], close) + 1,
                low=min(opens[i], close) - 1,
            )
            for i, close in enumerate(closes)
        ],
        "test",
        "none",
        "synthetic fixture",
    )
    draft = client.post("/api/strategy-drafts", json={"specification": SPEC}).json()
    draft = client.post(f"/api/strategy-drafts/{draft['id']}/approve", json={}).json()
    cfg = BacktestConfig(
        start="2020-01-01",
        end="2020-02-01",
        fast=2,
        slow=3,
        initial_cash=1000,
        commission_bps=0,
        slippage_bps=0,
    )
    result = run_backtest(cfg, data)
    result["strategy_draft"] = {"id": draft["id"], "specification": SPEC}
    with database() as db:
        run = BacktestRun(result=result)
        db.add(run)
        db.commit()
        run_id = run.id
    response = client.post(
        "/api/paper/sessions",
        json={
            "backtest_id": run_id,
            "limits": {
                "allocation_pct": 100,
                "max_position_pct": 100,
                "max_order_notional": 100000,
                "max_daily_loss_pct": 99,
                "max_drawdown_pct": 99,
                **limits,
            },
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_replay_exact_next_open_accounting_and_retry_idempotency(client, database):
    account = seed(client, database, opens=[10, 9, 8, 9, 11, 13, 9, 6])
    path = f"/api/paper/sessions/{account['id']}"
    response = client.post(f"{path}/advance", json={"expected_cursor": 0, "bars": 6})
    assert response.status_code == 200, response.text
    first = response.json()
    assert len(first["orders"]) == 1
    assert first["orders"][0]["market_date"] == "2020-01-06"
    assert Decimal(first["orders"][0]["price"]) == 13
    retried = client.post(f"{path}/advance", json={"expected_cursor": 0, "bars": 6}).json()
    assert retried == first
    final = client.post(f"{path}/advance", json={"expected_cursor": 6, "bars": 2}).json()
    assert final["status"] == "completed" and final["cursor"] == 8
    assert len(final["orders"]) == 2
    assert float(final["equity"]) == pytest.approx(461.538468)
    assert Decimal(final["quantity"]) == 0
    assert client.get(path).json() == final
    assert len({o["client_order_id"] for o in final["orders"]}) == 2


def test_future_bars_cannot_affect_first_ticks(client, database):
    a = seed(client, database, closes=[10, 9, 8, 9, 11, 12, 9, 7])
    b = seed(client, database, closes=[10, 9, 8, 9, 11, 12, 100, 7])
    histories = []
    for row in (a, b):
        r = client.post(
            f"/api/paper/sessions/{row['id']}/advance", json={"expected_cursor": 0, "bars": 6}
        ).json()
        histories.append(r["history"])
    assert histories[0] == histories[1]


def test_kill_switch_never_liquidates_and_blocks_new_ticks(client, database):
    row = seed(client, database)
    path = f"/api/paper/sessions/{row['id']}"
    held = client.post(f"{path}/advance", json={"expected_cursor": 0, "bars": 6}).json()
    assert Decimal(held["quantity"]) > 0
    stopped = client.post(f"{path}/stop", json={}).json()
    assert stopped["status"] == "stopped"
    assert stopped["cash"] == held["cash"] and stopped["quantity"] == held["quantity"]
    assert stopped["orders"] == held["orders"]
    assert client.post(f"{path}/start", json={}).status_code == 409
    assert client.post(f"{path}/advance", json={"expected_cursor": 6}).status_code == 409
    process_once(database, "stopped-test")
    assert client.get(path).json()["cursor"] == 6


def test_risk_breach_suspends_without_selling(client, database):
    row = seed(client, database, max_daily_loss_pct=5)
    path = f"/api/paper/sessions/{row['id']}"
    result = client.post(f"{path}/advance", json={"expected_cursor": 0, "bars": 8}).json()
    assert result["status"] == "suspended"
    assert Decimal(result["quantity"]) > 0
    assert [o["side"] for o in result["orders"]] == ["buy"]
    assert "daily loss" in result["risk_events"][0]["reason"]
    assert client.post(f"{path}/start", json={}).status_code == 409


def test_worker_restart_uses_durable_cursor_and_skips_paused(client, database):
    row = seed(client, database)
    path = f"/api/paper/sessions/{row['id']}"
    assert process_once(database, "first-worker") == 0
    client.post(f"{path}/start", json={})
    assert process_once(database, "first-worker") == 1
    assert process_once(database, "restarted-worker") == 1
    assert client.get(path).json()["cursor"] == 2
    assert client.get("/api/paper/status").json()["worker_recent"] is True
    client.post(f"{path}/pause", json={})
    assert process_once(database, "restarted-worker") == 0
    assert client.get(path).json()["cursor"] == 2


def test_rollback_recovers_cash_orders_and_cursor_atomically(client, database):
    row = seed(client, database)
    with database() as db:
        advance(db, row["id"], 0, 6)
        db.rollback()  # Simulates interruption before commit.
    with database() as db:
        persisted = db.get(PaperSession, row["id"])
        assert persisted.cursor == 0 and persisted.cash == 1000
        assert not list(db.scalars(select(PaperOrder)))
        advance(db, row["id"], 0, 6)
        db.commit()
    result = client.get(f"/api/paper/sessions/{row['id']}").json()
    assert len(result["orders"]) == 1 and result["cursor"] == 6


def test_rejected_exit_preserves_cash_and_holding(client, database):
    row = seed(client, database, opens=[10, 9, 8, 9, 11, 12, 9, 30], max_order_notional=200)
    path = f"/api/paper/sessions/{row['id']}"
    before = client.post(f"{path}/advance", json={"expected_cursor": 0, "bars": 7}).json()
    after = client.post(f"{path}/advance", json={"expected_cursor": 7}).json()
    assert after["status"] == "suspended"
    assert after["quantity"] == before["quantity"] and after["cash"] == before["cash"]
    rejected = after["orders"][-1]
    assert rejected["status"] == "rejected" and Decimal(rejected["filled_quantity"]) == 0
    assert "notional" in rejected["reason"]


def test_worker_refuses_external_execution_mode_even_if_database_is_changed(client, database):
    row = seed(client, database)
    with database() as db:
        account = db.get(PaperSession, row["id"])
        account.mode, account.status = "alpaca", "running"
        db.commit()
    assert process_once(database, "mode-guard") == 0
    result = client.get(f"/api/paper/sessions/{row['id']}").json()
    assert result["status"] == "suspended" and not result["orders"] and result["cursor"] == 0


def test_manual_backtest_or_unapproved_draft_cannot_start_replay(client, database):
    manual = client.post("/api/backtests", json={}).json()
    assert client.post("/api/paper/sessions", json={"backtest_id": manual["id"]}).status_code == 409
    row = seed(client, database)
    with database() as db:
        draft = db.get(StrategyDraft, row["draft_id"])
        draft.approved_at = None
        db.commit()
    assert (
        client.post("/api/paper/sessions", json={"backtest_id": row["backtest_id"]}).status_code
        == 409
    )
    assert (
        client.post(
            "/api/paper/sessions", json={"backtest_id": row["backtest_id"], "mode": "live"}
        ).status_code
        == 422
    )


@pytest.mark.parametrize(
    "change",
    [
        {"max_drawdown_pct": 0},
        {"allocation_pct": 50},
        {"max_order_notional": "NaN"},
        {"execute_live": True},
    ],
)
def test_invalid_risk_limits(change):
    with pytest.raises(ValidationError):
        RiskLimits(**change)


@pytest.mark.parametrize(
    "overrides,expected",
    [
        ({"quantity": Decimal(1000)}, "notional"),
        ({"cash": Decimal(1)}, "buying power"),
        ({"current_quantity": Decimal(20)}, "position exposure"),
        ({"orders_this_bar": 1}, "frequency"),
        ({"side": "sell", "quantity": Decimal(2), "current_quantity": Decimal(1)}, "Short"),
    ],
)
def test_deterministic_pretrade_rejections(overrides, expected):
    args = dict(
        side="buy",
        quantity=Decimal(1),
        price=Decimal(100),
        fee=Decimal(0),
        cash=Decimal(1000),
        current_quantity=Decimal(0),
        equity=Decimal(1000),
        orders_this_bar=0,
        limits=RiskLimits(),
    )
    assert expected in order_breach(**{**args, **overrides})


def test_portfolio_risk_thresholds():
    limits = RiskLimits()
    assert "drawdown" in portfolio_breach(Decimal(89), Decimal(100), Decimal(89), limits)
    assert "daily loss" in portfolio_breach(Decimal(98), Decimal(100), Decimal(100), limits)
    assert portfolio_breach(Decimal(100), Decimal(100), Decimal(100), limits) is None
