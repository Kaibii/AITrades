import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from importlib.resources import files
from typing import Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator


class DataError(ValueError):
    pass


class Bar(BaseModel):
    model_config = ConfigDict(frozen=True, allow_inf_nan=False)
    date: date
    open: Decimal = Field(gt=0)
    high: Decimal = Field(gt=0)
    low: Decimal = Field(gt=0)
    close: Decimal = Field(gt=0)
    volume: Decimal = Field(default=Decimal(0), ge=0)

    @model_validator(mode="after")
    def valid_ohlc(self):
        if self.low > min(self.open, self.close) or self.high < max(self.open, self.close):
            raise ValueError("Invalid OHLC range")
        return self


@dataclass(frozen=True)
class Dataset:
    bars: list[Bar]
    source: str
    adjustment: str
    license_note: str

    @property
    def version(self) -> str:
        content = [bar.model_dump(mode="json") for bar in self.bars]
        return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()


class MarketDataProvider(Protocol):
    def history(self, symbol: str, start: date, end: date) -> Dataset: ...


class SampleProvider:
    def history(self, symbol: str, start: date, end: date) -> Dataset:
        if symbol != "AAPL":
            raise DataError("Bundled historical sample supports AAPL only. Choose Alpaca for SPY.")
        rows = csv.DictReader(files(__package__).joinpath("aapl.csv").read_text().splitlines())
        bars = []
        for row in rows:
            day = date.fromisoformat(row["Date"])
            if start <= day <= end:
                # Apply the same adjusted-close factor to all price fields.
                factor = Decimal(row["AAPL.Adjusted"]) / Decimal(row["AAPL.Close"])
                bars.append(
                    Bar(
                        date=day,
                        volume=Decimal(row["AAPL.Volume"]),
                        **{
                            key: Decimal(row[f"AAPL.{key.title()}"]) * factor
                            for key in ("open", "high", "low", "close")
                        },
                    )
                )
        return Dataset(
            bars,
            "Plotly historical AAPL sample (2015-02-17 through 2017-02-16)",
            "OHLC scaled by supplied adjusted-close / close; hypothetical adjusted-share units. "
            "Dividends are implicit in the adjustment, not separate cash payments.",
            "Public research example; upstream accuracy and redistribution rights "
            "are not certified.",
        )


class AlpacaProvider:
    def __init__(self, key: str, secret: str, client: httpx.Client | None = None):
        self.key, self.secret, self.client = key, secret, client

    def history(self, symbol: str, start: date, end: date) -> Dataset:
        if not self.key or not self.secret:
            raise DataError(
                "Alpaca history requires APCA_API_KEY_ID and APCA_API_SECRET_KEY on the server."
            )
        client = self.client or httpx.Client(timeout=25)
        bars: list[Bar] = []
        params = {
            "timeframe": "1Day",
            "start": f"{start}T00:00:00Z",
            "end": f"{end}T23:59:59Z",
            "adjustment": "all",
            "feed": "iex",
            "limit": "10000",
            "sort": "asc",
        }
        seen_tokens: set[str] = set()
        try:
            while True:
                response = client.get(
                    f"https://data.alpaca.markets/v2/stocks/{symbol}/bars",
                    params=params,
                    headers={"APCA-API-KEY-ID": self.key, "APCA-API-SECRET-KEY": self.secret},
                )
                if response.status_code != 200:
                    raise DataError(
                        f"Alpaca returned HTTP {response.status_code}. Check credentials, "
                        "IEX data entitlement and requested dates. No sample data substituted."
                    )
                payload = response.json()
                if not isinstance(payload, dict) or not isinstance(payload.get("bars") or [], list):
                    raise DataError("Provider returned an invalid bars response")
                for row in payload.get("bars") or []:
                    bars.append(
                        Bar(
                            date=row["t"][:10],
                            open=row["o"],
                            high=row["h"],
                            low=row["l"],
                            close=row["c"],
                            volume=row["v"],
                        )
                    )
                token = payload.get("next_page_token")
                if token is None or token == "":
                    break
                if not isinstance(token, str):
                    raise DataError("Provider returned an invalid pagination token")
                if token in seen_tokens or len(bars) > 6000 or len(seen_tokens) >= 10:
                    raise DataError("Provider pagination exceeded supported bounds")
                seen_tokens.add(token)
                params["page_token"] = token
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, DataError):
                raise
            raise DataError("Unable to load valid historical data from Alpaca") from None
        finally:
            if self.client is None:
                client.close()
        return Dataset(
            bars,
            "Alpaca daily IEX bars",
            "Provider adjustment=all; adjusted OHLC research series, "
            "dividends implicit; no separate dividend cash flows.",
            "Requires user data entitlements. IEX is not consolidated market coverage. "
            "No commercial redistribution rights are implied.",
        )
