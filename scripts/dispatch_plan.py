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
    # Fair rotation across repositories: do not exhaust one product before others.
    # Historical generic task IDs do not consume V1 concrete task slots.
    dispatched_by_repo = {
        p["repo"]: sum(
            p["repo"].split("/")[-1] + ":" + task["id"] in reserved
            for area in task_areas[p["repo"]].values() for task in area["tasks"]
        )
        for p in ranking
    }
    projects = sorted(ranking, key=lambda p: (dispatched_by_repo[p["repo"]], p["repo"]))
    lanes = []
    for project in projects:
        repo = project["repo"]
        candidates = []
        for area in project["areas"]:
            key = area["id"]
            if area["accepted"] or area["remaining_pr_estimate"] <= 0:
                continue
            definition = task_areas[repo][key.split(":", 1)[1]]
            for task in definition["tasks"]:
                # Credentials, real deployments and optional scope are not autonomous work.
                if task.get("status") != "ready":
                    continue
                task_key = repo.split("/")[1] + ":" + task["id"]
                if task_key in reserved:
                    continue
                # Only task IDs reserve work. A separate open PR in the same
                # area does not block another explicitly scoped V1 task.
                candidates.append((area, task, task_key))
                break
        if not candidates:
            continue
        area, task, task_key = sorted(
            candidates, key=lambda entry: ({"P0": 0, "P1": 1, "P2": 2}[entry[1]["priority"]], entry[2])
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
            "only exact concrete task IDs reserve work; external dependencies require manual unblocking."
        ),
    }
    Path("reports/dispatch-plan.json").write_text(
        json.dumps(plan, indent=2, ensure_ascii=False) + "\n"
    )
    print(json.dumps(plan))


if __name__ == "__main__":
    main()
