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
from datetime import datetime, timezone, timedelta
import json
import os

import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Depends, Header
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

# Dev: localhost:3000 (Next.js on CF Pages). Prod origins added before 07-27.
_ORIGINS = os.environ.get("GOLDTRADER_CORS_ORIGINS",
                          "http://localhost:3000,http://localhost:8080").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _ORIGINS],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


# --- Auth (MVP: JWT stub; upgrade to real HS256 verification later) -----------
# For v0.1 the website side owns Stripe + JWT issuance; API just verifies.
# Public endpoints work without auth. Subscriber endpoints require Bearer.

def get_tier(authorization: str | None = Header(default=None)) -> str:
    """Return 'subscriber' if a valid JWT is present, else 'free'.

    MVP stub: any non-empty Bearer token counts as subscriber. Replace with
    real HS256 verification once GOLDTRADER_JWT_SECRET is provisioned:
        import jwt
        payload = jwt.decode(token, SECRET, algorithms=['HS256'])
        return payload.get('tier', 'free')
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        return "free"
    return "subscriber"


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


# Fields moved into the `audit` block (subscriber-only per website-AI response)
_AUDIT_FIELDS = ("trend_slope", "watch_expires_utc", "max_hold_min",
                  "funding_context", "basis_context", "cot_context",
                  "stand_down_windows")


def _tier_shape(row: dict, tier: str) -> dict:
    """Reshape alert row per subscription tier.

    - subscriber: full audit block visible
    - free: audit block stripped; live alerts (< 24h) also stripped of levels
    """
    out = dict(row)
    audit = {k: out.pop(k) for k in _AUDIT_FIELDS if k in out}
    if tier == "subscriber":
        out["audit"] = audit
        return out
    # Free tier: hide audit; if the alert is < 24h old, hide levels too
    ts = pd.Timestamp(out.get("ts_sent_utc"))
    if ts.tz is None:
        ts = ts.tz_localize("UTC")
    age_h = (pd.Timestamp.now(tz="UTC") - ts).total_seconds() / 3600
    if age_h < 24:
        for k in ("or_high", "or_low", "long", "short",
                  "stop_dist", "target_dist"):
            out.pop(k, None)
        out["redacted"] = "live alert — subscribe to see levels"
    return out


@app.get("/alerts/recent")
def alerts_recent(limit: int = Query(10, ge=1, le=100),
                   tier: str = Depends(get_tier)):
    """Recent PLAN alerts. Free tier: aged >24h shown with levels;
    fresh alerts redacted. Subscriber: full audit block visible."""
    alerts = _load_alerts_stream()
    if not alerts:
        return {"alerts": [], "next_cursor": None, "tier": tier,
                "note": "no plans emitted yet"}
    alerts = alerts[-limit:][::-1]
    alerts = [_tier_shape(a, tier) for a in alerts]
    return {"alerts": alerts, "next_cursor": alerts[0]["ts_sent_utc"] if alerts else None,
            "tier": tier, "disclaimer": DISCLAIMER}


@app.get("/alerts/stream")
def alerts_stream(after: str | None = Query(None, description="ISO-8601 UTC cursor"),
                   tier: str = Depends(get_tier)):
    """Alerts strictly after cursor. Subscriber-only for live alerts;
    free-tier callers get age-gated results."""
    alerts = _load_alerts_stream()
    if after:
        cursor = pd.Timestamp(after)
        if cursor.tz is None:
            cursor = cursor.tz_localize("UTC")
        alerts = [a for a in alerts if pd.Timestamp(a["ts_sent_utc"]) > cursor]
    alerts = [_tier_shape(a, tier) for a in alerts]
    next_cursor = alerts[-1]["ts_sent_utc"] if alerts else after
    return {"alerts": alerts, "next_cursor": next_cursor,
            "tier": tier, "disclaimer": DISCLAIMER}


@app.get("/trades/recent")
def trades_recent(limit: int = Query(20, ge=1, le=200),
                   tier: str = Depends(get_tier)):
    """Closed-trade blotter — for the P&L page. Free tier gets aggregates only."""
    df = _load_forward_log()
    if df.empty:
        return {"trades": [], "tier": tier}
    trades = df[df["took_trade"] == True].sort_values("entry_ts", ascending=False).head(limit)
    rows = []
    for _, t in trades.iterrows():
        row = {
            "session": t["session"],
            "entry_ts": t["entry_ts"].isoformat() if pd.notna(t["entry_ts"]) else None,
            "exit_ts": t["exit_ts"].isoformat() if pd.notna(t["exit_ts"]) else None,
            "direction": int(t["direction"]) if pd.notna(t["direction"]) else None,
            "net_pnl": float(t["net_pnl"]) if pd.notna(t["net_pnl"]) else None,
        }
        if tier == "subscriber":
            row["entry_price"] = float(t["entry_price"]) if pd.notna(t["entry_price"]) else None
            row["exit_price"] = float(t["exit_price"]) if pd.notna(t["exit_price"]) else None
            row["or_range"] = float(t["or_range"]) if pd.notna(t["or_range"]) else None
        rows.append(row)
    return {"trades": rows, "count": len(rows), "tier": tier,
            "disclaimer": DISCLAIMER}


@app.get("/trades/history")
def trades_history(since: str = Query(..., description="ISO-8601 date, e.g. 2026-06-01"),
                    tier: str = Depends(get_tier)):
    """Historical trades since a date. Powers the public 30-day widget +
    subscriber archive page."""
    try:
        since_ts = pd.Timestamp(since)
        if since_ts.tz is None:
            since_ts = since_ts.tz_localize("UTC")
    except Exception:
        raise HTTPException(status_code=400, detail="invalid 'since' date")
    df = _load_forward_log()
    if df.empty:
        return {"trades": [], "since": since_ts.isoformat(), "tier": tier}
    df = df[df["took_trade"] == True].copy()
    df = df[df["entry_ts"] >= since_ts].sort_values("entry_ts")
    trades = []
    for _, t in df.iterrows():
        row = {
            "session": t["session"],
            "entry_ts": t["entry_ts"].isoformat() if pd.notna(t["entry_ts"]) else None,
            "direction": int(t["direction"]) if pd.notna(t["direction"]) else None,
            "net_pnl": float(t["net_pnl"]) if pd.notna(t["net_pnl"]) else None,
        }
        if tier == "subscriber":
            row["entry_price"] = float(t["entry_price"]) if pd.notna(t["entry_price"]) else None
            row["exit_price"] = float(t["exit_price"]) if pd.notna(t["exit_price"]) else None
        trades.append(row)
    # Aggregate summary for both tiers
    net = df["net_pnl"].astype(float) if len(df) else pd.Series(dtype=float)
    return {
        "since": since_ts.isoformat(),
        "count": len(trades),
        "wins": int((net > 0).sum()),
        "losses": int((net <= 0).sum()),
        "net_pnl_usd": round(float(net.sum()), 2) if len(net) else 0.0,
        "win_rate_pct": round(float((net > 0).mean() * 100), 1) if len(net) else 0.0,
        "trades": trades,
        "tier": tier,
        "disclaimer": DISCLAIMER,
    }


@app.post("/subscribers/upsert")
def subscribers_upsert(payload: dict, authorization: str | None = Header(default=None)):
    """Called by the website side after Stripe events. Stub for MVP —
    real implementation writes to a subscriber-state file for future
    JWT verification to consult. Requires an admin bearer.
    """
    admin = os.environ.get("GOLDTRADER_ADMIN_TOKEN")
    if not admin or not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="admin bearer required")
    if authorization.split(" ", 1)[1].strip() != admin:
        raise HTTPException(status_code=401, detail="bad admin token")
    # For now just log — persist properly once schema is agreed with website side
    (ROOT / "data" / "subscribers.jsonl").parent.mkdir(parents=True, exist_ok=True)
    with open(ROOT / "data" / "subscribers.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": pd.Timestamp.now(tz="UTC").isoformat(),
                             **payload}, default=str) + "\n")
    return {"ok": True, "note": "stub — real state store coming with JWT verification"}


@app.get("/disclaimer")
def disclaimer():
    return {"text": DISCLAIMER}


@app.get("/")
def root():
    return {
        "name": "Gold Day Trader API",
        "version": "0.2.0",
        "endpoints": [
            "/health", "/stats/live", "/stats/historical",
            "/alerts/recent", "/alerts/stream",
            "/trades/recent", "/trades/history",
            "/subscribers/upsert",
            "/disclaimer",
        ],
        "auth": "Bearer JWT for subscribers; free tier for unauthenticated",
    }
