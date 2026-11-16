#!/usr/bin/env python3
"""Suggest historical PR-to-backlog matches; never infer acceptance or mutate GitHub."""
import json
import re
from pathlib import Path
from difflib import SequenceMatcher
from ec_backlog_sync import REPOS, get, pages, MARKER

STOP = {"feat", "fix", "chore", "test", "docs", "refactor", "add", "update", "implement", "improve", "the", "and", "for", "com", "para", "uma", "das", "dos"}
def tokens(text):
    return {t for t in re.findall(r"[a-z0-9]+", text.casefold()) if len(t) > 2 and t not in STOP}
def match_score(pr, area):
    title = pr.get("title") or ""
    area_name = area["name"]
    a, b = tokens(title), tokens(area_name + " " + area["id"].replace("-", " "))
    overlap = len(a & b) / max(1, len(b))
    similarity = SequenceMatcher(None, title.casefold(), area_name.casefold()).ratio()
    return round(0.8 * overlap + 0.2 * similarity, 3)
def main():
    backlog = json.loads(Path("config/backlog.json").read_text())
    github = json.loads(Path("reports/github-sync.json").read_text())
    projects = {p["repo"]: p for p in backlog["projects"]}
    report = {"generated_at": github["generated_at"], "repositories": {}, "policy": "Suggestions only. Never automatically mark complete or merge."}
    for repo in REPOS:
        areas = projects[repo]["areas"]
        prs = pages("repos/" + repo + "/pulls")
        candidates = []
        for pr in prs:
            markers = MARKER.findall(pr.get("body") or "")
            if markers:
                continue
            ranked = sorted(({"backlog_id": repo.split("/")[1] + ":" + a["id"], "score": match_score(pr, a)} for a in areas), key=lambda x: -x["score"])
            top = ranked[0]
            candidates.append({
                "pr": pr["number"], "url": pr["html_url"], "title": pr.get("title"),
                "state": pr["state"], "merged_at": pr.get("merged_at"),
                "suggested_area": top["backlog_id"] if top["score"] >= 0.30 else None,
                "confidence": top["score"], "needs_manual_classification": top["score"] < 0.65,
                "acceptance_verified": False,
            })
        report["repositories"][repo] = {"unlinked_prs": len(candidates), "candidates": candidates}
    Path("reports").mkdir(exist_ok=True)
    Path("reports/reconciliation.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({repo: len(data["candidates"]) for repo, data in report["repositories"].items()}))
if __name__ == "__main__":
    main()
