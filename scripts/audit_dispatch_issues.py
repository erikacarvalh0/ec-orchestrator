#!/usr/bin/env python3
"""Read-only dispatch audit: classify issue state using explicit GitHub evidence."""
import datetime as dt
import json
import os
import re
from pathlib import Path
from close_merged_dispatch_issues import ROOT, ORCH, PROJECTS, MARKER, DISPATCH, api, pages

TASK = re.compile(r"--task-[0-9]{2}$")
STATUS = re.compile(r"(?m)^### Dispatch status: (failed|pr_created|retry_queued)")
STALE_HOURS = int(os.getenv("STALE_HOURS", "24"))


def classify(issue, prs, comments, now):
    match = MARKER.search(issue.get("body") or "")
    key = match.group(1) if match else None
    if not key or issue.get("title") != "[EC-DISPATCH] " + key:
        return "invalid_metadata", "Issue title and Backlog-ID do not match", []
    project = key.split(":", 1)[0]
    linked = []
    for pr in prs[project]:
        body = pr.get("body") or ""
        numbers = DISPATCH.findall(body)
        markers = MARKER.findall(body)
        if numbers != [str(issue["number"])] or len(markers) != 1:
            continue
        area = TASK.sub("", key)
        if markers[0] not in (key, area):
            continue
        linked.append(pr)
    if len(linked) > 1:
        return "ambiguous_pr_links", "Multiple product PRs explicitly reference this issue", linked
    if linked:
        pr = linked[0]
        if pr.get("merged_at"):
            return "merged_pr_pending_close", "Merged PR found; closing workflow should reconcile", linked
        if pr["state"] == "open":
            return "pr_open", "Product PR awaits human review or merge", linked
        return "pr_closed_unmerged", "Product PR closed without merge; manual decision required", linked
    states = [m.group(1) for c in comments if (m := STATUS.search(c.get("body") or ""))]
    if states and states[-1] == "failed":
        return "dispatch_failed", "Latest dispatch status is failed", []
    if not TASK.search(key):
        return "legacy_no_pr", "Legacy area-level dispatch; manual reconciliation required", []
    age = now - dt.datetime.fromisoformat(issue["created_at"].replace("Z", "+00:00"))
    if age > dt.timedelta(hours=STALE_HOURS):
        return "stale_no_pr", "No linked PR after configured age; investigate executor", []
    return "awaiting_pr", "Granular task dispatched; no linked PR yet", []


def main():
    orch_token = os.environ["GITHUB_TOKEN"]
    product_token = os.environ["EC_BACKLOG_READ_TOKEN"]
    now = dt.datetime.now(dt.timezone.utc)
    issues = [i for i in pages(ROOT + ORCH + "/issues?state=all", orch_token)
              if "pull_request" not in i and i.get("title", "").startswith("[EC-DISPATCH]")]
    prs = {p: pages(ROOT + "erikacarvalh0/" + p + "/pulls?state=all", product_token)
           for p in PROJECTS}
    rows = []
    for issue in issues:
        comments = pages(ROOT + ORCH + f"/issues/{issue['number']}/comments", orch_token) if issue["state"] == "open" else []
        if issue["state"] == "closed":
            status, reason, linked = "closed", "Dispatch issue already closed", []
        else:
            status, reason, linked = classify(issue, prs, comments, now)
        match = MARKER.search(issue.get("body") or "")
        rows.append({"issue": issue["number"], "url": issue["html_url"],
                     "backlog_id": match.group(1) if match else None,
                     "issue_state": issue["state"], "status": status, "reason": reason,
                     "product_prs": [p["html_url"] for p in linked]})
    backlog = json.loads(Path("config/backlog.json").read_text())
    configured = {p["repo"].split("/")[-1] + ":" + t["id"]
                  for p in backlog["projects"] for a in p["areas"] for t in a["tasks"]}
    seen = {r["backlog_id"] for r in rows if r["backlog_id"]}
    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    report = {
        "generated_at": now.isoformat(), "read_only": True,
        "summary": {"issues": len(rows), "by_status": counts,
                    "configured_tasks": len(configured),
                    "never_dispatched_tasks": len(configured - seen)},
        "issues": sorted(rows, key=lambda r: r["issue"]),
        "undispatched_task_ids": sorted(configured - seen),
        "policy": "Evidence-based classification only; never auto-close, reopen, merge or mark accepted.",
    }
    Path("reports").mkdir(exist_ok=True)
    Path("reports/dispatch-audit.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(report["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
