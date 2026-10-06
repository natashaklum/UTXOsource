# utxoproof user guide ("slowstart")

The README quickstart gets you running in five minutes. This guide explains
what each step does, in the order you would actually use the tool. Every
command below is also documented with flags in `utxoproof --help`.

## 1. Concepts

- **Manual CSV** is the neutral interchange format:
  `date,side,btc,eur_per_btc,fee_eur` with `side` = BUY or SELL. Exchange
  imports convert to it; tax math consumes it.
- **Cost basis** is moving average by default (configurable). Buy fees join the
  cost pool; sell fees reduce proceeds.
- **Classification** (goede huisvader / speculator / passive holder) is a
  heuristic from observable signals plus your self-reported config flags —
  never a substitute for professional advice.
- **The SQLite DB** (`~/.utxoproof/utxoproof.db` by default) holds the on-chain
  transaction graph, price cache, KYC state and sync position. CSV flows work
  without it; on-chain and price features need it.

## 2. Installation

Native (Python 3.11+, [uv](https://docs.astral.sh/uv/)):

```bash
git clone --recurse-submodules https://github.com/natashaklum/utxoproof
cd utxoproof
uv venv
VIRTUAL_ENV=.venv uv pip install -e ".[dev]"
cp utxoproof.example.toml utxoproof.toml
```

Docker (runs the mainnet stack; regtest dev stack is `docker-compose.regtest.yml`):

```bash
cp utxoproof.example.toml utxoproof.toml
mkdir -p sources output
docker compose run --rm utxoproof --help
```

## 2b. Keep code and data separate (recommended)

Clone the tool into one folder, keep your real financial data in a canonical
data folder somewhere else. Everything utxoproof writes — the SQLite DB, the
price cache, evidence files — lives under a single data directory:

```bash
git clone --recurse-submodules https://github.com/natashaklum/utxoproof utxoproof
mkdir -p ~/utxoproof-data
export UTXOPROOF_DATA_DIR=~/utxoproof-data   # put this in your shell profile
```

With that set, every command uses `~/utxoproof-data/utxoproof.db` and
`~/utxoproof-data/evidence/` automatically — no flags needed, nothing lands
in the repo checkout or gets sprayed across home. Precedence when you need an
exception: explicit flags (`--db`, `--evidence-dir`, global `--data-dir`)
beat the environment variable, which beats the `~/.utxoproof` default:

```bash
utxoproof --data-dir /tmp/throwaway status --input manual.csv --price 40000
```

For a first real-data trial, point the variable at an empty folder: the worst
case is one folder to delete.

## 3. Configuration (`utxoproof.toml`)

Copy `utxoproof.example.toml` and review three sections:

- `[taxpayer]`: your report reference label and **communal surcharge rate**
  (Brussels 0.0587, Ghent 0.076, Antwerp 0.08, average 0.07). This rate lands
  directly on your computed tax, so set your municipality's value.
- `[classifier]`: score thresholds plus honest self-reporting — leverage,
  derivatives, professional crypto income, BTC share of total income. The
  classifier cannot observe these; wrong flags here mean a wrong classification.
- `[accounting]`: cost basis method (`moving_average` default; `fifo`, `lifo`,
  `hifo`, `lofo` also supported via rp2).

Bitcoin/RPC/output sections arrive with their sprints and are ignored for now.

## 4. Flow A — exchange history to tax report

Export your history (Kraken: ledgers.csv **and** trades.csv — see below;
Coinbase: transaction history; Binance: trade history; Bisq: trade history)
and convert it:

```bash
.venv/bin/utxoproof import --file ~/kraken_ledgers.csv --type kraken \
  --trades ~/kraken_trades.csv --out /tmp/utxo/manual.csv
```

Supported `--type` values: `kraken`, `coinbase`, `binance`, `bisq` (tagged
non-KYC), plus Belgian banks `ing`, `kbc`, `bnp`, `belfius`, `argenta` (these
produce bank-row CSVs for fiat-leg review, not trade rows). `--kyc` overrides
the exchange default. All non-Kraken shapes are best-effort — check the first
converted rows by eye before trusting a full year.

### Kraken: ledgers, trades, margin

Kraken exports two files that belong together:

- **ledgers.csv** (`txid,refid,time,type,subtype,aclass,asset,amount,fee,balance`)
  records money movement, grouped by `refid`.
- **trades.csv**
  (`txid,ordertxid,pair,time,type,ordertype,price,cost,fee,vol,margin,misc,ledgers`)
  records execution economics. Its `ledgers` column lists one *or more* ledger
  txids, which is how trades join back to ledger groups.

Ledgers alone suffice for plain spot history, but pass `--trades` anyway: it
supplies exact execution prices and flags **margined trades** (`margin`
non-zero). Margin settlements are taxable disposals (shown as `MARGIN` rows in
reports); **`rollover` rows are financing costs** added to your cost basis;
`settled` rows are ignorable; anything else unknown fails loudly instead of
being silently dropped. If margin activity is detected, `import` tells you to
set `used_leverage=true` in `utxoproof.toml [classifier]` — the tool cannot
infer leverage from spot legs alone.

Preview the number, then build the report bundle:

```bash
.venv/bin/utxoproof compute --input /tmp/utxo/manual.csv --year 2023
.venv/bin/utxoproof report --input /tmp/utxo/manual.csv --year 2023 \
  --source ~/kraken_2023.csv --out /tmp/utxo/2023
```

`--source` (repeatable) pulls raw files into the evidence ZIP, which lands next
to `report.html` together with `evidence.db` and `manifest.json`. `--no-zip`
skips it; `--alltime` writes a multi-year summary instead. Open `report.html`
in a browser and print to PDF for filing.

## 5. Flow B — on-chain wallets

You need Bitcoin Core (your own node for real use; regtest for practice —
see `docker-compose.regtest.yml`). One-time setup per xpub:

```bash
.venv/bin/utxoproof setup --rpc-url http://127.0.0.1:8332 \
  --rpc-user bitcoinrpc --rpc-password CHANGE_THIS \
  --wallet utxoproof_watchonly \
  --xpub <account-xpub> --fingerprint <master-fp: 8 hex chars>
```

`--purpose/--coin/--account` select the BIP44/49/84/86 template (default 84).
Then sync incrementally:

```bash
.venv/bin/utxoproof sync --rpc-url http://127.0.0.1:8332 \
  --rpc-user bitcoinrpc --rpc-password CHANGE_THIS \
  --wallet utxoproof_watchonly
```

Now the analytical commands read the local DB:

```bash
.venv/bin/utxoproof status --input /tmp/utxo/manual.csv --price 40000
.venv/bin/utxoproof privacy --db ~/.utxoproof/utxoproof.db --out /tmp/utxo/privacy
.venv/bin/utxoproof advise --db ~/.utxoproof/utxoproof.db --price 40000 \
  --as-of 2024-06-01 --out /tmp/utxo/advisory
.venv/bin/utxoproof provenance <txid>:<vout> --db ~/.utxoproof/utxoproof.db \
  --price 40000 --out /tmp/utxo/provenance
```

`status` values holdings at `--price` (or yesterday's oracle close without it).
`advise` ranks UTXOs by tax-if-sold with sell/hold/borrow/estate/privacy flags.
`provenance` walks a UTXO back to its origin with per-step EUR values.

## 6. Price history

Live prices come from Kraken OHLC (CoinGecko fallback, ECB for fiat) and are
cached in SQLite. For offline years, seed the cache from the vendored history
(first real BTC print 2010-08-18 through today):

```bash
ls data/  # btc_eur_daily.csv (Kraken + blockchain.info x ECB), usd_eur_daily.csv (ECB)
```

`EURPriceOracle.load_csv` imports them (existing rows win, so live data is
never clobbered). Refresh the vendored files with
`scripts/fetch_price_history.py`. Regenerate the demo site any time with
`scripts/build_demo.py --out site`.

## 7. Supporting evidence (scans, screenshots, PDFs)

Anything that is not machine-readable CSV goes through `attach`, which copies
the file into `evidence/<year>/` next to your database, hashes it, and links
it to a transaction (or leaves it general with `--tx` omitted):

```bash
.venv/bin/utxoproof attach --file ~/withdrawal-mail.png --tx <txid> \
  --note "Kraken withdrawal confirmation" --year 2023
.venv/bin/utxoproof attach --file ~/annual-statement.pdf --note "Bank 2023 totals"
```

Rules: originals stay untouched (the registry copy counts); re-attaching the
same content is a no-op via content hash; name collisions gain a suffix.
Conventions: one receipt often covers several transactions, so folders are
organized by year, not by txid. Images render as thumbnails in provenance
reports (large files become links); PDFs are always links.

What flows where: `provenance` shows an Attachments appendix for the chain's
transactions; `report --year` bundles `evidence/<year>/` into the evidence ZIP
under `attachments/` with hashes in `manifest.json`. Verify a bundle any time
by re-hashing against the manifest.

## 8. Troubleshooting

- `SELL with empty inventory`: your CSV sells more than it bought (check date
  order and missed deposits).
- `importdescriptors ... Missing checksum`: upgrade utxoproof — checksums are
  appended automatically since Sprint 3.
- Regtest `No such mempool transaction`: fixed — confirmed txs resolve via
  blockhash without txindex.
- No docker on this machine: daemon-backed runs are CI-only; everything else
  runs locally. The `regtest` pytest marker skips without a node.
- Pages demo not updating: Actions tab → re-run `Demo reports` (needs Pages
  source = GitHub Actions).
