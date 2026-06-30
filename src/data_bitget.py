"""Bitget XAU/USDT perp data feed.

Bitget public API — no auth needed for market data.

First-check (2026-06-30, completed): XAUUSDT perp has $42M OI, $148M 24h volume.
This is meaningful liquidity — not thin-book noise. Funding rate signal is usable.

Three gold perps exist on Bitget. We use XAUUSDT (direct gold/USDT):
  XAUUSDT  : $148M vol, $42M OI  ← primary (most liquid)
  XAUTUSDT : $42M  vol, $32M OI  ← Tether-Gold backed, not direct gold
  PAXGUSDT : $14M  vol, $13M OI  ← thin

Endpoints used (Bitget API v2):
  /api/v2/mix/market/candles            — OHLCV bars
  /api/v2/mix/market/current-fund-rate  — current funding rate
  /api/v2/mix/market/history-fund-rate  — historical funding (100/page)
  /api/v2/mix/market/open-interest      — current OI
  /api/v2/mix/market/ticker             — last price + 24h volume
"""
from __future__ import annotations
import urllib.request
import urllib.parse
import json
import time as time_module
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd


SYMBOL = "XAUUSDT"
PRODUCT_TYPE = "USDT-FUTURES"
BASE = "https://api.bitget.com"

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "bitget"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def _fetch(path: str, params: dict | None = None, retries: int = 3) -> dict:
    if params:
        path = path + "?" + urllib.parse.urlencode(params)
    url = BASE + path
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                data = json.loads(r.read().decode("utf-8"))
            if data.get("code") != "00000":
                raise RuntimeError(f"bitget API error: {data.get('msg', data)}")
            return data
        except Exception as e:
            if attempt == retries - 1:
                raise
            time_module.sleep(1.5 * (attempt + 1))
    raise RuntimeError("unreachable")


def fetch_ticker(symbol: str = SYMBOL) -> dict:
    """Current last price + 24h volume."""
    d = _fetch("/api/v2/mix/market/ticker",
               {"productType": PRODUCT_TYPE, "symbol": symbol})
    t = d["data"][0] if isinstance(d["data"], list) else d["data"]
    return {
        "symbol": symbol,
        "last": float(t["lastPr"]),
        "bid": float(t.get("bidPr", 0)),
        "ask": float(t.get("askPr", 0)),
        "vol_24h_usdt": float(t.get("quoteVolume", 0)),
        "ts": pd.Timestamp.now(tz="UTC"),
    }


def fetch_open_interest(symbol: str = SYMBOL) -> dict:
    """Current open interest in base-coin units + USDT notional."""
    d = _fetch("/api/v2/mix/market/open-interest",
               {"productType": PRODUCT_TYPE, "symbol": symbol})
    oi_list = d["data"].get("openInterestList", []) if isinstance(d["data"], dict) else []
    if not oi_list:
        return {"oi_size": 0, "oi_usdt": 0}
    size = float(oi_list[0]["size"])
    tk = fetch_ticker(symbol)
    return {"symbol": symbol, "oi_size": size, "oi_usdt": size * tk["last"],
            "ts": pd.Timestamp.now(tz="UTC")}


def fetch_current_funding(symbol: str = SYMBOL) -> dict:
    """Current funding rate (8H cycle)."""
    d = _fetch("/api/v2/mix/market/current-fund-rate",
               {"productType": PRODUCT_TYPE, "symbol": symbol})
    row = d["data"][0]
    return {"symbol": symbol, "funding_rate": float(row["fundingRate"]),
            "ts": pd.Timestamp.now(tz="UTC")}


def fetch_funding_history(symbol: str = SYMBOL, pages: int = 10) -> pd.DataFrame:
    """Historical funding rate. Each page returns 100 rows. 100 rows × 8H = ~33 days.

    10 pages × 100 = 1000 rows ≈ 333 days history.
    """
    all_rows = []
    for page in range(1, pages + 1):
        d = _fetch("/api/v2/mix/market/history-fund-rate",
                   {"productType": PRODUCT_TYPE, "symbol": symbol,
                    "pageSize": 100, "pageNo": page})
        rows = d.get("data", [])
        if not rows:
            break
        all_rows.extend(rows)
        time_module.sleep(0.2)  # rate-limit kindness
    if not all_rows:
        return pd.DataFrame()
    df = pd.DataFrame(all_rows)
    df["funding_rate"] = df["fundingRate"].astype(float)
    df["ts"] = pd.to_datetime(df["fundingTime"].astype("int64"), unit="ms", utc=True)
    df = df[["ts", "funding_rate"]].sort_values("ts").reset_index(drop=True)
    return df


