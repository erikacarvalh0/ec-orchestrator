#!/usr/bin/env python3
"""Queue and dispatch independent product tasks; never merge product PRs."""
import json
import os
import re
import urllib.request
from pathlib import Path

REPO = "erikacarvalh0/ec-orchestrator"
ROOT = "https://api.github.com/repos/"
TOKEN = os.environ["GITHUB_TOKEN"]
AREA_RE = re.compile(r"^ec-(finance|viagens|insurance):[a-z0-9-]+$")


def request(method, url, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {
        "Authorization": "Bearer " + TOKEN,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as response:
        if response.status == 204:
            return {}
        return json.load(response)


def pages(url):
    result = []
    for page in range(1, 11):
        separator = "&" if "?" in url else "?"
        batch = request("GET", f"{url}{separator}per_page=100&page={page}")
        result.extend(batch)
        if len(batch) < 100:
            return result
    raise RuntimeError("Pagination exceeded; refusing incomplete queue view")


def main():
    plan = json.loads(Path("reports/dispatch-plan.json").read_text())
    if plan.get("status") != "plan_only":
        raise RuntimeError("Unsupported dispatch plan status")
    issues = [x for x in pages(ROOT + REPO + "/issues?state=open") if "pull_request" not in x]
    dispatches = {
        (m.group(1), i["number"]): i
        for i in issues
        if (m := re.search(r"(?m)^Backlog-ID: (ec-(?:finance|viagens|insurance):[a-z0-9-]+)$", i.get("body") or ""))
        and i.get("title") == "[EC-DISPATCH] " + m.group(1)
    }
    dispatched = []
    for lane in plan.get("lanes", [])[:2]:
        key = lane["backlog_id"]
        target = lane["repository"]
        if not AREA_RE.fullmatch(key) or target != "erikacarvalh0/" + key.split(":")[0]:
            raise RuntimeError(f"Invalid lane metadata: {key} {target}")
        # Do not create another PR while one is already open for this area.
        prs = pages(ROOT + target + "/pulls?state=open")
        if any(
            key in (p.get("body") or "")
            or (
                p["head"]["ref"].startswith("codex/dispatch-")
                and p["head"]["ref"].endswith("-" + key.split(":")[1])
            )
            for p in prs
        ):
            print(f"Skipping {key}: existing product PR")
            continue
        existing = [i for (area, _), i in dispatches.items() if area == key]
        if existing:
            issue = sorted(existing, key=lambda i: i["number"])[-1]
        else:
            body = (
                f"Backlog-ID: {key}\n\nRepository: {target}\n"
                "Status: queued for autonomous dispatch\n\n"
                "Acceptance checklist:\n"
                "- [ ] Implement a narrowly scoped change\n"
                "- [ ] Run relevant tests\n"
                "- [ ] Open a PR for human review\n"
                "- [ ] Never auto-merge a product PR\n"
            )
            issue = request("POST", ROOT + REPO + "/issues", {
                "title": "[EC-DISPATCH] " + key, "body": body,
            })
        branch = f"codex/dispatch-{issue['number']}-{key.split(':')[1]}"
        # A prior attempt may have published a branch without a PR.
        # Fail closed instead of generating a duplicate.
        branches = pages(ROOT + target + "/branches")
        if any(b["name"] == branch for b in branches):
            print(f"Skipping {key}: existing branch {branch}")
            continue
        request("POST", ROOT + REPO + "/actions/workflows/codex-dispatch.yml/dispatches", {
            "ref": "main", "inputs": {"issue_number": str(issue["number"])}
        })
        dispatched.append({"area": key, "issue": issue["html_url"]})
    print(json.dumps({"dispatched": dispatched}))


if __name__ == "__main__":
    main()
