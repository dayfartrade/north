"""Telegram bot for alerts. Minimal — uses Bot API directly via requests.

Setup (one-time):
  1. Open Telegram, search for @BotFather, send /newbot. Note the token.
  2. Open Telegram, search for your new bot, click Start (send any message).
  3. Visit https://api.telegram.org/bot<TOKEN>/getUpdates to get your chat id.
  4. Set environment variables (PowerShell):
        $env:GOLDTRADER_TG_TOKEN         = "123456:ABC..."
        $env:GOLDTRADER_TG_CHAT          = "987654321"  # private/default chat
        $env:GOLDTRADER_TG_CHAT_PUBLIC   = "-100..."    # optional public channel id
        $env:GOLDTRADER_TG_CHAT_RESEARCH = "-100..."    # optional Knox research/beta channel
     Or write them to C:/golddaytrador/.telegram (key=value lines).

Routing:
  send(text, audience="private")   -> GOLDTRADER_TG_CHAT
  send(text, audience="public")    -> GOLDTRADER_TG_CHAT_PUBLIC if set,
                                      else falls back to GOLDTRADER_TG_CHAT
  send(text, audience="research")  -> GOLDTRADER_TG_CHAT_RESEARCH (Knox v8 unvalidated
                                      shadow signals; falls back to private with LOUD
                                      banner if unset — never public)
  send(text)                        -> default = private (preserves old behavior)
"""
from __future__ import annotations
import os
import sys
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".telegram"

_KEYS = ("GOLDTRADER_TG_TOKEN", "GOLDTRADER_TG_CHAT", "GOLDTRADER_TG_CHAT_PUBLIC",
         "GOLDTRADER_TG_CHAT_RESEARCH")


def _load_all() -> dict:
    """Return dict with token + both chat ids (private + optional public)."""
    out = {k: os.environ.get(k) for k in _KEYS}
    if any(v is None for v in out.values()) and ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip(); v = v.strip().strip('"').strip("'")
            if k in _KEYS and not out.get(k):
                out[k] = v
    return out


def load_creds():
    """Back-compat: (token, private_chat). Old callers continue to work."""
    c = _load_all()
    return c["GOLDTRADER_TG_TOKEN"], c["GOLDTRADER_TG_CHAT"]


def send(text: str, parse_mode: str = "Markdown", silent: bool = False,
          audience: str = "private") -> dict:
    """Send a message via Telegram.

    audience: "private" (default) or "public"
      - private routes to GOLDTRADER_TG_CHAT
      - public routes to GOLDTRADER_TG_CHAT_PUBLIC. When unset:
          * if GOLDTRADER_STRICT_PUBLIC=1, refuses to send (returns error)
          * otherwise falls back to private with a visible fallback banner
            so the operator can't miss that the public channel isn't wired
    """
    c = _load_all()
    tok = c["GOLDTRADER_TG_TOKEN"]
    if audience == "public":
        pub = c["GOLDTRADER_TG_CHAT_PUBLIC"]
        if pub:
            chat = pub
        else:
            if os.environ.get("GOLDTRADER_STRICT_PUBLIC") == "1":
                return {"ok": False, "error": "public_channel_not_configured",
                        "detail": "GOLDTRADER_TG_CHAT_PUBLIC unset and STRICT mode on"}
            chat = c["GOLDTRADER_TG_CHAT"]
            text = ("⚠️ *FALLBACK: public channel not configured — this alert "
                    "would have gone to subscribers*\n\n" + text)
    elif audience == "research":
        # Knox research/beta channel for v8 unvalidated shadow signals.
        # Never falls back to public — the fallback banner tells the operator
        # to configure GOLDTRADER_TG_CHAT_RESEARCH; unvalidated signals must
        # NEVER be sent to the public/subscriber channel.
        res = c["GOLDTRADER_TG_CHAT_RESEARCH"]
        if res:
            chat = res
        else:
            chat = c["GOLDTRADER_TG_CHAT"]
            text = ("⚠️ *FALLBACK: research channel not configured — "
                    "GOLDTRADER_TG_CHAT_RESEARCH unset*\n\n" + text)
    else:
        chat = c["GOLDTRADER_TG_CHAT"]
    if not tok or not chat:
        msg = (f"[telegram] credentials missing for audience={audience}. "
               f"Set GOLDTRADER_TG_TOKEN and chat id(s).")
        if not silent:
            print(msg, file=sys.stderr)
        return {"ok": False, "error": "no_credentials"}
    url = f"https://api.telegram.org/bot{tok}/sendMessage"
    payload = {"chat_id": chat, "text": text, "parse_mode": parse_mode,
               "disable_web_page_preview": True}
    try:
        r = requests.post(url, json=payload, timeout=20)
        return r.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}


def send_split(text: str, max_len: int = 3500) -> list[dict]:
    """Telegram has a ~4096 char limit per message. Split if needed."""
    if len(text) <= max_len:
        return [send(text)]
    out = []
    cur = ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > max_len:
            out.append(send(cur))
            cur = line
        else:
            cur = cur + "\n" + line if cur else line
    if cur:
        out.append(send(cur))
    return out


def selftest():
    tok, chat = load_creds()
    if not tok or not chat:
        print("MISSING CREDENTIALS.")
        print("To configure:")
        print("  PowerShell: $env:GOLDTRADER_TG_TOKEN='...'; $env:GOLDTRADER_TG_CHAT='...'")
        print(f"  Or write to {ENV_FILE}:")
        print("     GOLDTRADER_TG_TOKEN=...")
        print("     GOLDTRADER_TG_CHAT=...")
        return False
    r = send("✅ *gold-day-trader* connected. Telegram alerts are live.\n"
             "Reply STOP to mute (manual config for now).")
    print(r)
    return bool(r.get("ok"))


if __name__ == "__main__":
    selftest()
