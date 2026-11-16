#!/usr/bin/env python3
"""Deterministic dispatch PLAN only. No agent execution, PR creation or merges."""
import json
from pathlib import Path

def main():
    ranking = json.loads(Path("reports/priority.json").read_text())["ranking"]
    if not ranking:
        raise RuntimeError("No ranked projects")
    projects = sorted(ranking, key=lambda p: (p["remaining_pr_estimate"], p["repo"]))
    evidence = json.loads(Path("reports/github-sync.json").read_text())["projects"]
    # Two independent lanes: primary gets closest-to-done; secondary keeps another project moving.
    lanes = []
    for index, project in enumerate(projects[:2], 1):
        candidates = [a for a in project["areas"] if not a["accepted"] and a["remaining_pr_estimate"] > 0]
        candidates.sort(key=lambda a: (a["remaining_pr_estimate"], a["id"]))
        open_prs = evidence[project["repo"]]["open_prs"]
        def blocked(area):
            key = area["id"]
            suffix = "-" + key.split(":", 1)[1]
            return any(
                key in pr["backlog_ids"]
                or ("codex/dispatch-" in pr.get("branch", "") and pr["branch"].endswith(suffix))
                for pr in open_prs
            )
        candidates = [a for a in candidates if not blocked(a)]
        if not candidates:
            continue
        lanes.append({"lane":index,"repository":project["repo"],"backlog_id":candidates[0]["id"],"action":"queue_and_dispatch","requires_manual_pr_merge":True})
    plan = {"version":1,"lanes":lanes,"max_parallel_agents":2,"max_new_tasks_per_cycle":2,"requires_acceptance_review":True,"status":"plan_only","warning":"Estimates remain provisional. Agent execution requires configured API billing and secrets."}
    Path("reports/dispatch-plan.json").write_text(json.dumps(plan, indent=2, ensure_ascii=False)+"\n")
    print(json.dumps(plan))
if __name__=="__main__":
    main()
