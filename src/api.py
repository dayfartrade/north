"""FastAPI surface for the gold-day-trader website.

Serves the bot's state files directly — no DB, no state duplication.
Endpoints match the v0.1 contract; all times ISO-8601 UTC.

Run locally:
    uvicorn src.api:app --host 0.0.0.0 --port 8000 --reload

Production (behind Caddy/nginx TLS):
    uvicorn src.api:app --host 127.0.0.1 --port 8000 --workers 2
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import json

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parent.parent
HEALTH_FILE = ROOT / "data" / "health.json"
VALIDATION_FILE = ROOT / "data" / "validation_state.json"
FORWARD_LOG = ROOT / "data" / "tracker" / "orb_forward_log.csv"
ALERTS_STREAM = ROOT / "data" / "alerts_stream.jsonl"

LAUNCH_UTC = pd.Timestamp("2026-07-01T00:00:00Z")

DISCLAIMER = (
    "Not financial advice. Futures trading involves substantial risk of loss. "
    "Past results do not guarantee future performance. Your capital, your decision."
)

app = FastAPI(
    title="Gold Day Trader API",
    version="0.1.0",
    description="Public + subscriber surface for the GC session-ORB bot.",
)

# Allow the website origin(s). Tighten to actual domains before launch.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _safe_load_json(p: Path) -> dict:
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _load_forward_log() -> pd.DataFrame:
    if not FORWARD_LOG.exists():
        return pd.DataFrame()
    df = pd.read_csv(FORWARD_LOG)
    if df.empty:
        return df
    df["open_ts"] = pd.to_datetime(df["open_ts"], utc=True, errors="coerce")
    df["entry_ts"] = pd.to_datetime(df.get("entry_ts"), utc=True, errors="coerce")
    df["exit_ts"] = pd.to_datetime(df.get("exit_ts"), utc=True, errors="coerce")
    return df


@app.get("/health")
def health():
    """Bot liveness + last dispatch tick + last bar age."""
    h = _safe_load_json(HEALTH_FILE)
    last_disp = h.get("last_dispatch_utc")
    bot_online = False
    stale_min = None
    if last_disp:
        try:
            ts = pd.Timestamp(last_disp)
            if ts.tz is None:
                ts = ts.tz_localize("UTC")
            stale_min = (pd.Timestamp.now(tz="UTC") - ts).total_seconds() / 60
            bot_online = stale_min < 90  # matches GAP_ALERT_MINUTES in health.py
        except Exception:
            pass
    return {
        "ok": True,
        "server_time_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "last_dispatch_utc": last_disp,
        "last_dispatch_age_min": round(stale_min, 1) if stale_min is not None else None,
        "bot_online": bot_online,
        "last_heartbeat_date": h.get("last_heartbeat_utc_date"),
    }


@app.get("/stats/live")
def stats_live():
    """Honest live P&L since v7 launch. Numbers are the truth, no cherry-picking."""
    df = _load_forward_log()
    if df.empty:
        return {"window_start_utc": LAUNCH_UTC.isoformat(),
                "window_end_utc": pd.Timestamp.now(tz="UTC").isoformat(),
                "trades_taken": 0, "note": "no live trades yet"}
    since = df[df["open_ts"] >= LAUNCH_UTC].copy()
    trades = since[since["took_trade"] == True]
    n = len(trades)
    if n == 0:
        return {"window_start_utc": LAUNCH_UTC.isoformat(),
                "window_end_utc": pd.Timestamp.now(tz="UTC").isoformat(),
                "trades_taken": 0, "sessions_evaluated": len(since),
                "note": "no breakouts qualified since launch"}
    net = trades["net_pnl"].astype(float)
    wins = int((net > 0).sum())
    losses = int((net <= 0).sum())
    win_pnl = net[net > 0]
    loss_pnl = net[net <= 0]
    days_active = max(1, (pd.Timestamp.now(tz="UTC") - LAUNCH_UTC).days)
    return {
        "window_start_utc": LAUNCH_UTC.isoformat(),
        "window_end_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "trades_taken": n,
        "wins": wins,
        "losses": losses,
        "win_rate_pct": round(wins / n * 100, 1),
        "net_pnl_usd": round(float(net.sum()), 2),
        "avg_win_usd": round(float(win_pnl.mean()), 2) if len(win_pnl) else 0.0,
        "avg_loss_usd": round(float(loss_pnl.mean()), 2) if len(loss_pnl) else 0.0,
        "trades_per_day": round(n / days_active, 2),
        "note": (f"n={n} — statistically insufficient (< 20)"
                 if n < 20 else "weak-tier sample"),
        "disclaimer": DISCLAIMER,
    }


@app.get("/stats/historical")
def stats_historical():
    """Latest validated backtest verdict (from weekly Phase 7 auto-revalidation)."""
    v = _safe_load_json(VALIDATION_FILE)
    if not v:
        raise HTTPException(status_code=503,
                            detail="no validation snapshot yet — run "
                                   "src/weekly_validation.py --persist")
    return {**v, "disclaimer": DISCLAIMER}


@app.get("/alerts/recent")
def alerts_recent(limit: int = Query(10, ge=1, le=100)):
    """Recent PLAN alerts (structured JSONL from dispatch_orb)."""
    if not ALERTS_STREAM.exists():
        return {"alerts": [], "next_cursor": None,
                "note": "no plans emitted yet"}
    alerts = []
    with open(ALERTS_STREAM, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                alerts.append(json.loads(line))
            except Exception:
                continue
    alerts = alerts[-limit:][::-1]  # most recent first
    next_cursor = alerts[0]["ts_sent_utc"] if alerts else None
    return {"alerts": alerts, "next_cursor": next_cursor,
            "disclaimer": DISCLAIMER}


@app.get("/alerts/stream")
def alerts_stream(after: str | None = Query(None, description="ISO-8601 UTC cursor")):
    """Alerts strictly after cursor. For subscriber polling."""
    if not ALERTS_STREAM.exists():
        return {"alerts": [], "next_cursor": after}
    cursor = pd.Timestamp(after) if after else None
    if cursor is not None and cursor.tz is None:
        cursor = cursor.tz_localize("UTC")
    alerts = []
    with open(ALERTS_STREAM, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if cursor is None or pd.Timestamp(row["ts_sent_utc"]) > cursor:
                alerts.append(row)
    next_cursor = alerts[-1]["ts_sent_utc"] if alerts else after
    return {"alerts": alerts, "next_cursor": next_cursor,
            "disclaimer": DISCLAIMER}


@app.get("/disclaimer")
def disclaimer():
    return {"text": DISCLAIMER}


@app.get("/")
def root():
    return {
        "name": "Gold Day Trader API",
        "version": "0.1.0",
        "endpoints": [
            "/health", "/stats/live", "/stats/historical",
            "/alerts/recent", "/alerts/stream", "/disclaimer",
        ],
    }
