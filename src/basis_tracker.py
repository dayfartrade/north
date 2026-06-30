"""Bitget XAUUSDT vs COMEX GC basis tracker.

The user wants:
  - Private feed:  Bitget XAUUSDT reference price
  - Public feed:   COMEX GC reference price
Same underlying logic, two price quotes. The basis is the difference.

Bitget tracks gold spot. COMEX GC tracks the front-month futures contract
(includes cost-of-carry to delivery). Basis = GC - XAUUSDT ≈ structural
discount of spot to futures, driven mostly by interest rates and storage.

A drift in the basis can mean:
  - Stress in physical market (basis widens)
  - Funding spike pulling perp price (basis narrows or inverts)
  - Or just minute-to-minute timing differences (5m bars not synced)

We log basis every refresh and store it for monitoring.
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
import data_bitget
import data_gc

ROOT = Path(__file__).resolve().parent.parent
BASIS_LOG = ROOT / "data" / "bitget" / "basis_log.csv"


def current_basis() -> dict:
    """Return current snapshot of Bitget last vs COMEX GC last close."""
    bg = data_bitget.fetch_ticker()
    gc = data_gc.load("1m")  # most recent 1m bar
    if gc.empty:
        return {"error": "no GC data"}
    if gc.index.tz is None:
        gc.index = gc.index.tz_localize("UTC")
    gc_last_ts = gc.index.max()
    gc_last_price = float(gc.loc[gc_last_ts, "close"])
    bg_price = bg["last"]
    basis = gc_last_price - bg_price
    basis_pct = basis / bg_price * 100
    return {
        "ts": pd.Timestamp.now(tz="UTC"),
        "bitget_xauusdt": bg_price,
        "comex_gc": gc_last_price,
        "comex_gc_ts": gc_last_ts,
        "basis_dollars": basis,
        "basis_pct": basis_pct,
        "stale_minutes": (pd.Timestamp.now(tz="UTC") - gc_last_ts).total_seconds() / 60,
    }


def log_basis():
    """Append current basis to log."""
    snap = current_basis()
    if "error" in snap:
        return snap
    df = pd.DataFrame([snap])
    if BASIS_LOG.exists():
        df.to_csv(BASIS_LOG, mode="a", header=False, index=False)
    else:
        BASIS_LOG.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(BASIS_LOG, index=False)
    return snap


if __name__ == "__main__":
    snap = current_basis()
    if "error" in snap:
        print(snap)
    else:
        print(f"Bitget XAUUSDT: ${snap['bitget_xauusdt']:.2f}  (live)")
        print(f"COMEX GC:       ${snap['comex_gc']:.2f}  (last bar {snap['comex_gc_ts']}, {snap['stale_minutes']:.1f} min old)")
        print(f"Basis (GC-XAU): ${snap['basis_dollars']:+.2f}  ({snap['basis_pct']:+.3f}%)")
        if snap['stale_minutes'] > 60:
            print(f"  WARN: GC data stale by {snap['stale_minutes']:.0f} min (market closed?)")
        log_basis()
        print(f"\nLogged to {BASIS_LOG.name}")
