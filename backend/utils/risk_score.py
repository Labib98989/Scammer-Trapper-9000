'''# backend/utils/risk_score.py
def _human_base_reserve(lp_info: dict | None) -> float:
    if not lp_info:
        return 0.0
    # prefer explicit human amount (multi-base version)
    if "base_reserve_human" in lp_info:
        return float(lp_info["base_reserve_human"])
    # fallback: our old single-base field
    raw = lp_info.get("base_reserve_units")
    if raw is None:
        return float(lp_info.get("weth_reserve_eth", 0.0))
    try:
        return float(raw) / 1e18
    except Exception:
        return 0.0

def _usd_liquidity(lp_info: dict | None) -> float:
    if not lp_info:
        return 0.0
    try:
        return float(lp_info.get("usd_liquidity_est") or 0.0)
    except Exception:
        return 0.0

def score_token(
    ownership_result: str,
    flagged_functions: list,
    has_mint: bool = False,
    abi_verified: bool = True,
    lp_info: dict | None = None,
    context: dict | None = None,
    fees: dict | None = None,
    honeypot: dict | None = None,
) -> int:
    score = 0

    # --- Context / establishment
    age_days = (context or {}).get("age_days", None)
    usd_liq = _usd_liquidity(lp_info)
    base_res = _human_base_reserve(lp_info)

    # Treat as established if old OR deep USD liquidity.
    # Threshold is conservative to avoid false "established" on fresh memes.
    established = (isinstance(age_days, (int, float)) and age_days >= 180.0) or (usd_liq >= 200_000)

    # --- Ownership
    if "NOT renounced" in ownership_result:
        score += 15 if established else 50
    elif "Cannot detect" in ownership_result:
        score += 10 if established else 20

    # Admin/proxy hint
    if "(Contract)" in ownership_result:
        score += 0 if established else 10

    # --- ABI signals
    if flagged_functions:
        score += 30
    if has_mint:
        score += 5 if established else 20
    if not abi_verified:
        score += 15

    # --- Liquidity heuristics
    if lp_info is not None:
        burn_pct = lp_info.get("lp_burn_pct", 0.0)
        if established:
            if burn_pct < 1.0:
                score += 2
            if usd_liq > 1_000_000:
                score = max(0, score - 20)  # strong credit for deep liquidity
            elif usd_liq > 200_000:
                score = max(0, score - 10)
        else:
            if burn_pct < 1.0:
                score += 35
            if base_res < 1.0:
                score += 25

    # --- Fees (percent)
    if fees:
        max_fee = max(fees.values()) if fees else 0.0
        if max_fee >= 20.0:
            score += 40
        elif max_fee >= 10.0:
            score += 25
        elif max_fee >= 5.0:
            score += 10

    # --- Honeypot probe
    if honeypot:
        if honeypot.get("sell_quote_ok") is False:
            score += 25
        elif honeypot.get("suspicious_abi"):
            score += 8

    return min(max(int(score), 0), 100)
'''
'''# backend/core/score.py
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
'''