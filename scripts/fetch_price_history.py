"""Fetch daily price history into data/ (one-off + refresh).

Sources (all free, no keys):
- BTC/EUR 2024-10 -> now: Kraken OHLC directly (native EUR daily close).
- BTC/USD 2010 -> 2024-10: blockchain.info charts (daily), converted with ECB.
- USD/EUR 1999 -> now: ECB eurofxref-hist.zip (business days; forward-filled).

Outputs: data/btc_eur_daily.csv (date,close_eur,source),
data/usd_eur_daily.csv (date,usd_per_eur). Deterministic: re-running with the
same upstream data yields identical files.
"""

from __future__ import annotations

import csv
import datetime
import io
import zipfile
from decimal import Decimal
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "utxoproof" / "data"

BCI_URL = "https://api.blockchain.info/charts/market-price"
ECB_ZIP_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip"
KRAKEN_URL = "https://api.kraken.com/0/public/OHLC"


def fetch_bci_usd(client: httpx.Client, start: str, timespan: str) -> dict[str, Decimal]:
    response = client.get(BCI_URL, params={"timespan": timespan, "start": start, "format": "json"})
    response.raise_for_status()
    out = {}
    for point in response.json()["values"]:
        day = datetime.datetime.fromtimestamp(point["x"], datetime.UTC).date()
        out[day.isoformat()] = Decimal(str(point["y"]))
    return out


def fetch_kraken_eur(client: httpx.Client) -> dict[str, Decimal]:
    out: dict[str, Decimal] = {}
    since: int | None = None
    while True:
        params: dict[str, str | int] = {"pair": "XBTEUR", "interval": 1440}
        if since is not None:
            params["since"] = since
        response = client.get(KRAKEN_URL, params=params)
        response.raise_for_status()
        payload = response.json()
        if payload.get("error"):
            raise RuntimeError(f"Kraken error: {payload['error']}")
        candles = next(iter([v for k, v in payload["result"].items() if k != "last"]))
        for candle in candles:
            day = datetime.datetime.fromtimestamp(candle[0], datetime.UTC).date()
            out[day.isoformat()] = Decimal(str(candle[4]))
        new_since = int(payload["result"]["last"])
        if new_since == since or len(candles) < 720:
            break
        since = new_since
    return out


def fetch_ecb_usd(client: httpx.Client) -> dict[str, Decimal]:
    response = client.get(ECB_ZIP_URL)
    response.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        name = next(n for n in zf.namelist() if n.endswith(".csv"))
        text = zf.read(name).decode("utf-8")
    rows = list(csv.DictReader(io.StringIO(text)))
    usd_col = next(c for c in rows[0].keys() if c and c.strip().upper() == "USD")
    out = {}
    for row in rows:
        date = (row.get("Date") or "").strip()
        rate = (row.get(usd_col) or "").strip()
        if date and rate and rate != "N/A":
            out[date] = Decimal(rate)
    return out


def forward_fill(rates: dict[str, Decimal], start: str, end: str) -> dict[str, Decimal]:
    """Fill weekends/holidays with the most recent prior rate."""
    day = datetime.date.fromisoformat(start)
    last_day = datetime.date.fromisoformat(end)
    filled: dict[str, Decimal] = {}
    current: Decimal | None = None
    while day <= last_day:
        key = day.isoformat()
        if key in rates:
            current = rates[key]
        if current is not None:
            filled[key] = current
        day += datetime.timedelta(days=1)
    return filled


def main() -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    client = httpx.Client(timeout=60.0)

    print("ECB USD/EUR ...")
    ecb = fetch_ecb_usd(client)
    usd_path = DATA / "usd_eur_daily.csv"
    with open(usd_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "usd_per_eur"])
        for date in sorted(ecb):
            writer.writerow([date, str(ecb[date])])
    print(f"  {len(ecb)} business days -> {usd_path}")

    print("blockchain.info BTC/USD 2010-2014 ...")
    early_usd: dict[str, Decimal] = {}
    for year in ("2010", "2011", "2012", "2013"):
        early_usd.update(fetch_bci_usd(client, f"{year}-01-01", "1year"))
    print("blockchain.info BTC/USD 2014-2019, 2019-2024 ...")
    early_usd.update(fetch_bci_usd(client, "2014-01-01", "5years"))
    early_usd.update(fetch_bci_usd(client, "2019-01-01", "5years"))
    print(f"  {len(early_usd)} USD days")

    print("Kraken BTC/EUR ...")
    kraken = fetch_kraken_eur(client)
    print(f"  {len(kraken)} Kraken days ({min(kraken)} -> {max(kraken)})")

    filled = forward_fill(ecb, min(early_usd), max(kraken))
    eur: dict[str, tuple[str, str]] = {}  # date -> (close_eur, source)
    for date, usd_price in sorted(early_usd.items()):
        if date in kraken or usd_price <= 0:
            continue  # pre-market zeros carry no signal; Kraken wins overlaps
        eur[date] = (str(usd_price / filled[date]), "blockchain.info-x-ecb")
    for date in sorted(kraken):
        eur[date] = (str(kraken[date]), "kraken")
    btc_path = DATA / "btc_eur_daily.csv"
    with open(btc_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "close_eur", "source"])
        for date in sorted(eur):
            close, source = eur[date]
            writer.writerow([date, close, source])
    print(f"  {len(eur)} days ({min(eur)} -> {max(eur)}) -> {btc_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
