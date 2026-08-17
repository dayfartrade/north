"""Pre-commit / CI check: refuse to commit content files with em-dashes.

Memory rule (docs/../memory/feedback_writing_style_no_ai_tropes.md):
    No em-dashes anywhere. Text must sound human.

This script scans staged content files for em-dashes and exits non-zero
if any are found. Meant to run as a git pre-commit hook or in CI on
docs and script text.

Usage:
    python scripts/check_em_dashes.py              # scans only files staged for commit
    python scripts/check_em_dashes.py --all        # scans the whole repo (1000+ historical violations, informational only)
    python scripts/check_em_dashes.py file1 file2  # only these files
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Paths / prefixes to skip - historical or third-party content where we do
# not enforce the rule.
SKIP_PATH_PREFIXES = (
    "docs/launch/telegram_posts.md",              # Engine A era, historical
    "docs/launch/2026-07-18_soft_launch_plan.md", # Engine A era, historical
    "research material/",                          # licensed research, third-party
    "research/janus_2026_07_31/",                  # third-party AI's content
    "backups/",
    ".git/",
    "__pycache__/",
    "data/",
    "site/",
)


def should_scan(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    for skip in SKIP_PATH_PREFIXES:
        if rel.startswith(skip):
            return False
    if path.suffix not in (".md", ".py"):
        return False
    return True


def scan(paths: list[Path]) -> int:
    violations: list[tuple[Path, int, str]] = []
    for p in paths:
        if not p.exists() or p.is_dir():
            continue
        if not should_scan(p):
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if "\u2014" in line:  # em-dash
                violations.append((p, lineno, line))
    if not violations:
        return 0
    print(f"Em-dash violations found ({len(violations)}):")
    for p, lineno, line in violations[:40]:
        rel = p.relative_to(ROOT).as_posix()
        print(f"  {rel}:{lineno}: {line.strip()[:120]}")
    if len(violations) > 40:
        print(f"  ... and {len(violations) - 40} more")
    print()
    print("Fix by replacing em-dashes (U+2014) with a hyphen or rephrasing.")
    print("Memory rule: no em-dashes anywhere; text must sound human.")
    return 1


def staged_files() -> list[Path]:
    r = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        capture_output=True, text=True, cwd=ROOT
    )
    if r.returncode != 0:
        return []
    files = [ROOT / line.strip() for line in r.stdout.splitlines() if line.strip()]
    return files


def main() -> None:
    args = sys.argv[1:]
    if args == ["--all"]:
        paths = []
        for suffix in ("*.md", "*.py"):
            paths.extend(ROOT.rglob(suffix))
    elif args:
        paths = [Path(a).resolve() for a in args]
    else:
        paths = staged_files()
        if not paths:
            print("No files staged for commit. Pass --all to scan the whole repo, or pass file paths.")
            sys.exit(0)
    sys.exit(scan(paths))


if __name__ == "__main__":
    main()
