#!/usr/bin/env python3
"""Resolve a trusted orchestrator dispatch issue to an allowlisted target."""
import json
import os
import re
import urllib.request

ALLOWED = {"ec-finance", "ec-viagens", "ec-insurance"}
number = int(os.environ["ISSUE_NUMBER"])
url = f"https://api.github.com/repos/erikacarvalh0/ec-orchestrator/issues/{number}"
req = urllib.request.Request(url, headers={
    "Authorization": "Bearer " + os.environ["GITHUB_TOKEN"],
    "Accept": "application/vnd.github+json",
})
with urllib.request.urlopen(req, timeout=20) as response:
    issue = json.load(response)
if issue["state"] != "open" or not issue["title"].startswith("[EC-DISPATCH] "):
    raise SystemExit("Not an open dispatch issue")
body = issue.get("body") or ""
match = re.search(r"(?m)^Backlog-ID: (ec-(?:finance|viagens|insurance)):(?P<area>[a-z0-9-]+)$", body)
if not match:
    raise SystemExit("Missing valid Backlog-ID")
project, area = match.group(1), match.group("area")
if project not in ALLOWED or issue["title"] != f"[EC-DISPATCH] {project}:{area}":
    raise SystemExit("Dispatch metadata mismatch")
out = os.environ["GITHUB_OUTPUT"]
with open(out, "a") as f:
    f.write(f"repository=erikacarvalh0/{project}\n")
    f.write(f"area={area}\n")
    f.write(f"branch=codex/dispatch-{number}-{area}\n")
    f.write(f"issue_url={issue['html_url']}\n")
print(f"Validated issue {number}: {project}:{area}")
