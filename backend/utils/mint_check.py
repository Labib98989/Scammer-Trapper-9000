# backend/utils/mint_check.py
def check_mint_function(abi: list) -> bool:
    """
    Returns True if a mint-like function exists (name contains 'mint').
    """
    for item in abi:
        if item.get("type") == "function":
            name = (item.get("name") or "").lower()
            if "mint" in name:
                return True
    return False
