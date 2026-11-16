#!/usr/bin/env python3
"""Produce a conservative priority ranking from canonical backlog and GitHub evidence."""
import json
from pathlib import Path

def main():
    backlog = json.loads(Path("config/backlog.json").read_text())
    github = json.loads(Path("reports/github-sync.json").read_text())
    ranking = []
    for project in backlog["projects"]:
        repo = project["repo"]
        evidence = github["projects"].get(repo)
        if evidence is None:
            raise RuntimeError("Missing GitHub evidence for " + repo)
        areas = []
        for area in project["areas"]:
            key = repo.split("/")[1] + ":" + area["id"]
            urls = evidence["linked_evidence"].get(key, [])
            # Linked PRs and green CI are evidence only, not acceptance.
            accepted = bool(area.get("acceptance_verified", False))
            remaining = 0 if accepted else area["remaining_pr_estimate"]
            areas.append({"id":key,"remaining_pr_estimate":remaining,"accepted":accepted,"evidence_urls":urls})
        remaining = sum(x["remaining_pr_estimate"] for x in areas)
        ranking.append({"repo":repo,"remaining_pr_estimate":remaining,"unlinked_prs":evidence["unlinked_prs"],"areas":areas})
    ranking.sort(key=lambda x:(x["remaining_pr_estimate"],x["repo"]))
    out={"generated_at":github["generated_at"],"ranking":ranking,"priority_repo":ranking[0]["repo"] if ranking else None,"warning":"Provisional estimates; unlinked historical PRs and unverified acceptance may change ranking. Not a task dispatcher."}
    Path("reports/priority.json").write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n")
    print(json.dumps({"priority_repo":out["priority_repo"],"ranking":[{"repo":x["repo"],"remaining_pr_estimate":x["remaining_pr_estimate"]} for x in ranking]}))
if __name__=="__main__":main()
