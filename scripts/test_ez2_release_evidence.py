"""Regression: six exact-head artifacts, five successful workflows, zero deployment."""
import copy
import datetime as dt
from ez2_release_evidence import audit, evaluate, get_head

SHA = "a" * 40
# The offline audit also calls evaluate() with the real clock. A fixed fixture
# expiry eventually makes a valid release fail at midnight in CI.
NOW = dt.datetime.now(dt.timezone.utc)
FUTURE_EXPIRY = (NOW + dt.timedelta(days=7)).isoformat().replace("+00:00", "Z")
PAST_EXPIRY = (NOW - dt.timedelta(days=1)).isoformat().replace("+00:00", "Z")
WORKFLOWS = ("Quality", "Runtime Smoke", "Release Install Smoke",
             "EZ2 Elementor Ephemeral Runtime (No Deployment)",
             "EZ2 Hero Candidate (No Deployment)")
PREFIXES = (
    ("ezb-release-", 103), ("ez2-release-set-evidence-", 103),
    ("ez2-public-content-candidate-", 103),
    ("ez2-synthetic-browser-4.3.4-", 104),
    ("ez2-synthetic-browser-4.3.5-", 104),
    ("ez2-hero-review-", 105),
)


def fixture():
    pr = {"number": 1, "state": "open", "draft": True,
          "base": {"ref": "main"}, "head": {"ref": "feature/vertical-slice-v1",
          "sha": SHA, "repo": {"full_name": "Alplead/ez-blinds-website"}}}
    runs = [{"id": i, "name": name, "head_sha": SHA, "event": "pull_request",
             "head_branch": "feature/vertical-slice-v1",
             "repository": {"full_name": "Alplead/ez-blinds-website"},
             "head_repository": {"full_name": "Alplead/ez-blinds-website"},
             "pull_requests": [{"number": 1,
                                "head": {"ref": "feature/vertical-slice-v1", "sha": SHA},
                                "base": {"ref": "main"}}],
             "status": "completed", "conclusion": "success",
             "created_at": "2026-10-16T00:00:00Z", "run_attempt": 1}
            for i, name in enumerate(WORKFLOWS, 101)]
    artifacts = [{"id": 900 + i, "name": prefix + SHA, "expired": False,
                  "size_in_bytes": 1234, "expires_at": FUTURE_EXPIRY,
                  "workflow_run": {"id": workflow_id, "head_sha": SHA}}
                 for i, (prefix, workflow_id) in enumerate(PREFIXES)]
    return pr, runs, artifacts


pr, runs, arts = fixture()
assert get_head(pr) == SHA
good = evaluate(SHA, runs, arts, NOW)
assert good["status"] == "EXACT_HEAD_CI_ARTIFACT_PASS"
assert good["matrix_complete"] and len(good["artifact_matrix"]) == 6
assert all(good["artifact_matrix"].values())
assert not good["localwp_verified"] and not good["one_click_complete"]
cases = 1

for change in (
    lambda p: p.update(draft=False),
    lambda p: p["head"].update(sha="bad"),
    lambda p: p["base"].update(ref="feature"),
    lambda p: p["head"]["repo"].update(full_name="other/repo"),
):
    p, _, _ = copy.deepcopy(fixture())
    change(p)
    try:
        get_head(p)
    except ValueError:
        cases += 1
    else:
        raise AssertionError("Unexpected PR accepted")

for change in (
    lambda r, a: r.pop(),
    lambda r, a: r[0].update(head_sha="b" * 40),
    lambda r, a: r[0].update(conclusion="failure"),
    lambda r, a: r[0].update(status="in_progress"),
    lambda r, a: r[1].update(event="push"),
    lambda r, a: r[3].update(conclusion="failure"),
    lambda r, a: r[4].update(conclusion="failure"),
    lambda r, a: a[0].update(expired=True),
    lambda r, a: a[0].update(name="other"),
    lambda r, a: a[0]["workflow_run"].update(id=999),
    lambda r, a: a[0].update(size_in_bytes=0),
    lambda r, a: a[0].update(id=0),
    lambda r, a: a[0].update(workflow_run=None),
    lambda r, a: a[0]["workflow_run"].update(head_sha="b" * 40),
    lambda r, a: a[0]["workflow_run"].pop("head_sha"),
    lambda r, a: r[2].update(id=0),
    lambda r, a: a[0].update(expires_at=PAST_EXPIRY),
    lambda r, a: a[3].update(expired=True),
    lambda r, a: a[5].update(expired=True),
):
    _, r, a = copy.deepcopy(fixture())
    change(r, a)
    assert evaluate(SHA, r, a, NOW)["status"] == "BLOCKED_EVIDENCE"
    cases += 1

