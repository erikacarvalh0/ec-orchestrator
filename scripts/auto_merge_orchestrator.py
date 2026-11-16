#!/usr/bin/env python3
"""Conservative GitHub auto-merge: orchestrator only; never merge product repositories."""
import fnmatch, json, os, urllib.request, urllib.parse, urllib.error

REPO = "erikacarvalh0/ec-orchestrator"
TOKEN = os.environ["GITHUB_TOKEN"]
API = "https://api.github.com/"
def request(path, method="GET", payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(API + path, data=data, method=method, headers={
        "Authorization": "Bearer " + TOKEN,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)
def all_pages(path):
    result = []
    for page in range(1, 21):
        separator = "&" if "?" in path else "?"
        items = request(path + separator + urllib.parse.urlencode({"per_page": 100, "page": page}))
        result.extend(items)
        if len(items) < 100:
            return result
    raise RuntimeError("Pagination exceeded for " + path)
def eligible(pr, policy):
    if pr["base"]["repo"]["full_name"] != REPO or pr["base"]["ref"] != "main":
        return False, "unexpected base repository/branch"
    if pr.get("draft"):
        return False, "draft"
    if pr.get("mergeable") is not True:
        return False, "mergeability not confirmed"
    if pr.get("mergeable_state") not in ("clean", "has_hooks"):
        return False, "merge state not clean"
    number = pr["number"]
    files = all_pages(f"repos/{REPO}/pulls/{number}/files")
    if not files:
        return False, "no changed files"
    blocked = policy["block_sensitive_paths"]
    for file in files:
        if any(fnmatch.fnmatch(file["filename"], pattern) for pattern in blocked):
            return False, "sensitive file: " + file["filename"]
    sha = pr["head"]["sha"]
    checks = request(f"repos/{REPO}/commits/{sha}/check-runs?per_page=100").get("check_runs", [])
    if len(checks) == 100:
        return False, "check pagination not fully evaluated"
    statuses = request(f"repos/{REPO}/commits/{sha}/status").get("statuses", [])
    if not checks and not statuses:
        return False, "no CI checks observed"
    if any(c["status"] != "completed" or c.get("conclusion") not in ("success", "neutral", "skipped") for c in checks):
        return False, "checks not successful"
    if any(s["state"] != "success" for s in statuses):
        return False, "commit status not successful"
    if pr.get("requested_reviewers") or pr.get("requested_teams"):
        return False, "review pending"
    return True, "eligible"
def main():
    with open("config/merge-policy.json", encoding="utf-8") as f:
        policy = json.load(f)["repositories"][REPO]
    if policy["merge_mode"] != "automatic" or not policy["required_ci"]:
        raise RuntimeError("Automatic merge not permitted by policy")
    for item in all_pages(f"repos/{REPO}/pulls?state=open"):
        pr = request(f"repos/{REPO}/pulls/{item['number']}")
        ok, reason = eligible(pr, policy)
        print(f"PR #{pr['number']}: {reason}", flush=True)
        if not ok:
            continue
        try:
            result = request(f"repos/{REPO}/pulls/{pr['number']}/merge", "PUT", {
                "sha": pr["head"]["sha"], "merge_method": "squash"
            })
            print(f"PR #{pr['number']}: merged={result.get('merged', False)}", flush=True)
        except urllib.error.HTTPError as exc:
            if exc.code in (405, 409, 422):
                print(f"PR #{pr['number']}: merge blocked by GitHub ({exc.code})", flush=True)
            else:
                raise
if __name__ == "__main__":
    main()
