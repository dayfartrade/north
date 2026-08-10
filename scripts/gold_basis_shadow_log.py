"""Gold basis LONG-only shadow log — daily updater.

Source of truth for spot:
    XAUUSD spot from Dukascopy 5m bars, resampled to daily
    (via research.tools.data_loader.load_gold_5m + resample)

Source for futures:
    GC=F daily from yfinance (or local data/gc/GC_1d.csv)

basis = GC_close - XAUUSD_daily_close

This matches the OOS-validated backtest in gold_basis_long_only_oos.py.

Signal (LOCKED, matches OOS pre-reg):
    lookback = 180 days
    p_low = 0.025 (basis at trailing 2.5th percentile)
    cold-start floor: 180 days of aligned history
    degenerate-distribution guard: (p_high - p_low) >= $0.50
    LONG when today's basis <= p_low
    Stop = 2 * ATR(20) on the spot instrument
    Hold = 7 trading days OR stop hit
    Fill = next-day open on GC=F

FRESHNESS GATE:
    Both spot and futures must be no more than 3 days stale.
    Otherwise the script refuses to emit new signals (still resolves
    existing signals whose windows have elapsed on available data).

Persistence:
    data/gold_basis_shadow.jsonl  (signals + resolves, append-only)

Not published to Telegram. Research shadow only. Purpose: grow n from
54 (OOS) to 100+ via forward tracking before considering ship.

Usage:
    python scripts/gold_basis_shadow_log.py           (tick)
    python scripts/gold_basis_shadow_log.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from research.tools.data_loader import load_gold_5m, resample

SHADOW_LOG = ROOT / "data" / "gold_basis_shadow.jsonl"
GC_DAILY_CSV = ROOT / "data" / "gc" / "GC_1d.csv"

LOOKBACK = 180
P_LOW = 0.025
P_HIGH = 0.975
MIN_SPREAD_USD = 0.5
HOLD_DAYS = 7
ATR_PERIOD = 20
STOP_ATR_MULT = 2.0
CONTRACT_SIZE = 100  # GC = 100 oz
RT_COST = 3.0
MAX_STALE_DAYS = 3


def notify_private(msg: str) -> None:
    """Best-effort private-chat Telegram ping. Silent no-op on any failure."""
    try:
        sys.path.insert(0, str(ROOT / "src"))
        from telegram_bot import send
        send(msg, audience="private")
    except Exception as e:
        print(f"[notify] private-chat send failed: {type(e).__name__}: {e}")


def _ms_to_iso_date(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def load_xau_daily() -> pd.DataFrame:
    """Load full XAUUSD daily from Dukascopy 5m."""
    print("[data] loading XAUUSD 5m + resampling to daily...")
    xau_5m = load_gold_5m()
    daily = resample(xau_5m, target_minutes=1440)
    rows = [
        {"date": _ms_to_iso_date(b.timestamp),
         "xau_open": b.open, "xau_high": b.high,
         "xau_low": b.low, "xau_close": b.close}
        for b in daily
    ]
    return pd.DataFrame(rows)


def load_gc_daily() -> pd.DataFrame:
    """Load GC=F daily from local CSV."""
    if not GC_DAILY_CSV.exists():
        raise FileNotFoundError(f"GC daily CSV missing: {GC_DAILY_CSV}")
    df = pd.read_csv(GC_DAILY_CSV, parse_dates=["ts"])
    df["date"] = pd.to_datetime(df["ts"], utc=True).dt.strftime("%Y-%m-%d")
    return df[["date", "open", "high", "low", "close"]].rename(
        columns={"open": "gc_open", "high": "gc_high",
                 "low": "gc_low", "close": "gc_close"})


def build_basis(xau: pd.DataFrame, gc: pd.DataFrame) -> pd.DataFrame:
    merged = xau.merge(gc, on="date", how="inner").sort_values("date")
    merged["basis"] = merged["gc_close"] - merged["xau_close"]
    return merged.reset_index(drop=True)


def check_freshness(basis_df: pd.DataFrame) -> tuple[bool, str]:
    last = basis_df["date"].max()
    last_dt = pd.Timestamp(last, tz="UTC")
    age = (pd.Timestamp.now(tz="UTC") - last_dt).total_seconds() / 86400
    if age > MAX_STALE_DAYS:
        return False, f"basis data stale by {age:.1f}d (last: {last})"
    return True, f"basis fresh: last={last} ({age:.1f}d ago)"


def compute_atr(basis_df: pd.DataFrame, period: int) -> pd.Series:
    prev_close = basis_df["xau_close"].shift(1)
    tr = pd.concat([
        basis_df["xau_high"] - basis_df["xau_low"],
        (basis_df["xau_high"] - prev_close).abs(),
        (basis_df["xau_low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()


def load_shadow_log() -> list[dict]:
    if not SHADOW_LOG.exists():
        return []
    with open(SHADOW_LOG) as f:
        return [json.loads(l) for l in f if l.strip()]


def append_shadow(rec: dict):
    SHADOW_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(SHADOW_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, default=str) + "\n")


def emit_signal_if_triggered(basis_df: pd.DataFrame, existing_log: list[dict],
                              dry_run: bool) -> dict | None:
    if len(basis_df) < LOOKBACK + 1:
        print(f"[signal] cold-start: only {len(basis_df)} rows")
        return None
    today_row = basis_df.iloc[-1]
    today_date = today_row["date"]
    sid = f"basis_long_{today_date}"

    if any(r.get("signal_id") == sid and r.get("type") == "signal" for r in existing_log):
        print(f"[signal] {sid}: already emitted, skipping")
        return None

    window = sorted(basis_df["basis"].iloc[-LOOKBACK:].tolist())
    def pct(p):
        idx = p * (len(window) - 1)
        lo = int(idx); hi = min(lo + 1, len(window) - 1)
        frac = idx - lo
        return window[lo] * (1 - frac) + window[hi] * frac
    p_low = pct(P_LOW)
    p_high = pct(P_HIGH)
    spread = p_high - p_low
    if spread < MIN_SPREAD_USD:
        print(f"[signal] degenerate-guard: spread=${spread:.3f} < ${MIN_SPREAD_USD}")
        return None

    today_basis = float(today_row["basis"])
    atr_ser = compute_atr(basis_df, ATR_PERIOD)
    today_atr = float(atr_ser.iloc[-1]) if pd.notna(atr_ser.iloc[-1]) else None

    triggered = today_basis <= p_low
    atr_str = f"${today_atr:.2f}" if today_atr else "n/a"
    print(f"[signal] {today_date}: basis=${today_basis:.2f} "
          f"p_low=${p_low:.2f} p_high=${p_high:.2f} spread=${spread:.2f} "
          f"atr={atr_str} -> {'LONG' if triggered else 'FLAT'}")
    if not triggered or today_atr is None or today_atr <= 0:
        return None

    rec = {
        "type": "signal",
        "signal_id": sid,
        "signal_date": today_date,
        "direction": "LONG",
        "basis": round(today_basis, 3),
        "p_low_180d": round(p_low, 3),
        "p_high_180d": round(p_high, 3),
        "gc_close": round(float(today_row["gc_close"]), 2),
        "xau_close": round(float(today_row["xau_close"]), 2),
        "hold_days": HOLD_DAYS,
        "atr20": round(today_atr, 3),
        "entry_plan": "next NY session GC=F open (t+1)",
        "stop_offset": round(STOP_ATR_MULT * today_atr, 2),
        "emitted_utc": datetime.now(timezone.utc).isoformat(),
        "spot_source": "dukascopy_xauusd_5m_resampled_daily",
    }
    if not dry_run:
        append_shadow(rec)
        print(f"[signal] {sid}: EMITTED (LONG)")
        notify_private(
            f"🕯 SHADOW SIGNAL — gold basis LONG-only\n"
            f"date: {today_date}\n"
            f"basis: ${today_basis:.2f} (p2.5={p_low:.2f})\n"
            f"entry plan: next NY session GC=F open\n"
            f"stop offset: ${STOP_ATR_MULT * today_atr:.2f} (2xATR20)\n"
            f"hold: {HOLD_DAYS} trading days"
        )
    else:
        print(f"[signal] {sid}: WOULD EMIT (dry-run)")
    return rec


def resolve_open_signals(basis_df: pd.DataFrame, existing_log: list[dict],
                          dry_run: bool):
    signals = [r for r in existing_log if r.get("type") == "signal"]
    resolved_ids = {r["signal_id"] for r in existing_log if r.get("type") == "resolve"}
    by_date = {row["date"]: row for _, row in basis_df.iterrows()}
    dates = sorted(by_date.keys())

    for sig in signals:
        sid = sig["signal_id"]
        if sid in resolved_ids:
            continue
        sig_date = sig["signal_date"]
        try:
            idx = dates.index(sig_date)
        except ValueError:
            continue
        if idx + 1 >= len(dates):
            continue
        entry_idx = idx + 1
        entry_row = by_date[dates[entry_idx]]
        entry_price = float(entry_row["gc_open"])

        exit_idx = min(entry_idx + HOLD_DAYS, len(dates) - 1)
        if exit_idx == entry_idx:
            continue
        stop_offset = STOP_ATR_MULT * sig["atr20"]
        stop_price = entry_price - stop_offset
        exit_price = None
        exit_reason = None
        exit_date = None
        for j in range(entry_idx, exit_idx + 1):
            bar = by_date[dates[j]]
            if float(bar["gc_low"]) <= stop_price:
                exit_price = stop_price
                exit_reason = "stop"
                exit_date = dates[j]
                break
        if exit_price is None:
            if exit_idx - entry_idx < HOLD_DAYS:
                continue
            exit_price = float(by_date[dates[exit_idx]]["gc_close"])
            exit_reason = "time_exit"
            exit_date = dates[exit_idx]

        r_mult = (exit_price - entry_price) / stop_offset
        pnl = (exit_price - entry_price) * CONTRACT_SIZE - RT_COST
        outcome = {
            "type": "resolve",
            "signal_id": sid,
            "signal_date": sig_date,
            "entry_date": entry_date,
            "exit_date": exit_date,
            "entry_price": round(entry_price, 2),
            "exit_price": round(exit_price, 2),
            "stop_price": round(stop_price, 2),
            "exit_reason": exit_reason,
            "r_multiple": round(r_mult, 4),
            "pnl_dollars": round(pnl, 2),
            "resolved_utc": datetime.now(timezone.utc).isoformat(),
        }
        print(f"[resolve] {sid}: entry ${entry_price:.2f} -> "
              f"exit ${exit_price:.2f} ({exit_reason}) R={r_mult:+.2f} $={pnl:+.0f}")
        if not dry_run:
            append_shadow(outcome)
            icon = "✅" if r_mult > 0 else "🟥"
            notify_private(
                f"🕯 SHADOW RESOLVE — gold basis LONG-only {icon}\n"
                f"signal date: {sig_date}\n"
                f"entry ${entry_price:.2f} → exit ${exit_price:.2f}\n"
                f"reason: {exit_reason}\n"
                f"R: {r_mult:+.2f}  |  $: {pnl:+.0f}"
            )


def print_track_record(log: list[dict]):
    resolved = [r for r in log if r.get("type") == "resolve"]
    if not resolved:
        print("[track] no resolved signals yet")
        return
    n = len(resolved)
    rs = [r["r_multiple"] for r in resolved]
    dol = [r["pnl_dollars"] for r in resolved]
    wins = sum(1 for r in rs if r > 0)
    print(f"[track] resolved={n} wins={wins}/{n} ({wins/n:.1%}) "
          f"mean_R={sum(rs)/n:+.3f} total_$={sum(dol):+.0f} "
          f"best=${max(dol):+.0f} worst=${min(dol):+.0f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="emit signals even if data is stale (for testing)")
    args = ap.parse_args()

    print(f"[gold_basis_shadow_log] {datetime.now(timezone.utc).isoformat()}")

    xau = load_xau_daily()
    gc = load_gc_daily()
    basis_df = build_basis(xau, gc)
    print(f"[data] {len(basis_df)} aligned days ({basis_df['date'].min()} to {basis_df['date'].max()})")

    fresh, msg = check_freshness(basis_df)
    print(f"[data] {msg}")
    log = load_shadow_log()
    n_sig = sum(1 for r in log if r.get("type") == "signal")
    n_res = sum(1 for r in log if r.get("type") == "resolve")
    print(f"[shadow_log] {n_sig} signals, {n_res} resolves")

    # Always try to resolve open signals — this uses whatever data we have
    resolve_open_signals(basis_df, log, args.dry_run)

    if not fresh and not args.force:
        print("[signal] REFUSING to emit new signals: data stale beyond "
              f"{MAX_STALE_DAYS}d gate. Fix spot data (VPS Dukascopy) and re-run.")
    else:
        emit_signal_if_triggered(basis_df, log, args.dry_run)

    if not args.dry_run:
        log = load_shadow_log()
    print_track_record(log)


if __name__ == "__main__":
    main()
