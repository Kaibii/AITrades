from decimal import Decimal

import httpx
import pytest
from quantpilot.execution import (
    HistoricalPaperBroker,
    OrderIntent,
    OrderUpdate,
    validate_order_update,
)
from quantpilot.execution.alpaca import AlpacaPaperBroker, BrokerUnavailable, SubmissionUncertain

INTENT = OrderIntent(client_order_id="test-intent", symbol="AAPL", side="buy", quantity=2)


def test_replay_fill_costs():
    result = HistoricalPaperBroker(Decimal(100), Decimal(10), Decimal(5)).submit_order(INTENT)
    assert result.average_fill_price == Decimal("100.1")
    assert result.fee == Decimal("0.1001")
    assert result.filled_quantity == 2 and result.status == "filled"


def test_alpaca_submission_disabled_without_touching_network():
    def forbidden(request):
        pytest.fail("Disabled adapter must not send an HTTP request")

    with httpx.Client(transport=httpx.MockTransport(forbidden)) as client:
        broker = AlpacaPaperBroker("test", "test", client=client)
        with pytest.raises(BrokerUnavailable, match="disabled"):
            broker.submit_order(INTENT)


def test_timeout_reconciles_by_same_client_id_without_retrying_post():
    requests = []

    def respond(request):
        requests.append(request)
        assert request.url.host == "paper-api.alpaca.markets"
        if request.method == "POST":
            raise httpx.ReadTimeout("simulated dropped response")
        assert request.url.params["client_order_id"] == INTENT.client_order_id
        return httpx.Response(
            200,
            json={
                "id": "broker-id",
                "client_order_id": "test-intent",
                "status": "partially_filled",
                "filled_qty": "1",
                "filled_avg_price": "100",
            },
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        broker = AlpacaPaperBroker("test", "test", enabled=True, client=client)
        with pytest.raises(SubmissionUncertain):
            broker.submit_order(INTENT)
        update = broker.get_order(INTENT.client_order_id)
        assert update.status == "partially_filled" and update.filled_quantity == 1
    assert [r.method for r in requests] == ["POST", "GET"]


@pytest.mark.parametrize("status", [408, 500, 503])
def test_unknown_submission_outcome_is_distinct_from_rejection(status):
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(status))) as client:
        broker = AlpacaPaperBroker("test", "test", enabled=True, client=client)
        with pytest.raises(SubmissionUncertain):
            broker.submit_order(INTENT)


def test_malformed_successful_post_is_uncertain():
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={
                    "id": "broker-id",
                    "client_order_id": "test-intent",
                    "status": "filled",
                    "filled_qty": "999",
                    "filled_avg_price": "100",
                },
            )
        )
    ) as client:
        with pytest.raises(SubmissionUncertain):
            AlpacaPaperBroker("test", "test", enabled=True, client=client).submit_order(INTENT)


@pytest.mark.parametrize(
    "state,qty,price",
    [
        ("new", "0", None),
        ("partially_filled", "1", "100"),
        ("filled", "2", "100"),
        ("rejected", "0", None),
        ("canceled", "1", "100"),
        ("unfamiliar", "0", None),
    ],
)
def test_paper_order_states(state, qty, price):
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={
                    "id": "broker-id",
                    "client_order_id": "test-intent",
                    "status": state,
                    "filled_qty": qty,
                    "filled_avg_price": price,
                },
            )
        )
    ) as client:
        update = AlpacaPaperBroker("test", "test", client=client).get_order("test-intent")
    validate_order_update(INTENT, None, update)
    assert update.status == {"new": "accepted", "unfamiliar": "unknown"}.get(state, state)


def test_cumulative_order_updates_are_monotonic_and_terminal_states_stay_terminal():
    partial = OrderUpdate(
        client_order_id="test-intent",
        broker_order_id="broker-id",
        status="partially_filled",
        filled_quantity=1,
        average_fill_price=100,
    )
    filled = partial.model_copy(update={"status": "filled", "filled_quantity": Decimal(2)})
    validate_order_update(INTENT, partial, filled)
    validate_order_update(INTENT, filled, filled)  # Duplicate reconciliation is harmless.
    with pytest.raises(ValueError):
        validate_order_update(INTENT, filled, partial)
    with pytest.raises(ValueError):
        validate_order_update(
            INTENT, partial, partial.model_copy(update={"filled_quantity": Decimal("0.5")})
        )


def test_lookup_not_found_does_not_submit():
    methods = []

    def respond(request):
        methods.append(request.method)
        return httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        assert AlpacaPaperBroker("test", "test", client=client).get_order("test-intent") is None
    assert methods == ["GET"]
