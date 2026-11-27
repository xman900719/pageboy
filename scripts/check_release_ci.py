#!/usr/bin/env python3
"""Fail closed unless the latest matching main push workflow and all five jobs succeeded."""
import json
import re
import subprocess
import sys

REPO = "xman900719/pageboy"
REQUIRED = {"api-and-docs", "pg-migration", "web-build", "web-e2e", "web-e2e-webkit"}

def api(path):
    return json.loads(subprocess.check_output(["gh", "api", path], text=True))

def verify(sha, request=api):
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("invalid full SHA")
    prefix = f"repos/{REPO}"
    runs = request(f"{prefix}/actions/runs?head_sha={sha}&branch=main&event=push&per_page=100")["workflow_runs"]
    matches = [r for r in runs if r.get("head_sha") == sha and r.get("head_branch") == "main"
               and r.get("event") == "push" and r.get("path") == ".github/workflows/verify.yml"]
    if not matches:
        raise ValueError("no matching main push workflow")
    run = max(matches, key=lambda r: (r["created_at"], r["id"]))
    if (run.get("status"), run.get("conclusion")) != ("completed", "success"):
        raise ValueError("latest workflow not successful")
    jobs = request(f"{prefix}/actions/runs/{run['id']}/attempts/{run['run_attempt']}/jobs?per_page=100")["jobs"]
    for name in REQUIRED:
        entries = [j for j in jobs if j.get("name") == name]
        if len(entries) != 1 or (entries[0].get("status"), entries[0].get("conclusion")) != ("completed", "success"):
            raise ValueError(f"required check not successful: {name}")
    return run["id"]

if __name__ == "__main__":
    try:
        print(f"RELEASE_CI_OK: run={verify(sys.argv[1])} sha={sys.argv[1]}")
    except (ValueError, KeyError, IndexError, OSError, subprocess.CalledProcessError) as exc:
        sys.exit(f"RELEASE_CI_REFUSED: {exc}")
