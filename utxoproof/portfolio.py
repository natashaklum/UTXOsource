"""Portfolio overview model + dependency-free SVG charts (dashboard).

Entities (wallets, bank accounts, exchange balances) hold UTXO or fiat
positions. Pure functions over plain data so tests stay offline; the demo
site wires them to the sample graph. Charts are inline SVG (no JavaScript,
print-friendly).
"""

from __future__ import annotations

import html
import math
from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class Entity:
    id: str
    kind: str  # wallet | bank | exchange
    label: str
    detail: str = ""


@dataclass
class UtxoHolding:
    entity_id: str
    txid: str
    vout: int
    btc: Decimal
    eur_value: Decimal
    kyc_status: str


@dataclass
class FiatHolding:
    entity_id: str
    amount_eur: Decimal
    note: str = ""


@dataclass
class Portfolio:
    entities: list[Entity] = field(default_factory=list)
    utxos: list[UtxoHolding] = field(default_factory=list)
    fiat: list[FiatHolding] = field(default_factory=list)
    current_price_eur: Decimal = Decimal("0")

    @property
    def btc_total(self) -> Decimal:
        return sum((u.btc for u in self.utxos), Decimal("0"))

    @property
    def btc_value_eur(self) -> Decimal:
        return sum((u.eur_value for u in self.utxos), Decimal("0"))

    @property
    def fiat_total_eur(self) -> Decimal:
        return sum((f.amount_eur for f in self.fiat), Decimal("0"))

    @property
    def net_worth_eur(self) -> Decimal:
        return self.btc_value_eur + self.fiat_total_eur

    def entity_value_eur(self, entity_id: str) -> Decimal:
        utxo_value = sum(
            (u.eur_value for u in self.utxos if u.entity_id == entity_id), Decimal("0")
        )
        fiat_value = sum(
            (f.amount_eur for f in self.fiat if f.entity_id == entity_id), Decimal("0")
        )
        return utxo_value + fiat_value

    def allocation(self) -> list[tuple[str, str, Decimal, Decimal]]:
        """(entity_id, label, value_eur, share_pct) sorted by value desc."""
        total = self.net_worth_eur
        rows = [(e.id, e.label, self.entity_value_eur(e.id)) for e in self.entities]
        rows.sort(key=lambda r: r[2], reverse=True)
        return [
            (eid, label, value, (value / total * 100 if total > 0 else Decimal("0")))
            for eid, label, value in rows
        ]

    def kyc_split(self) -> list[tuple[str, Decimal]]:
        """BTC value per KYC status, descending."""
        by_status: dict[str, Decimal] = {}
        for u in self.utxos:
            by_status[u.kyc_status] = by_status.get(u.kyc_status, Decimal("0")) + u.eur_value
        return sorted(by_status.items(), key=lambda kv: kv[1], reverse=True)


def _esc(text: str) -> str:
    return html.escape(text)


def svg_bars(
    items: list[tuple[str, Decimal, str]],
    width: int = 560,
    row_height: int = 26,
) -> str:
    """Horizontal bar chart. Items: (label, value, link-href or "")."""
    peak = max([value for _, value, _ in items] + [Decimal("0")])
    height = max(row_height * len(items) + 10, 30)
    rows = []
    for i, (label, value, href) in enumerate(items):
        y = 5 + i * row_height
        bar_w = int(width * 0.52 * float(value / peak)) if peak > 0 else 0
        label_cell = f'<a href="{_esc(href)}">{_esc(label)}</a>' if href else _esc(label)
        bar_cell = f'<rect x="150" y="{y}" width="{bar_w}" height="16" fill="#2f6fed">'
        if href:
            bar_cell = f'<a href="{_esc(href)}">{bar_cell}</a>'
        rows.append(
            f'<text x="0" y="{y + 13}" font-size="12">{label_cell}</text>'
            f"{bar_cell}"
            f'<text x="{160 + int(width * 0.52)}" y="{y + 13}" font-size="12">{value:,.2f}</text>'
        )
    return f'<svg width="{width}" height="{height}" role="img">' + "".join(rows) + "</svg>"


def svg_donut(
    segments: list[tuple[str, Decimal]],
    size: int = 180,
) -> str:
    """Donut chart with legend. Segments: (label, value)."""
    total = sum((v for _, v in segments), Decimal("0"))
    colors = ["#2f6fed", "#e8a13d", "#3faf6e", "#b0b0b0", "#8e5bd6"]
    radius, thickness, cx, cy = 70, 26, 90, 90
    parts = []
    angle = 0.0
    for i, (label, value) in enumerate(segments):
        frac = float(value / total) if total > 0 else 0.0
        large = 1 if frac > 0.5 else 0
        start, end = angle, angle + frac * 360.0
        angle = end
        if frac <= 0:
            continue

        def pt(a: float) -> tuple[float, float]:
            r = math.radians(a - 90)
            return (cx + radius * math.cos(r), cy + radius * math.sin(r))

        x1, y1 = pt(start)
        x2, y2 = pt(end)
        color = colors[i % len(colors)]
        parts.append(
            f'<path d="M {x1:.1f} {y1:.1f} A {radius} {radius} 0 {large} 1 {x2:.1f} {y2:.1f} '
            f'stroke="{color}" stroke-width="{thickness}" fill="none"/>'
        )
        parts.append(
            f'<text x="{cx + radius + 14}" y="{30 + i * 20}" font-size="12">'
            f'<tspan fill="{color}">&#9679;</tspan> {_esc(label)} {value:,.0f}</text>'
        )
    parts.append(
        f'<text x="{cx}" y="{cy + 6}" font-size="14" text-anchor="middle">{total:,.0f}</text>'
    )
    return f'<svg width="{size + 190}" height="{size}" role="img">' + "".join(parts) + "</svg>"