# A green run for the same SHA is not evidence for PR #1 if its branch,
# repository or pull-request association is wrong or missing.
for mutate in (
    lambda r: r[0].update(head_branch="unrelated-branch"),
    lambda r: r[0]["repository"].update(full_name="other/repo"),
    lambda r: r[0]["head_repository"].update(full_name="other/repo"),
    lambda r: r[0].update(pull_requests=[]),
    lambda r: r[0].update(pull_requests=None),
    lambda r: r[0]["pull_requests"][0].update(number=2),
    lambda r: r[0]["pull_requests"][0].update(number=True),
    lambda r: r[0]["pull_requests"][0]["head"].update(sha="b" * 40),
    lambda r: r[0]["pull_requests"][0]["head"].update(ref="other-branch"),
    lambda r: r[0]["pull_requests"][0]["base"].update(ref="develop"),
    lambda r: r[0].pop("repository"),
    lambda r: r[0].pop("head_repository"),
):
    _, r, a = copy.deepcopy(fixture())
    mutate(r)
    assert evaluate(SHA, r, a, NOW)["status"] == "BLOCKED_EVIDENCE"
    cases += 1

# A run may list several PRs, but one exact matching PR #1 is mandatory.
_, r, a = copy.deepcopy(fixture())
r[0]["pull_requests"].insert(0, {"number": 2, "head": {"ref": "other",
                             "sha": SHA}, "base": {"ref": "main"}})
assert evaluate(SHA, r, a, NOW)["status"] == "EXACT_HEAD_CI_ARTIFACT_PASS"
cases += 1

for index in range(6):
    _, r, a = copy.deepcopy(fixture())
    a.pop(index)
    result = evaluate(SHA, r, a, NOW)
    assert result["status"] == "BLOCKED_EVIDENCE"
    assert not result["matrix_complete"]
    cases += 1

_, r, a = fixture()
r.append({**r[0], "id": 201, "created_at": "2026-10-16T01:00:00Z", "conclusion": "failure"})
assert evaluate(SHA, r, a, NOW)["status"] == "BLOCKED_EVIDENCE"
cases += 1
_, r, a = fixture()
r.append({**r[0], "id": 201, "created_at": "2026-10-16T01:00:00Z"})
assert evaluate(SHA, r, a, NOW)["status"] == "EXACT_HEAD_CI_ARTIFACT_PASS"
cases += 1

p, r, a = fixture()
def fetch(url):
    if url.endswith("/pulls/1"):
        return p
    if "/actions/runs?" in url:
        return {"total_count": len(r), "workflow_runs": r}
    if "/artifacts?" in url:
        run_id = int(url.split("/actions/runs/")[1].split("/")[0])
        selected = [item for item in a if item["workflow_run"]["id"] == run_id]
        return {"total_count": len(selected), "artifacts": selected}
    raise ValueError("Unexpected URL")
assert audit(fetch)["status"] == "EXACT_HEAD_CI_ARTIFACT_PASS"
cases += 1

p, r, a = fixture()
counter = [0]
def changed_fetch(url):
    if url.endswith("/pulls/1"):
        counter[0] += 1
        return p if counter[0] == 1 else {**p, "head": {**p["head"], "sha": "b" * 40}}
    if "/actions/runs?" in url:
        return {"total_count": len(r), "workflow_runs": r}
    if "/artifacts?" in url:
        run_id = int(url.split("/actions/runs/")[1].split("/")[0])
        selected = [item for item in a if item["workflow_run"]["id"] == run_id]
        return {"total_count": len(selected), "artifacts": selected}
    raise ValueError("Unexpected URL")
try:
    audit(changed_fetch)
except ValueError:
    cases += 1
else:
    raise AssertionError("Changing PR head accepted")

print(f"EZ2_RELEASE_EVIDENCE_PASS cases={cases} matrix=6 workflows=5")
