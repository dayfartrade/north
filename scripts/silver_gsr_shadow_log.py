"""Silver GSR z-score reversion shadow log — daily updater.

Source of truth:
    XAUUSD + XAGUSD spot from Dukascopy 5m bars, resampled to daily
    (via research.tools.data_loader.load_gold_5m / load_silver_5m + resample)

    GSR = gold_close / silver_close
    z_score = rolling 180d z-score of GSR
    LONG silver  when z >= +1.5  (silver too cheap vs gold)
    SHORT silver when z <= -1.5  (silver too expensive vs gold)

This matches the OOS-validated backtest in silver_gsr_oos_revisit.py.

Signal (LOCKED, matches OOS pre-reg):
    lookback = 180 days
    |z| threshold = 1.5
    max_hold = 10 trading days
    stop = 2 * silver_ATR(20) from entry
    fill = same-bar close on silver spot (matches OOS methodology)
    cold-start floor: 180 days of aligned history

Exit rules (in priority order per bar):
    1. Stop hit (silver_low <= stop for LONG, silver_high >= stop for SHORT)
    2. z-score crosses zero (mean reversion complete)
    3. max_hold_bars reached (time exit at that day's close)

FRESHNESS GATE:
    Both spot series must be no more than 3 days stale.
    Otherwise the script refuses to emit new signals (still resolves
    existing signals whose windows have elapsed on available data).

Persistence:
    data/silver_gsr_shadow.jsonl  (signals + resolves, append-only)

Not published to Telegram. Research shadow only. Purpose: grow n from
the OOS baseline via forward tracking before considering ship.

Usage:
    python scripts/silver_gsr_shadow_log.py           (tick)
    python scripts/silver_gsr_shadow_log.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from research.tools.data_loader import load_gold_5m, load_silver_5m, resample

SHADOW_LOG = ROOT / "data" / "silver_gsr_shadow.jsonl"

LOOKBACK = 180
Z_THRESHOLD = 1.5
MAX_HOLD_DAYS = 10
ATR_PERIOD = 20
STOP_ATR_MULT = 2.0
CONTRACT_SIZE = 5000  # SI = 5000 oz
RT_COST = 5.0
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


def load_daily(loader, label: str) -> pd.DataFrame:
    print(f"[data] loading {label} 5m + resampling to daily...")
    bars_5m = loader()
    daily = resample(bars_5m, target_minutes=1440)
    rows = [
        {"date": _ms_to_iso_date(b.timestamp),
         "open": b.open, "high": b.high,
         "low": b.low, "close": b.close}
        for b in daily
    ]
    return pd.DataFrame(rows)


def build_gsr(gold: pd.DataFrame, silver: pd.DataFrame) -> pd.DataFrame:
    g = gold.rename(columns={"open": "gold_open", "high": "gold_high",
                             "low": "gold_low", "close": "gold_close"})
    s = silver.rename(columns={"open": "silver_open", "high": "silver_high",
                               "low": "silver_low", "close": "silver_close"})
    merged = g.merge(s, on="date", how="inner").sort_values("date")
    merged["gsr"] = merged["gold_close"] / merged["silver_close"]
    return merged.reset_index(drop=True)


def check_freshness(df: pd.DataFrame) -> tuple[bool, str]:
    last = df["date"].max()
    last_dt = pd.Timestamp(last, tz="UTC")
    age = (pd.Timestamp.now(tz="UTC") - last_dt).total_seconds() / 86400
    if age > MAX_STALE_DAYS:
        return False, f"GSR data stale by {age:.1f}d (last: {last})"
    return True, f"GSR fresh: last={last} ({age:.1f}d ago)"


def compute_atr(df: pd.DataFrame, period: int) -> pd.Series:
    prev_close = df["silver_close"].shift(1)
    tr = pd.concat([
        df["silver_high"] - df["silver_low"],
        (df["silver_high"] - prev_close).abs(),
        (df["silver_low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()


def compute_z(df: pd.DataFrame, lookback: int) -> pd.Series:
    def _z(window: pd.Series) -> float:
        vals = window.tolist()
        if len(vals) < lookback:
            return float("nan")
        mu = statistics.fmean(vals)
        sd = statistics.pstdev(vals)
        if sd == 0:
            return float("nan")
        return (vals[-1] - mu) / sd
    return df["gsr"].rolling(lookback, min_periods=lookback).apply(_z, raw=False)


def load_shadow_log() -> list[dict]:
    if not SHADOW_LOG.exists():
        return []
    with open(SHADOW_LOG) as f:
        return [json.loads(l) for l in f if l.strip()]


def append_shadow(rec: dict):
    SHADOW_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(SHADOW_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, default=str) + "\n")


def emit_signal_if_triggered(gsr_df: pd.DataFrame, z_ser: pd.Series,
                              atr_ser: pd.Series, existing_log: list[dict],
                              dry_run: bool) -> dict | None:
    if len(gsr_df) < LOOKBACK + 1:
        print(f"[signal] cold-start: only {len(gsr_df)} rows")
        return None
    today_row = gsr_df.iloc[-1]
    today_date = today_row["date"]
    today_z = float(z_ser.iloc[-1]) if pd.notna(z_ser.iloc[-1]) else None
    today_atr = float(atr_ser.iloc[-1]) if pd.notna(atr_ser.iloc[-1]) else None

    if today_z is None:
        print(f"[signal] {today_date}: z=nan (insufficient window)")
        return None

    if today_z >= Z_THRESHOLD:
        direction = "LONG"
    elif today_z <= -Z_THRESHOLD:
        direction = "SHORT"
    else:
        direction = "FLAT"

    atr_str = f"${today_atr:.3f}" if today_atr else "n/a"
    print(f"[signal] {today_date}: gsr={float(today_row['gsr']):.3f} "
          f"z={today_z:+.3f} atr={atr_str} -> {direction}")

    if direction == "FLAT" or today_atr is None or today_atr <= 0:
        return None

    sid = f"silver_gsr_{direction.lower()}_{today_date}"
    if any(r.get("signal_id") == sid and r.get("type") == "signal" for r in existing_log):
        print(f"[signal] {sid}: already emitted, skipping")
        return None

    # Guard: don't stack same-direction signals while a same-direction position is open
    open_ids = {r["signal_id"] for r in existing_log if r.get("type") == "signal"} - \
               {r["signal_id"] for r in existing_log if r.get("type") == "resolve"}
    for oid in open_ids:
        if f"silver_gsr_{direction.lower()}_" in oid:
            print(f"[signal] {sid}: same-direction open signal {oid} exists, skipping")
            return None

    entry_price = float(today_row["silver_close"])
    if direction == "LONG":
        stop_price = entry_price - STOP_ATR_MULT * today_atr
    else:
        stop_price = entry_price + STOP_ATR_MULT * today_atr

    rec = {
        "type": "signal",
        "signal_id": sid,
        "signal_date": today_date,
        "direction": direction,
        "gsr": round(float(today_row["gsr"]), 4),
        "z_score": round(today_z, 4),
        "gold_close": round(float(today_row["gold_close"]), 2),
        "silver_close": round(entry_price, 3),
        "entry_price": round(entry_price, 3),
        "stop_price": round(stop_price, 3),
        "stop_offset": round(STOP_ATR_MULT * today_atr, 3),
        "atr20": round(today_atr, 3),
        "max_hold_days": MAX_HOLD_DAYS,
        "entry_plan": "same-bar close on silver spot (matches OOS)",
        "emitted_utc": datetime.now(timezone.utc).isoformat(),
        "spot_source": "dukascopy_xagusd_5m_resampled_daily",
    }
    if not dry_run:
        append_shadow(rec)
        print(f"[signal] {sid}: EMITTED ({direction})")
        notify_private(
            f"🕯 SHADOW SIGNAL — silver GSR {direction}\n"
            f"date: {today_date}\n"
            f"GSR: {float(today_row['gsr']):.3f}  z: {today_z:+.3f}\n"
            f"entry: silver same-bar close ${entry_price:.3f}\n"
            f"stop: ${stop_price:.3f} (2xATR20)\n"
            f"max hold: {MAX_HOLD_DAYS} trading days"
        )
    else:
        print(f"[signal] {sid}: WOULD EMIT (dry-run)")
    return rec


def resolve_open_signals(gsr_df: pd.DataFrame, z_ser: pd.Series,
                          existing_log: list[dict], dry_run: bool):
    signals = [r for r in existing_log if r.get("type") == "signal"]
    resolved_ids = {r["signal_id"] for r in existing_log if r.get("type") == "resolve"}
    dates = gsr_df["date"].tolist()
    by_date = {row["date"]: (i, row) for i, row in gsr_df.iterrows()}
    z_by_date = {d: (float(z) if pd.notna(z) else None)
                 for d, z in zip(dates, z_ser.tolist())}

    for sig in signals:
        sid = sig["signal_id"]
        if sid in resolved_ids:
            continue
        sig_date = sig["signal_date"]
        if sig_date not in by_date:
            continue
        entry_idx, _ = by_date[sig_date]
        # Entry is same-bar close on signal_date
        entry_price = float(sig["entry_price"])
        stop_price = float(sig["stop_price"])
        direction = sig["direction"]
        stop_offset = float(sig["stop_offset"])
        max_exit_idx = min(entry_idx + MAX_HOLD_DAYS, len(dates) - 1)
        if max_exit_idx <= entry_idx:
            continue  # no forward bar available yet

        exit_price = None
        exit_reason = None
        exit_date = None
        # Scan bars AFTER entry (entry_idx+1..max_exit_idx) for stop, z-cross
        for j in range(entry_idx + 1, max_exit_idx + 1):
            bar = gsr_df.iloc[j]
            if direction == "LONG":
                if float(bar["silver_low"]) <= stop_price:
                    exit_price = stop_price
                    exit_reason = "stop"
                    exit_date = bar["date"]
                    break
            else:  # SHORT
                if float(bar["silver_high"]) >= stop_price:
                    exit_price = stop_price
                    exit_reason = "stop"
                    exit_date = bar["date"]
                    break
            z_j = z_by_date.get(bar["date"])
            if z_j is not None:
                if direction == "LONG" and z_j <= 0:
                    exit_price = float(bar["silver_close"])
                    exit_reason = "z_crossed_zero"
                    exit_date = bar["date"]
                    break
                if direction == "SHORT" and z_j >= 0:
                    exit_price = float(bar["silver_close"])
                    exit_reason = "z_crossed_zero"
                    exit_date = bar["date"]
                    break

        if exit_price is None:
            # Not yet at time limit — leave open
            if max_exit_idx - entry_idx < MAX_HOLD_DAYS:
                continue
            # Time exit at max_exit_idx close
            exit_bar = gsr_df.iloc[max_exit_idx]
            exit_price = float(exit_bar["silver_close"])
            exit_reason = "time_exit"
            exit_date = exit_bar["date"]

        if direction == "LONG":
            r_mult = (exit_price - entry_price) / stop_offset
            gross = (exit_price - entry_price) * CONTRACT_SIZE
        else:
            r_mult = (entry_price - exit_price) / stop_offset
            gross = (entry_price - exit_price) * CONTRACT_SIZE
        pnl = gross - RT_COST
        outcome = {
            "type": "resolve",
            "signal_id": sid,
            "signal_date": sig_date,
            "direction": direction,
            "entry_date": sig_date,
            "exit_date": exit_date,
            "entry_price": round(entry_price, 3),
            "exit_price": round(exit_price, 3),
            "stop_price": round(stop_price, 3),
            "exit_reason": exit_reason,
            "r_multiple": round(r_mult, 4),
            "pnl_dollars": round(pnl, 2),
            "resolved_utc": datetime.now(timezone.utc).isoformat(),
        }
        print(f"[resolve] {sid}: entry ${entry_price:.3f} -> "
              f"exit ${exit_price:.3f} ({exit_reason}) R={r_mult:+.2f} $={pnl:+.0f}")
        if not dry_run:
            append_shadow(outcome)
            icon = "✅" if r_mult > 0 else "🟥"
            notify_private(
                f"🕯 SHADOW RESOLVE — silver GSR {direction} {icon}\n"
                f"signal date: {sig_date}\n"
                f"entry ${entry_price:.3f} → exit ${exit_price:.3f}\n"
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

    print(f"[silver_gsr_shadow_log] {datetime.now(timezone.utc).isoformat()}")

    gold = load_daily(load_gold_5m, "XAUUSD")
    silver = load_daily(load_silver_5m, "XAGUSD")
    gsr_df = build_gsr(gold, silver)
    print(f"[data] {len(gsr_df)} aligned days "
          f"({gsr_df['date'].min()} to {gsr_df['date'].max()})")

    fresh, msg = check_freshness(gsr_df)
    print(f"[data] {msg}")

    atr_ser = compute_atr(gsr_df, ATR_PERIOD)
    z_ser = compute_z(gsr_df, LOOKBACK)

    log = load_shadow_log()
    n_sig = sum(1 for r in log if r.get("type") == "signal")
    n_res = sum(1 for r in log if r.get("type") == "resolve")
    print(f"[shadow_log] {n_sig} signals, {n_res} resolves")

    resolve_open_signals(gsr_df, z_ser, log, args.dry_run)

    if not fresh and not args.force:
        print("[signal] REFUSING to emit new signals: data stale beyond "
              f"{MAX_STALE_DAYS}d gate. Fix spot data and re-run.")
    else:
        emit_signal_if_triggered(gsr_df, z_ser, atr_ser, log, args.dry_run)

    if not args.dry_run:
        log = load_shadow_log()
    print_track_record(log)


if __name__ == "__main__":
    main()
