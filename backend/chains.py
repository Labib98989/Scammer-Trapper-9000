# backend/chains.py
# Purpose: Chain config + web3 factory (Web3 v7). Injects POA middleware for BSC.

import os
from web3 import Web3
from web3.middleware.proof_of_authority import ExtraDataToPOAMiddleware

print("[CHAINS] module loaded (web3 v7)")

# One Etherscan V2 base works for multi-chain keys
EXPLORER_V2_BASE = "https://api.etherscan.io/v2/api"

CHAINS = {
    "eth": {
        "name": "eth",
        "chainid": 1,
        "rpc_env": "WEB3_PROVIDER_ETH",
        "factory_v2": Web3.to_checksum_address("0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f"),  # Uniswap V2
        "explorer_v1_host": "https://api.etherscan.io/api",
        "bases": [
            {"symbol": "WETH", "address": Web3.to_checksum_address("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"), "type": "wrapped"},
            {"symbol": "USDC", "address": Web3.to_checksum_address("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"), "type": "stable"},
            {"symbol": "USDT", "address": Web3.to_checksum_address("0xdAC17F958D2ee523a2206206994597C13D831ec7"), "type": "stable"},
            {"symbol": "DAI",  "address": Web3.to_checksum_address("0x6B175474E89094C44Da98b954EedeAC495271d0F"), "type": "stable"},
        ],
    },
    "bsc": {
        "name": "bsc",
        "chainid": 56,
        "rpc_env": "WEB3_PROVIDER_BSC",
        "factory_v2": Web3.to_checksum_address("0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73"),  # Pancake V2
        "explorer_v1_host": "https://api.bscscan.com/api",
        "bases": [
            {"symbol": "WBNB", "address": Web3.to_checksum_address("0xBB4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"), "type": "wrapped"},
            {"symbol": "USDT", "address": Web3.to_checksum_address("0x55d398326f99059fF775485246999027B3197955"), "type": "stable"},
            {"symbol": "USDC", "address": Web3.to_checksum_address("0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d"), "type": "stable"},
            {"symbol": "BUSD", "address": Web3.to_checksum_address("0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56"), "type": "stable"},
        ],
    },
}

def get_w3_for_chain(chain_key: str) -> Web3:
    print(f"[CHAINS] get_w3_for_chain({chain_key})")
    if chain_key not in CHAINS:
        raise ValueError(f"Unknown chain: {chain_key}")

    cfg = CHAINS[chain_key]
    rpc = os.getenv(cfg["rpc_env"]) or (os.getenv("WEB3_PROVIDER") if chain_key == "eth" else "")
    rpc = (rpc or "").strip().rstrip("\r")

    if not rpc or rpc in {"https://", "http://"}:
        if chain_key == "bsc":
            rpc = "https://bsc-dataseed.binance.org"
            print(f"[CHAINS] Using default BSC RPC: {rpc}")
        else:
            raise ValueError(f"Missing/invalid RPC URL for {chain_key}. Set {cfg['rpc_env']} in .env")

    print(f"[CHAINS] HTTPProvider -> {rpc}")
    w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 30}))

    # Inject POA middleware for PoA-like chains (BSC, etc.)
    if cfg["chainid"] in (56, 97):
        try:
            w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
            print(f"[CHAINS] POA middleware injected (ExtraDataToPOAMiddleware) for {chain_key}")
        except Exception as e:
            print(f"[CHAINS] POA inject failed for {chain_key}: {e}")

    cid = w3.eth.chain_id
    print(f"[CHAINS] Connected chainId={cid}")
    return w3

__all__ = ["EXPLORER_V2_BASE", "CHAINS", "get_w3_for_chain"]
