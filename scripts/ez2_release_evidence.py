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


# A complete EZ2 A candidate needs more than theme/core.  Each artifact
# belongs to a specific successful exact-head workflow; a filename alone
# cannot prove provenance or readiness for a LocalWP update.
EXTRA = ("EZ2 Elementor Ephemeral Runtime (No Deployment)",
         "EZ2 Hero Candidate (No Deployment)")
ARTIFACT_MATRIX = (
    ("theme_core", "ezb-release-", "Release Install Smoke"),
    ("release_catalog", "ez2-release-set-evidence-", "Release Install Smoke"),
    ("content_candidate", "ez2-public-content-candidate-", "Release Install Smoke"),
    ("elementor_4_3_4", "ez2-synthetic-browser-4.3.4-", EXTRA[0]),
    ("elementor_4_3_5", "ez2-synthetic-browser-4.3.5-", EXTRA[0]),
    ("home_review", "ez2-hero-review-", EXTRA[1]),
)


def belongs_to_target_pr(run, sha):
    """Reject unrelated workflow runs even when they happen to share a commit."""
    if (run.get("head_branch") != BRANCH
            or not isinstance(run.get("repository"), dict)
            or run["repository"].get("full_name") != REPO
            or not isinstance(run.get("head_repository"), dict)
            or run["head_repository"].get("full_name") != REPO):
        return False
    pulls = run.get("pull_requests")
    if not isinstance(pulls, list):
        return False
    for pr in pulls:
        if not isinstance(pr, dict) or type(pr.get("number")) is not int:
            continue
        head, base = pr.get("head"), pr.get("base")
        if (pr["number"] == PR and isinstance(head, dict)
                and isinstance(base, dict) and head.get("sha") == sha
                and head.get("ref") == BRANCH and base.get("ref") == "main"):
            return True
    return False


def choose_runs(sha, runs):
    chosen = {}
    for run in runs:
        if (not isinstance(run, dict) or run.get("name") not in REQUIRED + EXTRA
                or run.get("head_sha") != sha or run.get("event") != "pull_request"
                or type(run.get("id")) is not int or run["id"] <= 0
                or not belongs_to_target_pr(run, sha)):
            continue
        name = run["name"]
        if (name not in chosen or (run.get("created_at", ""), run.get("run_attempt", 0), run["id"])
                > (chosen[name].get("created_at", ""), chosen[name].get("run_attempt", 0), chosen[name]["id"])):
            chosen[name] = run
    return chosen


def evaluate(sha, runs, artifacts, now=None):
    if not isinstance(sha, str) or not SHA.fullmatch(sha):
        raise ValueError("Invalid exact SHA")
    if not isinstance(runs, list) or not isinstance(artifacts, list):
        raise ValueError("Malformed GitHub evidence")
    chosen = choose_runs(sha, runs)
    results = {}
    for name in REQUIRED + EXTRA:
        run = chosen.get(name)
        results[name] = {"run_id": run.get("id") if run else None,
                         "status": "PASS" if run and run.get("status") == "completed"
                         and run.get("conclusion") == "success" else "NOT_PASS"}
    now = now or dt.datetime.now(dt.timezone.utc)
    matrix = {}
    for label, prefix, workflow in ARTIFACT_MATRIX:
        run = chosen.get(workflow)
        valid = []
        for item in artifacts:
            if (not isinstance(item, dict) or item.get("name") != prefix + sha
                    or item.get("expired") is not False
                    or type(item.get("id")) is not int or item["id"] <= 0
                    or type(item.get("size_in_bytes")) is not int or item["size_in_bytes"] <= 0):
                continue
            provenance = item.get("workflow_run")
            if (results[workflow]["status"] != "PASS"
                    or not run or not isinstance(provenance, dict)
                    or provenance.get("id") != run["id"]
                    or provenance.get("head_sha") != sha):
                continue
            try:
                expiry = dt.datetime.fromisoformat(item["expires_at"].replace("Z", "+00:00"))
            except (KeyError, AttributeError, ValueError):
                continue
            if expiry.tzinfo is None or expiry <= now:
                continue
            valid.append((expiry, item))
        item = max(valid, key=lambda pair: pair[0])[1] if valid else None
        matrix[label] = ({"id": item["id"], "run_id": run["id"],
                          "expires_at_utc": item["expires_at"],
                          "size_bytes": item["size_in_bytes"]} if item else None)
    complete = all(result["status"] == "PASS" for result in results.values()) and all(matrix.values())
    return {"status": "EXACT_HEAD_CI_ARTIFACT_PASS" if complete else "BLOCKED_EVIDENCE",
            "source_sha": sha, "pr_draft_unmerged_required": True,
            "workflows": results, "artifact_matrix": matrix,
            "artifact": ({"id": matrix["theme_core"]["id"],
                          "expires_at_utc": matrix["theme_core"]["expires_at_utc"],
                          "size_bytes": matrix["theme_core"]["size_bytes"]}
                         if matrix["theme_core"] else None),
            "matrix_complete": bool(complete),
            "localwp_verified": False, "wordpress_restore_rehearsed": False,
            "one_click_complete": False, "deployment_authorized": False,
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
    chosen = choose_runs(first, runs)
    artifacts = []
    for workflow in ("Release Install Smoke",) + EXTRA:
        run = chosen.get(workflow)
        if run is None:
            continue
        data = fetch(BASE + f"/actions/runs/{run['id']}/artifacts?per_page=100")
        if not isinstance(data, dict) or data.get("total_count", 0) > 100:
            raise ValueError("Artifact result incomplete or malformed")
        items = data.get("artifacts")
        if not isinstance(items, list):
            raise ValueError("Missing artifact list")
        artifacts.extend(items)
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
