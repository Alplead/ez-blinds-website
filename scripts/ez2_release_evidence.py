#!/usr/bin/env python3
"""Read-only exact-head CI/artifact evidence for the public EZ2 Draft PR.

No deployment or publication authority is implied by a PASS. Network reads use
GitHub's public REST API; no private data, media, or credentials are printed.
"""
import datetime as dt
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

REPO = "Alplead/ez-blinds-website"
PR = 1
BRANCH = "feature/vertical-slice-v1"
REQUIRED = ("Quality", "Runtime Smoke", "Release Install Smoke")
SHA = re.compile(r"[0-9a-f]{40}\Z")
BASE = f"https://api.github.com/repos/{REPO}"


def fetch_json(url):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "EZ2-readonly-release-auditor",
               "X-GitHub-Api-Version": "2022-11-28"}
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=15) as response:
        return json.load(response)


def get_head(pr):
    if (pr.get("number") != PR or pr.get("state") != "open" or pr.get("draft") is not True
            or pr.get("base", {}).get("ref") != "main"
            or pr.get("head", {}).get("ref") != BRANCH
            or pr.get("head", {}).get("repo", {}).get("full_name") != REPO):
        raise ValueError("Unexpected PR identity, branch or publication state")
    sha = pr["head"].get("sha")
    if not isinstance(sha, str) or not SHA.fullmatch(sha):
        raise ValueError("Invalid exact PR head")
    return sha


def evaluate(sha, runs, artifacts, now=None):
    if not isinstance(sha, str) or not SHA.fullmatch(sha):
        raise ValueError("Invalid exact SHA")
    if not isinstance(runs, list) or not isinstance(artifacts, list):
        raise ValueError("Malformed GitHub evidence")
    chosen = {}
    for run in runs:
        if (not isinstance(run, dict) or run.get("name") not in REQUIRED
                or run.get("head_sha") != sha or run.get("event") != "pull_request"
                or type(run.get("id")) is not int or run["id"] <= 0):
            continue
        name = run["name"]
        if (name not in chosen or (run.get("created_at", ""), run.get("run_attempt", 0), run.get("id", 0))
                > (chosen[name].get("created_at", ""), chosen[name].get("run_attempt", 0), chosen[name].get("id", 0))):
            chosen[name] = run
    results = {}
    for name in REQUIRED:
        run = chosen.get(name)
        results[name] = {"run_id": run.get("id") if run else None,
                         "status": "PASS" if run and run.get("status") == "completed"
                         and run.get("conclusion") == "success" else "NOT_PASS"}
    release = chosen.get("Release Install Smoke")
    now = now or dt.datetime.now(dt.timezone.utc)
    valid = []
    for item in artifacts:
        if not isinstance(item, dict):
            continue
        if item.get("name") != "ezb-release-" + sha or item.get("expired") is not False:
            continue
        if (type(item.get("id")) is not int or item["id"] <= 0
                or type(item.get("size_in_bytes")) is not int or item["size_in_bytes"] <= 0):
            continue
        provenance = item.get("workflow_run")
        # GitHub artifact metadata must bind the ZIP to both the successful
        # release run and the exact commit; a name alone is not evidence.
        if (not release or not isinstance(provenance, dict)
                or provenance.get("id") != release.get("id")
                or provenance.get("head_sha") != sha):
            continue
        try:
            expiry = dt.datetime.fromisoformat(item["expires_at"].replace("Z", "+00:00"))
        except (KeyError, AttributeError, ValueError):
            continue
        if expiry.tzinfo is None or expiry <= now:
            continue
        valid.append((expiry, item))
    artifact = max(valid, key=lambda pair: pair[0])[1] if valid else None
    passed = all(x["status"] == "PASS" for x in results.values()) and artifact is not None
    return {"status": "EXACT_HEAD_CI_ARTIFACT_PASS" if passed else "BLOCKED_EVIDENCE",
            "source_sha": sha, "pr_draft_unmerged_required": True,
            "workflows": results, "artifact": ({"id": artifact["id"],
            "expires_at_utc": artifact["expires_at"], "size_bytes": artifact["size_in_bytes"]}
            if artifact else None), "localwp_verified": False,
            "wordpress_restore_rehearsed": False, "deployment_authorized": False,
            "production_approved": False}


def audit(fetch=fetch_json):
    pr_url = BASE + f"/pulls/{PR}"
    first = get_head(fetch(pr_url))
    query = urllib.parse.urlencode({"head_sha": first, "event": "pull_request", "per_page": 100})
    run_doc = fetch(BASE + "/actions/runs?" + query)
    if not isinstance(run_doc, dict) or run_doc.get("total_count", 0) > 100:
        raise ValueError("Workflow result incomplete or malformed")
    runs = run_doc.get("workflow_runs")
    if not isinstance(runs, list):
        raise ValueError("Missing workflow runs")
    release = [r for r in runs if isinstance(r, dict) and r.get("name") == "Release Install Smoke"
               and r.get("head_sha") == first and r.get("event") == "pull_request"]
    release.sort(key=lambda r: (r.get("created_at", ""), r.get("run_attempt", 0), r.get("id", 0)), reverse=True)
    artifacts = []
    if release:
        data = fetch(BASE + f"/actions/runs/{release[0]['id']}/artifacts?per_page=100")
        if not isinstance(data, dict) or data.get("total_count", 0) > 100:
            raise ValueError("Artifact result incomplete or malformed")
        artifacts = data.get("artifacts")
        if not isinstance(artifacts, list):
            raise ValueError("Missing artifact list")
    result = evaluate(first, runs, artifacts)
    if get_head(fetch(pr_url)) != first:
        raise ValueError("PR head changed during evidence audit; retry fresh")
    return result


if __name__ == "__main__":
    try:
        result = audit()
        print(json.dumps(result, sort_keys=True))
        sys.exit(0 if result["status"] == "EXACT_HEAD_CI_ARTIFACT_PASS" else 2)
    except (ValueError, KeyError, TypeError, urllib.error.URLError, TimeoutError) as exc:
        print("EZ2_RELEASE_EVIDENCE_FAIL: " + str(exc), file=sys.stderr)
        sys.exit(1)
