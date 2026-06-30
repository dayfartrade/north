"""CFTC Commitments of Traders (COT) data for Gold Futures.

Source: CFTC public reporting API (Socrata), Disaggregated Futures Only
weekly report for Gold (CME Group GC, commodity code 088691).

Endpoint:
  https://publicreporting.cftc.gov/resource/72hh-3qpy.json

We pull managed-money positions and compute net long. Cached locally in
data/cot/gold_disaggregated.csv. Refresh once per week (Friday late after
the official 15:30 ET release; we don't worry about same-day timing).

Fields we keep (per CFTC schema):
  report_date_as_yyyy_mm_dd
  m_money_positions_long_all          (managed money longs)
  m_money_positions_short_all         (managed money shorts)
  open_interest_all                   (total OI for context)
"""
from __future__ import annotations
from pathlib import Path
import json
import requests
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
COT_DIR = ROOT / "data" / "cot"
COT_FILE = COT_DIR / "gold_disaggregated.csv"

API = "https://publicreporting.cftc.gov/resource/72hh-3qpy.json"
COMMODITY = "GOLD - COMMODITY EXCHANGE INC."
DEFAULT_LIMIT = 200  # ~4 years of weekly data, plenty for 52-week percentile


def fetch_cot(limit: int = DEFAULT_LIMIT) -> pd.DataFrame:
    """Fetch the latest N weekly reports from CFTC SODA API. Returns DataFrame
    sorted ascending by report_date."""
    params = {
        "$where": f"market_and_exchange_names='{COMMODITY}'",
        "$order": "report_date_as_yyyy_mm_dd DESC",
        "$limit": str(limit),
    }
    r = requests.get(API, params=params, timeout=30)
    r.raise_for_status()
    rows = r.json()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    # Coerce numeric fields
    for col in ("m_money_positions_long_all", "m_money_positions_short_all",
                "open_interest_all"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["report_date"] = pd.to_datetime(df["report_date_as_yyyy_mm_dd"], errors="coerce")
    df = df.dropna(subset=["report_date"]).sort_values("report_date").reset_index(drop=True)
    # Derive net long
    df["mm_net_long"] = (df["m_money_positions_long_all"]
                          - df["m_money_positions_short_all"])
    return df[["report_date", "m_money_positions_long_all",
               "m_money_positions_short_all", "open_interest_all", "mm_net_long"]]


def refresh_cot(force: bool = False) -> pd.DataFrame:
    """Fetch latest COT, save to disk, return. Skip API call if local file
    is fresher than 6 days (one report cadence) unless force=True."""
    COT_DIR.mkdir(parents=True, exist_ok=True)
    if not force and COT_FILE.exists():
        import time
        age_days = (time.time() - COT_FILE.stat().st_mtime) / 86400
        if age_days < 6:
            return load_cot()
    df = fetch_cot()
    if df.empty:
        return df
    df.to_csv(COT_FILE, index=False)
    return df


def load_cot() -> pd.DataFrame:
    """Load cached COT data. Empty DataFrame if no cache yet."""
    if not COT_FILE.exists():
        return pd.DataFrame()
    df = pd.read_csv(COT_FILE)
    if df.empty:
        return df
    df["report_date"] = pd.to_datetime(df["report_date"], errors="coerce")
    return df.dropna(subset=["report_date"]).sort_values("report_date").reset_index(drop=True)


def latest_snapshot() -> dict:
    """Return latest row + 52-week percentile of mm_net_long. Empty dict if
    cache unavailable."""
    df = load_cot()
    if df.empty:
        return {}
    latest = df.iloc[-1]
    # 52-week window for percentile (or whatever we have if less)
    window = df.tail(52)["mm_net_long"]
    cur = float(latest["mm_net_long"])
    pct = float((window < cur).mean()) if len(window) > 1 else float("nan")
    return {
        "report_date": str(latest["report_date"].date()),
        "mm_net_long": cur,
        "mm_long": int(latest["m_money_positions_long_all"]),
        "mm_short": int(latest["m_money_positions_short_all"]),
        "open_interest": int(latest["open_interest_all"]),
        "pct_52w": pct,
        "n_history_weeks": len(df),
    }


if __name__ == "__main__":
    import sys
    if "--refresh" in sys.argv:
        df = refresh_cot(force=True)
        print(f"Fetched {len(df)} weekly rows")
    snap = latest_snapshot()
    if not snap:
        print("No COT cache. Run with --refresh to fetch.")
    else:
        print(f"Latest report: {snap['report_date']}")
        print(f"  MM long:  {snap['mm_long']:,}")
        print(f"  MM short: {snap['mm_short']:,}")
        print(f"  MM NET:   {snap['mm_net_long']:+,}  (P{int(snap['pct_52w']*100)} of last 52w)")
        print(f"  Total OI: {snap['open_interest']:,}")
        print(f"  History:  {snap['n_history_weeks']} weeks")
