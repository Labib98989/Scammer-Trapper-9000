# backend/utils/addr.py
from web3 import Web3

def normalize_evm_address(raw: str) -> str:
    """Strictly validate & checksum an EVM address."""
    s = (raw or "").strip()
    if "..." in s:
        raise ValueError("Ellipses ('...') are not allowed. Provide the full 42-char 0x address.")
    if not s.startswith("0x") or len(s) != 42:
        raise ValueError("Invalid address: must be 0x-prefixed and 42 characters long (0x + 40 hex).")
    try:
        return Web3.to_checksum_address(s)
    except Exception:
        raise ValueError("Invalid address: not a valid hex string.")
