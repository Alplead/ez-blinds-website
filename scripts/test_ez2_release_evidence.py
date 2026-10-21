"""Offline checks for exact-head CI and artifact gating."""
import copy
import datetime as dt
from ez2_release_evidence import audit, evaluate, get_head

SHA = "a" * 40
NOW = dt.datetime(2026, 10, 16, tzinfo=dt.timezone.utc)


def fixture():
    pr = {"number": 1, "state": "open", "draft": True,
          "base": {"ref": "main"}, "head": {"ref": "feature/vertical-slice-v1",
          "sha": SHA, "repo": {"full_name": "Alplead/ez-blinds-website"}}}
    runs = [{"id": i, "name": n, "head_sha": SHA, "event": "pull_request",
             "status": "completed", "conclusion": "success", "created_at": "2026-10-16T00:00:00Z",
             "run_attempt": 1} for i, n in enumerate(
                 ("Quality", "Runtime Smoke", "Release Install Smoke"), 101)]
    artifacts = [{"id": 900, "name": "ezb-release-" + SHA, "expired": False,
                  "size_in_bytes": 1234, "expires_at": "2026-10-30T00:00:00Z",
                  "workflow_run": {"id": 103, "head_sha": SHA}}]
    return pr, runs, artifacts


pr, runs, arts = fixture()
assert get_head(pr) == SHA
assert evaluate(SHA, runs, arts, NOW)["status"] == "EXACT_HEAD_CI_ARTIFACT_PASS"
cases = 1

pr_changes = (
    lambda p: p.update(draft=False),
    lambda p: p["head"].update(sha="bad"),
    lambda p: p["base"].update(ref="feature"),
    lambda p: p["head"]["repo"].update(full_name="other/repo"),
)
for change in pr_changes:
    p, r, a = copy.deepcopy(fixture())
    change(p)
    try:
        get_head(p)
    except ValueError:
        cases += 1
    else:
        raise AssertionError("Unexpected PR accepted")

bad_changes = (
    lambda r, a: r.pop(),
    lambda r, a: r[0].update(head_sha="b" * 40),
    lambda r, a: r[0].update(conclusion="failure"),
    lambda r, a: r[0].update(status="in_progress"),
    lambda r, a: r[1].update(event="push"),
    lambda r, a: a[0].update(expired=True),
    lambda r, a: a[0].update(name="other"),
    lambda r, a: a[0]["workflow_run"].update(id=999),
    lambda r, a: a[0].update(size_in_bytes=0),
    lambda r, a: a[0].update(id=0),
    lambda r, a: a[0].update(workflow_run=None),
    lambda r, a: a[0]["workflow_run"].update(head_sha="b" * 40),
    lambda r, a: a[0]["workflow_run"].pop("head_sha"),
    lambda r, a: r[2].update(id=0),
    lambda r, a: a[0].update(expires_at="2026-10-15T00:00:00Z"),
)
for change in bad_changes:
    p, r, a = copy.deepcopy(fixture())
    change(r, a)
    assert evaluate(SHA, r, a, NOW)["status"] == "BLOCKED_EVIDENCE"
    cases += 1

p, r, a = fixture()
r.append({**r[0], "id": 201, "created_at": "2026-10-16T01:00:00Z", "conclusion": "failure"})
assert evaluate(SHA, r, a, NOW)["status"] == "BLOCKED_EVIDENCE"
cases += 1
p, r, a = fixture()
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
        return {"total_count": len(a), "artifacts": a}
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
    return {"total_count": len(a), "artifacts": a}
try:
    audit(changed_fetch)
except ValueError:
    cases += 1
else:
    raise AssertionError("Changing PR head accepted")

assert cases == 24, cases
print(f"EZ2_RELEASE_EVIDENCE_PASS cases={cases}")
