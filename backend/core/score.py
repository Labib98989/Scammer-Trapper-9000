# backend/core/score.py
from __future__ import annotations
from typing import Iterable, Tuple, Optional

def score_token(
    *,
    ownership: Optional[str] = None,
    abi_verified: Optional[bool] = None,
    suspicious_functions: Optional[Iterable[str]] = None,
    has_mint: bool = False,
    usd_liquidity_est: Optional[float] = None,  # dollars
    lp_burn_pct: Optional[float] = None,        # 0..100
    age_days: Optional[float] = None,
) -> Tuple[int, str]:
    """Return (score 0..100, tier) with simple, transparent rules."""
    score = 0

    # Ownership
    if ownership:
        up = ownership.upper()
        if "NOT RENOUNCED" in up:
            score += 25
        elif "RENOUNCED" in up:
            score -= 10

    # ABI
    if abi_verified is False:
        score += 20

    # Suspicious names
    if suspicious_functions:
        susp = list(suspicious_functions)
        if susp:
            score += 30

    # Mint
    if has_mint:
        score += 15

    # Liquidity
    if usd_liquidity_est is None or usd_liquidity_est < 1_000:
        score += 20

    # LP burn (if known and small)
    if lp_burn_pct is not None and lp_burn_pct < 1:
        score += 10

    # Age
    if age_days is not None:
        if age_days < 2:
            score += 10
        elif age_days > 365:
            score -= 5

    score = max(0, min(100, score))
    tier = "LOW" if score < 25 else ("MEDIUM" if score < 60 else "HIGH")
    return score, tier
