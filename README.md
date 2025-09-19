Scammer Trapper 9000

A token risk radar for Ethereum & BSC. It inspects ERC-20/BEP-20 contracts, flags suspicious patterns, and assigns a simple risk score.
You can run it as a web app, a FastAPI backend, or from the command line (CLI / batch scanner).

⚠️ Disclaimer: This tool is for research and educational purposes only. It is not financial advice. Always do your own research.

Features

Multi-chain support: Ethereum (ETH) and Binance Smart Chain (BSC).

Risk checks include:

Ownership renounced or not (including proxy heuristics).

ABI verification & suspicious functions (blacklist, maxTx, etc).

Mint function detection.

Fee getter inspection (buy/sell/transfer taxes).

Liquidity depth across common bases (WETH, USDC, BNB, etc).

Contract age via Etherscan API.

Optional honeypot probe (buy/sell quotes).

Scoring: Assigns a 0–100 risk score with LOW / MEDIUM / HIGH tiers.

Interfaces:

Web UI (index.html) with dark theme, filters, CSV/JSON export.

FastAPI backend (api.py) exposing /api/risk and /api/batch.

CLI (cli.py) for single addresses.

Batch CLI (batch_cli.py) for text files → CSV/JSON results.

Developer-friendly:

Debug prints for every step.

Environment-driven config (.env).

Pluggable Web3 RPCs and rate-limited explorer calls.

Project Structure
.
├── api.py                # FastAPI app with /api endpoints
├── cli.py                # CLI scanner for one address
├── batch_cli.py          # Batch scanner with CSV/JSON output
├── index.html            # Web UI (frontend)
├── backend/
│   ├── core/
│   │   ├── analyze.py    # Orchestrates all checks → analyze_token()
│   │   └── score.py      # Simple scoring rules
│   ├── utils/
│   │   ├── abi_loader.py # Fetch ABI + suspicious functions
│   │   ├── addr.py       # EVM address normalizer
│   │   ├── cache.py      # TTL memoization decorator
│   │   ├── context.py    # Contract creation & age
│   │   ├── fee_check.py  # Extract buy/sell/transfer fees
│   │   ├── honeypot.py   # Honeypot probe via router
│   │   ├── liquidity.py  # Find deepest V2 pair (Uniswap/Pancake)
│   │   ├── mint_check.py # Mint function detection
│   │   ├── ownership.py  # Owner detection (EOA/Contract, renounced, proxy)
│   │   ├── ratelimit.py  # HTTP + rate limiting for APIs
│   │   └── risk_score.py # Alternative advanced scoring model
│   └── chains.py         # Chain config + Web3 factory
├── .env                  # Environment variables
├── requirements.txt      # Python dependencies

Installation

Clone the repo.

Install dependencies:

pip install -r requirements.txt


Copy .env and configure:

ETHERSCAN_API_KEY=yourEtherscanOrBscScanKey
WEB3_PROVIDER_ETH=https://eth-mainnet.g.alchemy.com/v2/yourKey
WEB3_PROVIDER_BSC=https://bsc-dataseed.binance.org
HONEYPOT_PROBE=0     # set to 1 to enable honeypot probing
ETHERSCAN_QPS=4      # rate limit for API calls

Usage
1. FastAPI Backend

Run:

uvicorn api:app --reload


Endpoints:

GET /api/health → {ok: true}

GET /api/risk/{address}?chain=eth|bsc → single analysis

POST /api/batch → JSON body with { chain, addresses, concurrency, etherscan_qps }

2. Web UI

Open index.html in a browser.
It talks to your local FastAPI (/api/batch).
Features: paste addresses, choose chain, set concurrency/QPS, filter results, export CSV/JSON.

3. CLI (single address)
python cli.py --chain eth --address 0xYourToken


Options:

--json → dump raw JSON result.

4. Batch CLI
python batch_cli.py --chain bsc --infile tokens.txt --out-csv results.csv --out-json results.json


Where tokens.txt contains one address per line.

Example Output

Single run (cli.py):

✅ Connected. Chain=eth  Address=0x123...
🚩 Ownership NOT renounced — owner=0xabc... (EOA)
✅ No mint function found.
💸 Fees detected: buy≈4.00%, sell≈6.00%
🔹 Base reserve ≈ 25,000 USDC
📅 Contract age ≈ 3.2 days
🧮 Final Risk Score: 64/100
❗ HIGH RISK


Web UI (index.html):
Shows a sortable/filterable table of results with colored badges (LOW/MEDIUM/HIGH).

Scoring

By default, backend/core/score.py is used:

Ownership not renounced: +25 risk.

ABI not verified: +20 risk.

Suspicious functions: +30 risk.

Mint present: +15 risk.

Low liquidity (<$1k): +20 risk.

LP not burned: +10 risk.

New (<2d): +10 risk.

Scores map to tiers:

0–24 → LOW

25–59 → MEDIUM

60–100 → HIGH

An experimental advanced model exists in utils/risk_score.py for more nuanced scoring.

Development Notes

Debug prints are everywhere ([ANALYZE], [API], etc).

analyze_token() is the heart: it orchestrates ownership, ABI, mint, fees, liquidity, age, honeypot, then scoring.

Rate limiting ensures you don’t hammer Etherscan/BscScan (default 4 req/s).

Honeypot probe is disabled by default via .env. Enable only if you know the risks.

License

For educational / research use. Not licensed for financial advice or production trading bots.
