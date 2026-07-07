---
name: Website is BINARY (console + public) — no subscription tier
description: Rook's correction to earlier website-AI reply. No Stripe/JWT/subscribers. Console = private/TOTP (Farhad only), Public = everyone else. Defer implementation until after trader is done.
type: project
originSessionId: bb75b257-d83d-4c28-b913-c3fc4a842a01
---
**Source:** Rook (via Farhad, 2026-07-07). Correction to an earlier website-AI (§4) reply that assumed a 3-tier FREE/SUB/CONSOLE model with Stripe checkout + JWT.

**Correct model — binary:**

| Bucket | Access | Sees | Auth |
|---|---|---|---|
| **Console** | Farhad only (private) | Full alert data live · full audit block · ops view (health, dispatch age, state internals) | Existing admin TOTP (`lib/admin-auth.ts` + `lib/totp.ts`) — zero new infra |
| **Public** | Everyone else, no auth | Aggregate stats · tier badge · methodology · **historical resolved trades only** · "Bot offline" state when stale | None |

**Killed from scope:** Stripe, JWT subscriber tier, subscription checkout, `/subscribers/upsert`, "middle bucket" redaction rules, paid-tier payload gating, `GOLDTRADER_ADMIN_TOKEN` on API side (TOTP is on website side).

**Preserved:** Existing admin TOTP for Console gating. Free-tier redaction rules from note #8 (blur prices for <24h alerts) still apply — but the "unblur" happens only in Console, never for public.

## What this means for my API code (to fix WHEN we come back)

Current `src/api.py` v0.2.1 has three artifacts that need reshaping to binary:

1. **`get_tier()` dependency** — currently returns 'subscriber' if any Bearer present. Rename concept to `is_console` and gate on a shared secret between website+API (or drop server-side auth entirely and trust the website to redact for public).
2. **`_tier_shape()` redaction** — currently branches on 'subscriber' vs 'free'. Rebrand branches as `console` vs `public`. Semantic is identical (audit block + full levels for console; blur/redact for public).
3. **`POST /subscribers/upsert`** — delete entirely. No Stripe.

**Trade rendering (`/trades/recent`, `/trades/history`):** public sees historical **resolved** trades only. Add a filter: only include rows where `exit_ts` is set AND `exit_ts < now - 1h` (or similar) for public callers. Console sees everything including open positions if any.

**Payload emission from `dispatch_orb.py`:** unchanged — `data/alerts_stream.jsonl` still carries the full audit block. Redaction is at the API surface, not at emit time.

## My logic take on the binary design

**Right call.** Reasons:

- Eliminates entire failure surface: no JWT verification, no Stripe sync, no subscriber state, no billing edge cases.
- Uses existing auth: TOTP is battle-tested and already in the website codebase.
- Matches the actual customer at launch: **there is no paying customer yet**. Building tier logic for a hypothetical is premature.
- Rook's sizing (~10-12 dev-days vs 15-20) frees runway for what matters — trader accuracy and honest presentation.
- Public gets honest history + methodology → builds trust without needing marketing spin.
- If a paid tier is added later, we reintroduce SUBSCRIBER as a third bucket. Reversible.

**One edge to keep in mind:** if you want to give a friend pilot access to live alerts, they'd need Console access (TOTP). That means they also see ops internals. Options if that's awkward: (a) let it be — friend gets full trust access; or (b) add a "Console-lite" mode later that shows alerts but hides ops. Not a launch blocker.

## When to act on this

**Now implemented (2026-07-07 pm)** — Rook's follow-up gave concrete API spec so I refactored greenfield (no callers yet, no compat cost).

## Rook's concrete API spec (2026-07-07)

**TWO endpoint families under `/v1`:**

- `/v1/public/*` — no auth, redacted at API layer
- `/v1/console/*` — requires `X-Console-Secret: <shared>` header, returns everything

**Secret flow:** API generates a random string; user shares once; Rook drops into Cloudflare env as `KNOX_CONSOLE_SECRET`. Website's Next.js server route (already gated behind admin TOTP) attaches the header before proxying to the API. Browser never touches the secret. Rotation = update both env vars.

**`/v1/public/*` minimum surface (only 4 endpoints):**
- `GET /v1/public/health` — returns `{ bot_online }` only, no dispatch internals
- `GET /v1/public/stats/historical` — `{ verdict, size_tag, n_trades, last_run_utc }`, that's it
- `GET /v1/public/trades/history?since=<date>` — resolved trades where `resolved_at < now - 24h`
- `GET /v1/public/disclaimer` — static text

**`/v1/console/*`:** everything I built at v0.2.1 (except `/subscribers/upsert` — deleted).

**Rate limits:**
- `/public/*`: 60 req/min/IP
- `/console/*`: loose (single client is the website); log warning if called from non-website IP so leakage is detectable early

**Why server-side over UI-only redaction (Rook's reasoning):**
1. `curl` bypass on `api.<domain>` is real; UI redaction doesn't help
2. Redaction is a security property, not a display preference
3. Cost is ~30 min of middleware code — cheap defense-in-depth
4. Better incident story: "we didn't serve the data" beats "we chose not to render it"
