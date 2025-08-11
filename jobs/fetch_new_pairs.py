# jobs/fetch_new_pairs.py
'''import os, json, math, argparse, time
from datetime import datetime, timezone
from dotenv import load_dotenv
from web3 import Web3
from web3._utils.events import get_event_data

# reuse your modules
from backend.utils.abi_loader import fetch_contract_abi
from backend.core.liquidity import get_best_pool_and_usd_liquidity  # your latest multi-base function
from backend.core.context import estimate_contract_age_days          # your existing helper
from backend.core.chains import get_chain_config                     # chain rpc + bases + factories

load_dotenv()

PAIR_CREATED_ABI = [{
    "anonymous": False,
    "inputs": [
        {"indexed": True,  "internalType": "address", "name": "token0", "type": "address"},
        {"indexed": True,  "internalType": "address", "name": "token1", "type": "address"},
        {"indexed": False, "internalType": "address", "name": "pair",   "type": "address"},
        {"indexed": False, "internalType": "uint256", "name": "",       "type": "uint256"}
    ],
    "name": "PairCreated",
    "type": "event"
}]

def connect_w3(rpc_url: str) -> Web3:
    w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 20}))
    assert w3.is_connected(), f"RPC not reachable: {rpc_url}"
    return w3

def topic_sig(w3: Web3, abi_event):
    return w3.keccak(text=f"{abi_event['name']}(address,address,address,uint256)").hex()

def fetch_recent_pairs(w3: Web3, chain_cfg: dict, lookback_blocks: int):
    factory_addr = Web3.to_checksum_address(chain_cfg["univ2_factory"])
    event_abi = PAIR_CREATED_ABI[0]
    event_topic = topic_sig(w3, event_abi)

    latest = w3.eth.block_number
    frm = max(0, latest - lookback_blocks)
    logs = w3.eth.get_logs({
        "fromBlock": frm,
        "toBlock": "latest",
        "address": factory_addr,
        "topics": [event_topic]
    })

    factory = w3.eth.contract(address=factory_addr, abi=PAIR_CREATED_ABI)
    decoded = []
    for log in logs:
        try:
            ev = get_event_data(w3.codec, event_abi, log)
            token0 = Web3.to_checksum_address(ev["args"]["token0"])
            token1 = Web3.to_checksum_address(ev["args"]["token1"])
            pair   = Web3.to_checksum_address(ev["args"]["pair"])
            decoded.append((token0, token1, pair, log["blockNumber"]))
        except Exception:
            continue
    return decoded

def is_unverified(token_addr: str, chain: str) -> bool:
    try:
        _ = fetch_contract_abi(token_addr, chain=chain)  # reuses your unified loader
        return False
    except Exception:
        return True

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chain", required=True, choices=["eth","bsc"])
    ap.add_argument("--lookback", type=int, default=5000, help="blocks to scan back (≈ ~17h on ETH, ~3.5h on BSC)")
    ap.add_argument("--limit", type=int, default=20, help="max tokens to return")
    ap.add_argument("--max_usd_liq", type=float, default=10000.0, help="<= this USD liq")
    ap.add_argument("--max_age_days", type=float, default=1.0, help="<= this age (days)")
    ap.add_argument("--out", default="addresses.txt", help="file to write token addresses, one per line")
    args = ap.parse_args()

    cfg = get_chain_config(args.chain)
    rpc = cfg["rpc"]
    w3  = connect_w3(rpc)

    print(f"🔎 Fetching new pairs on {args.chain} … (lookback={args.lookback} blocks)")

    pairs = fetch_recent_pairs(w3, cfg, args.lookback)
    print(f"• Found {len(pairs)} PairCreated events")

    picks = []
    seen_tokens = set()

    for token0, token1, pair, blk in pairs[::-1]:  # iterate newest first
        # choose the *non-base* as "token" to score (we only want new launches)
        bases = {a.lower() for a in cfg["bases"].values()}
        t0_is_base = token0.lower() in bases
        t1_is_base = token1.lower() in bases

        if t0_is_base == t1_is_base:
            # either both base (rare) or neither base; skip (we only want base<>new token)
            continue

        token = token1 if t0_is_base else token0
        if token in seen_tokens:
            continue
        seen_tokens.add(token)

        # age
        age_days = estimate_contract_age_days(w3, token)

        # unverified?
        unverified = is_unverified(token, chain=args.chain)

        # USD liquidity via your multi-base helper
        liq = get_best_pool_and_usd_liquidity(w3, token, cfg)
        usd_liq = liq["usd_liquidity_est"] if liq else 0.0

        # filter to “clean HIGH risk test set”
        if (unverified and usd_liq <= args.max_usd_liq and age_days <= args.max_age_days):
            picks.append({
                "chain": args.chain,
                "token": token,
                "pair": liq["pair"] if liq else None,
                "base_symbol": liq["base_symbol"] if liq else None,
                "usd_liq": round(usd_liq, 2),
                "age_days": round(age_days, 4),
            })
            if len(picks) >= args.limit:
                break

    # write addresses for batch scanner
    with open(args.out, "w") as f:
        for p in picks:
            f.write(p["token"] + "\n")

    print(f"✅ Wrote {len(picks)} tokens to {args.out}")
    print(json.dumps(picks, indent=2))

if __name__ == "__main__":
    main()
'''