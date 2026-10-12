"""Repo guard: no silent pre-reg discipline bypass flags.

Scans Python files in scripts/ for argparse flags that could silently
bypass a pre-reg discipline check (n>=X gate, cooling-off, signoff,
etc.) and fails if any such flag is not explicitly allow-listed via
an adjacent comment.

The accepted allow-marker is an inline comment on the `add_argument`
line itself:

    ap.add_argument("--force", action="store_true",  # bypass-allowed: ...
                     help="...")

Only `# bypass-allowed: <reason>` is accepted. The reason must be
non-empty. The marker exists so legitimate operational overrides
(stale-data guard, kill switch) can be distinguished from pre-reg
discipline traps.

What this catches:
  - Flags whose help text contains words like "bypass", "skip",
    "override", "force", "disable" AND "check" / "gate" / "pre-reg" /
    "cooling-off" / "signoff" / "n>=" / "ship gate".
  - --skip-*, --bypass-*, --no-*-check flag names.

What this does NOT catch (nothing can):
  - A flag whose help text is innocuous but whose implementation
    bypasses discipline anyway. The author still has to be honest.
  - Code paths that bypass checks without a flag. The author still
    has to be honest.

This is a defense-in-depth tool, not a complete safeguard.

Usage:
    python scripts/check_no_discipline_bypass.py
    # exit code 0 if clean, 2 if any unmarked bypass flag found
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"

# Patterns that strongly suggest a bypass flag.
BYPASS_KEYWORDS = re.compile(
    r"\b(bypass|skip|override|force|disable)\b", re.IGNORECASE)
DISCIPLINE_KEYWORDS = re.compile(
    r"\b(check|gate|pre-?reg|cooling-?off|signoff|sign-?off|"
    r"n\s*>=|ship\s*gate|post-?hoc|discipline)\b", re.IGNORECASE)
BYPASS_FLAG_NAMES = re.compile(
    r'--(?:skip-|bypass-|force-|no-[a-z]+-check|override-)[\w-]+', re.IGNORECASE)
# Match --force (the general-purpose case we care about most)
GENERAL_FORCE = re.compile(r'"--force"')

ALLOW_MARKER = re.compile(
    r"#\s*bypass-allowed\s*:\s*\S.*", re.IGNORECASE)


def scan_file(path: Path) -> list[tuple[int, str, str]]:
    """Returns list of (line_no, line, reason) for each un-allowed bypass flag."""
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    issues: list[tuple[int, str, str]] = []

    # Group multi-line add_argument calls by locating opening parens.
    i = 0
    while i < len(lines):
        line = lines[i]
        if "add_argument" not in line:
            i += 1
            continue
        # Collect the full add_argument(...) span (naive: up to balanced parens
        # or next add_argument / def / class / blank-at-column-0).
        start = i
        span = [line]
        depth = line.count("(") - line.count(")")
        j = i + 1
        while j < len(lines) and depth > 0:
            span.append(lines[j])
            depth += lines[j].count("(") - lines[j].count(")")
            j += 1
        joined = "\n".join(span)

        # Does this add_argument call define a bypass flag?
        is_bypass = (
            BYPASS_FLAG_NAMES.search(joined)
            or GENERAL_FORCE.search(joined)
            or (BYPASS_KEYWORDS.search(joined) and DISCIPLINE_KEYWORDS.search(joined))
        )
        if is_bypass:
            has_marker = ALLOW_MARKER.search(joined) is not None
            if not has_marker:
                reason = ("bypass-pattern argparse flag with no "
                          "'# bypass-allowed: <reason>' marker")
                issues.append((start + 1, line.strip(), reason))

        i = j if j > i else i + 1

    return issues


def main() -> int:
    all_issues: list[tuple[Path, int, str, str]] = []
    for py in sorted(SCRIPTS.glob("*.py")):
        # Skip this checker itself.
        if py.name == "check_no_discipline_bypass.py":
            continue
        for ln, line, reason in scan_file(py):
            all_issues.append((py, ln, line, reason))

    if not all_issues:
        print("OK: no unmarked bypass flags in scripts/*.py")
        return 0

    print(f"FAIL: {len(all_issues)} unmarked bypass flag(s) in scripts/*.py:")
    print()
    for path, ln, line, reason in all_issues:
        rel = path.relative_to(ROOT)
        print(f"  {rel}:{ln}")
        print(f"    {line}")
        print(f"    REASON: {reason}")
        print(f"    FIX: add '# bypass-allowed: <reason>' comment on the "
              f"add_argument line, OR remove the flag.")
        print()
    print("The '# bypass-allowed: <reason>' marker exists to distinguish "
          "legitimate operational overrides (stale-data guard, kill switch) "
          "from pre-reg discipline traps. Every bypass flag needs an "
          "explicit justification. If you cannot write one honestly, "
          "the flag should not exist.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
