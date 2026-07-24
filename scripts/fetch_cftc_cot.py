"""Fetch CFTC Commitments of Traders (COT) historical data.

Free from CFTC — yearly zip files with all commodity COT data.
Gold contract: CFTC code 088691 (COMEX Gold).

Fields extracted per Friday report:
  - Commercial (hedgers) net position
  - Non-commercial (speculators) net position
  - Non-reportable (small traders) net position
  - Open interest

Output: data/macro/cot_gold.csv with weekly rows.
"""
from __future__ import annotations

import argparse
import io
import sys
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT_CSV = ROOT / "data" / "macro" / "cot_gold.csv"
CFTC_GOLD_CODE = "088691"
UA = {"User-Agent": "Mozilla/5.0 (compatible; FAR/1.0)"}


def download_year(year: int) -> pd.DataFrame | None:
    url = f"https://www.cftc.gov/files/dea/history/deacot{year}.zip"
    print(f"[{year}] fetching {url} ...", end="", flush=True)
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        print(f" {len(data)/1024:.1f} KB")
    except Exception as e:
        print(f" FAILED {e}")
        return None

    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = z.namelist()
            print(f"  contents: {names[:3]}")
            txt_name = next((n for n in names if n.endswith(".txt")), None)
            if not txt_name:
                return None
            with z.open(txt_name) as f:
                raw = f.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"  unzip failed: {e}")
        return None

    df = pd.read_csv(io.StringIO(raw), low_memory=False)

    # Find the code column (name varies across years)
    code_col = None
    for c in df.columns:
        if "Contract Market Code" in c and "Quotes" not in c:
            code_col = c; break
    if code_col:
        return df[df[code_col].astype(str).str.strip() == CFTC_GOLD_CODE]

    # Fallback: market name text match
    for c in df.columns:
        if "Market" in c and "Names" in c:
            gold = df[df[c].astype(str).str.contains("GOLD", case=False, na=False)]
            gold = gold[gold[c].astype(str).str.contains("COMEX", case=False, na=False)]
            return gold
    print(f"  can't find code column; columns: {list(df.columns)[:8]}")
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start-year", type=int, default=2010)
    ap.add_argument("--end-year", type=int, default=2026)
    args = ap.parse_args()

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    frames = []
    for year in range(args.start_year, args.end_year + 1):
        df = download_year(year)
        if df is not None and not df.empty:
            frames.append(df)
            print(f"  [{year}] {len(df)} rows")

    if not frames:
        print("No data fetched.")
        return

    combined = pd.concat(frames, ignore_index=True)
    print(f"\nTotal rows: {len(combined)}")
    print(f"Columns: {list(combined.columns)[:12]}")

    # Find date column
    date_col = None
    for c in combined.columns:
        cl = c.replace("_", " ")
        if "As of Date" in cl and "YYYY-MM-DD" in cl:
            date_col = c; break
    if not date_col:
        for c in combined.columns:
            cl = c.replace("_", " ")
            if "As of Date" in cl:
                date_col = c; break
    if not date_col:
        print("Warning: no date column found")
    else:
        combined[date_col] = pd.to_datetime(combined[date_col], errors="coerce")
        combined = combined.dropna(subset=[date_col]).sort_values(date_col)

    combined.to_csv(OUT_CSV, index=False)
    print(f"\nSaved {OUT_CSV}")


if __name__ == "__main__":
    main()
