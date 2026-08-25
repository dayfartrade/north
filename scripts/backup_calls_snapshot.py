"""Weekly backup of NORTH research corpus to two separate storage systems.

Rationale: never lose any call history or research artifact. Snapshots
the R&D corpus to two off-tree destinations so no single failure can
erase state needed for future analysis:

  1. Telegram DM to operator's private chat (GOLDTRADER_TG_CHAT).
     Off-platform from GitHub. Survives full repo loss.

  2. GitHub Release on dayfartrade/north, tagged `snapshot-<week>` with
     the same assets attached. Separate storage layer from the git
     tree. Survives force-push or branch corruption. Immutable per week.

What gets shipped each run:
  - `far_weekly_calls.jsonl` (source-of-truth call history, sent raw
    so it's directly readable without extraction).
  - `far_weekly_current.json` + `far_weekly_history.json` (site payloads).
  - `north_research_corpus_<week>.tar.gz` bundling:
      data/*.jsonl, data/*.json (all live/state logs)
      data/experiments/, data/tracker/, data/calendar/, data/alerts/,
        data/logs/, data/backtests/  (research artifacts)
      site/data/*.json  (all site payloads incl. price series + briefs)
      docs/experiments/  (pre-registration docs)
      docs/development_story.md, docs/launch/  (narrative + launch kit)
      memory/  (operator memory files, local runs only)

Excluded (regenerable from source or covered by separate one-shot
backups): data/external/ (Dukascopy 5m, 441MB, has its own tar.gz
snapshot from 2026-07), data/gc/ (yfinance-regenerable), data/macro/
(FRED-regenerable).

Both destinations are free and use credentials already present. Runs
weekly from weekly-publish immediately after publish. Idempotent: skips
GitHub side if the week's release already exists, always sends Telegram
(safe for manual reruns).

Usage:
    python scripts/backup_calls_snapshot.py
    python scripts/backup_calls_snapshot.py --dry-run
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

import urllib.request
import urllib.parse
import mimetypes

ROOT = Path(__file__).resolve().parent.parent
CALLS_JSONL = ROOT / "data" / "far_weekly_calls.jsonl"
SITE_CURRENT = ROOT / "site" / "data" / "far_weekly_current.json"
SITE_HISTORY = ROOT / "site" / "data" / "far_weekly_history.json"
MEMORY_DIR = Path.home() / ".claude" / "projects" / "C--golddaytrador" / "memory"

GITHUB_REPO = "dayfartrade/north"

# Paths to bundle into the research corpus tarball. Relative to ROOT.
# Directories are added recursively; loose files are added by name.
CORPUS_PATHS = [
    "data/experiments",
    "data/tracker",
    "data/calendar",
    "data/alerts",
    "data/logs",
    "data/backtests",
    "site/data",
    "docs/experiments",
    "docs/launch",
    "docs/development_story.md",
]

# Any loose files at data/*.jsonl or data/*.json are added dynamically.


def load_calls() -> list[dict]:
    if not CALLS_JSONL.exists():
        return []
    with open(CALLS_JSONL) as f:
        return [json.loads(l) for l in f if l.strip()]


def latest_call_week(calls: list[dict]) -> str | None:
    for row in reversed(calls):
        if row.get("type") == "call" and row.get("week_of"):
            return row["week_of"]
    return None


def load_env_from_dotfile(path: Path) -> dict:
    """Parse KEY=VALUE lines from a dotenv-style file."""
    out = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def resolve_credentials() -> tuple[str | None, str | None, str | None]:
    """Return (tg_token, tg_private_chat, gh_token) from env or dotfiles.

    Env vars take priority (CI); dotfiles are the local fallback.
    """
    tg_token = os.environ.get("GOLDTRADER_TG_TOKEN")
    tg_chat = os.environ.get("GOLDTRADER_TG_CHAT")
    gh_token = os.environ.get("GITHUB_TOKEN")

    if not tg_token or not tg_chat:
        dot = load_env_from_dotfile(ROOT / ".telegram")
        tg_token = tg_token or dot.get("GOLDTRADER_TG_TOKEN")
        tg_chat = tg_chat or dot.get("GOLDTRADER_TG_CHAT")

    if not gh_token:
        gh_file = ROOT / ".github-token"
        if gh_file.exists():
            gh_token = gh_file.read_text(encoding="utf-8").strip()

    return tg_token, tg_chat, gh_token


def _multipart_body(fields: dict, files: dict) -> tuple[bytes, str]:
    """Build a multipart/form-data body. `files` is {field: (name, content)}."""
    boundary = "----NorthBackup" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    lines = []
    for k, v in fields.items():
        lines.append(f"--{boundary}".encode())
        lines.append(f'Content-Disposition: form-data; name="{k}"'.encode())
        lines.append(b"")
        lines.append(str(v).encode())
    for field, (fname, content) in files.items():
        mime = mimetypes.guess_type(fname)[0] or "application/octet-stream"
        lines.append(f"--{boundary}".encode())
        lines.append(
            f'Content-Disposition: form-data; name="{field}"; filename="{fname}"'
            .encode())
        lines.append(f"Content-Type: {mime}".encode())
        lines.append(b"")
        lines.append(content)
    lines.append(f"--{boundary}--".encode())
    lines.append(b"")
    return b"\r\n".join(lines), f"multipart/form-data; boundary={boundary}"


def telegram_send_document(token: str, chat_id: str, filename: str,
                            content: bytes, caption: str = "") -> dict:
    url = f"https://api.telegram.org/bot{token}/sendDocument"
    fields = {"chat_id": chat_id}
    if caption:
        fields["caption"] = caption
        fields["parse_mode"] = "HTML"
    files = {"document": (filename, content)}
    body, content_type = _multipart_body(fields, files)
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", content_type)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def github_api(method: str, path: str, token: str, body: dict | None = None,
                extra_headers: dict | None = None,
                raw_body: bytes | None = None) -> tuple[int, dict | bytes]:
    url = f"https://api.github.com{path}" if path.startswith("/") else path
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "north-backup-script",
    }
    if extra_headers:
        headers.update(extra_headers)
    if raw_body is not None:
        data = raw_body
    elif body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    else:
        data = None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            if r.status == 204 or not raw:
                return r.status, {}
            try:
                return r.status, json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                return r.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw.decode("utf-8"))
        except Exception:
            return e.code, {"error": raw.decode("utf-8", errors="ignore")}


def github_release_exists(tag: str, token: str) -> bool:
    code, _ = github_api("GET", f"/repos/{GITHUB_REPO}/releases/tags/{tag}", token)
    return code == 200


def github_create_release(tag: str, name: str, body: str, token: str) -> dict:
    code, resp = github_api("POST", f"/repos/{GITHUB_REPO}/releases", token,
                              body={
                                  "tag_name": tag,
                                  "target_commitish": "main",
                                  "name": name,
                                  "body": body,
                                  "draft": False,
                                  "prerelease": False,
                              })
    if code >= 400:
        raise RuntimeError(f"release create failed: {code} {resp}")
    return resp


def github_upload_asset(upload_url: str, filename: str,
                          content: bytes, token: str) -> None:
    base = upload_url.split("{")[0]
    url = f"{base}?name={urllib.parse.quote(filename)}"
    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    code, resp = github_api("POST", url, token, raw_body=content,
                              extra_headers={"Content-Type": mime})
    if code >= 400:
        raise RuntimeError(f"asset upload failed for {filename}: {code} {resp}")


def build_research_tarball(week: str | None) -> tuple[str, bytes, list[str]]:
    """Build the R&D corpus tarball in-memory. Returns (filename, bytes, index)."""
    stamp = week or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    tar_name = f"north_research_corpus_{stamp}.tar.gz"
    buf = io.BytesIO()
    added: list[str] = []
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        # 1. Loose data files at data/*.jsonl and data/*.json
        for pattern in ("*.jsonl", "*.json"):
            for f in sorted((ROOT / "data").glob(pattern)):
                arc = f.relative_to(ROOT).as_posix()
                tf.add(str(f), arcname=arc)
                added.append(arc)
        # 2. Curated directories + docs/development_story.md
        for rel in CORPUS_PATHS:
            src = ROOT / rel
            if not src.exists():
                continue
            arc = src.relative_to(ROOT).as_posix()
            tf.add(str(src), arcname=arc)
            added.append(arc)
        # 3. Operator memory (local only; CI runners won't have this path)
        if MEMORY_DIR.exists():
            tf.add(str(MEMORY_DIR), arcname="memory")
            added.append("memory/")
    return tar_name, buf.getvalue(), added


def build_files_bundle(week: str | None) -> list[tuple[str, bytes]]:
    """Return list of (filename, content_bytes) to attach to both destinations.

    Raw call history + site JSONs are sent uncompressed so they can be read
    directly. The full research corpus tarball is sent alongside.
    """
    bundle = []
    for src in (CALLS_JSONL, SITE_CURRENT, SITE_HISTORY):
        if src.exists():
            bundle.append((src.name, src.read_bytes()))
    tar_name, tar_bytes, index = build_research_tarball(week)
    print(f"[corpus] {tar_name} = {len(tar_bytes)/1024:.1f} KB, "
          f"{len(index)} paths bundled")
    bundle.append((tar_name, tar_bytes))
    return bundle


def build_caption(calls: list[dict], week: str | None) -> str:
    n_total = sum(1 for c in calls if c.get("type") == "call")
    n_resolved = sum(1 for c in calls
                      if c.get("type") == "call"
                      and c.get("outcome", {}).get("result") == "resolved")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    week_str = week or "unknown"
    return (f"<b>NORTH backup</b>\n"
            f"Week: {week_str}\n"
            f"Total calls: {n_total} ({n_resolved} resolved)\n"
            f"Snapshot: {now}")


def build_release_body(calls: list[dict], week: str | None) -> str:
    n_total = sum(1 for c in calls if c.get("type") == "call")
    n_resolved = sum(1 for c in calls
                      if c.get("type") == "call"
                      and c.get("outcome", {}).get("result") == "resolved")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return (f"Snapshot of NORTH research corpus as of {now}.\n\n"
            f"- Active week: `{week or 'unknown'}`\n"
            f"- Total calls: {n_total}\n"
            f"- Resolved: {n_resolved}\n\n"
            f"### Assets\n\n"
            f"- `far_weekly_calls.jsonl` (source-of-truth call history)\n"
            f"- `far_weekly_current.json`, `far_weekly_history.json` (site payloads)\n"
            f"- `north_research_corpus_<week>.tar.gz` (bundle: all live logs, "
            f"experiment registry, pre-reg docs, launch kit, development story, "
            f"operator memory when built locally)\n\n"
            f"Emitted by `scripts/backup_calls_snapshot.py` from the "
            f"weekly-publish workflow. See script docstring for the exact "
            f"included/excluded paths.")


def run(dry_run: bool = False) -> int:
    calls = load_calls()
    week = latest_call_week(calls)
    bundle = build_files_bundle(week)
    if not bundle:
        print("[skip] no files to back up")
        return 0
    print(f"[bundle] {len(bundle)} attachments: "
          f"{[(n, f'{len(b)//1024}KB') for n, b in bundle]} "
          f"(latest week={week})")

    tg_token, tg_chat, gh_token = resolve_credentials()
    caption = build_caption(calls, week)

    tg_ok = False
    gh_ok = False

    # 1. Telegram DM
    if not tg_token or not tg_chat:
        print("[telegram] missing GOLDTRADER_TG_TOKEN or GOLDTRADER_TG_CHAT, skip")
    elif dry_run:
        print(f"[telegram] dry-run: would send {len(bundle)} files to chat {tg_chat}")
        tg_ok = True
    else:
        try:
            for i, (fname, content) in enumerate(bundle):
                cap = caption if i == 0 else ""
                resp = telegram_send_document(tg_token, tg_chat, fname, content, cap)
                if not resp.get("ok"):
                    raise RuntimeError(f"telegram rejected: {resp}")
                print(f"[telegram] sent {fname} ({len(content)} bytes)")
            tg_ok = True
        except Exception as e:
            print(f"[telegram] FAILED: {type(e).__name__}: {e}")

    # 2. GitHub Release
    if not gh_token:
        print("[github] missing GITHUB_TOKEN / .github-token, skip")
    else:
        tag = f"snapshot-{week or datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
        if dry_run:
            print(f"[github] dry-run: would create release {tag} with "
                  f"{len(bundle)} assets")
            gh_ok = True
        elif github_release_exists(tag, gh_token):
            print(f"[github] release {tag} already exists, skip "
                  f"(delete to re-create)")
            gh_ok = True
        else:
            try:
                body = build_release_body(calls, week)
                release = github_create_release(tag, f"NORTH snapshot {week}",
                                                  body, gh_token)
                for fname, content in bundle:
                    github_upload_asset(release["upload_url"], fname,
                                         content, gh_token)
                    print(f"[github] uploaded {fname} to release {tag}")
                gh_ok = True
                print(f"[github] release live: {release.get('html_url')}")
            except Exception as e:
                print(f"[github] FAILED: {type(e).__name__}: {e}")

    print(f"[summary] telegram={'OK' if tg_ok else 'FAIL'} "
          f"github={'OK' if gh_ok else 'FAIL'}")
    return 0 if (tg_ok and gh_ok) else 1


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    print(f"[backup_calls_snapshot] {datetime.now(timezone.utc).isoformat()}")
    rc = run(dry_run=args.dry_run)
    sys.exit(rc)


if __name__ == "__main__":
    main()
