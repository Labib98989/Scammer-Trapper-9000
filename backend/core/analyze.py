# backend/core/analyze.py (debug)
from __future__ import annotations

import os
from typing import Dict, Any, Optional, List, Tuple
from web3 import Web3


print("[ANALYZE] Module import start")

from backend.chains import get_w3_for_chain, CHAINS
from backend.utils.addr import normalize_evm_address
from backend.utils.ownership import check_ownership
from backend.utils.abi_loader import fetch_contract_abi, scan_for_suspicious_functions
from backend.utils.mint_check import check_mint_function
from backend.utils.fee_check import read_fees
from backend.utils.liquidity import get_deepest_v2_pool
from backend.utils.context import get_contract_age_days
from backend.core.score import score_token
from backend.utils.honeypot import probe_honeypot
_ENABLE_HONEYPOT = os.getenv("HONEYPOT_PROBE", "0").strip().lower() not in {"0","false","no","off",""}


print("[ANALYZE] Imports OK")

def _risk_tier(score: int) -> str:
    # Mirror the tier logic in score.py for safety
    return "LOW" if score < 25 else ("MEDIUM" if score < 60 else "HIGH")

def _lp_pct_to_percent(lp_burn_pct: Optional[float]) -> Optional[float]:
    """Liquidity helper: convert 0..1 to 0..100 if needed."""
    if lp_burn_pct is None:
        return None
    return lp_burn_pct * 100.0 if lp_burn_pct <= 1.0 else lp_burn_pct

def analyze_token(chain_key: str, token_address: str) -> Dict[str, Any]:
    print(f"[ANALYZE] analyze_token start chain={chain_key} addr={token_address}")

    # 1) Normalize address
    try:
        token = normalize_evm_address(token_address)
        print(f"[ANALYZE] Address normalized: {token}")
    except Exception as e:
        print(f"[ANALYZE] Address normalize FAIL: {e}")
        raise

    # 2) Web3 for chain
    try:
        w3 = get_w3_for_chain(chain_key)
        print(f"[ANALYZE] Web3 ready. chainId={w3.eth.chain_id}")
    except Exception as e:
        print(f"[ANALYZE] get_w3_for_chain FAIL: {e}")
        raise

    # 3) Ownership
    ownership = None
    try:
        ownership = check_ownership(w3, token)
        print(f"[ANALYZE] Ownership OK: {ownership}")
    except Exception as e:
        ownership = f"error: {e}"
        print(f"[ANALYZE] Ownership FAIL: {e}")

    # 4) ABI fetch + scans
    abi_verified = False
    abi_error: Optional[str] = None
    abi: Optional[List[dict]] = None
    flagged_functions: List[str] = []
    try:
        api_key = (os.getenv("ETHERSCAN_API_KEY") if chain_key == "eth"
                   else (os.getenv("BSCSCAN_API_KEY") or os.getenv("ETHERSCAN_API_KEY", "")))
        chainid = CHAINS[chain_key]["chainid"]
        v1_host = CHAINS[chain_key].get("explorer_v1_host")
        print(f"[ANALYZE] ABI fetch params -> chainid={chainid} v1_host={v1_host} key={'yes' if api_key else 'no'}")
        abi = fetch_contract_abi(token, api_key, chainid, v1_host)
        abi_verified = True
        print(f"[ANALYZE] ABI fetch OK. items={len(abi)}")
        flagged_functions = scan_for_suspicious_functions(abi)
        print(f"[ANALYZE] Suspicious scan -> {flagged_functions}")
    except Exception as e:
        abi_error = str(e)
        abi_verified = False
        print(f"[ANALYZE] ABI fetch/scan FAIL: {e}")

    # 5) Mint check (only if we have ABI)
    has_mint = False
    try:
        if abi_verified and abi:
            has_mint = check_mint_function(abi)
            print(f"[ANALYZE] Mint check: {has_mint}")
        else:
            print("[ANALYZE] Mint check skipped (no ABI)")
    except Exception as e:
        print(f"[ANALYZE] Mint check FAIL: {e}")

    # 6) Fee getters (only if we have ABI)
    fees: Dict[str, float] | Dict[str, Any] = {}
    try:
        if abi_verified and abi:
            fees = read_fees(w3, token, abi) or {}
            print(f"[ANALYZE] Fees OK: {fees}")
        else:
            print("[ANALYZE] Fees skipped (no ABI)")
    except Exception as e:
        fees = {"error": str(e)}
        print(f"[ANALYZE] Fees FAIL: {e}")

    # 7) Liquidity
    lp_info = None
    try:
        lp_info = get_deepest_v2_pool(w3, chain_key, token)
        print(f"[ANALYZE] Liquidity OK: keys={list(lp_info.keys()) if isinstance(lp_info, dict) else None}")
    except Exception as e:
        lp_info = None
        print(f"[ANALYZE] Liquidity FAIL: {e}")

    # 8) Context
    context = {}
    try:
        ctx = get_contract_age_days(chain_key, token)
        context = ctx if isinstance(ctx, dict) else {"age_days": ctx}
        print(f"[ANALYZE] Context OK: age_days={context.get('age_days')}")
    except Exception as e:
        context = {"age_days": None, "error": str(e)}
        print(f"[ANALYZE] Context FAIL: {e}")

    # 9) Honeypot probe (best-effort)
    hp = {"skipped": True, "reason": "disabled"}
    try:
        if _ENABLE_HONEYPOT:
            base_addr = (lp_info or {}).get("base_address")
            if base_addr and (abi is not None):
                print(f"[ANALYZE] Honeypot probe -> base={base_addr}")
                # NOTE: expected signature: probe_honeypot(w3, chain_key, token, base_token, abi)
                hp = probe_honeypot(w3, chain_key, token, base_addr, abi)
                print(f"[ANALYZE] Honeypot OK: {hp}")
            else:
                hp = {"skipped": True, "reason": "needs base pair + abi"}
                print("[ANALYZE] Honeypot skipped (needs base pair + abi)")
        else:
            print("[ANALYZE] Honeypot skipped (disabled via HONEYPOT_PROBE)")
    except Exception as e:
        hp = {"error": str(e)}
        print(f"[ANALYZE] Honeypot FAIL: {e}")

    # 10) Score
    try:
        usd_liq = (lp_info or {}).get("usd_liquidity_est") if isinstance(lp_info, dict) else None
        lp_burn_pct = _lp_pct_to_percent((lp_info or {}).get("lp_burn_pct") if isinstance(lp_info, dict) else None)
        age_days = context.get("age_days") if isinstance(context, dict) else None

        score, tier = score_token(
            ownership=ownership if isinstance(ownership, str) else str(ownership),
            abi_verified=abi_verified,
            suspicious_functions=flagged_functions,
            has_mint=has_mint,
            usd_liquidity_est=usd_liq,
            lp_burn_pct=lp_burn_pct,
            age_days=age_days,
        )
        print(f"[ANALYZE] Score OK: score={score} tier={tier}")
    except Exception as e:
        print(f"[ANALYZE] Score FAIL: {e}")
        raise

    result = {
        "chain": chain_key,
        "address": token,
        "ownership": ownership,
        "abi_verified": abi_verified,
        "abi_error": abi_error,
        "suspicious_functions": flagged_functions,
        "has_mint": has_mint,
        "fees_percent": fees,
        "liquidity": lp_info,
        "context": context,
        "honeypot": hp,
        "score": int(score),
        "risk_tier": tier if isinstance(tier, str) else _risk_tier(int(score)),
    }
    print(f"[ANALYZE] analyze_token done chain={chain_key} addr={token} score={result['score']} tier={result['risk_tier']}")
    return result
