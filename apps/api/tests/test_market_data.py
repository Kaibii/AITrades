from datetime import date

import httpx
import pytest
from quantpilot.market_data import AlpacaProvider, DataError, SampleProvider


def test_sample_rejects_other_symbols():
    with pytest.raises(DataError, match="AAPL only"):
        SampleProvider().history("SPY", date(2015, 1, 1), date(2017, 1, 1))


def test_alpaca_requires_credentials():
    with pytest.raises(DataError, match="requires"):
        AlpacaProvider("", "").history("SPY", date(2020, 1, 1), date(2020, 2, 1))


def test_alpaca_pagination_and_adjustment():
    calls = []

    def handler(request):
        calls.append(request)
        assert request.url.host == "data.alpaca.markets"
        assert request.url.params["adjustment"] == "all"
        assert request.url.params["feed"] == "iex"
        assert request.headers["APCA-API-KEY-ID"] == "test-only"
        page = "page_token" in request.url.params
        return httpx.Response(
            200,
            json={
                "bars": [
                    {
                        "t": "2020-01-03T05:00:00Z" if page else "2020-01-02T05:00:00Z",
                        "o": 10,
                        "h": 12,
                        "l": 9,
                        "c": 11,
                        "v": 123,
                    }
                ],
                "next_page_token": None if page else "second",
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        data = AlpacaProvider("test-only", "test-only", client).history(
            "SPY", date(2020, 1, 1), date(2020, 2, 1)
        )
    assert len(calls) == len(data.bars) == 2
    assert calls[1].url.params["page_token"] == "second"


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_provider_errors_do_not_expose_response_or_substitute_sample(status):
    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(status, text="sensitive-provider-details")
            )
        ) as client,
        pytest.raises(DataError) as exc,
    ):
        AlpacaProvider("test-only", "test-only", client).history(
            "SPY", date(2020, 1, 1), date(2020, 2, 1)
        )
    assert str(status) in str(exc.value)
    assert "sensitive" not in str(exc.value)


@pytest.mark.parametrize("payload", [[], {"bars": "invalid"}, {"bars": [], "next_page_token": []}])
def test_malformed_provider_response_rejected(payload):
    with (
        httpx.Client(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
        ) as client,
        pytest.raises(DataError),
    ):
        AlpacaProvider("test-only", "test-only", client).history(
            "SPY", date(2020, 1, 1), date(2020, 2, 1)
        )


def test_repeated_pagination_token_rejected():
    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"bars": [], "next_page_token": "same"})
            )
        ) as client,
        pytest.raises(DataError, match="pagination"),
    ):
        AlpacaProvider("test-only", "test-only", client).history(
            "SPY", date(2020, 1, 1), date(2020, 2, 1)
        )
