# backend/utils/fee_check.py
from __future__ import annotations
from typing import Dict, List, Tuple
from web3 import Web3

FEE_KEYWORDS = ["fee", "tax", "buy", "sell", "transfer"]
DENOM_KEYWORDS = ["denominator", "feeDenominator", "taxDenominator", "feesDenominator"]
TOTAL_SUPPLY_NAMES = ["totalSupply"]

def _is_uint_type(t: str) -> bool:
    return t.startswith("uint")

def _collect_getters(abi: list, name_keywords: List[str]) -> List[str]:
    """
    From ABI, return names of view functions with:
      - 0 inputs
      - 1 output (uint*)
      - name contains any of name_keywords
    """
    out = []
    for item in abi:
        if item.get("type") != "function":
            continue
        name = (item.get("name") or "")
        if not any(kw.lower() in name.lower() for kw in name_keywords):
            continue
        # only getters with no inputs and single uint output
        inputs = item.get("inputs", [])
        outputs = item.get("outputs", [])
        if len(inputs) == 0 and len(outputs) == 1:
            otype = outputs[0].get("type", "")
            if _is_uint_type(otype):
                out.append(name)
    return list(dict.fromkeys(out))  # dedupe, keep order

def _try_call_getter(contract, fn_name: str) -> int | None:
    try:
        fn = getattr(contract.functions, fn_name)
        val = fn().call()
        if isinstance(val, int):
            return val
        # Some ABIs return (int,) tuple
        if isinstance(val, (list, tuple)) and len(val) == 1 and isinstance(val[0], int):
            return val[0]
    except Exception:
        pass
    return None

def _guess_denominators() -> List[int]:
    # common patterns: 100 (percent), 1000, 10000 (basis points), 1e6 (ppm)
    return [100, 1000, 10000, 1_000_000]

def _normalize_with_denominators(raw: int, denom: int) -> float:
    if denom <= 0:
        return float(raw)
    return (raw / denom) * 100.0

def read_fees(w3: Web3, address: str, abi: list) -> Dict[str, float]:
    """
    Returns dict of normalized fee percentages, e.g.:
      { "buyFee": 5.0, "sellTax": 12.5, "transferFee": 0.0, ... }
    If no fee getters or nothing callable → returns {}.
    """
    address = Web3.to_checksum_address(address)
    contract = w3.eth.contract(address=address, abi=abi)

    # 1) Find candidate fee getters
    fee_getters = _collect_getters(abi, FEE_KEYWORDS)
    if not fee_getters:
        return {}

    # 2) Optional denominator getters
    denom_getters = _collect_getters(abi, DENOM_KEYWORDS)

    # Read denominators (prefer explicit)
    denom_values = []
    for g in denom_getters:
        val = _try_call_getter(contract, g)
        if isinstance(val, int) and val > 0:
            denom_values.append(val)

    # If none found, use guesses
    if not denom_values:
        denom_values = _guess_denominators()

    # 3) Read fee raw values and normalize against denominators
    result: Dict[str, float] = {}
    for g in fee_getters:
        raw = _try_call_getter(contract, g)
        if raw is None:
            continue

        # Pick the first denominator that yields a sensible percentage (<=1000%)
        normalized = None
        for d in denom_values:
            pct = _normalize_with_denominators(raw, d)
            # Heuristic sanity bound; ignore absurd 1000%+ rates
            if pct <= 1000.0:
                normalized = pct
                break

        # If still None, just treat raw as already percent
        if normalized is None:
            normalized = float(raw)

        result[g] = normalized

    return result
