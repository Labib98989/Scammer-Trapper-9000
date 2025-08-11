# backend/utils/abi_loader.py
import json
from typing import List
from backend.chains import EXPLORER_V2_BASE
from backend.utils.ratelimit import http_get_json
from backend.utils.cache import memoize_ttl

SUSPICIOUS_KEYWORDS = [
    "blacklist", "whitelist", "bot", "restrict",
    "settrading", "enabletrading", "opentrading", "starttrading",
    "setfee", "settax", "maxtx", "maxwallet", "cooldown"
]

def _host_key_for_v1(v1_host: str | None) -> str:
    if not v1_host:
        return "explorer_v1"
    if "bscscan" in v1_host:
        return "bscscan_v1"
    if "etherscan" in v1_host:
        return "etherscan_v1"
    return "explorer_v1"

@memoize_ttl(ttl_seconds=600)
def fetch_contract_abi(address: str, api_key: str, chainid: int, v1_host: str | None = None) -> List[dict]:
    # V2 multichain first
    v2_params = {"chainid": chainid, "module": "contract", "action": "getabi", "address": address, "apikey": api_key}
    data = http_get_json("etherscan_v2", EXPLORER_V2_BASE, v2_params)
    if data.get("status") == "1":
        return json.loads(data["result"])

    # V1 fallback
    if v1_host:
        v1_params = {"module": "contract", "action": "getabi", "address": address, "apikey": api_key}
        data = http_get_json(_host_key_for_v1(v1_host), v1_host, v1_params)
        if data.get("status") == "1":
            return json.loads(data["result"])
        raise ValueError("❌ ABI fetch failed: " + data.get("result", "Unknown error"))

    raise ValueError("❌ ABI fetch failed via V2 (no V1 fallback configured)")

def scan_for_suspicious_functions(abi: list) -> list:
    flagged = []
    for item in abi:
        if item.get("type") == "function":
            name = (item.get("name") or "").lower()
            if any(kw in name for kw in SUSPICIOUS_KEYWORDS):
                flagged.append(item.get("name"))
    return flagged
