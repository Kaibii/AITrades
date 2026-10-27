"""Alpaca PAPER adapter foundation. Not wired into the replay worker or API."""

import httpx

from quantpilot.execution import OrderIntent, OrderUpdate, validate_order_update


class BrokerUnavailable(ValueError):
    pass


class SubmissionUncertain(BrokerUnavailable):
    """A POST may have reached the broker. Reconcile by client ID; never blindly resubmit."""


class AlpacaPaperBroker:
    BASE = "https://paper-api.alpaca.markets"

    def __init__(
        self, key: str, secret: str, *, enabled: bool = False, client: httpx.Client | None = None
    ):
        self.key, self.secret, self.enabled, self.client = key, secret, enabled, client

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        if not self.key or not self.secret:
            raise BrokerUnavailable("Alpaca paper credentials are required")
        client = self.client or httpx.Client(timeout=15)
        try:
            return client.request(
                method,
                self.BASE + path,
                headers={
                    "APCA-API-KEY-ID": self.key,
                    "APCA-API-SECRET-KEY": self.secret,
                },
                **kwargs,
            )
        except httpx.HTTPError:
            if method == "POST":
                raise SubmissionUncertain(
                    "Paper submission outcome unknown; reconcile by client ID"
                ) from None
            raise BrokerUnavailable("Unable to reach Alpaca paper API") from None
        finally:
            if self.client is None:
                client.close()

    @staticmethod
    def _update(response: httpx.Response) -> OrderUpdate:
        try:
            row = response.json()
            statuses = {
                "new": "accepted",
                "accepted": "accepted",
                "pending_new": "accepted",
                "partially_filled": "partially_filled",
                "filled": "filled",
                "rejected": "rejected",
                "canceled": "canceled",
                "expired": "canceled",
            }
            return OrderUpdate(
                client_order_id=row["client_order_id"],
                broker_order_id=row["id"],
                status=statuses.get(row["status"], "unknown"),
                filled_quantity=row["filled_qty"],
                average_fill_price=row.get("filled_avg_price"),
            )
        except (ValueError, TypeError, KeyError):
            raise BrokerUnavailable(
                "Invalid paper order response; reconciliation required"
            ) from None

    def submit_order(self, intent: OrderIntent) -> OrderUpdate:
        if not self.enabled:
            raise BrokerUnavailable("Alpaca paper submission is disabled")
        # Exactly one POST. Callers must journal the intent before calling and reconcile
        # uncertain outcomes with get_order(), never retry this method after a timeout.
        response = self._request(
            "POST",
            "/v2/orders",
            json={
                "symbol": intent.symbol,
                "side": intent.side,
                "qty": str(intent.quantity),
                "type": "market",
                "time_in_force": "day",
                "client_order_id": intent.client_order_id,
            },
        )
        if response.status_code >= 500 or response.status_code == 408:
            raise SubmissionUncertain("Paper submission outcome unknown; reconcile by client ID")
        if response.status_code not in (200, 201):
            raise BrokerUnavailable(
                f"Paper broker returned HTTP {response.status_code}; inspect order state"
            )
        try:
            update = self._update(response)
            validate_order_update(intent, None, update)
        except ValueError:
            raise SubmissionUncertain(
                "Invalid paper submission response; reconcile before proceeding"
            ) from None
        return update

    def get_order(self, client_order_id: str) -> OrderUpdate | None:
        response = self._request(
            "GET",
            "/v2/orders:by_client_order_id",
            params={
                "client_order_id": client_order_id,
            },
        )
        if response.status_code == 404:
            # Not found is not evidence that a preceding timed-out submission failed.
            return None
        if response.status_code != 200:
            raise BrokerUnavailable(f"Paper reconciliation returned HTTP {response.status_code}")
        return self._update(response)

    def cancel_order(self, broker_order_id: str) -> None:
        if not self.enabled:
            raise BrokerUnavailable("Alpaca paper cancellation is disabled")
        from uuid import UUID

        order_id = str(UUID(broker_order_id))
        response = self._request("DELETE", f"/v2/orders/{order_id}")
        if response.status_code not in (200, 204):
            raise BrokerUnavailable(f"Paper cancellation returned HTTP {response.status_code}")

    def get_account(self) -> dict:
        response = self._request("GET", "/v2/account")
        if response.status_code != 200:
            raise BrokerUnavailable(f"Paper account returned HTTP {response.status_code}")
        row = response.json()
        return {
            key: row[key] for key in ("id", "cash", "equity", "buying_power", "trading_blocked")
        }
