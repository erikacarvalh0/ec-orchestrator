#!/usr/bin/env python3
"""Select up to two independent dispatch lanes without duplicating queued work."""
import json
import os
import re
import urllib.request
from pathlib import Path

ROOT = "https://api.github.com/repos/erikacarvalh0/ec-orchestrator/issues"
DISPATCH = re.compile(r"(?m)^Backlog-ID: (ec-(?:finance|viagens|insurance):[a-z0-9-]+)$")


def open_dispatch_areas():
    """Existing open issues reserve their areas until reviewed or closed."""
    token = os.environ["GITHUB_TOKEN"]
    blocked = set()
    for page in range(1, 11):
        request = urllib.request.Request(
            f"{ROOT}?state=open&per_page=100&page={page}",
            headers={
                "Authorization": "Bearer " + token,
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            batch = json.load(response)
        for issue in batch:
            if "pull_request" in issue:
                continue
            match = DISPATCH.search(issue.get("body") or "")
            if match and issue.get("title") == "[EC-DISPATCH] " + match.group(1):
                blocked.add(match.group(1))
        if len(batch) < 100:
            return blocked
    raise RuntimeError("Issue pagination limit reached; refusing incomplete dispatch view")


def main():
    ranking = json.loads(Path("reports/priority.json").read_text())["ranking"]
    evidence = json.loads(Path("reports/github-sync.json").read_text())["projects"]
    if not ranking:
        raise RuntimeError("No ranked projects")
    reserved = open_dispatch_areas()
    projects = sorted(ranking, key=lambda p: (p["remaining_pr_estimate"], p["repo"]))
    lanes = []
    for project in projects:
        repo = project["repo"]
        open_prs = evidence[repo]["open_prs"]

        def available(area):
            key = area["id"]
            suffix = "-" + key.split(":", 1)[1]
            return (
                not area["accepted"]
                and area["remaining_pr_estimate"] > 0
                and key not in reserved
                and not any(
                    key in pr["backlog_ids"]
                    or (pr.get("branch", "").startswith("codex/dispatch-")
                        and pr["branch"].endswith(suffix))
                    for pr in open_prs
                )
            )

        candidates = sorted(
            (area for area in project["areas"] if available(area)),
            key=lambda area: (area["remaining_pr_estimate"], area["id"]),
        )
        if not candidates:
            continue
        lanes.append({
            "lane": len(lanes) + 1,
            "repository": repo,
            "backlog_id": candidates[0]["id"],
            "action": "queue_and_dispatch",
            "requires_manual_pr_merge": True,
        })
        if len(lanes) == 2:
            break
    plan = {
        "version": 1,
        "lanes": lanes,
        "max_parallel_agents": 2,
        "max_new_tasks_per_cycle": 2,
        "requires_acceptance_review": True,
        "status": "plan_only",
        "warning": (
            "Estimates are provisional. Open dispatch issues reserve their areas; "
            "review and close them before dispatching more work in that area."
        ),
    }
    Path("reports/dispatch-plan.json").write_text(
        json.dumps(plan, indent=2, ensure_ascii=False) + "\n"
    )
    print(json.dumps(plan))


if __name__ == "__main__":
    main()
