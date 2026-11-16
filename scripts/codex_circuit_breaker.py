#!/usr/bin/env python3
"""Pause dispatch after three consecutive infrastructure or Codex agent failures.

Close the generated breaker issue to acknowledge/reset the circuit.
"""
import datetime as dt
import json
import os
import urllib.request

REPO = "erikacarvalh0/ec-orchestrator"
BASE = "https://api.github.com/repos/" + REPO
TITLE = "[EC-CIRCUIT-BREAKER] Codex infrastructure failures"
LIMIT = 3
INFRA_STEPS = (
    "Check required secrets", "Checkout product repository",
    "Load orchestrator PR description generator",
    "Resolve upstream PR dependency", "Check for existing dispatch PR",
    "Prepare dedicated unprivileged Codex workspace",
    "Ensure npm lockfile", "Bootstrap Codex proxy",
    "Verify and grant agent read access", "Restore workspace ownership",
    # Quota/billing failures are reported by codex-action in this step.
    # Treat repeated agent failures as fail-closed to avoid API-cost retry loops.
    "Inspect conventions and implement with Codex",
)


def api(path, method="GET", payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={
            "Authorization": "Bearer " + os.environ["GITHUB_TOKEN"],
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            **({"Content-Type": "application/json"} if data is not None else {}),
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return {} if response.status == 204 else json.load(response)


def check():
    issues = []
    for page in range(1, 11):
        batch = api(f"/issues?state=all&per_page=100&page={page}")
        issues.extend(batch)
        if len(batch) < 100:
            break
    else:
        raise RuntimeError("Breaker issue pagination incomplete; refusing dispatch")
    breakers = [i for i in issues if "pull_request" not in i and i["title"] == TITLE]
    if any(i["state"] == "open" for i in breakers):
        print("Circuit breaker OPEN: close the breaker issue after fixing infrastructure.")
        return True

    # Closing a breaker issue is an explicit reset: ignore older failures.
    reset = max(
        (dt.datetime.fromisoformat(i["closed_at"].replace("Z", "+00:00"))
         for i in breakers if i["state"] == "closed" and i.get("closed_at")),
        default=dt.datetime.min.replace(tzinfo=dt.timezone.utc),
    )
    runs = api("/actions/workflows/codex-dispatch.yml/runs?per_page=100")["workflow_runs"]
    completed = sorted(
        (r for r in runs if r["status"] == "completed"
         and dt.datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")) > reset),
        key=lambda r: (r["created_at"], r["id"]), reverse=True,
    )
    failures = []
    for run in completed:
        if run["conclusion"] != "failure":
            break
        jobs = api("/actions/runs/" + str(run["id"]) + "/jobs?per_page=100")["jobs"]
        failed_steps = [
            step["name"] for job in jobs for step in job.get("steps", [])
            if step.get("conclusion") == "failure"
        ]
        # Unknown failures are not classified as infrastructure.
        if not failed_steps or not all(
            any(step.startswith(prefix) for prefix in INFRA_STEPS)
            for step in failed_steps
        ):
            break
        failures.append((run["id"], failed_steps))
        if len(failures) >= LIMIT:
            break

    if len(failures) < LIMIT:
        print(f"Circuit breaker CLOSED: {len(failures)} consecutive infrastructure failures.")
        return False

    body = (
        "Automatic dispatch paused after 3 consecutive Codex infrastructure/agent failures (including quota exhaustion).\n\n"
        + "\n".join(
            f"- Run https://github.com/{REPO}/actions/runs/{run_id}: "
            + ", ".join(steps) for run_id, steps in failures
        )
        + "\n\n**Recovery:** fix the root cause, then CLOSE THIS ISSUE to "
          "explicitly reset the breaker. The next scheduled/manual Sync may dispatch again. "
          "Product PRs still require manual merge.\n"
    )
    issue = api("/issues", "POST", {"title": TITLE, "body": body})
    print("Circuit breaker OPEN: " + issue["html_url"])
    return True


if __name__ == "__main__":
    if check():
        print("Dispatch paused; backlog collection may continue.")
