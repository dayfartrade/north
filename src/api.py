"""FastAPI surface for the gold-day-trader website.

Two endpoint families per Rook's binary spec (2026-07-07):

  /v1/public/*   -> no auth, redacted at API layer
  /v1/console/*  -> requires X-Console-Secret header, returns everything

Run locally:
    uvicorn src.api:app --host 0.0.0.0 --port 8000 --reload

Production (behind Caddy/Cloudflare TLS):
    uvicorn src.api:app --host 127.0.0.1 --port 8000 --workers 2

Env vars:
    GOLDTRADER_CONSOLE_SECRET  = shared secret with website's server route
    GOLDTRADER_CORS_ORIGINS    = comma-separated allowed origins
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone, timedelta
import json
import os
import logging

import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Header, Request, APIRouter
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parent.parent
HEALTH_FILE = ROOT / "data" / "health.json"
VALIDATION_FILE = ROOT / "data" / "validation_state.json"
FORWARD_LOG = ROOT / "data" / "tracker" / "orb_forward_log.csv"
ALERTS_STREAM = ROOT / "data" / "alerts_stream.jsonl"

LAUNCH_UTC = pd.Timestamp("2026-07-01T00:00:00Z")
PUBLIC_TRADE_MIN_AGE_HOURS = 24  # public sees resolved trades only, >24h old

DISCLAIMER = (
    "Not financial advice. Futures trading involves substantial risk of loss. "
    "Past results do not guarantee future performance. Your capital, your decision."
)

log = logging.getLogger("goldtrader.api")

app = FastAPI(
    title="Gold Day Trader API",
    version="0.3.0",
    description="Binary access model — /v1/public/* (redacted, no auth) + /v1/console/* (full, shared-secret).",
)

_ORIGINS = os.environ.get("GOLDTRADER_CORS_ORIGINS",
                          "http://localhost:3000,http://localhost:8080").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _ORIGINS],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-Console-Secret"],
)


# --- shared helpers ----------------------------------------------------------

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


def _load_alerts_stream() -> list[dict]:
    if not ALERTS_STREAM.exists():
        return []
    out = []
    with open(ALERTS_STREAM, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


# --- console-secret gate -----------------------------------------------------

def require_console(request: Request,
                     x_console_secret: str | None = Header(default=None)) -> None:
    """Verify the shared X-Console-Secret header. Log warning if a request
    hits /console/* from an unexpected IP so leakage is detectable early."""
    expected = os.environ.get("GOLDTRADER_CONSOLE_SECRET")
    if not expected:
        raise HTTPException(status_code=503,
                            detail="console secret not configured on server")
    if not x_console_secret or x_console_secret != expected:
        raise HTTPException(status_code=401, detail="invalid console secret")
    # Loose early-warning: log if a client IP is not the expected proxy.
    # Configure GOLDTRADER_CONSOLE_ALLOWED_IPS as comma-separated allowlist.
    allow = os.environ.get("GOLDTRADER_CONSOLE_ALLOWED_IPS", "").split(",")
    allow = [a.strip() for a in allow if a.strip()]
    if allow:
        client = request.client.host if request.client else "?"
        if client not in allow:
            log.warning(f"console request from unexpected IP: {client}")


# =============================================================================
# /v1/public/* — no auth, redacted at API layer
# =============================================================================
public = APIRouter(prefix="/v1/public", tags=["public"])


@public.get("/health")
def public_health():
    """Minimal liveness — only bot_online, no internals."""
    h = _safe_load_json(HEALTH_FILE)
    last_disp = h.get("last_dispatch_utc")
    online = False
    if last_disp:
        try:
            ts = pd.Timestamp(last_disp)
            if ts.tz is None:
                ts = ts.tz_localize("UTC")
            age = (pd.Timestamp.now(tz="UTC") - ts).total_seconds() / 60
            online = age < 90
        except Exception:
            pass
    return {"bot_online": online}


@public.get("/stats/historical")
def public_stats_historical():
    """Only the four fields Rook needs — verdict + size_tag + n_trades + last_run_utc."""
    v = _safe_load_json(VALIDATION_FILE)
    if not v:
        raise HTTPException(status_code=503, detail="no validation snapshot yet")
    return {
        "verdict": v.get("verdict"),
        "size_tag": v.get("size_tag"),
        "n_trades": v.get("n_trades"),
        "last_run_utc": v.get("last_run_utc"),
    }


@public.get("/trades/history")
def public_trades_history(since: str = Query(..., description="ISO-8601 date")):
    """Resolved trades only, and only where exit_ts < now - 24h."""
    try:
        since_ts = pd.Timestamp(since)
        if since_ts.tz is None:
            since_ts = since_ts.tz_localize("UTC")
    except Exception:
        raise HTTPException(status_code=400, detail="invalid 'since' date")
    df = _load_forward_log()
    if df.empty:
        return {"since": since_ts.isoformat(), "count": 0, "trades": []}
    now_utc = pd.Timestamp.now(tz="UTC")
    cutoff = now_utc - pd.Timedelta(hours=PUBLIC_TRADE_MIN_AGE_HOURS)
    df = df[df["took_trade"] == True].copy()
    df = df[df["entry_ts"] >= since_ts]
    df = df[df["exit_ts"].notna() & (df["exit_ts"] < cutoff)]
    df = df.sort_values("entry_ts")
    trades = []
    for _, t in df.iterrows():
        trades.append({
            "session": t["session"],
            "entry_ts": t["entry_ts"].isoformat() if pd.notna(t["entry_ts"]) else None,
            "exit_ts": t["exit_ts"].isoformat() if pd.notna(t["exit_ts"]) else None,
            "direction": int(t["direction"]) if pd.notna(t["direction"]) else None,
            "net_pnl": float(t["net_pnl"]) if pd.notna(t["net_pnl"]) else None,
        })
    net = df["net_pnl"].astype(float) if len(df) else pd.Series(dtype=float)
    return {
        "since": since_ts.isoformat(),
        "count": len(trades),
        "wins": int((net > 0).sum()),
        "losses": int((net <= 0).sum()),
        "net_pnl_usd": round(float(net.sum()), 2) if len(net) else 0.0,
        "win_rate_pct": round(float((net > 0).mean() * 100), 1) if len(net) else 0.0,
        "trades": trades,
        "disclaimer": DISCLAIMER,
    }


@public.get("/disclaimer")
def public_disclaimer():
    return {"text": DISCLAIMER}


app.include_router(public)


# =============================================================================
# /v1/console/* — X-Console-Secret required, returns everything
# =============================================================================
console = APIRouter(prefix="/v1/console", tags=["console"])


@console.get("/health")
def console_health(_: None = None):
    require_console_dep = None  # placeholder for readability
    h = _safe_load_json(HEALTH_FILE)
    last_disp = h.get("last_dispatch_utc")
    stale_min = None
    online = False
    if last_disp:
        try:
            ts = pd.Timestamp(last_disp)
            if ts.tz is None:
                ts = ts.tz_localize("UTC")
            stale_min = (pd.Timestamp.now(tz="UTC") - ts).total_seconds() / 60
            online = stale_min < 90
        except Exception:
            pass
    return {
        "bot_online": online,
        "server_time_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "last_dispatch_utc": last_disp,
        "last_dispatch_age_min": round(stale_min, 1) if stale_min is not None else None,
        "last_heartbeat_date": h.get("last_heartbeat_utc_date"),
        "orb_lag_defers": h.get("orb_lag_defers", {}),
    }


@console.get("/stats/live")
def console_stats_live():
    df = _load_forward_log()
    if df.empty:
        return {"trades_taken": 0, "note": "no live trades yet"}
    since = df[df["open_ts"] >= LAUNCH_UTC].copy()
    trades = since[since["took_trade"] == True]
    n = len(trades)
    if n == 0:
        return {"trades_taken": 0, "sessions_evaluated": len(since)}
    net = trades["net_pnl"].astype(float)
    wins = int((net > 0).sum()); losses = int((net <= 0).sum())
    win_pnl = net[net > 0]; loss_pnl = net[net <= 0]
    days_active = max(1, (pd.Timestamp.now(tz="UTC") - LAUNCH_UTC).days)
    return {
        "window_start_utc": LAUNCH_UTC.isoformat(),
        "window_end_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "trades_taken": n, "wins": wins, "losses": losses,
        "win_rate_pct": round(wins / n * 100, 1),
        "net_pnl_usd": round(float(net.sum()), 2),
        "avg_win_usd": round(float(win_pnl.mean()), 2) if len(win_pnl) else 0.0,
        "avg_loss_usd": round(float(loss_pnl.mean()), 2) if len(loss_pnl) else 0.0,
        "trades_per_day": round(n / days_active, 2),
        "note": (f"n={n} — statistically insufficient (< 20)"
                 if n < 20 else "weak-tier sample"),
        "disclaimer": DISCLAIMER,
    }


@console.get("/stats/historical")
def console_stats_historical():
    v = _safe_load_json(VALIDATION_FILE)
    if not v:
        raise HTTPException(status_code=503, detail="no validation snapshot yet")
    return {**v, "disclaimer": DISCLAIMER}


@console.get("/alerts/recent")
def console_alerts_recent(limit: int = Query(10, ge=1, le=100)):
    alerts = _load_alerts_stream()
    alerts = alerts[-limit:][::-1] if alerts else []
    return {"alerts": alerts,
            "next_cursor": alerts[0]["ts_sent_utc"] if alerts else None,
            "disclaimer": DISCLAIMER}


@console.get("/alerts/stream")
def console_alerts_stream(after: str | None = Query(None)):
    alerts = _load_alerts_stream()
    if after:
        cursor = pd.Timestamp(after)
        if cursor.tz is None:
            cursor = cursor.tz_localize("UTC")
        alerts = [a for a in alerts if pd.Timestamp(a["ts_sent_utc"]) > cursor]
    return {"alerts": alerts,
            "next_cursor": alerts[-1]["ts_sent_utc"] if alerts else after,
            "disclaimer": DISCLAIMER}


@console.get("/trades/recent")
def console_trades_recent(limit: int = Query(20, ge=1, le=200)):
    df = _load_forward_log()
    if df.empty:
        return {"trades": []}
    trades = df[df["took_trade"] == True].sort_values("entry_ts", ascending=False).head(limit)
    rows = []
    for _, t in trades.iterrows():
        rows.append({
            "session": t["session"],
            "entry_ts": t["entry_ts"].isoformat() if pd.notna(t["entry_ts"]) else None,
            "exit_ts": t["exit_ts"].isoformat() if pd.notna(t["exit_ts"]) else None,
            "direction": int(t["direction"]) if pd.notna(t["direction"]) else None,
            "net_pnl": float(t["net_pnl"]) if pd.notna(t["net_pnl"]) else None,
            "entry_price": float(t["entry_price"]) if pd.notna(t["entry_price"]) else None,
            "exit_price": float(t["exit_price"]) if pd.notna(t["exit_price"]) else None,
            "or_range": float(t["or_range"]) if pd.notna(t["or_range"]) else None,
        })
    return {"trades": rows, "count": len(rows), "disclaimer": DISCLAIMER}


@console.get("/trades/history")
def console_trades_history(since: str = Query(...)):
    try:
        since_ts = pd.Timestamp(since)
        if since_ts.tz is None:
            since_ts = since_ts.tz_localize("UTC")
    except Exception:
        raise HTTPException(status_code=400, detail="invalid 'since' date")
    df = _load_forward_log()
    if df.empty:
        return {"since": since_ts.isoformat(), "count": 0, "trades": []}
    df = df[df["took_trade"] == True].copy()
    df = df[df["entry_ts"] >= since_ts].sort_values("entry_ts")
    trades = []
    for _, t in df.iterrows():
        trades.append({
            "session": t["session"],
            "entry_ts": t["entry_ts"].isoformat() if pd.notna(t["entry_ts"]) else None,
            "exit_ts": t["exit_ts"].isoformat() if pd.notna(t["exit_ts"]) else None,
            "direction": int(t["direction"]) if pd.notna(t["direction"]) else None,
            "net_pnl": float(t["net_pnl"]) if pd.notna(t["net_pnl"]) else None,
            "entry_price": float(t["entry_price"]) if pd.notna(t["entry_price"]) else None,
            "exit_price": float(t["exit_price"]) if pd.notna(t["exit_price"]) else None,
        })
    net = df["net_pnl"].astype(float) if len(df) else pd.Series(dtype=float)
    return {
        "since": since_ts.isoformat(),
        "count": len(trades),
        "wins": int((net > 0).sum()),
        "losses": int((net <= 0).sum()),
        "net_pnl_usd": round(float(net.sum()), 2) if len(net) else 0.0,
        "win_rate_pct": round(float((net > 0).mean() * 100), 1) if len(net) else 0.0,
        "trades": trades,
        "disclaimer": DISCLAIMER,
    }


@console.get("/disclaimer")
def console_disclaimer():
    return {"text": DISCLAIMER}


# Apply the console-gate dependency to every console route
for r in console.routes:
    r.dependencies = list(getattr(r, "dependencies", [])) + [
        __import__("fastapi").Depends(require_console)
    ]
app.include_router(console)


# =============================================================================
# Self-describing index
# =============================================================================
@app.get("/")
def root():
    return {
        "name": "Gold Day Trader API",
        "version": "0.3.0",
        "model": "binary — /v1/public/* (no auth, redacted) + /v1/console/* (X-Console-Secret)",
        "tier_thresholds": {
            "INSUFFICIENT": {"n": "< 20"},
            "WEAK":         {"n": "20 to 99"},
            "USABLE":       {"n": "100 to 249"},
            "STRONG":       {"n": ">= 250"},
        },
        "public_routes": [
            {"path": "/v1/public/health",           "summary": "Bot online/offline only"},
            {"path": "/v1/public/stats/historical", "summary": "Verdict + tier + n + last_run_utc"},
            {"path": "/v1/public/trades/history",   "summary": "Resolved trades >24h old since <date>"},
            {"path": "/v1/public/disclaimer",       "summary": "Static risk text"},
        ],
        "console_routes": [
            {"path": "/v1/console/health",           "summary": "Full health incl. dispatch age + lag-defer map"},
            {"path": "/v1/console/stats/live",       "summary": "Full live P&L since v7 launch"},
            {"path": "/v1/console/stats/historical", "summary": "Full validation snapshot"},
            {"path": "/v1/console/alerts/recent",    "summary": "Recent PLAN alerts with full audit block"},
            {"path": "/v1/console/alerts/stream",    "summary": "Cursor-based polling, full data"},
            {"path": "/v1/console/trades/recent",    "summary": "Closed-trade blotter with prices"},
            {"path": "/v1/console/trades/history",   "summary": "Full history incl. open positions"},
            {"path": "/v1/console/disclaimer",       "summary": "Static risk text"},
        ],
        "notes": {
            "console_auth": "Attach header X-Console-Secret: <shared>. Configure via env GOLDTRADER_CONSOLE_SECRET.",
            "public_trade_min_age_hours": PUBLIC_TRADE_MIN_AGE_HOURS,
            "outage_disclosure": "2026-07-03 dispatch missed ~10h (yfinance stall). Fix commits: da3dec9 and a363282.",
        },
    }
