#!/usr/bin/env python3
"""Select up to two independent dispatch lanes without duplicating queued work."""
import json
import os
import re
import urllib.request
from pathlib import Path

ROOT = "https://api.github.com/repos/erikacarvalh0/ec-orchestrator/issues"
DISPATCH = re.compile(r"(?m)^Backlog-ID: (ec-(?:finance|viagens|insurance):[a-z0-9-]+)$")


def dispatched_task_ids():
    """Never requeue a task ID already dispatched, including closed issues."""
    token = os.environ["GITHUB_TOKEN"]
    blocked = set()
    for page in range(1, 11):
        request = urllib.request.Request(
            f"{ROOT}?state=all&per_page=100&page={page}",
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
    reserved = dispatched_task_ids()
    # Legacy area-level dispatches are not valid task reservations.
    reserved = {key for key in reserved if re.search(r"--task-[0-9]{2}$", key)}
    backlog = json.loads(Path("config/backlog.json").read_text())
    task_areas = {p["repo"]: {a["id"]: a for a in p["areas"]} for p in backlog["projects"]}
    projects = sorted(ranking, key=lambda p: (p["remaining_pr_estimate"], p["repo"]))
    lanes = []
    for project in projects:
        repo = project["repo"]
        open_prs = evidence[repo]["open_prs"]

        candidates = []
        for area in project["areas"]:
            key = area["id"]
            if area["accepted"] or area["remaining_pr_estimate"] <= 0:
                continue
            # One open PR per area avoids conflicting parallel changes, but
            # merged PRs and old dispatch issues do not block the next task.
            if any(
                key in pr["backlog_ids"]
                or (pr.get("branch", "").startswith("codex/dispatch-")
                    and (pr["branch"].endswith("-" + key.split(":", 1)[1])
                         or ("-" + key.split(":", 1)[1] + "--task-") in pr["branch"]))
                for pr in open_prs
            ):
                continue
            definition = task_areas[repo][key.split(":", 1)[1]]
            for task in definition["tasks"]:
                task_key = repo.split("/")[1] + ":" + task["id"]
                # A dispatch issue reserves only its task, never the area.
                if task_key in reserved:
                    continue
                # Do not create another task in an area while a previous task
                # remains open, unless it has an existing product PR.
                # This keeps implementation sequential within each area.
                candidates.append((area, task, task_key))
                break
        if not candidates:
            continue
        area, task, task_key = sorted(
            candidates, key=lambda entry: (entry[0]["remaining_pr_estimate"], entry[2])
        )[0]
        lanes.append({
            "lane": len(lanes) + 1,
            "repository": repo,
            "backlog_id": task_key,
            "area_id": area["id"],
            "task_title": task["title"],
            "task_scope": task["scope"],
            "task_acceptance": task["acceptance"],
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
            "Estimates are provisional. All historical task dispatch issues reserve individual tasks; "
            "open product PRs reserve areas until review and merge."
        ),
    }
    Path("reports/dispatch-plan.json").write_text(
        json.dumps(plan, indent=2, ensure_ascii=False) + "\n"
    )
    print(json.dumps(plan))


if __name__ == "__main__":
    main()
