# backend/app/utils/money.py
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Union

Number = Union[int, float, Decimal]


def money(x: Number) -> Decimal:
    """Convert to Decimal safely."""
    if isinstance(x, Decimal):
        return x
    return Decimal(str(x))


def round_money(x: Number, places: int = 2) -> Decimal:
    """Round using banker-safe half-up style common in finance."""
    q = Decimal("1").scaleb(-places)  # e.g., 0.01
    return money(x).quantize(q, rounding=ROUND_HALF_UP)


def fmt_money(x: Number, currency: str = "$") -> str:
    """Format money for UI."""
    v = round_money(x)
    return f"{currency}{v:,.2f}"


def safe_mul(a: Number, b: Number) -> Decimal:
    """Multiply and round to cents."""
    return round_money(money(a) * money(b))