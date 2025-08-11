# backend/utils/context.py
# Purpose: Get contract age (days) & creation tx with safe fallbacks (Web3 v7).
# Order:
#   1) Etherscan V2 -> contract/getcontractcreation  (single key, add chainid)
#   2) Legacy V1 (ETH only unless BSCSCAN_API_KEY exists)
#   3) Earliest token transfer timestamp (ETH via V1; BSC only if BSCSCAN_API_KEY)
#   4) Give up (return created_tx_unknown)
#
# Note: POA middleware is handled in backend/chains.get_w3_for_chain().

from __future__ import annotations
import os
import time
from typing import Dict, Any, Optional
import requests

from backend.chains import get_w3_for_chain, CHAINS, EXPLORER_V2_BASE

print("[CONTEXT] module loaded")

# ---------- helpers ----------

def _etherscan_v2_creation(chain_key: str, address: str, api_key: str) -> Optional[dict]:
    """
    Returns {"txHash": str|None, "timestamp": int|None} or None if not found.
    """
    try:
        chainid = CHAINS[chain_key]["chainid"]
        url = (
            f"{EXPLORER_V2_BASE}"
            f"?chainid={chainid}"
            f"&module=contract&action=getcontractcreation"
            f"&contractaddresses={address}"
            f"&apikey={api_key}"
        )
        print(f"[CONTEXT] V2 creation -> {url}")
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()
        res = data.get("result") or []
        if isinstance(res, list) and res:
            item = res[0]
            txh = item.get("txHash") or item.get("txhash")
            ts = item.get("timestamp")
            if ts is not None:
                try:
                    ts = int(ts)
                except Exception:
                    ts = None
            print(f"[CONTEXT] V2 creation hit tx={txh} ts={ts}")
            return {"txHash": txh, "timestamp": ts}
        print(f"[CONTEXT] V2 creation miss: {data}")
    except Exception as e:
        print(f"[CONTEXT] V2 creation error: {e}")
    return None


def _etherscan_v1_creation(chain_key: str, address: str) -> Optional[str]:
    """
    Legacy v1 creation lookup.
    - Uses ETHERSCAN_API_KEY on ETH
    - Uses BSCSCAN_API_KEY on BSC (if present), otherwise skips
    """
    try:
        host = CHAINS[chain_key]["explorer_v1_host"]
        if chain_key == "eth":
            key = os.getenv("ETHERSCAN_API_KEY", "")
        else:
            key = os.getenv("BSCSCAN_API_KEY", "")
            if not key:
                print("[CONTEXT] skip V1 creation on non-eth without chain-specific key")
                return None

        url = f"{host}?module=contract&action=getcontractcreation&contractaddresses={address}&apikey={key}"
        print(f"[CONTEXT] V1 creation -> {url}")
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()
        res = data.get("result") or []
        if isinstance(res, list) and res:
            txh = res[0].get("txHash") or res[0].get("txhash")
            if txh:
                print(f"[CONTEXT] V1 creation tx = {txh}")
                return txh
        print(f"[CONTEXT] V1 creation miss: {data}")
    except Exception as e:
        print(f"[CONTEXT] V1 creation error: {e}")
    return None


