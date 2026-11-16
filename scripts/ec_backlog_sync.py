#!/usr/bin/env python3
"""Read-only reconciliation of three GitHub projects. Never merges PRs."""
import json, os, re, urllib.request, urllib.parse, pathlib, datetime
REPOS=["erikacarvalh0/ec-finance","erikacarvalh0/ec-viagens","erikacarvalh0/ec-insurance"]
TOKEN=os.environ["EC_BACKLOG_READ_TOKEN"]
MARKER=re.compile(r"(?im)^\s*Backlog-ID:\s*([\w.-]+:[\w.-]+)\s*$")
def get(path, **params):
    url="https://api.github.com/"+path
    if params: url+="?"+urllib.parse.urlencode(params)
    req=urllib.request.Request(url,headers={"Authorization":"Bearer "+TOKEN,"Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28"})
    with urllib.request.urlopen(req,timeout=30) as r: return json.load(r)
def pages(path):
    out=[]
    for page in range(1,21):
        batch=get(path,per_page=100,page=page,state="all")
        out+=batch
        if len(batch)<100:return out
    raise RuntimeError("Pagination limit reached: "+path)
def run():
    result={"generated_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),"projects":{},"priority":[]}
    for repo in REPOS:
        issues=[x for x in pages("repos/"+repo+"/issues") if "pull_request" not in x]
        prs=pages("repos/"+repo+"/pulls")
        linked={}
        for item in issues+prs:
            for marker in MARKER.findall(item.get("body") or ""):
                linked.setdefault(marker,[]).append(item["html_url"])
        open_prs=[]
        for pr in prs:
            if pr["state"]!="open":continue
            sha=pr["head"]["sha"]
            checks=get("repos/"+repo+"/commits/"+sha+"/check-runs",per_page=100).get("check_runs",[])
            combined=get("repos/"+repo+"/commits/"+sha+"/status")
            statuses=combined.get("statuses",[])
            failure=any(c.get("conclusion") in ("failure","timed_out","cancelled","action_required") for c in checks) or any(s.get("state")=="failure" or s.get("state")=="error" for s in statuses)
            pending=any(c.get("status")!="completed" for c in checks) or any(s.get("state")=="pending" for s in statuses)
            green=bool(checks or statuses) and not failure and not pending and all(c.get("conclusion") in ("success","neutral","skipped") for c in checks) and all(s.get("state")=="success" for s in statuses)
            open_prs.append({"number":pr["number"],"url":pr["html_url"],"sha":sha,"ci":"failing" if failure else "observed_green" if green else "pending_or_unknown","backlog_ids":MARKER.findall(pr.get("body") or "")})
        result["projects"][repo]={"issues":len(issues),"open_prs":open_prs,"linked_evidence":linked,"unlinked_prs":sum(not MARKER.search(p.get("body") or "") for p in prs),"note":"CI green is not proof of acceptance or required branch protection."}
    pathlib.Path("reports").mkdir(exist_ok=True)
    pathlib.Path("reports/github-sync.json").write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n")
    print(json.dumps({"repositories":list(result["projects"]),"report":"reports/github-sync.json"}))
if __name__=="__main__":run()
