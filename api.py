# api.py
import os
from pathlib import Path
from typing import List

print("[API] Booting FastAPI...")

from fastapi import FastAPI, HTTPException, Query, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed

_loaded = load_dotenv()
print(f"[API] .env loaded: {_loaded}")
print(f"[API] ENV presence -> ETH RPC: {'yes' if os.getenv('WEB3_PROVIDER_ETH') else 'no'}, "
      f"BSC RPC: {'yes' if os.getenv('WEB3_PROVIDER_BSC') else 'no'}, "
      f"ETHERSCAN_API_KEY: {'yes' if os.getenv('ETHERSCAN_API_KEY') else 'no'}, "
      f"BSCSCAN_API_KEY: {'yes' if os.getenv('BSCSCAN_API_KEY') else 'no'}")

try:
    from backend.core.analyze import analyze_token
    print("[API] Import analyze_token: OK")
except Exception as e:
    print("[API] Import analyze_token: FAIL ->", e)
    raise

try:
    from backend.utils.ratelimit import set_default_qps
    print("[API] Import set_default_qps: OK")
except Exception as e:
    print("[API] Import set_default_qps: FAIL ->", e)
    raise

app = FastAPI(title="Token Rug Radar API", version="0.3.1-debug")
print("[API] FastAPI instance created.")

# CORS
try:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    print("[API] CORS middleware registered.")
except Exception as e:
    print("[API] CORS registration failed:", e)

api = APIRouter(prefix="/api")
print("[API] APIRouter created at /api.")


@api.get("/health")
def health():
    print("[API] GET /api/health")
    return {"ok": True}


@api.get("/risk/{address}")
def risk(address: str, chain: str = Query(default="eth", pattern="^(eth|bsc)$")):
    print(f"[API] GET /api/risk/{address}?chain={chain} -> start")
    try:
        out = analyze_token(chain, address)
        print(f"[API] /risk OK address={address} chain={chain} score={out.get('score')} tier={out.get('risk_tier')}")
        return out
    except ValueError as ve:
        print(f"[API] /risk ValueError address={address} chain={chain} -> {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        print(f"[API] /risk ERROR address={address} chain={chain} -> {e}")
        raise HTTPException(status_code=400, detail=str(e))


from pydantic import BaseModel
class BatchJob(BaseModel):
    chain: str = "eth"
    addresses: List[str]
    concurrency: int = 2
    etherscan_qps: float = 4.0


@api.post("/batch")
def batch(job: BatchJob):
    print(f"[API] POST /api/batch -> chain={job.chain} count={len(job.addresses)} conc={job.concurrency} qps={job.etherscan_qps}")
    if job.chain not in ("eth", "bsc"):
        print("[API] /batch error: invalid chain")
        raise HTTPException(status_code=400, detail="chain must be 'eth' or 'bsc'")
    if not job.addresses:
        print("[API] /batch error: empty addresses")
        raise HTTPException(status_code=400, detail="addresses list is empty")

    try:
        set_default_qps(job.etherscan_qps)
        print(f"[API] /batch rate limit set: {job.etherscan_qps} req/s")
    except Exception as e:
        print("[API] /batch rate limit set FAIL:", e)

    out = []

    def work(addr: str):
        print(f"[API][WORK] Start {addr}")
        try:
            res = analyze_token(job.chain, addr)
            print(f"[API][WORK] OK {addr} score={res.get('score')} tier={res.get('risk_tier')}")
            return res
        except Exception as e:
            print(f"[API][WORK] FAIL {addr} -> {e}")
            return {"chain": job.chain, "address": addr, "error": str(e)}

    try:
        with ThreadPoolExecutor(max_workers=max(1, min(8, job.concurrency))) as ex:
            futs = {ex.submit(work, a): a for a in job.addresses}
            for fut in as_completed(futs):
                out.append(fut.result())
        print(f"[API] /batch completed -> {len(out)} results")
    except Exception as e:
        print("[API] /batch thread pool error:", e)
        raise HTTPException(status_code=500, detail=str(e))

    return {"count": len(out), "results": out}


# Register API first, then static site at /
app.include_router(api)
print("[API] Router included.")

# Safe static mount: prefer ./web, fall back to current dir if missing
static_dir = Path("web")
try:
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="web")
        print("[API] Static mount: / -> web/")
    else:
        app.mount("/", StaticFiles(directory=".", html=True), name="web")
        print("[API] ⚠️ web/ not found; mounted current directory '.' instead.")
except Exception as e:
    print("[API] Static mount FAILED:", e)
