# backend/utils/ownership.py
from typing import Optional
from web3 import Web3
from web3.exceptions import ContractLogicError, BadFunctionCallOutput

# Common owner/admin getters seen in the wild
OWNER_METHOD_CANDIDATES = [
    "owner", "getOwner", "ownerAddress",
    "admin", "getAdmin", "proxyAdmin",
]

# EIP-1967 implementation slot: keccak256('eip1967.proxy.implementation') - 1
EIP1967_IMPL_SLOT = int(
    "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc", 16
)

def _dbg(msg: str) -> None:
    print(f"[ownership] {msg}")

def _addr_or_none(raw: bytes) -> Optional[str]:
    """Interpret the last 20 bytes of a 32-byte storage value as an address."""
    if not raw or len(raw) < 20:
        return None
    addr = "0x" + raw[-20:].hex()
    if addr.lower() == "0x0000000000000000000000000000000000000000":
        return None
    if not Web3.is_address(addr):
        return None
    return Web3.to_checksum_address(addr)

def _addr_type(w3: Web3, address: str) -> str:
    """Return 'EOA' if no code, else 'Contract'."""
    code = w3.eth.get_code(Web3.to_checksum_address(address))
    return "EOA" if len(code) == 0 else "Contract"

def _call_owner_like(w3: Web3, address: str) -> Optional[str]:
    """Try ABI-based getters like owner(), admin(), etc."""
    addr = Web3.to_checksum_address(address)
    for name in OWNER_METHOD_CANDIDATES:
        abi = [{
            "constant": True,
            "inputs": [],
            "name": name,
            "outputs": [{"name": "", "type": "address"}],
            "type": "function",
        }]
        contract = w3.eth.contract(address=addr, abi=abi)
        try:
            _dbg(f"try getter: {name}()")
            val = getattr(contract.functions, name)().call()
            if isinstance(val, str) and Web3.is_address(val):
                return Web3.to_checksum_address(val)
        except (ContractLogicError, BadFunctionCallOutput, ValueError):
            continue
        except Exception:
            continue
    return None

def _raw_owner_like(w3: Web3, address: str) -> Optional[str]:
    """
    Low-level call (no ABI) to common selectors: owner(), getOwner(), admin(), etc.
    If function exists and returns a 32-byte ABI-encoded address, decode it.
    """
    addr = Web3.to_checksum_address(address)
    signatures = [
        "owner()", "getOwner()", "ownerAddress()",
        "admin()", "getAdmin()", "proxyAdmin()",
    ]
    for sig in signatures:
        try:
            selector = w3.keccak(text=sig)[:4]  # 4-byte selector
            data = "0x" + selector.hex()
            res = w3.eth.call({"to": addr, "data": data})
            if res and len(res) >= 32:
                a = "0x" + res[-20:].hex()
                if Web3.is_address(a) and a.lower() != "0x0000000000000000000000000000000000000000":
                    _dbg(f"raw owner hit via {sig} -> {a}")
                    return Web3.to_checksum_address(a)
        except Exception:
            continue
    return None

def _read_eip1967_impl(w3: Web3, address: str) -> Optional[str]:
    """Read the EIP-1967 implementation slot; return implementation address if present."""
    try:
        raw = w3.eth.get_storage_at(Web3.to_checksum_address(address), EIP1967_IMPL_SLOT)
        impl = _addr_or_none(raw)
        if impl:
            _dbg(f"EIP-1967 impl slot nonzero → {impl}")
        else:
            _dbg("EIP-1967 impl slot empty/zero")
        return impl
    except Exception as e:
        _dbg(f"EIP-1967 read error: {e}")
        return None

def _heuristic_owner_slots(w3: Web3, address: str) -> Optional[str]:
    """
    [Inference] Probe slot 0 and 1 for an address-like value.
    Not guaranteed; some Ownable patterns store _owner at slot 0.
    """
    try:
        for slot in (0, 1):
            raw = w3.eth.get_storage_at(Web3.to_checksum_address(address), slot)
            cand = _addr_or_none(raw)
            if cand:
                _dbg(f"[heuristic] slot {slot} looks like addr → {cand}")
                return cand
    except Exception as e:
        _dbg(f"[heuristic] slot read error: {e}")
    return None

def check_ownership(w3: Web3, token_address: str) -> str:
    """Ownership checker with raw calls, ABI getters, proxy follow, and heuristics."""
    _dbg(f"checking ownership for {Web3.to_checksum_address(token_address)}")

    # 0) raw low-level try (no ABI)
    raw_owner = _raw_owner_like(w3, token_address)
    if raw_owner:
        otype = _addr_type(w3, raw_owner)
        if raw_owner.lower() == "0x0000000000000000000000000000000000000000":
            return "✅ Ownership is RENOUNCED."
        return f"🚩 Ownership NOT renounced — owner={raw_owner} ({otype})"

    # 1) ABI-based getters
    direct_owner = _call_owner_like(w3, token_address)
    if direct_owner:
        otype = _addr_type(w3, direct_owner)
        if direct_owner.lower() == "0x0000000000000000000000000000000000000000":
            return "✅ Ownership is RENOUNCED."
        return f"🚩 Ownership NOT renounced — owner={direct_owner} ({otype})"

    # 2) EIP-1967 proxy? follow to implementation and retry
    impl = _read_eip1967_impl(w3, token_address)
    if impl:
        impl_raw_owner = _raw_owner_like(w3, impl) or _call_owner_like(w3, impl)
        if impl_raw_owner:
            otype = _addr_type(w3, impl_raw_owner)
            if impl_raw_owner.lower() == "0x0000000000000000000000000000000000000000":
                return "✅ Ownership is RENOUNCED (via proxy impl)."
            return f"🚩 Ownership NOT renounced (proxy) — owner={impl_raw_owner} ({otype})"
        _dbg("proxy impl has no standard owner/admin getter")

    # 3) As a last resort, try heuristic slots on main & impl
    heur = _heuristic_owner_slots(w3, token_address)
    if heur:
        otype = _addr_type(w3, heur)
        return f"[Inference] 🚩 Owner-like value from storage — owner≈{heur} ({otype})"

    if impl:
        heur2 = _heuristic_owner_slots(w3, impl)
        if heur2:
            otype2 = _addr_type(w3, heur2)
            return f"[Inference] 🚩 Owner-like (proxy impl) — owner≈{heur2} ({otype2})"

    # 4) nothing worked
    return "⚠️ Cannot detect ownership — contract may be nonstandard or protected."
