"""Regression coverage: Elementor 4.3.4 baseline and 4.3.5 forward-compatibility CI.

Only static synthetic tampering. This does not run or deploy WordPress.
"""
import json
from pathlib import Path
from ez2_elementor_ephemeral_guard import check_contract, ROOT

workflow = (ROOT / ".github/workflows/ez2-elementor-ephemeral.yml").read_text()
candidate = json.loads((ROOT / "design/ez2-home-hero-candidate.json").read_text())
failed, total = check_contract(workflow, candidate)
assert not failed and total == 25, (failed, total)
cases = 1

def reject(bad_workflow=None, bad_candidate=None):
    global cases
    failures, _ = check_contract(
        workflow if bad_workflow is None else bad_workflow,
        candidate if bad_candidate is None else bad_candidate,
    )
    assert failures, "Unsafe workflow contract accepted"
    cases += 1

reject(workflow.replace("'4.3.4', '4.3.5'", "'4.3.4'"))
reject(workflow.replace("fail-fast: false", "fail-fast: true"))
reject(workflow.replace("EZ2_ELEMENTOR_VERSION: ${{ matrix.elementor_version }}", "EZ2_ELEMENTOR_VERSION: latest"))
reject(workflow.replace('--version="$EZ2_ELEMENTOR_VERSION"', '--version=latest'))
reject(workflow.replace('EZ2_EXPECTED_ELEMENTOR_VERSION="$EZ2_ELEMENTOR_VERSION"', 'EZ2_EXPECTED_ELEMENTOR_VERSION=4.3.4'))
reject(workflow.replace('v${{ strategy.job-index }}', ''))
reject(workflow.replace('down -v --remove-orphans', 'down --remove-orphans'))
reject(workflow.replace('if: always()', 'if: success()'))
reject(workflow.replace('option update ez2_site_identity ez2-isolated-only', 'option update ez2_site_identity production'))
reject(workflow.replace('http://ez2-review.local', 'https://ezbns.com.au'))
reject(workflow.replace('permissions:\n  contents: read', 'permissions:\n  contents: write'))
reject(workflow.replace('echo "EZ2_ELEMENTOR_RUNTIME_VERSION_PASS version=$EZ2_ELEMENTOR_VERSION"', 'echo SKIP'))
reject(bad_candidate={**candidate, "version": "4.3.5"})
reject(workflow.replace('for attempt in 1 2 3; do', 'for attempt in 1 2 100; do'))
reject(workflow.replace('if docker pull "$image"; then', 'if true; then'))
reject(workflow.replace('EZ2_CONTAINER_PULL_UNAVAILABLE image=$image', 'IGNORE_FAILED_PULL'))
reject(workflow.replace('sleep $((attempt * 10))', 'sleep 0'))
assert cases == 18, cases
print(f"EZ2_ELEMENTOR_MATRIX_REGRESSION_PASS cases={cases}")
