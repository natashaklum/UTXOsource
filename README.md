# utxoproof

Bitcoin wealth management and compliance tool for Belgian self-custodians.
Self-hosted. Privacy-first. No data leaves your machine.

utxoproof answers three questions:

1. **What do I owe?** — Belgian personal income tax on Bitcoin disposals
   (goede huisvader 33% flat vs. speculator progressive), with a reproducible
   HTML report and evidence ZIP for SPF Finances.
2. **What should I do?** — per-UTXO advisory (sell, hold, borrow against,
   estate plan), flagging speculation taint, tax cost, and KYC complications.
3. **Where did this coin come from?** — full chain-of-custody provenance for
   any UTXO, EUR-valued at every step.

Browse the [demo portfolio dashboard](https://natashaklum.github.io/UTXOsource/overview/overview.html):
wallets, bank and exchange balances with allocation charts, drillable down to
each UTXO and its provenance chain.

## Status

Implemented and covered by tests + live regtest runs: exchange imports
(Kraken, Coinbase, Binance, Bisq) and Belgian bank parsing, EUR price oracle,
Belgian classifier with `utxoproof.toml`, HTML reports (tax, status, privacy,
advisory, provenance, all-time) with evidence ZIPs, KYC propagation, on-chain
descriptor sync against Bitcoin Core, and demo reports published to GitHub
Pages on every `main` push. See the sprint roadmap in `utxo-source-plan_v5.md`
for what remains.

## Installation

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

Native:

```bash
git clone --recurse-submodules https://github.com/natashaklum/UTXOsource
cd UTXOsource
uv venv
VIRTUAL_ENV=.venv uv pip install -e ".[dev]"
cp utxoproof.example.toml utxoproof.toml  # then edit municipality rate etc.
```

Docker (mainnet stack per `docker-compose.yml`; regtest dev stack in
`docker-compose.regtest.yml`):

```bash
cp utxoproof.example.toml utxoproof.toml
mkdir -p sources output
docker compose run --rm utxoproof sync --rpc-url http://bitcoind:8332 ...
```

## Quickstart

```bash
.venv/bin/utxoproof compute --input tests/fixtures/manual_2023.csv --year 2023
.venv/bin/utxoproof status --input tests/fixtures/manual_2023.csv --price 40000
.venv/bin/utxoproof report --input tests/fixtures/manual_2023.csv --year 2023 --out /tmp/utxo-report
.venv/bin/python scripts/build_demo.py --out site  # all demo reports + index
```

On-chain (needs a node; regtest via `docker-compose.regtest.yml`):

```bash
.venv/bin/utxoproof setup --rpc-url http://127.0.0.1:18443 --rpc-user utxoproof \
  --rpc-password utxoproof-test --wallet utxoproof_watchonly \
  --xpub <account-xpub> --fingerprint <master-fp>
.venv/bin/utxoproof sync --rpc-url http://127.0.0.1:18443 --rpc-user utxoproof \
  --rpc-password utxoproof-test --wallet utxoproof_watchonly
```

Checks (see [CONTRIBUTING.md](CONTRIBUTING.md)):

```bash
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/mypy utxoproof/ scripts/
.venv/bin/python -m pytest
```

## Layout

```text
utxoproof/
  belgian_tax.py  # 33% flat + communal surcharge, proportional fee-split
  cli.py          # compute/report/status/privacy/advise/provenance/setup/sync
  db.py + schema.sql  # Sec. 8 SQLite schema (tx graph, prices, KYC…)
  exchange.py + kraken_csv.py / coinbase_csv.py / binance_csv.py / bisq_csv.py
  banks.py + matching.py  # Belgian bank profiles, fiat-leg matcher
  price_oracle.py  # Kraken OHLC + CoinGecko + ECB, SQLite cache
  classifier.py + config.py  # Sec. 6 scores, utxoproof.toml
  descriptors.py  # BIP32/84 templates + address derivation (embit)
  bitcoin_rpc.py + onchain.py  # Core JSON-RPC, tx-graph sync
  kyc.py + advisory.py + provenance.py + evidence.py + reports.py
tests/
  fixtures/  # synthetic only, hand-verified, never real data
```

## rp2 fork

Tax computation reuses [rp2](https://github.com/eprbell/rp2) via our fork
[`natashaklum/rp2`](https://github.com/natashaklum/rp2), which adds the Belgian
`BE` country plugin (`rp2_be`). The plan's full spec is `utxo-source-plan_v5.md`.

## License

See [LICENSE](LICENSE). This tool is a computational aid, not professional tax
advice — verify all figures with a certified Belgian tax adviser before filing.
