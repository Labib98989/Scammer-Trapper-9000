# scanner.py
'''from web3 import Web3
import os
from dotenv import load_dotenv

from backend.utils.ownership import check_ownership
from backend.utils.abi_loader import fetch_contract_abi, scan_for_suspicious_functions
from backend.utils.mint_check import check_mint_function
from backend.utils.fee_check import read_fees              # <-- NEW
from backend.utils.risk_score import score_token
from backend.utils.liquidity import get_v2_pair, read_pair_liquidity
from backend.utils.context import get_contract_age_days

load_dotenv()
w3 = Web3(Web3.HTTPProvider(os.getenv("WEB3_PROVIDER")))

print("✅ Connected to Ethereum")
print("Latest block:", w3.eth.block_number)

token_address = "0x042F6d08d62De8A46ec44999ffbb8b6276916e62" # change per test order

# --- Ownership (works without ABI)
ownership_result = check_ownership(w3, token_address)
print(ownership_result)

# --- ABI-dependent checks
abi_verified = True
flagged = []
has_mint = False
fees = {}

try:
    abi = fetch_contract_abi(token_address)

    flagged = scan_for_suspicious_functions(abi)
    print("🚨 Suspicious functions detected:", flagged) if flagged else print("✅ No blacklist/whitelist/bot traps found.")

    has_mint = check_mint_function(abi)
    print("🚨 Mint function found!" if has_mint else "✅ No mint function found.")

    fees = read_fees(w3, token_address, abi)
    if fees:
        # print top few fees sorted by value
        top = sorted(fees.items(), key=lambda kv: kv[1], reverse=True)[:6]
        pretty = ", ".join([f"{k}≈{v:.2f}%" for k, v in top])
        print(f"💸 Fees detected: {pretty}")
    else:
        print("✅ No explicit fee getters detected.")

except ValueError as e:
    print(str(e))
    print("ℹ️ Skipping ABI-based checks for this contract.")
    abi_verified = False

# --- Liquidity (Uniswap V2)
lp_info = None
pair = get_v2_pair(w3, token_address)
if pair:
    lp_info = read_pair_liquidity(w3, pair)
    print(f"🔹 Pair: {lp_info['pair']}")
    print(f"🔹 WETH reserve ≈ {lp_info['weth_reserve_eth']:.6f} ETH")
    print(f"🔹 LP burn ≈ {lp_info['lp_burn_pct']:.2f}% (burned {lp_info['lp_burned']}/{lp_info['lp_total_supply']})")
else:
    print("ℹ️ No UniswapV2 token/WETH pair found — skipping liquidity checks.")

# --- Context (age)
age_days = get_contract_age_days(w3, token_address)
print(f"📅 Contract age ≈ {age_days:.1f} days")
context = {"age_days": age_days}

# --- Score (now includes fees)
risk = score_token(
    ownership_result,
    flagged,
    has_mint,
    abi_verified,
    lp_info,
    context,
    fees,
)
print(f"🧮 Final Risk Score: {risk}/100")
if risk >= 70:
    print("❗ HIGH RISK")
elif risk >= 30:
    print("⚠️  MEDIUM RISK")
else:
    print("✅ LOW RISK")'''
