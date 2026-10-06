# AGENTS.md — utxoproof

> **Self-maintenance rule (binding).** Any coding agent that changes this repo's
> layout, toolchain, conventions, or multi-repo workflow MUST update this file
> in the same change. A change that alters how agents should work here but leaves
> this file stale is incomplete. Keep it short: facts and commands, no essays.
> This rule applies to itself — if the rule stops working, fix the rule.

## What this is

utxoproof: Bitcoin wealth management + Belgian tax compliance for self-custodians.
Full spec: `utxo-source-plan_v5.md`. Two repos:

- This repo (`UTXOsource`): the tool. Python 3.11+, `utxoproof/` package.
- [`natashaklum/rp2`](https://github.com/natashaklum/rp2) fork: rp2 + Belgian `BE`
  country plugin. This repo depends on it (pinned SHA in `pyproject.toml`, kept in
  lockstep with the `vendor/rp2` submodule pointer).
  rp2-side changes (country plugin, templates) go there, not here.
- Local checkouts: this repo embeds the fork as the `vendor/rp2` git submodule
  (never clone rp2 separately; `/tmp` is wiped on restart anyway).
  Iterating on both: `VIRTUAL_ENV=.venv uv pip install -e vendor/rp2`, run rp2
  checks from the submodule (`cd vendor/rp2 && ../.venv/bin/python -m pytest
  tests/test_plugin_country_be.py`), then commit+push in `vendor/rp2` first,
  `git add vendor/rp2` here, and bump the pinned SHA in `pyproject.toml`.

## Commands

```bash
uv venv                                            # one-time
VIRTUAL_ENV=.venv uv pip install -e ".[dev]"
.venv/bin/utxoproof compute --input tests/fixtures/manual_2023.csv --year 2023
.venv/bin/utxoproof status --input tests/fixtures/manual_2023.csv --price 40000
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/mypy utxoproof/ scripts/               # strict, must be clean
.venv/bin/python -m pytest                         # must pass
.venv/bin/python scripts/build_demo.py --out site  # demo HTML reports
```

No system pip, no `cc` on dev machines: keep runtime deps pure-Python.
DaLI is intentionally absent until its sprints (needs a C toolchain).
`embit` is allowed (pure-python wheel, no compiler needed).

## Conventions

- Money: `Decimal` only, never float. Tax math lives in `utxoproof/belgian_tax.py`.
- Chain crypto (xpub parsing, address derivation) goes through `utxoproof/descriptors.py`
  (embit); new vectors must be spec vectors, hand-verified before pinning.
- Bitcoin Core access goes through `utxoproof/bitcoin_rpc.py` (httpx JSON-RPC) and
  `utxoproof/onchain.py` (tx-graph sync). Daemon-backed tests are marked
  `regtest` and skip without a node; CI `regtest` job starts one via docker.
- KYC lives in `utxoproof/kyc.py` (proportional propagation, mixing detection);
  `utxoproof privacy` renders it. Shared sample graph: `create_sample_graph()`.
- Advisory lives in `utxoproof/advisory.py` (Sec. 13 flag rules, estate score);
  cost basis is acquisition-date close (rp2 lot integration pending).
  `utxoproof advise --db --price --as-of [--out]`; speculation taint defaults
  off until the Sprint 7 classifier feeds it.
- Provenance lives in `utxoproof/provenance.py` (backward graph walk, largest
  parent, cycle guard, depth cap); `utxoproof provenance txid:vout --db
  [--price/--as-of/--depth/--out]`. Unrealized gain is omitted from the header
  (needs lot matching); first-traced value shown instead.
- Evidence lives in `utxoproof/evidence.py` (SHA-256 manifest, content dedupe,
  ZIP bundle). `utxoproof report --year Y [--source F]...` builds it unless
  `--no-zip`; `report --alltime` writes the per-year summary (no ZIP).
- Dashboard lives in `utxoproof/portfolio.py` (entities, rollups, inline SVG
  charts — no JavaScript). Overview -> entity pages -> provenance pages;
  chart HTML is trusted generator output (`| safe` in templates, everything
  else stays autoescaped).
- Packaging: `Dockerfile` (+`.dockerignore`), `docker-compose.yml` (mainnet)
  and `docker-compose.regtest.yml` (dev). CI `docker` job builds + smoke-tests
  the image (no docker on dev boxes, so image builds are CI-only).
- Classification lives in `utxoproof/classifier.py` (Sec. 6 scores) with signals
  from `signals_from_csv`; config in `utxoproof/config.py` (`utxoproof.toml`,
  example at `utxoproof.example.toml`). `utxoproof report --config` applies
  communal rate + classifier flags. Progressive speculator rates are NOT
  computed (needs annual bracket table); the report says so.
- Exchanges: `kraken_csv` / `coinbase_csv` / `binance_csv` / `bisq_csv` yield
  `exchange.ExchangeTx` (Bisq defaults non_kyc). Banks: `banks.py` profile
  engine (headers UNVERIFIED, alias-driven); `matching.py` fiat-leg matcher.
  All non-Kraken shapes are best-effort fixtures for later correction.
- Regtest stack: `docker-compose.regtest.yml` (bitcoind only; no docker on dev
  boxes, so daemon runs are CI-only).
- SQLite schema (`utxoproof/schema.sql`) is created whole (Sec. 8); schema changes
  need a migration note + `tests/test_schema.py` update.
- `tests/fixtures/*.csv` are hand-verified: recompute expected values
  independently before pinning them in tests.
- `S101` (asserts) is ignored for `tests/**` in `pyproject.toml`; everything else
  must satisfy `ruff check`, `ruff format`, and strict `mypy`.
- Sprint deliverables follow `utxo-source-plan_v5.md` Sec. 20; flag spec-vs-reality
  gaps (e.g. rp2's `AbstractCountry` has no `apply_tax` hook) instead of forcing
  the spec's shape.

## Branches

Single branch: `main` (default). No `master`. Commit as
`natashaklum <natashaklum@users.noreply.github.com>`.