def fetch_candles(symbol: str = SYMBOL, granularity: str = "5m",
                   limit: int = 1000) -> pd.DataFrame:
    """OHLCV bars. granularity ∈ {1m, 5m, 15m, 30m, 1H, 4H, 1D}.
    Bitget limit is 1000 per call; oldest-first ordering.
    """
    d = _fetch("/api/v2/mix/market/candles",
               {"productType": PRODUCT_TYPE, "symbol": symbol,
                "granularity": granularity, "limit": limit})
    rows = d.get("data", [])
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows, columns=["ts_ms", "open", "high", "low", "close", "volume", "quoteVol"])
    df["ts"] = pd.to_datetime(df["ts_ms"].astype("int64"), unit="ms", utc=True)
    for c in ("open", "high", "low", "close", "volume", "quoteVol"):
        df[c] = df[c].astype(float)
    df = df[["ts", "open", "high", "low", "close", "volume"]].sort_values("ts").set_index("ts")
    return df


# ---- caching layer ----
def cached_path(name: str) -> Path:
    return DATA_DIR / f"{name}.csv"


def refresh_funding_history(symbol: str = SYMBOL, pages: int = 10) -> pd.DataFrame:
    """Pull funding history; merge into local CSV. Returns the merged frame."""
    cache = cached_path(f"funding_{symbol}")
    new = fetch_funding_history(symbol, pages=pages)
    if cache.exists():
        old = pd.read_csv(cache, parse_dates=["ts"])
        if old["ts"].dt.tz is None:
            old["ts"] = old["ts"].dt.tz_localize("UTC")
        merged = pd.concat([old, new]).drop_duplicates(subset="ts").sort_values("ts").reset_index(drop=True)
    else:
        merged = new
    merged.to_csv(cache, index=False)
    return merged


def refresh_candles(symbol: str = SYMBOL, granularity: str = "5m") -> pd.DataFrame:
    cache = cached_path(f"candles_{symbol}_{granularity}")
    new = fetch_candles(symbol, granularity)
    if cache.exists():
        old = pd.read_csv(cache, parse_dates=["ts"]).set_index("ts")
        if old.index.tz is None:
            old.index = old.index.tz_localize("UTC")
        merged = pd.concat([old, new]).reset_index().drop_duplicates(subset="ts").sort_values("ts").set_index("ts")
    else:
        merged = new
    merged.to_csv(cache)
    return merged


def load_funding(symbol: str = SYMBOL) -> pd.DataFrame:
    p = cached_path(f"funding_{symbol}")
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_csv(p, parse_dates=["ts"])
    if df["ts"].dt.tz is None:
        df["ts"] = df["ts"].dt.tz_localize("UTC")
    return df.sort_values("ts").reset_index(drop=True)


def load_candles(symbol: str = SYMBOL, granularity: str = "5m") -> pd.DataFrame:
    p = cached_path(f"candles_{symbol}_{granularity}")
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_csv(p, parse_dates=["ts"]).set_index("ts")
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    return df.sort_index()


if __name__ == "__main__":
    print("=== Bitget XAUUSDT health check ===")
    tk = fetch_ticker()
    print(f"last={tk['last']:.2f}  bid={tk['bid']:.2f}  ask={tk['ask']:.2f}  spread_bps={(tk['ask']-tk['bid'])/tk['last']*10000:.1f}  vol_24h=${tk['vol_24h_usdt']:,.0f}")
    oi = fetch_open_interest()
    print(f"OI: {oi['oi_size']:,.2f} oz  notional=${oi['oi_usdt']:,.0f}")
    fr = fetch_current_funding()
    print(f"funding(8H): {fr['funding_rate']:.6f} = {fr['funding_rate']*1095:.2%} annualized")
    print()
    print("Refreshing funding history (10 pages × 100 = ~333 days)...")
    fh = refresh_funding_history(pages=10)
    print(f"  funding history rows: {len(fh)}  range: {fh['ts'].min()} -> {fh['ts'].max()}")
    print(f"  abs(funding)>0:        {(fh['funding_rate'].abs() > 0).sum()} / {len(fh)} = {(fh['funding_rate'].abs() > 0).mean()*100:.1f}%")
    print(f"  P95 |funding|:         {fh['funding_rate'].abs().quantile(0.95):.6f}")
    print(f"  P99 |funding|:         {fh['funding_rate'].abs().quantile(0.99):.6f}")
    print(f"  max |funding|:         {fh['funding_rate'].abs().max():.6f}")
    print()
    print("Refreshing 5m candles...")
    cd = refresh_candles(granularity="5m")
    print(f"  candle rows: {len(cd)}  range: {cd.index.min()} -> {cd.index.max()}")
