#!/usr/bin/env python3
"""Generate a PR body following the target product repository's conventions."""
import argparse
import re
import subprocess
from pathlib import Path

def git(*args):
    return subprocess.check_output(["git", *args], text=True).strip()

p = argparse.ArgumentParser()
for flag in ("repo", "area", "issue-url", "dependency", "base", "output"):
    p.add_argument("--" + flag, required=True)
a = p.parse_args()
if a.repo not in ("erikacarvalh0/ec-finance", "erikacarvalh0/ec-viagens", "erikacarvalh0/ec-insurance"):
    p.error("Unknown product repository")
files = git("diff", "--name-only", f"origin/{a.base}...HEAD").splitlines()
if not files:
    p.error("No changes")
subject = git("log", "-1", "--format=%s")
changes = "\n".join("- `" + f + "`" for f in files[:20])
if len(files) > 20:
    changes += f"\n- ... and {len(files)-20} additional files"
tests = [f for f in files if re.search(r"(^|/)(tests?/|__tests__/|e2e/)|\.(test|spec)\.", f)]
test_note = ("Test files changed: " + ", ".join(tests)) if tests else "No test files changed; test coverage not verified."
dependency = ("Independent branch based on main." if a.dependency == "none"
              else f"Stacked on PR #{a.dependency} (base: {a.base}); merge upstream first and rerun CI.")
summary = f"## Summary\n{subject}\n\n## Changes\n{changes}\n\n"
if a.repo.endswith("ec-finance"):
    body = summary + f"## Independence\n{dependency}\n\n## Validation\n{test_note}\nCI pending verification.\n\n## Review\n- [ ] CI green\n- [ ] Human review and merge"
elif a.repo.endswith("ec-viagens"):
    body = summary + f"## Validation\n{test_note}\nAwait GitHub checks before merge.\n\n## Workflow\n{dependency}\nMaintainer controls merge."
else:
    body = summary + f"## TDD\n{test_note}\nTest-first development not independently verified.\n\n## Verification\n- [ ] CI green\n- [ ] User review and merge\n\n{dependency}\nNo automatic merge."
body += f"\n\nBacklog-ID: {a.repo.split('/')[-1]}:{a.area}\nDispatch: {a.issue_url}\n"
Path(a.output).write_text(body, encoding="utf-8")
