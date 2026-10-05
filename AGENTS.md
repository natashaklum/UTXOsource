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
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/mypy utxoproof/                          # strict, must be clean
.venv/bin/python -m pytest                         # must pass
```

No system pip, no `cc` on dev machines: keep runtime deps pure-Python.
DaLI / `python-bitcoinrpc` are intentionally absent until their sprints (need a
C toolchain) — see the comment in `pyproject.toml`.

## Conventions

- Money: `Decimal` only, never float. Tax math lives in `utxoproof/belgian_tax.py`.
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
