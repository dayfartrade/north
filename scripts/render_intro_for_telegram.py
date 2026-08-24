"""Convert the intro .md to Telegram-safe copy for launch day.

The intro at docs/launch/north_public_intro.md is authored in GitHub
Markdown, which uses **bold** and > blockquotes. Telegram's classic
Markdown differs enough that pasting GitHub Markdown into Telegram
either parse-errors or shows literal formatting characters.

This script emits three artifacts:
  1. --format=plain    plain text, no formatting (safest fallback)
  2. --format=telegram Telegram classic Markdown with * for bold
                       (works for the copy-paste-send flow)
  3. --format=html     Telegram HTML tags (most forgiving; use if the
                       bot sends via API with parse_mode=HTML)

Default is `telegram` since that is what Farhad copy-pastes on launch
day. On launch day, the paste path is Telegram app -> new message ->
paste -> send. Telegram detects the * markers and bolds automatically.

Usage:
    python scripts/render_intro_for_telegram.py
    python scripts/render_intro_for_telegram.py --format html
    python scripts/render_intro_for_telegram.py --format plain
    python scripts/render_intro_for_telegram.py | clip.exe   # copy on Windows Git Bash
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INTRO = ROOT / "docs" / "launch" / "north_public_intro.md"


def strip_frontmatter(md: str) -> str:
    parts = md.split("---")
    return parts[2].strip() if len(parts) >= 3 else md


def to_plain(md: str) -> str:
    body = strip_frontmatter(md)
    # Drop bold markers entirely
    body = re.sub(r"\*\*(.+?)\*\*", r"\1", body)
    # Drop leading > blockquote markers on lines
    body = re.sub(r"^> ?", "", body, flags=re.MULTILINE)
    return body


def to_telegram_markdown(md: str) -> str:
    body = strip_frontmatter(md)
    # **bold** -> *bold*
    body = re.sub(r"\*\*(.+?)\*\*", r"*\1*", body)
    # Drop leading > blockquote markers (Telegram classic MD does not support)
    body = re.sub(r"^> ?", "", body, flags=re.MULTILINE)
    return body


def to_html(md: str) -> str:
    body = strip_frontmatter(md)
    # Strip leading > blockquote markers before HTML escape so they don't
    # show up as literal > characters after escaping.
    body = re.sub(r"^> ?", "", body, flags=re.MULTILINE)
    # Escape HTML entities.
    body = body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # **bold** -> <b>bold</b> (run before single-*)
    body = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", body)
    # *italic* -> <i>italic</i>
    body = re.sub(r"\*(.+?)\*", r"<i>\1</i>", body)
    return body


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--format", choices=["plain", "telegram", "html"], default="telegram")
    args = ap.parse_args()
    md = INTRO.read_text(encoding="utf-8")
    if args.format == "plain":
        print(to_plain(md))
    elif args.format == "html":
        print(to_html(md))
    else:
        print(to_telegram_markdown(md))


if __name__ == "__main__":
    main()
