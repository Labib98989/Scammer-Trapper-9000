# batch_cli.py
import argparse, json, csv, sys, os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

print("[BATCH] Booting...")

from dotenv import load_dotenv
_loaded = load_dotenv()
print(f"[BATCH] .env loaded: {_loaded}")
print(f"[BATCH] ENV presence -> ETH RPC: {'yes' if os.getenv('WEB3_PROVIDER_ETH') else 'no'}, "
      f"BSC RPC: {'yes' if os.getenv('WEB3_PROVIDER_BSC') else 'no'}, "
      f"ETHERSCAN_API_KEY: {'yes' if os.getenv('ETHERSCAN_API_KEY') else 'no'}, "
      f"BSCSCAN_API_KEY: {'yes' if os.getenv('BSCSCAN_API_KEY') else 'no'}")

try:
    from backend.core.analyze import analyze_token
    print("[BATCH] Import analyze_token: OK")
except Exception as e:
    print("[BATCH] Import analyze_token: FAIL ->", e)
    sys.exit(1)

try:
    from backend.utils.ratelimit import set_default_qps
    print("[BATCH] Import set_default_qps: OK")
except Exception as e:
    print("[BATCH] Import set_default_qps: FAIL ->", e)
    sys.exit(1)


def load_addresses(path: str) -> list[str]:
    print(f"[BATCH] Loading addresses from: {path}")
    p = Path(path)
    if not p.exists():
        print(f"[BATCH] ❌ Input file not found: {path}", file=sys.stderr)
        sys.exit(1)
    addrs = []
    with p.open() as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            addrs.append(s)
    print(f"[BATCH] Loaded {len(addrs)} addresses")
    if addrs:
        print("[BATCH] First 3:", addrs[:3])
    return addrs


def _safe_float(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default


def flatten_result(res: dict) -> dict:
    print(f"[BATCH] Flattening result for {res.get('address','?')}")
    fees = (res.get("fees_percent") or {})
    fees_numeric = {k: v for k, v in fees.items() if isinstance(v, (int, float))}
    max_fee = max(fees_numeric.values()) if fees_numeric else 0.0

    lp = res.get("liquidity") or {}
    base_res = lp.get("base_reserve_human")
    if base_res is None:
        base_res = (lp.get("base_reserve_units") or 0.0) / 1e18
    usd = lp.get("usd_liquidity_est") or 0.0

    flat = {
        "chain": res.get("chain"),
        "address": res.get("address"),
        "ownership": res.get("ownership"),
        "abi_verified": res.get("abi_verified"),
        "suspicious_functions": ";".join(res.get("suspicious_functions") or []),
        "has_mint": res.get("has_mint"),
        "max_fee_pct": f"{_safe_float(max_fee):.2f}",
        "lp_burn_pct": f"{_safe_float(lp.get('lp_burn_pct', 0.0)):.2f}",
        "base_symbol": lp.get("base_symbol",""),
        "base_reserve": f"{_safe_float(base_res):.6f}",
        "usd_liquidity": f"{_safe_float(usd):.0f}",
        "age_days": f"{_safe_float((res.get('context') or {}).get('age_days', 0.0)):.1f}",
        "score": res.get("score"),
        "risk_tier": res.get("risk_tier"),
        "error": "",
    }
    print(f"[BATCH] Flattened: score={flat['score']} tier={flat['risk_tier']} max_fee={flat['max_fee_pct']} usd_liq={flat['usd_liquidity']}")
    return flat


def main():
    print("[BATCH] Parsing arguments...")
    ap = argparse.ArgumentParser(description="Token Rug Radar - Batch Scanner (debug prints)")
    ap.add_argument("--chain", default="eth", choices=["eth", "bsc"], help="Chain to scan")
    ap.add_argument("--infile", required=True, help="Path to text file with one address per line")
    ap.add_argument("--out-csv", default="batch_scan.csv", help="CSV output path")
    ap.add_argument("--out-json", default="batch_scan.json", help="JSON output path")
    ap.add_argument("--concurrency", type=int, default=2, help="Parallel scans (1–3 safe on free plans)")
    ap.add_argument("--etherscan-qps", type=float, default=4.0, help="Max req/s to explorer APIs")
    args = ap.parse_args()
    print(f"[BATCH] Args -> chain={args.chain} infile={args.infile} out_csv={args.out_csv} out_json={args.out_json} "
          f"conc={args.concurrency} qps={args.etherscan_qps}")

    set_default_qps(args.etherscan_qps)
    print(f"[BATCH] Rate limit set to {args.etherscan_qps} req/s")

    addresses = load_addresses(args.infile)

    print(f"[BATCH] Scanning {len(addresses)} addresses on {args.chain} with concurrency={args.concurrency}")
    rows, json_out = [], []

    def work(addr: str):
        print(f"[BATCH][WORK] Start {addr}")
        try:
            res = analyze_token(args.chain, addr)
            print(f"[BATCH][WORK] analyze_token OK {addr}")
            row = flatten_result(res)
            return row, res, None
        except Exception as e:
            print(f"[BATCH][WORK] analyze_token FAIL {addr} -> {e}")
            return {
                "chain": args.chain, "address": addr, "ownership": "", "abi_verified": "",
                "suspicious_functions": "", "has_mint": "", "max_fee_pct": "",
                "lp_burn_pct": "", "base_symbol": "", "base_reserve": "", "usd_liquidity": "",
                "age_days": "", "score": "", "risk_tier": "", "error": str(e)
            }, None, e

    try:
        with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as ex:
            futs = {ex.submit(work, a): a for a in addresses}
            for fut in as_completed(futs):
                row, res, err = fut.result()
                rows.append(row)
                json_out.append(res if res else {"chain": args.chain, "address": row["address"], "error": row["error"]})
                print(f"[BATCH] Result {row['address']} -> score={row.get('score','')} tier={row.get('risk_tier','')} {'(err:'+row['error']+')' if row['error'] else ''}")
        print("[BATCH] All tasks completed.")
    except Exception as e:
        print("[BATCH] Thread pool error:", e)

    fieldnames = ["chain","address","ownership","abi_verified","suspicious_functions","has_mint",
                  "max_fee_pct","lp_burn_pct","base_symbol","base_reserve","usd_liquidity",
                  "age_days","score","risk_tier","error"]
    try:
        with open(args.out_csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(rows)
        print(f"[BATCH] Wrote CSV -> {args.out_csv}")
    except Exception as e:
        print("[BATCH] CSV write FAIL:", e)

    try:
        with open(args.out_json, "w") as f:
            json.dump(json_out, f, indent=2)
        print(f"[BATCH] Wrote JSON -> {args.out_json}")
    except Exception as e:
        print("[BATCH] JSON write FAIL:", e)

    print("✅ Done. CSV →", args.out_csv, " JSON →", args.out_json)


if __name__ == "__main__":
    main()