def _etherscan_earliest_tokentx_timestamp(chain_key: str, address: str) -> Optional[int]:
    """
    Fallback: earliest ERC-20 transfer timestamp.
    - ETH uses Etherscan V1 with ETHERSCAN_API_KEY
    - BSC requires BSCSCAN_API_KEY; otherwise skip
    """
    try:
        if chain_key == "eth":
            host = CHAINS[chain_key]["explorer_v1_host"]
            key = os.getenv("ETHERSCAN_API_KEY", "")
        else:
            key = os.getenv("BSCSCAN_API_KEY", "")
            if not key:
                print("[CONTEXT] skip earliest tokentx on non-eth without chain-specific key")
                return None
            host = CHAINS[chain_key]["explorer_v1_host"]

        url = (
            f"{host}?module=account&action=tokentx"
            f"&contractaddress={address}&page=1&offset=1&sort=asc&apikey={key}"
        )
        print(f"[CONTEXT] earliest tokentx -> {url}")
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()
        res = data.get("result") or []
        if isinstance(res, list) and res:
            ts = res[0].get("timeStamp") or res[0].get("timestamp")
            if ts:
                try:
                    ts_int = int(ts)
                    print(f"[CONTEXT] earliest tokentx timestamp = {ts_int}")
                    return ts_int
                except Exception as e:
                    print(f"[CONTEXT] ts parse error: {e}")
        print(f"[CONTEXT] earliest tokentx miss: {data}")
    except Exception as e:
        print(f"[CONTEXT] earliest tokentx error: {e}")
    return None


# ---------- main ----------

def get_contract_age_days(chain_key: str, token_address: str) -> Dict[str, Any]:
    """
    Return:
      { "age_days": float, "created_tx": "0x..." }  on success
      { "age_days": None,  "error": "..." }         on failure
    """
    print(f"[CONTEXT] start chain={chain_key} addr={token_address}")

    # web3 (only needed if we must fetch block timestamp via tx receipt)
    try:
        w3 = get_w3_for_chain(chain_key)
        print(f"[CONTEXT] web3 ok chainId={w3.eth.chain_id}")
    except Exception as e:
        msg = f"w3_init_failed: {e}"
        print(f"[CONTEXT] {msg}")
        return {"age_days": None, "error": msg}

    # 1) Etherscan V2 (single key, works for ETH + BSC via chainid)
    v2 = _etherscan_v2_creation(chain_key, token_address, os.getenv("ETHERSCAN_API_KEY", ""))
    if v2:
        ts = v2.get("timestamp")
        txh = v2.get("txHash")
        # Prefer direct timestamp if provided
        if ts is not None:
            try:
                age_days = (time.time() - int(ts)) / 86400.0
                print(f"[CONTEXT] V2 timestamp age_days={age_days}")
                return {"age_days": float(age_days), "created_tx": txh}
            except Exception as e:
                print(f"[CONTEXT] V2 ts parse error: {e}")
        # Else compute from block via receipt
        if txh:
            try:
                txr = w3.eth.get_transaction_receipt(txh)
                blk = w3.eth.get_block(txr.blockNumber)
                age_days = (time.time() - blk.timestamp) / 86400.0
                print(f"[CONTEXT] V2 tx age_days={age_days}")
                return {"age_days": float(age_days), "created_tx": txh}
            except Exception as e:
                print(f"[CONTEXT] V2 tx age lookup failed: {e}")

    # 2) Legacy V1 creation (ETH or if chain-specific key exists)
    tx_v1 = _etherscan_v1_creation(chain_key, token_address)
    if tx_v1:
        try:
            txr = w3.eth.get_transaction_receipt(tx_v1)
            blk = w3.eth.get_block(txr.blockNumber)
            age_days = (time.time() - blk.timestamp) / 86400.0
            print(f"[CONTEXT] V1 tx age_days={age_days}")
            return {"age_days": float(age_days), "created_tx": tx_v1}
        except Exception as e:
            print(f"[CONTEXT] V1 tx age lookup failed: {e}")

    # 3) Earliest transfer timestamp (when supported)
    ts2 = _etherscan_earliest_tokentx_timestamp(chain_key, token_address)
    if ts2:
        try:
            age_days = (time.time() - int(ts2)) / 86400.0
            print(f"[CONTEXT] Fallback age_days={age_days} (earliest tokentx)")
            return {"age_days": float(age_days), "created_tx": None}
        except Exception as e:
            print(f"[CONTEXT] tokentx age calc error: {e}")

    # 4) Give up
    print("[CONTEXT] created_tx_unknown (all fallbacks failed)")
    return {"age_days": None, "error": "created_tx_unknown"}
