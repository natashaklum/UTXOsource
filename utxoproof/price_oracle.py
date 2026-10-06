"""EUR price oracle (plan Sec. 7).

BTC/EUR daily close: Kraken OHLC, CoinGecko fallback. Non-EUR fiat: ECB daily
reference rates (most recent prior publication for weekends/holidays).
Everything is cached in the SQLite ``price_cache`` table; tests inject a mock
``httpx.Client`` so no test touches the network.
"""

from __future__ import annotations

import datetime
import sqlite3
from decimal import Decimal
from pathlib import Path

import httpx

KRAKEN_OHLC_URL = "https://api.kraken.com/0/public/OHLC"
COINGECKO_HISTORY_URL = "https://api.coingecko.com/api/v3/coins/bitcoin/history"
ECB_URL_TEMPLATE = (
    "https://data-api.ecb.europa.eu/service/data/EXR/D.{currency}.EUR.SP00.A?format=csvdata"
)


class PriceOracleError(RuntimeError):
    pass


def _first_value(row: dict[str, str]) -> str:
    for key, value in row.items():
        if key not in ("date", "source") and value not in (None, ""):
            return str(value)
    return ""


class EURPriceOracle:
    def __init__(self, db: sqlite3.Connection, client: httpx.Client | None = None) -> None:
        self._db = db
        self._client = client or httpx.Client(timeout=30.0)

    # -- public API ----------------------------------------------------

    def get_btc_eur(self, date: datetime.date) -> Decimal:
        """BTC/EUR daily close. Cache -> Kraken -> CoinGecko."""
        cached = self._cached(date.isoformat(), "BTC/EUR")
        if cached is not None:
            return cached
        try:
            price = self._kraken_btc_eur(date)
            source = "kraken"
        except PriceOracleError:
            price = self._coingecko_btc_eur(date)
            source = "coingecko"
        self._store(date.isoformat(), "BTC/EUR", price, source)
        return price

    def get_fiat_eur(self, currency: str, date: datetime.date) -> Decimal:
        """Fiat/EUR rate. Cache -> ECB reference rates."""
        currency = currency.upper()
        if currency == "EUR":
            return Decimal("1")
        cached = self._cached(date.isoformat(), f"{currency}/EUR")
        if cached is not None:
            return cached
        price = self._ecb_fiat_eur(currency, date)
        self._store(date.isoformat(), f"{currency}/EUR", price, "ecb")
        return price

    def to_eur(
        self,
        amount: Decimal,
        currency: str,
        date: datetime.date,
    ) -> Decimal:
        currency = currency.upper()
        if currency == "EUR":
            return amount
        if currency in ("BTC", "XBT"):
            return amount * self.get_btc_eur(date)
        return amount * self.get_fiat_eur(currency, date)

    # -- cache ----------------------------------------------------------

    def _cached(self, date: str, pair: str) -> Decimal | None:
        row = self._db.execute(
            "SELECT close_eur FROM price_cache WHERE date=? AND pair=?",
            (date, pair),
        ).fetchone()
        return Decimal(row[0]) if row else None

    def load_csv(self, path: str | Path, pair: str, source: str, invert: bool = False) -> int:
        """Seed the cache from a CSV (date, value[, source]) file.

        With ``invert``, stores 1/value (for foreign-per-EUR quotes like the
        ECB series). Existing rows win (INSERT OR IGNORE) so live data is
        never clobbered. Returns rows added.
        """
        import csv

        added = 0
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                date = (row.get("date") or "").strip()[:10]
                raw = (row.get("close_eur") or row.get("value") or _first_value(row)).strip()
                if not date or not raw:
                    continue
                value = Decimal(raw)
                if invert:
                    if value == 0:
                        continue
                    value = Decimal("1") / value
                row_source = (row.get("source") or "").strip() or source
                cursor = self._db.execute(
                    "INSERT OR IGNORE INTO price_cache "
                    "(date, pair, close_eur, source, fetched_at) VALUES (?,?,?,?,?)",
                    (
                        date,
                        pair,
                        str(value),
                        row_source,
                        datetime.datetime.now(datetime.UTC).isoformat(),
                    ),
                )
                added += cursor.rowcount
        self._db.commit()
        return added

    def _store(self, date: str, pair: str, close_eur: Decimal, source: str) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO price_cache "
            "(date, pair, close_eur, source, fetched_at) VALUES (?,?,?,?,?)",
            (
                date,
                pair,
                str(close_eur),
                source,
                datetime.datetime.now(datetime.UTC).isoformat(),
            ),
        )
        self._db.commit()

    # -- Kraken ----------------------------------------------------------

    def _kraken_btc_eur(self, date: datetime.date) -> Decimal:
        since = int(
            datetime.datetime(date.year, date.month, date.day, tzinfo=datetime.UTC).timestamp()
        )
        try:
            response = self._client.get(
                KRAKEN_OHLC_URL,
                params={"pair": "XBTEUR", "interval": 1440, "since": since},
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise PriceOracleError(f"Kraken OHLC request failed: {exc}") from exc
        if payload.get("error"):
            raise PriceOracleError(f"Kraken OHLC error: {payload['error']}")
        try:
            candles = next(iter(payload["result"].values()))
            day = datetime.datetime.fromtimestamp(candles[0][0], datetime.UTC).date()
            if day != date:
                raise PriceOracleError(f"Kraken returned {day}, wanted {date}")
            return Decimal(str(candles[0][4]))  # close
        except (KeyError, IndexError, StopIteration) as exc:
            raise PriceOracleError(f"Kraken OHLC parse failed: {exc}") from exc

    # -- CoinGecko fallback ------------------------------------------------

    def _coingecko_btc_eur(self, date: datetime.date) -> Decimal:
        try:
            response = self._client.get(
                COINGECKO_HISTORY_URL,
                params={
                    "date": date.strftime("%d-%m-%Y"),
                    "localization": "false",
                },
            )
            response.raise_for_status()
            price = response.json()["market_data"]["current_price"]["eur"]
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise PriceOracleError(f"CoinGecko fallback failed: {exc}") from exc
        return Decimal(str(price))

    # -- ECB fiat ----------------------------------------------------------

    def _ecb_fiat_eur(self, currency: str, date: datetime.date) -> Decimal:
        """Most recent published rate on or before ``date`` (weekend-proof)."""
        try:
            response = self._client.get(ECB_URL_TEMPLATE.format(currency=currency))
            response.raise_for_status()
            return self._parse_ecb_csv(response.text, date)
        except httpx.HTTPError as exc:
            raise PriceOracleError(f"ECB request failed: {exc}") from exc

    @staticmethod
    def _parse_ecb_csv(text: str, date: datetime.date) -> Decimal:
        best_date: datetime.date | None = None
        best_rate: Decimal | None = None
        for line in text.splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 2:
                continue
            try:
                day = datetime.date.fromisoformat(parts[0][:10])
                rate = Decimal(parts[1])
            except (ValueError, ArithmeticError):
                continue
            if day <= date and (best_date is None or day > best_date):
                best_date, best_rate = day, rate
        if best_rate is None:
            raise PriceOracleError(f"No ECB {date} rate on or before {date}")
        # ECB quotes foreign currency per EUR; invert to foreign->EUR factor.
        return Decimal("1") / best_rate
