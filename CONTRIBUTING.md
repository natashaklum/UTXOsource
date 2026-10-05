# Contributing to utxoproof

## Setup

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/). No system pip, no C
compiler needed — runtime deps are pure-Python by policy.

```bash
git clone --recurse-submodules https://github.com/natashaklum/UTXOsource
cd UTXOsource
uv venv
VIRTUAL_ENV=.venv uv pip install -e ".[dev]"
```

## Checks (must all pass)

```bash
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/mypy utxoproof/ scripts/
.venv/bin/python -m pytest
.venv/bin/python scripts/build_demo.py --out site
```

## Conventions

- Money is `Decimal`, never float.
- New fixtures go in `tests/fixtures/` with hand-verified expectations:
  recompute expected values independently before pinning them.
- Chain crypto goes through `utxoproof/descriptors.py`; Bitcoin Core access
  through `utxoproof/bitcoin_rpc.py` + `utxoproof/onchain.py`.
- Daemon-backed tests are marked `regtest` and skip without a node
  (`docker-compose.regtest.yml`; CI starts one).
- Parser shapes for formats never validated against a live export are marked
  `UNVERIFIED` in code — correct the profile, don't work around it.
- `AGENTS.md` has a self-maintenance rule: changes to layout, toolchain or
  conventions must update it in the same change.

## The rp2 submodule

`vendor/rp2` tracks the [`natashaklum/rp2`](https://github.com/natashaklum/rp2)
fork (Belgian `BE` plugin). Iterate with
`VIRTUAL_ENV=.venv uv pip install -e vendor/rp2`, commit + push there first,
then `git add vendor/rp2` here and bump the pinned SHA in `pyproject.toml`
to match.

## Reports

Demo HTML reports build from synthetic fixtures only — never commit real
transaction data, xpubs, or wallet files. The demo site deploys to GitHub Pages
on every `main` push.
