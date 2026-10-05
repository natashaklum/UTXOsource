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

## Status

Sprint 0 (foundation) is done: rp2 + Belgian plugin produce a verified tax
number, the full SQLite schema exists, and `utxoproof compute` works on
synthetic data. See the sprint roadmap in `utxo-source-plan_v5.md` (and
`docs/supported_countries.md` in the rp2 fork) for what comes next.

## Quickstart (Sprint 0)

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv venv
VIRTUAL_ENV=.venv uv pip install -e ".[dev]"
.venv/bin/utxoproof compute --input tests/fixtures/manual_2023.csv --year 2023
```

Checks:

```bash
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/mypy utxoproof/
.venv/bin/python -m pytest
```

## Layout

```text
utxoproof/
  belgian_tax.py  # 33% flat + communal surcharge, proportional fee-split
  cli.py          # Sprint 0: `compute --input --year` (grows into `report`)
  db.py           # SQLite init
  schema.sql      # Full Sec. 8 schema (transactions, tx graph, prices, KYC…)
tests/
  fixtures/manual_2023.csv  # 12 synthetic rows, gain cross-checked by hand
```

## rp2 fork

Tax computation reuses [rp2](https://github.com/eprbell/rp2) via our fork
[`natashaklum/rp2`](https://github.com/natashaklum/rp2), which adds the Belgian
`BE` country plugin (`rp2_be`). The plan's full spec is `utxo-source-plan_v5.md`.

## License

See [LICENSE](LICENSE). This tool is a computational aid, not professional tax
advice — verify all figures with a certified Belgian tax adviser before filing.
