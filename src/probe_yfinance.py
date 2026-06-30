"""Probe what GC=F intraday data we can actually obtain from yfinance for free."""
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

INTERVALS = [
    ("1m", "7d"),
    ("2m", "60d"),
    ("5m", "60d"),
    ("15m", "60d"),
    ("30m", "60d"),
    ("60m", "730d"),
    ("1h", "730d"),
    ("1d", "max"),
]

ticker = "GC=F"
print(f"Probing {ticker}\n" + "="*60)
for interval, period in INTERVALS:
    try:
        df = yf.download(ticker, period=period, interval=interval,
                         progress=False, auto_adjust=False)
        if df.empty:
            print(f"  {interval:5s} period={period:5s} -> EMPTY")
            continue
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        print(f"  {interval:5s} period={period:5s} -> rows={len(df):6d} "
              f"first={df.index[0]} last={df.index[-1]} "
              f"cols={list(df.columns)}")
    except Exception as e:
        print(f"  {interval:5s} period={period:5s} -> ERROR {e}")
