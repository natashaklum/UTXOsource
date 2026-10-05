"""BIP32/84 descriptor helpers (plan Sec. 9). Pure-python via embit.

Covers descriptor-template building for the four supported address types and
watch-only address derivation from an account xpub. Verified against BIP32 and
BIP84 spec vectors in ``tests/test_descriptors.py``.
"""

from __future__ import annotations

from embit import bip32, networks, script

# purpose -> (Core descriptor function, account derivation prefix)
TEMPLATES: dict[int, tuple[str, str]] = {
    44: ("pkh", "44h"),
    49: ("sh(wpkh({})", "49h"),  # closed below: sh(wpkh(<inner>))
    84: ("wpkh", "84h"),
    86: ("tr", "86h"),
}

NETWORKS = ("main", "test", "regtest")


def validate_account_xpub(xpub: str) -> bip32.HDKey:
    """Parse an account xpub (xpub/ypub/zpub/vpub/...). Raises on garbage."""
    try:
        return bip32.HDKey.from_base58(xpub)
    except Exception as exc:
        raise ValueError(f"Invalid account xpub: {exc}") from exc


def build_descriptors(
    xpub: str,
    fingerprint_hex: str,
    purpose: int = 84,
    coin: int = 0,
    account: int = 0,
) -> dict[str, str]:
    """Build Core external/change descriptors for an account xpub.

    Returns ``{"external": ..., "change": ...}`` e.g.
    ``wpkh([aabbccdd/84h/0h/0h]xpub.../0/*)``. ``fingerprint_hex`` is the
    master fingerprint (8 hex chars, from the hardware wallet).
    """
    if purpose not in TEMPLATES:
        raise ValueError(f"Unsupported purpose {purpose}; expected one of {sorted(TEMPLATES)}")
    if len(fingerprint_hex) != 8:
        raise ValueError("fingerprint_hex must be 8 hex chars (master fingerprint)")
    try:
        bytes.fromhex(fingerprint_hex)
    except ValueError as exc:
        raise ValueError("fingerprint_hex must be 8 hex chars (master fingerprint)") from exc
    validate_account_xpub(xpub)

    func, purpose_h = TEMPLATES[purpose]
    origin = f"[{fingerprint_hex}/{purpose_h}/{coin}h/{account}h]"
    if purpose == 49:
        inner = f"wpkh({origin}{xpub}/{{chain}}/*)"
        return {
            "external": f"sh({inner.format(chain=0)})",
            "change": f"sh({inner.format(chain=1)})",
        }
    return {
        "external": f"{func}({origin}{xpub}/0/*)",
        "change": f"{func}({origin}{xpub}/1/*)",
    }


def derive_addresses(
    xpub: str,
    chain: int = 0,
    start: int = 0,
    count: int = 1,
    network: str = "main",
) -> list[str]:
    """Derive ``count`` P2WPKH addresses from an account xpub.

    ``chain`` 0 = external, 1 = change. ``network`` one of main/test/regtest.
    """
    if network not in NETWORKS:
        raise ValueError(f"Unknown network {network!r}; expected one of {NETWORKS}")
    if chain not in (0, 1):
        raise ValueError("chain must be 0 (external) or 1 (change)")
    if start < 0 or count < 1:
        raise ValueError("start must be >= 0 and count >= 1")
    account = validate_account_xpub(xpub)
    net = networks.NETWORKS[network]
    return [
        script.p2wpkh(account.derive([chain, index]).get_public_key()).address(net)
        for index in range(start, start + count)
    ]
