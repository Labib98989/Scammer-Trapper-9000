# backend/utils/honeypot.py
from typing import Dict, Any, List
from web3 import Web3

# Routers we query for quotes (read-only)
ROUTERS = {
    "eth": Web3.to_checksum_address("0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D"),  # Uniswap V2
    "bsc": Web3.to_checksum_address("0x10ED43C718714eb63d5aA57B78B54704E256024E"),  # Pancake V2
}

ROUTER_ABI = [{
    "name": "getAmountsOut",
    "type": "function",
    "stateMutability": "view",
    "inputs": [{"name": "amountIn", "type": "uint256"}, {"name": "path", "type": "address[]"}],
    "outputs": [{"name": "amounts", "type": "uint256[]"}],
}]

ERC20_DECIMALS_ABI = [{"name":"decimals","outputs":[{"type":"uint8"}],"inputs":[],"stateMutability":"view","type":"function"}]

# name-based heuristics that often gate trading/selling
HP_KEYWORDS = [
    "blacklist","whitelist","bot","maxwallet","maxtx","maxtxamount","cooldown",
    "enabletrading","opentrading","settrading","starttrading","tradingopen",
    "swapenabled","setfees","settax","excludeFromFees","setlimits"
]

def _has_hp_keywords(abi: List[Dict[str, Any]]) -> bool:
    for it in abi or []:
        if it.get("type") == "function":
            name = (it.get("name") or "").lower()
            if any(kw in name for kw in HP_KEYWORDS):
                return True
    return False

def _safe_decimals(w3: Web3, token: str) -> int:
    try:
        return int(w3.eth.contract(address=token, abi=ERC20_DECIMALS_ABI).functions.decimals().call())
    except Exception:
        return 18  # default fallback

def probe_honeypot(w3: Web3, chain_key: str, token: str, base_token: str, abi: List[Dict[str, Any]] | None) -> Dict[str, Any]:
    """
    Read-only probe:
      - ask router for buy quote (base->token) and sell quote (token->base)
      - set 'buy_quote_ok' / 'sell_quote_ok' based on nonzero amounts
      - mark 'suspicious_abi' if we see trading gates / blacklists in function names
    This is not a full on-chain simulation, but it's safe and cheap.
    """
    out = {"buy_quote_ok": None, "sell_quote_ok": None, "suspicious_abi": False, "notes": []}

    try:
        router_addr = ROUTERS[chain_key]
        router = w3.eth.contract(address=router_addr, abi=ROUTER_ABI)

        base = Web3.to_checksum_address(base_token)
        tok = Web3.to_checksum_address(token)

        # --- buy quote: small base (0.01 in raw units, assumes 18-dec base like WETH/WBNB)
        buy_in = int(1e16)
        try:
            amounts = router.functions.getAmountsOut(buy_in, [base, tok]).call()
            out["buy_quote_ok"] = (len(amounts) == 2 and int(amounts[1]) > 0)
        except Exception as e:
            out["buy_quote_ok"] = False
            out["notes"].append(f"buy quote failed: {e}")

        # --- sell quote: small token amount based on token decimals (0.001 token)
        dec = _safe_decimals(w3, tok)
        sell_in = max(1, 10 ** max(0, dec - 3))  # 0.001 token in raw units
        try:
            amounts = router.functions.getAmountsOut(sell_in, [tok, base]).call()
            out["sell_quote_ok"] = (len(amounts) == 2 and int(amounts[1]) > 0)
        except Exception as e:
            out["sell_quote_ok"] = False
            out["notes"].append(f"sell quote failed: {e}")

    except Exception as e:
        out["notes"].append(f"router probe skipped: {e}")

    # ABI heuristic
    if abi:
        out["suspicious_abi"] = _has_hp_keywords(abi)

    return out
