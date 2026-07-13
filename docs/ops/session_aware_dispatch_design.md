# Session-aware dispatch — design doc

**Owner:** Knox. **Target apply date:** 2026-07-13 post-CPI (14:00 UTC+).
**Reason:** Current 30-min dispatch fires unconditionally. During COMEX close (17:00-18:00 ET = 21:00-22:00 UTC standard / 22:00-23:00 UTC DST) there is no gold trading — those ticks are wasted CPU and pollute log statistics. On weekends the dispatcher wakes for gold trading that is entirely closed.

## Current behavior

`src/dispatch.py` runs every 30 min via Task Scheduler / systemd timer. Inside:
- `dispatch_orb_alerts()` iterates `SESSIONS_LOCAL` and checks whether any is currently in preview/pre/plan window
- Falls through with "no alerts due" if none

Cost of wasted ticks:
- COMEX close (~1h/day): 2 ticks/day = 730 ticks/year of pure noise in `dispatch.log`
- Weekends (Fri 22:00 UTC → Sun 22:00 UTC gap ≈ 48h): 96 ticks/weekend = ~5,000 ticks/year
- Total: ~5,700 unnecessary ticks/year (~14% of scheduled runs)

## Proposed change

Add a market-state guard at the top of `dispatch_orb_alerts()`:

```python
def is_gold_market_open(now_utc: datetime) -> tuple[bool, str]:
    """Return (is_open, reason_if_closed)."""
    # COMEX daily close: 17:00-18:00 ET.
    # In UTC that's:
    #   Standard time (Nov-Mar): 22:00-23:00 UTC
    #   Daylight time (Mar-Nov): 21:00-22:00 UTC
    et = now_utc.astimezone(pytz.timezone("America/New_York"))
    dow = et.weekday()  # 0=Mon, 6=Sun

    # Weekend gap: Friday 17:00 ET -> Sunday 18:00 ET
    if dow == 5:  # Saturday
        return False, "weekend (Saturday)"
    if dow == 6 and et.hour < 18:  # Sunday before 18:00 ET
        return False, "weekend (Sunday pre-open)"
    if dow == 4 and et.hour >= 17:  # Friday after 17:00 ET
        return False, "weekend (Friday close)"

    # Daily close 17:00-18:00 ET
    if et.hour == 17:
        return False, "COMEX daily close (17:00-18:00 ET)"

    return True, ""


def dispatch_orb_alerts():
    now = datetime.now(timezone.utc)
    is_open, reason = is_gold_market_open(now)
    if not is_open:
        _log(f"[dispatch] gold market closed: {reason}. Skipping.")
        return  # early return; scheduled timer keeps calling, but this exits fast
    ...existing logic...
```

## Testing plan

1. **Unit tests** in `tests/test_session_aware.py`:
   - Weekday 14:00 UTC → open
   - Saturday 14:00 UTC → closed (weekend)
   - Sunday 22:00 UTC → open (Sunday post-18:00 ET)
   - Sunday 21:00 UTC → closed (Sunday pre-open in ET)
   - Weekday 21:30 UTC in July (DST) → closed (COMEX close 17:30 ET)
   - Weekday 21:30 UTC in January (EST) → open (COMEX still trading)

2. **Manual verification** post-apply:
   - Trigger a dispatch during COMEX close window
   - Verify log emits "gold market closed" and returns without work

## Risk assessment

**LOW risk change.** Failure modes:
- If our clock skew mislabels a session, we might miss a real ORB window
  - Mitigation: log the guard decision each tick for auditability; keep the timer running every 30 min so the next tick catches up if we mis-skipped
- If DST transitions are handled wrong, we double-skip or double-run
  - Mitigation: use `pytz.timezone("America/New_York")` for automatic DST; add DST-transition tests

**Backwards compatibility:** none broken — the change only ADDS an early return in a known no-op condition.

## Impact on halt_monitor.py

If dispatch is skipped, halt_monitor.py won't run. That's fine — halt state doesn't change if there are no new trades. On the next open-market tick, halt_monitor runs and picks up any changes.

## Wiring halt_monitor into dispatch (bonus)

While we're touching dispatch, wire halt_monitor as a subprocess check at start of tick:

```python
def dispatch_orb_alerts():
    now = datetime.now(timezone.utc)
    is_open, reason = is_gold_market_open(now)
    if not is_open:
        _log(f"[dispatch] gold market closed: {reason}. Skipping.")
        return

    # NEW: halt-monitor early check
    try:
        from scripts.halt_monitor import main as halt_main
        # halt_main returns 0 (safe) or 1 (halt)
        # If halt state is HALT, log and abort ORB dispatch (no new positions)
        halt_state_path = ROOT / "data/halt_state.json"
        if halt_state_path.exists():
            with open(halt_state_path) as f:
                halt_state = json.load(f)
            if halt_state.get("verdict") == "HALT":
                _log(f"[dispatch] halt_monitor verdict=HALT — no new ORB entries. reason={halt_state.get('reason')}")
                return
    except Exception as e:
        _log(f"[dispatch] halt_monitor check failed (continuing): {type(e).__name__}: {e}")

    ...existing logic...
```

Fail-open on exception: if halt_monitor check itself fails, dispatch continues normally (so a bug in halt_monitor doesn't stop trading; user still has manual override).

## Apply order (post-CPI, 14:00 UTC+)

1. Write `tests/test_session_aware.py` with the 6 test cases above
2. Add `is_gold_market_open` helper to `src/dispatch_orb.py`
3. Add early return in `dispatch_orb_alerts()`
4. Run tests
5. Trigger manual dispatch during COMEX close window (21:00-22:00 UTC today) → verify
6. Add halt_monitor early check wiring (separate commit for isolation)
7. Update `hosting_blocker.md` memory to remove S4U-band-aid concerns for closed hours

## Total effort estimate

~45 min including tests. Post-CPI apply target.
