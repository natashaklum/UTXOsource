"""Sprint 1: EUR price oracle (mocked HTTP, no network in tests)."""

import datetime
import sqlite3
from decimal import Decimal

import httpx

from utxoproof.db import open_memory_db
from utxoproof.price_oracle import EURPriceOracle


def _kraken_candle(date: datetime.date, close: str) -> dict:
    ts = int(datetime.datetime(date.year, date.month, date.day, tzinfo=datetime.UTC).timestamp())
    return {"error": [], "result": {"XXBTZEUR": [[ts, "1", "1", "1", close, "1", "1", 0]]}}


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _oracle(handler) -> tuple[EURPriceOracle, sqlite3.Connection, dict[str, int]]:
    calls: dict[str, int] = {"n": 0}
    base_handler = handler

    def counting(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return base_handler(request)

    db = open_memory_db()
    return EURPriceOracle(db, _client(counting)), db, calls


def test_kraken_close_and_cache() -> None:
    day = datetime.date(2023, 1, 10)

    def handler(request: httpx.Request) -> httpx.Response:
        assert "OHLC" in request.url.path
        return httpx.Response(200, json=_kraken_candle(day, "20000.5"))

    oracle, _, calls = _oracle(handler)
    assert oracle.get_btc_eur(day) == Decimal("20000.5")
    assert oracle.get_btc_eur(day) == Decimal("20000.5")
    assert calls["n"] == 1  # second call served from SQLite cache


def test_coingecko_fallback_on_kraken_error() -> None:
    from decimal import Decimal

    day = datetime.date(2023, 1, 10)

    def handler(request: httpx.Request) -> httpx.Response:
        if "OHLC" in request.url.path:
            return httpx.Response(200, json={"error": ["EGeneral:bad"], "result": {}})
        return httpx.Response(200, json={"market_data": {"current_price": {"eur": 19950.25}}})

    oracle, db, _ = _oracle(handler)
    assert oracle.get_btc_eur(day) == Decimal("19950.25")
    row = db.execute("SELECT source FROM price_cache WHERE pair='BTC/EUR'").fetchone()
    assert row == ("coingecko",)


def test_ecb_weekend_carries_friday_rate() -> None:
    from decimal import Decimal

    saturday = datetime.date(2023, 1, 14)  # a Saturday

    def handler(request: httpx.Request) -> httpx.Response:
        assert "ecb.europa.eu" in str(request.url)
        return httpx.Response(
            200,
            text="TIME_PERIOD,OBS_VALUE\n2023-01-13,1.0800\n2023-01-12,1.0750\n",
        )

    oracle, _, _ = _oracle(handler)
    # 1/1.08 USD->EUR factor from Friday's publication.
    assert oracle.get_fiat_eur("USD", saturday) == Decimal("1") / Decimal("1.0800")
