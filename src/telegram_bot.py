"""Telegram bot for alerts. Minimal — uses Bot API directly via requests.

Setup (one-time):
  1. Open Telegram, search for @BotFather, send /newbot. Note the token.
  2. Open Telegram, search for your new bot, click Start (send any message).
  3. Visit https://api.telegram.org/bot<TOKEN>/getUpdates to get your chat id.
  4. Set environment variables (PowerShell):
        $env:GOLDTRADER_TG_TOKEN = "123456:ABC..."
        $env:GOLDTRADER_TG_CHAT  = "987654321"
     Or write them to C:/golddaytrador/.telegram (key=value lines).

Use:
  from telegram_bot import send
  send("Hello world")
"""
from __future__ import annotations
import os
import sys
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".telegram"


def load_creds():
    tok = os.environ.get("GOLDTRADER_TG_TOKEN")
    chat = os.environ.get("GOLDTRADER_TG_CHAT")
    if (not tok or not chat) and ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip(); v = v.strip().strip('"').strip("'")
            if k == "GOLDTRADER_TG_TOKEN" and not tok:
                tok = v
            if k == "GOLDTRADER_TG_CHAT" and not chat:
                chat = v
    return tok, chat


def send(text: str, parse_mode: str = "Markdown", silent: bool = False) -> dict:
    """Send a message via Telegram. Returns API response dict."""
    tok, chat = load_creds()
    if not tok or not chat:
        msg = ("[telegram] credentials missing. Set env GOLDTRADER_TG_TOKEN and "
               "GOLDTRADER_TG_CHAT, or write them to .telegram file.")
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
