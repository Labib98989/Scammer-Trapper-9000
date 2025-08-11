# backend/utils/liquidity.py
from typing import Optional, Dict, Any, List
from web3 import Web3
from backend.chains import CHAINS
from backend.utils.cache import memoize_ttl

ZERO = "0x0000000000000000000000000000000000000000"

FACTORY_ABI = [{
    "name": "getPair",
    "outputs": [{"type": "address","name": "pair"}],
    "inputs": [{"type": "address","name": "tokenA"}, {"type": "address","name": "tokenB"}],
    "stateMutability": "view", "type": "function"
}]

PAIR_ABI = [
    {"name":"getReserves","outputs":[
        {"type":"uint112","name":"_reserve0"},
        {"type":"uint112","name":"_reserve1"},
        {"type":"uint32","name":"_blockTimestampLast"}],
     "inputs":[], "stateMutability":"view","type":"function"},
    {"name":"token0","outputs":[{"type":"address","name":""}],"inputs":[],"stateMutability":"view","type":"function"},
    {"name":"token1","outputs":[{"type":"address","name":""}],"inputs":[],"stateMutability":"view","type":"function"},
]

ERC20_ABI = [
    {"name":"decimals","outputs":[{"type":"uint8","name":""}],"inputs":[],"stateMutability":"view","type":"function"},
    {"name":"symbol","outputs":[{"type":"string","name":""}],"inputs":[],"stateMutability":"view","type":"function"},
]

def _dbg(msg: str):
    print(f"[liquidity] {msg}")

@memoize_ttl(10)
def get_deepest_v2_pool(w3: Web3, chain_key: str, token: str) -> Optional[Dict[str, Any]]:
    cfg = CHAINS[chain_key]
    token = Web3.to_checksum_address(token)
    factory_addr = cfg["factory_v2"]
    bases: List[Dict[str, str]] = cfg.get("bases", [])
    factory = w3.eth.contract(address=factory_addr, abi=FACTORY_ABI)

    best = None
    best_depth = -1.0

    # preload token symbol (debug only)
    try:
        tsym = w3.eth.contract(address=token, abi=ERC20_ABI).functions.symbol().call()
    except Exception:
        tsym = token[-4:]

    _dbg(f"factory={factory_addr} chain={chain_key} token={tsym}({token})")

    for b in bases:
        base_addr = Web3.to_checksum_address(b["address"])
        base_sym = b["symbol"]

        if base_addr == token:
            # skip self-pair attempt
            _dbg(f"skip base={base_sym} because base==token")
            continue

        try:
            pair = factory.functions.getPair(token, base_addr).call()
        except Exception as e:
            _dbg(f"getPair failed for base={base_sym}: {e}")
            continue

        if not pair or pair == ZERO:
            _dbg(f"no pair for {base_sym}")
            continue

        pair_c = w3.eth.contract(address=pair, abi=PAIR_ABI)
        t0 = pair_c.functions.token0().call()
        t1 = pair_c.functions.token1().call()
        r0, r1, _ = pair_c.functions.getReserves().call()

        # identify which reserve is the base
        if Web3.to_checksum_address(t0) == base_addr:
            base_reserve = r0
            token_reserve = r1
        else:
            base_reserve = r1
            token_reserve = r0

        # humanize base reserve
        try:
            base_dec = w3.eth.contract(address=base_addr, abi=ERC20_ABI).functions.decimals().call()
        except Exception:
            base_dec = 18
        base_human = float(base_reserve) / float(10 ** base_dec)

        # Heuristic USD estimate: stables ~1, wrapped ignored (set 0, we’ll still compare by base_human)
        usd_est = base_human if b.get("type") == "stable" else 0.0

        depth_key = usd_est if b.get("type") == "stable" else base_human
        if depth_key > best_depth:
            best_depth = depth_key
            best = {
                "pair": pair,
                "base_symbol": base_sym,
                "base_address": base_addr,
                "base_reserve_human": base_human,
                "usd_liquidity_est": usd_est,
                "token_reserve_units": int(token_reserve),
            }

        _dbg(f"pair found base={base_sym} pair={pair} base_reserve≈{base_human}")

    if not best:
        _dbg("no V2 token/base pairs found across bases")

    return best
