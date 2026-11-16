#!/usr/bin/env python3
"""Close dispatch issues only after an explicitly linked product PR is merged."""
import json
import os
import re
import urllib.request

ORCH = "erikacarvalh0/ec-orchestrator"
ROOT = "https://api.github.com/repos/"
PROJECTS = ("ec-finance", "ec-viagens", "ec-insurance")
MARKER = re.compile(r"(?m)^Backlog-ID: (ec-(?:finance|viagens|insurance):[a-z0-9-]+)$")
DISPATCH = re.compile(r"(?m)^Dispatch: https://github\.com/erikacarvalh0/ec-orchestrator/issues/([1-9][0-9]*)\s*$")
DRY_RUN = os.getenv("DRY_RUN", "true").lower() != "false"


def api(method, url, token, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        **({"Content-Type": "application/json"} if data is not None else {}),
    })
    with urllib.request.urlopen(req, timeout=30) as response:
        return {} if response.status == 204 else json.load(response)


def pages(url, token):
    result = []
    for page in range(1, 21):
        sep = "&" if "?" in url else "?"
        batch = api("GET", f"{url}{sep}per_page=100&page={page}", token)
        result.extend(batch)
        if len(batch) < 100:
            return result
    raise RuntimeError("Pagination limit reached; refusing incomplete evidence")


def main():
    orch_token = os.environ["GITHUB_TOKEN"]
    product_token = os.environ["EC_BACKLOG_READ_TOKEN"]
    issues = pages(ROOT + ORCH + "/issues?state=open", orch_token)
    pending = {}
    for issue in issues:
        if "pull_request" in issue:
            continue
        m = MARKER.search(issue.get("body") or "")
        if not m or issue.get("title") != "[EC-DISPATCH] " + m.group(1):
            continue
        project = m.group(1).split(":", 1)[0]
        pending[issue["number"]] = (issue, m.group(1), project)

    evidence = {number: [] for number in pending}
    for project in PROJECTS:
        prs = pages(ROOT + "erikacarvalh0/" + project + "/pulls?state=closed", product_token)
        for pr in prs:
            if not pr.get("merged_at"):
                continue
            body = pr.get("body") or ""
            linked = DISPATCH.findall(body)
            if len(linked) != 1:
                continue
            number = int(linked[0])
            if number not in pending:
                continue
            issue, backlog_id, expected_project = pending[number]
            if expected_project != project:
                continue
            markers = MARKER.findall(body)
            # Granular PRs require an exact task ID. Legacy PRs may have only
            # an area-level marker but must still explicitly link the issue.
            area_id = re.sub(r"--task-[0-9]{2}$", "", backlog_id)
            if len(markers) != 1 or markers[0] not in (backlog_id, area_id):
                continue
            if markers[0] == area_id and markers[0] != backlog_id and "--task-" not in backlog_id:
                continue
            evidence[number].append(pr)

    report = {"dry_run": DRY_RUN, "closed": [], "eligible": [], "unmatched": []}
    for number, (issue, backlog_id, project) in sorted(pending.items()):
        prs = evidence[number]
        if len(prs) != 1:
            report["unmatched"].append({"issue": number, "matches": len(prs)})
            continue
        pr = prs[0]
        entry = {"issue": number, "backlog_id": backlog_id, "pr": pr["html_url"]}
        report["eligible"].append(entry)
        if DRY_RUN:
            continue
        # A successful close is the sole acceptance signal. Never merge PRs.
        api("PATCH", ROOT + ORCH + f"/issues/{number}", orch_token, {"state": "closed"})
        api("POST", ROOT + ORCH + f"/issues/{number}/comments", orch_token, {
            "body": f"Automatically closed after verified merged product PR: {pr['html_url']}\nBacklog-ID: {backlog_id}"
        })
        report["closed"].append(entry)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
