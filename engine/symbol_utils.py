"""
Utilities for working with SmartAPI option trading symbols.
"""

from __future__ import annotations

import re
from typing import Optional

_CANONICAL_SUFFIX_PATTERN = re.compile(r"(CE|PE)$")
_DIRECTION_PREFIX_PATTERN = re.compile(r"^([A-Z]+)(\d{2}[A-Z]{3}\d{2})([CP])(\d+)$")
_DIRECTION_SUFFIX_PATTERN = re.compile(r"^([A-Z]+)(\d{2}[A-Z]{3}\d{2})(\d+)([CP])$")


def canonicalize_tradingsymbol(symbol: Optional[str]) -> str:
    """
    Normalize various broker-specific option symbol formats to SmartAPI's
    canonical `{SYMBOL}{DDMMMYY}{STRIKE}{CE/PE}` representation.
    """
    if symbol is None:
        return ""
    sanitized = str(symbol).strip().upper()
    if not sanitized or sanitized in {"NAN", "NONE", "NULL"}:
        return ""

    if _CANONICAL_SUFFIX_PATTERN.search(sanitized):
        return sanitized

    match = _DIRECTION_PREFIX_PATTERN.match(sanitized)
    if match:
        prefix, expiry, cp, strike = match.groups()
        return f"{prefix}{expiry}{strike}{cp}E"

    match = _DIRECTION_SUFFIX_PATTERN.match(sanitized)
    if match:
        prefix, expiry, strike, cp = match.groups()
        return f"{prefix}{expiry}{strike}{cp}E"

    return sanitized


def tradingsymbols_equal(lhs: Optional[str], rhs: Optional[str]) -> bool:
    """
    Compare two trading symbols after canonicalization.
    """
    left = canonicalize_tradingsymbol(lhs)
    right = canonicalize_tradingsymbol(rhs)
    return bool(left and right and left == right)

