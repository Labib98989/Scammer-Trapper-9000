# backend/utils/ratelimit.py
import time, random, threading
from collections import deque
import requests

# Default QPS (requests per second) for explorer APIs (Etherscan/BscScan).
# You can override at runtime (see set_default_qps).
DEFAULT_QPS = 4.0

# One limiter per "host key" (e.g., 'etherscan_v2', 'etherscan_v1', 'bscscan_v1')
_LIMITERS = {}
_LOCK = threading.Lock()

class RateLimiter:
    def __init__(self, max_per_sec: float):
        self.max_per_sec = max(0.1, float(max_per_sec))
        self.window = deque()
        self.lock = threading.Lock()

    def wait(self):
        with self.lock:
            now = time.monotonic()
            # drop timestamps older than 1s
            while self.window and now - self.window[0] > 1.0:
                self.window.popleft()

            if len(self.window) >= self.max_per_sec:
                # sleep until we drop under the limit
                sleep_for = 1.0 - (now - self.window[0]) + 0.001
                if sleep_for > 0:
                    time.sleep(sleep_for)
                # cleanup after sleeping
                now = time.monotonic()
                while self.window and now - self.window[0] > 1.0:
                    self.window.popleft()

            self.window.append(time.monotonic())

def _get_limiter(host_key: str, max_qps: float | None):
    with _LOCK:
        qps = DEFAULT_QPS if max_qps is None else float(max_qps)
        lim = _LIMITERS.get(host_key)
        if lim is None or getattr(lim, "max_per_sec", None) != qps:
            lim = RateLimiter(qps)
            _LIMITERS[host_key] = lim
        return lim

def http_get_json(host_key: str, url: str, params: dict, max_qps: float | None = None, timeout: int = 15) -> dict:
    """
    GET with per-host rate limiting + retries. Returns response.json() or raises.
    Retries on 429/5xx, small jitter, keeps QPS under control.
    """
    lim = _get_limiter(host_key, max_qps)
    backoff = 0.5
    for attempt in range(5):
        lim.wait()
        try:
            resp = requests.get(url, params=params, timeout=timeout)
            status = resp.status_code
            if status == 200:
                return resp.json()
            if status in (429, 500, 502, 503, 504):
                time.sleep(backoff + random.uniform(0, 0.2))
                backoff = min(backoff * 2, 4.0)
                continue
            # other status codes: bail
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException:
            time.sleep(backoff + random.uniform(0, 0.2))
            backoff = min(backoff * 2, 4.0)
    # final try (let the exception surface for visibility)
    lim.wait()
    resp = requests.get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    return resp.json()

def set_default_qps(qps: float):
    global DEFAULT_QPS
    DEFAULT_QPS = max(0.1, float(qps))
