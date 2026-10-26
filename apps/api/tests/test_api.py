import pytest
from app.database import Base, get_session
from app.main import app
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)

    def session():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_session] = session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()


def test_api_runs_persists_and_retrieves(client):
    assert client.get("/health").json()["live_trading_enabled"] is False
    response = client.post("/api/backtests", json={})
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["data"]["bars"] == 506
    assert result["trades"]
    assert client.get(f"/api/backtests/{result['id']}").json() == result
    assert client.get("/api/backtests").json()[0]["id"] == result["id"]


def test_api_validation_and_missing_run(client):
    assert client.post("/api/backtests", json={"fast": 50, "slow": 20}).status_code == 422
    assert client.post("/api/backtests", json={"symbol": "SPY"}).status_code == 422
    assert client.get("/api/backtests/00000000-0000-0000-0000-000000000000").status_code == 404
    assert client.get("/api/backtests/not-a-uuid").status_code == 422
    assert client.post("/api/orders", json={}).status_code == 404
