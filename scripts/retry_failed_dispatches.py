#!/usr/bin/env python3
"""Retry failed dispatches once, fail-closed on uncertain state."""
import datetime as dt
import json
import os
import re
import urllib.request

BASE = "https://api.github.com/repos/"
ORCH = "erikacarvalh0/ec-orchestrator"
TOKEN = os.environ["GITHUB_TOKEN"]
PRODUCT_TOKEN = os.environ["EC_BACKLOG_READ_TOKEN"]
AREA = re.compile(r"(?m)^Backlog-ID: (ec-(?:finance|viagens|insurance):[a-z0-9-]+)$")
STATUS = re.compile(r"^### Dispatch status: (failed|pr_created|retry_queued)", re.M)
COOLDOWN = dt.timedelta(minutes=10)


def api(method, url, token=TOKEN, payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=body, method=method, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        **({"Content-Type": "application/json"} if body is not None else {}),
    })
    with urllib.request.urlopen(req, timeout=30) as response:
        return {} if response.status == 204 else json.load(response)


def pages(url, token=TOKEN):
    result = []
    for page in range(1, 11):
        separator = "&" if "?" in url else "?"
        batch = api("GET", f"{url}{separator}per_page=100&page={page}", token)
        result.extend(batch)
        if len(batch) < 100:
            return result
    raise RuntimeError("Pagination exceeded; refusing partial retry evidence")


def run():
    now = dt.datetime.now(dt.timezone.utc)
    runs = api("GET", BASE + ORCH + "/actions/workflows/codex-dispatch.yml/runs?per_page=100")["workflow_runs"]
    # Global fail-closed guard: no retry while any agent is queued/running.
    if any(r["status"] != "completed" for r in runs):
        print("Skipping retries: dispatch workflow currently active")
        return
    # A verified successful executor run provides a recovery boundary for
    # dispatches that exhausted retries during the previous infrastructure outage.
    successful = [
        r for r in runs if r["status"] == "completed" and r["conclusion"] == "success"
    ]
    recovery_at = max(
        (dt.datetime.fromisoformat(r["created_at"].replace("Z", "+00:00"))
         for r in successful),
        default=None,
    )
    issues = pages(BASE + ORCH + "/issues?state=open")
    for issue in issues:
        if "pull_request" in issue:
            continue
        match = AREA.search(issue.get("body") or "")
        if not match or issue["title"] != "[EC-DISPATCH] " + match.group(1):
            continue
        key = match.group(1)
        if not re.search(r"--task-[0-9]{2}$", key):
            print(f"Skipping legacy dispatch {key}: granular task ID required")
            continue
        comments = pages(issue["comments_url"])
        statuses = [(STATUS.search(c.get("body") or "").group(1), c)
                    for c in comments if STATUS.search(c.get("body") or "")]
        if not statuses or statuses[-1][0] != "failed":
            continue
        failures = sum(status == "failed" for status, _ in statuses)
        failed_at = dt.datetime.fromisoformat(statuses[-1][1]["created_at"].replace("Z", "+00:00"))
        # Standard retry: once per issue. Recovery retry: once only when
        # a newer successful executor proves the global bootstrap was repaired.
        recovery = (
            failures > 1
            and recovery_at is not None
            and failed_at < recovery_at
            and not any(status == "retry_queued" and
                        dt.datetime.fromisoformat(comment["created_at"].replace("Z", "+00:00")) > failed_at
                        for status, comment in statuses)
        )
        if failures != 1 and not recovery:
            print(f"Skipping {key}: retry limit reached")
            continue
        if now - failed_at < COOLDOWN and not recovery:
            continue
        target = "erikacarvalh0/" + key.split(":")[0]
        branch = f"codex/dispatch-{issue['number']}-{key.split(':')[1]}"
        # All PR states matter: never retry after a PR has ever been published.
        prs = pages(BASE + target + "/pulls?state=all", PRODUCT_TOKEN)
        if any(p["head"]["ref"] == branch or key in (p.get("body") or "") for p in prs):
            print(f"Skipping {key}: existing product PR")
            continue
        branches = pages(BASE + target + "/branches", PRODUCT_TOKEN)
        if any(b["name"] == branch for b in branches):
            print(f"Skipping {key}: existing product branch")
            continue
        # Persist a reservation before dispatching. A failed dispatch requires manual
        # recovery rather than risking duplicate jobs on the next sync.
        api("POST", issue["comments_url"], payload={
            "body": "### Dispatch status: retry_queued\n\n"
                    + ("One recovery retry reserved after a successful executor bootstrap. " if recovery else "One automatic retry reserved after a failed execution. ")
                    + "If dispatch does not start, investigate manually."
        })
        api("POST", BASE + ORCH + "/actions/workflows/codex-dispatch.yml/dispatches",
            payload={"ref": "main", "inputs": {"issue_number": str(issue["number"])}})
        print(json.dumps({"retried_issue": issue["number"], "area": key}))
        return  # one retry per sync, avoiding parallel retry races
    print("No safely retryable dispatch found")


if __name__ == "__main__":
    run()
