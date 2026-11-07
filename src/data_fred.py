"""Fetch FRED macro series. Keyed JSON API when FRED_API_KEY is set, public CSV fallback.

We pull the data values (not release dates). Release timestamps are reconstructed
in src/calendar_events.py from known schedules.
"""
from __future__ import annotations
from pathlib import Path
from io import StringIO
from datetime import datetime, timezone
import os
import time

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "data" / "macro"
STORE.mkdir(parents=True, exist_ok=True)

# Macro series mapped to FRED series IDs.
SERIES = {
    "cpi_yoy_proxy":    "CPIAUCSL",   # CPI level (we derive YoY)
    "cpi_core":         "CPILFESL",   # Core CPI level
    "nfp":              "PAYEMS",     # Nonfarm Payrolls (level, thousands)
    "unrate":           "UNRATE",     # Unemployment rate
    "ppi":              "PPIACO",     # Producer Price Index
    "retail_sales":     "RSAFS",      # Retail Sales Advance
    "gdp_qoq":          "A191RL1Q225SBEA",  # Real GDP % change QoQ annualized
    "claims":           "ICSA",       # Initial Jobless Claims (weekly)
    "fedfunds_target":  "DFEDTARU",   # Upper bound of fed funds target
    # Driver/context series
    "real_yield_10y":   "DFII10",     # 10Y TIPS yield (daily)
    "dxy_proxy":        "DTWEXBGS",   # Trade-weighted USD (daily, broad)
    "tnx_10y":          "DGS10",      # 10Y nominal yield
}

FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
FRED_API = "https://api.stlouisfed.org/fred/series/observations"
# fredgraph.csv throttles GitHub runner IPs (all series timed out from CI
# since ~2026-08). The keyed JSON API is the primary path when FRED_API_KEY
# is set; the CSV endpoint stays as fallback (works from home IPs).
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    df["date"] = pd.to_datetime(df["date"])
    # FRED uses '.' for missing values
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df[["date", "value"]].dropna(subset=["value"]).reset_index(drop=True)


def _fetch_api(series_id: str, key: str, timeout: int) -> pd.DataFrame:
    r = requests.get(FRED_API, timeout=timeout, params={
        "series_id": series_id, "api_key": key, "file_type": "json"})
    r.raise_for_status()
    obs = r.json()["observations"]
    return _normalize(pd.DataFrame(obs)[["date", "value"]])


def _fetch_csv(series_id: str, timeout: int) -> pd.DataFrame:
    r = requests.get(FRED_CSV.format(sid=series_id), timeout=timeout,
                     headers={"User-Agent": BROWSER_UA})
    r.raise_for_status()
    df = pd.read_csv(StringIO(r.text))
    # Columns typically: ["observation_date" or "DATE", SERIES_ID]
    date_col = next(c for c in df.columns if c.lower() in ("observation_date", "date"))
    val_col = next(c for c in df.columns if c != date_col)
    return _normalize(df.rename(columns={date_col: "date", val_col: "value"}))


def fetch_series(series_id: str, timeout: int = 30, retries: int = 3) -> pd.DataFrame:
    key = os.environ.get("FRED_API_KEY", "").strip()
    sources = ([("api", lambda: _fetch_api(series_id, key, timeout))] if key else [])
    sources.append(("csv", lambda: _fetch_csv(series_id, timeout)))
    errors = []
    for name, fn in sources:
        for attempt in range(1, retries + 1):
            try:
                return fn()
            except Exception as e:  # noqa: BLE001
                msg = str(e).replace(key, "***") if key else str(e)
                errors.append(f"{name}#{attempt}: {msg}")
                if attempt < retries:
                    time.sleep(2 ** attempt)
    raise RuntimeError(" | ".join(errors))


def snapshot_all(verbose: bool = True) -> dict:
    stats = {}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for name, sid in SERIES.items():
        try:
            df = fetch_series(sid)
            path = STORE / f"{name}__{sid}.csv"
            df.to_csv(path, index=False)
            stats[name] = {
                "status": "ok",
                "series_id": sid,
                "rows": len(df),
                "first": str(df["date"].min().date()),
                "last": str(df["date"].max().date()),
            }
            if verbose:
                print(f"[{now}] {name:18s} ({sid:14s}) rows={len(df):>6d} "
                      f"{df['date'].min().date()} .. {df['date'].max().date()}")
        except Exception as e:
            stats[name] = {"status": "error", "error": str(e)}
            if verbose:
                print(f"[{now}] {name:18s} ({sid}) ERROR: {e}")
    return stats


def load(name: str) -> pd.DataFrame:
    matches = list(STORE.glob(f"{name}__*.csv"))
    if not matches:
        raise FileNotFoundError(f"No stored macro data for {name}; run snapshot first.")
    return pd.read_csv(matches[0], parse_dates=["date"])


if __name__ == "__main__":
    snapshot_all()
