#!/usr/bin/env python3
"""Idempotently queue one task in the orchestrator repository, never in product repositories."""
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

REPO = "erikacarvalh0/ec-orchestrator"
API = "https://api.github.com/repos/" + REPO + "/issues"
def request(method, url, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Authorization": "Bearer " + os.environ["GITHUB_TOKEN"], "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)
def main():
    plan = json.loads(Path("reports/dispatch-plan.json").read_text())
    if plan.get("status") != "plan_only":
        raise RuntimeError("Unsupported dispatch plan status")
    lanes = plan.get("lanes", [])
    if not lanes:
        print("No eligible lanes")
        return
    # Strictly one new issue per run; a pending task prevents repeated creation.
    issues = []
    for page in range(1, 11):
        batch = request("GET", API + "?state=open&per_page=100&page=" + str(page))
        issues.extend(x for x in batch if "pull_request" not in x)
        if len(batch) < 100:
            break
    else:
        raise RuntimeError("Issue pagination limit reached; fail closed")
    if any("[EC-DISPATCH]" in (i.get("title") or "") for i in issues):
        print("Open dispatch task exists; no new task queued")
        return
    lane = lanes[0]
    key = lane["backlog_id"]
    if any(key in (i.get("body") or "") for i in issues):
        print("Area already queued; no duplicate")
        return
    body = ("Backlog-ID: " + key + "\n\n"
            "Repository: " + lane["repository"] + "\n"
            "Status: pending agent assignment (no coding agent connected)\n\n"
            "Acceptance checklist:\n- [ ] Validate scope and historical PR evidence\n"
            "- [ ] Implement and test in an isolated branch\n"
            "- [ ] Open a product-repository PR for human review\n"
            "- [ ] Do not merge product PR automatically\n\n"
            "This issue is a queue item only, not an agent execution.")
    created = request("POST", API, {"title": "[EC-DISPATCH] " + key, "body": body})
    print(json.dumps({"queued_issue": created["html_url"], "backlog_id": key}))
if __name__ == "__main__":
    main()
