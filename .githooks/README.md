# .githooks

Repo-managed git hooks. Enable them once per clone with:

```
git config core.hooksPath .githooks
```

## pre-commit

Runs `python scripts/check_em_dashes.py` on files staged for commit.
Fails the commit if any staged content file contains an em-dash
(U+2014). Rationale: memory rule requires all human-readable text to
sound human, and em-dashes are a common AI signature.

Historical files (Engine A era docs, third-party research) are carved
out in `check_em_dashes.py::SKIP_PATH_PREFIXES`.

To bypass in a true emergency: `git commit --no-verify`. Fix the
violation in a follow-up commit.
