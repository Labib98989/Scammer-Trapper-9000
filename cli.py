# cli.py
import argparse
import json
import os
import sys
from pathlib import Path

print("[CLI] Booting...")

from dotenv import load_dotenv
_loaded = load_dotenv()
print(f"[CLI] .env loaded: {_loaded}")
print(f"[CLI] ENV presence -> ETH RPC: {'yes' if os.getenv('WEB3_PROVIDER_ETH') else 'no'}, "
      f"BSC RPC: {'yes' if os.getenv('WEB3_PROVIDER_BSC') else 'no'}, "
      f"ETHERSCAN_API_KEY: {'yes' if os.getenv('ETHERSCAN_API_KEY') else 'no'}, "
      f"BSCSCAN_API_KEY: {'yes' if os.getenv('BSCSCAN_API_KEY') else 'no'}")

try:
    from backend.core.analyze import analyze_token
    print("[CLI] Import analyze_token: OK")
except Exception as e:
    print("[CLI] Import analyze_token: FAIL ->", e)
    sys.exit(1)


def main():
    print("[CLI] Parsing arguments...")
    p = argparse.ArgumentParser(description="Token Rug Radar CLI (debug prints)")
    p.add_argument("--chain", default="eth", choices=["eth", "bsc"], help="Chain to use (eth|bsc)")
    p.add_argument("--address", required=True, help="ERC-20 contract address")
    p.add_argument("--json", action="store_true", help="Print JSON only")
    args = p.parse_args()
    print(f"[CLI] Args -> chain={args.chain} address={args.address} json={args.json}")

    print("[CLI] Calling analyze_token...")
    try:
        result = analyze_token(args.chain, args.address)
        print("[CLI] analyze_token: OK")
    except Exception as e:
        print("[CLI] analyze_token: FAIL ->", e)
        return

    if args.json:
        print("[CLI] --json requested; dumping raw result...")
        print(json.dumps(result, indent=2, sort_keys=False, default=str))
        print("[CLI] Done.")
        return

    # Pretty output with defensive checks
    try:
        print(f"✅ Connected. Chain={result.get('chain','?')}  Address={result.get('address','?')}")
        print("[CLI] Ownership block...")
        print(result.get("ownership"))

        print("[CLI] ABI checks block...")
        if result.get("abi_verified"):
            funcs = result.get("suspicious_functions") or []
            if funcs:
                print("🚨 Suspicious functions:", funcs)
            else:
                print("✅ No blacklist/whitelist/bot traps found.")
            print("🚨 Mint function found!" if result.get("has_mint") else "✅ No mint function found.")
            fees = result.get("fees_percent") or {}
            if fees:
                # Keep only numeric values to prevent formatting crashes
                numeric = {k: v for k, v in fees.items() if isinstance(v, (int, float))}
                if numeric:
                    top = sorted(numeric.items(), key=lambda kv: kv[1], reverse=True)[:6]
                    pretty = ", ".join([f"{k}≈{v:.2f}%" for k, v in top])
                    print(f"💸 Fees detected: {pretty}")
                else:
                    print("✅ No numeric fee getters detected.")
            else:
                print("✅ No explicit fee getters detected.")
        else:
            print(result.get("abi_error") or "ABI not verified.")
            print("ℹ️ Skipping ABI-based checks for this contract.")

        print("[CLI] Liquidity block...")
        lp = result.get("liquidity")
        if lp:
            pair = lp.get("pair")
            if pair:
                print(f"🔹 Pair: {pair}")
            else:
                print("🔹 Pair: n/a (field missing)")

            base_sym = lp.get("base_symbol")
            if base_sym:
                print(f"🔹 Deepest base: {base_sym}")

            base_human = lp.get("base_reserve_human")
            if base_human is None:
                base_human = (lp.get("base_reserve_units", 0.0) / 1e18)
            try:
                print(f"🔹 Base reserve ≈ {float(base_human):.6f}")
            except Exception as e:
                print(f"🔹 Base reserve: n/a (format error: {e})")

            usd = lp.get("usd_liquidity_est")
            if usd is not None:
                try:
                    print(f"🔹 ~USD liquidity ≈ ${float(usd):,.0f}")
                except Exception as e:
                    print(f"🔹 ~USD liquidity: n/a (format error: {e})")

            if "lp_burn_pct" in lp:
                try:
                    print(f"🔹 LP burn ≈ {float(lp['lp_burn_pct']):.2f}% "
                          f"(burned {lp.get('lp_burned','?')}/{lp.get('lp_total_supply','?')})")
                except Exception as e:
                    print(f"🔹 LP burn: n/a (format error: {e})")
            else:
                print("🔹 LP burn: n/a (not computed)")
        else:
            print("ℹ️ No V2 token/base pair found — skipping liquidity checks.")

        ctx = result.get("context") or {}
        age = ctx.get("age_days")
        if isinstance(age, (int, float)):
            print(f"📅 Contract age ≈ {float(age):.1f} days")
        else:
            print("📅 Contract age: unknown")


        try:
            print(f"🧮 Final Risk Score: {result.get('score','?')}/100")
            tier = result.get("risk_tier", "?")
            print("❗ HIGH RISK" if tier == "HIGH"
                  else "⚠️  MEDIUM RISK" if tier == "MEDIUM"
                  else "✅ LOW RISK" if tier == "LOW"
                  else f"❓ Unknown tier: {tier}")
        except Exception as e:
            print("[CLI] Risk print failed:", e)

    except Exception as e:
        print("[CLI] Pretty print block: FAIL ->", e)

    print("[CLI] Done.")


if __name__ == "__main__":
    main()
