#!/usr/bin/env python3
"""Fail-closed static contract for two pinned, disposable Elementor Free runtimes.

No WordPress, LocalWP, deployment or customer media writes occur in this guard.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def check_contract(workflow, candidate):
    checks = [
        workflow.startswith("name: EZ2 Elementor Ephemeral Runtime (No Deployment)"),
        "\non:\n  pull_request:\n" in workflow,
        all(x not in workflow for x in ("pull_request_target:", "workflow_dispatch:", "\n  push:", "\n  schedule:")),
        "permissions:\n  contents: read" in workflow,
        "ref: ${{ github.event.pull_request.head.sha }}" in workflow,
        'test "$(git rev-parse HEAD)" = "${{ github.event.pull_request.head.sha }}"' in workflow,
        "matrix:\n        elementor_version: ['4.3.4', '4.3.5']" in workflow,
        "fail-fast: false" in workflow,
        "EZ2_ELEMENTOR_VERSION: ${{ matrix.elementor_version }}" in workflow,
        'ez2ci${{ github.run_id }}v${{ strategy.job-index }}' in workflow,
        "down -v --remove-orphans" in workflow and "if: always()" in workflow,
        "option update ez2_site_identity ez2-isolated-only" in workflow,
        "http://ez2-review.local" in workflow,
        isinstance(candidate, dict) and candidate.get("version") == "4.3.4",
        'plugin install elementor --version="$EZ2_ELEMENTOR_VERSION" --activate' in workflow,
        '-e EZ2_EXPECTED_ELEMENTOR_VERSION="$EZ2_ELEMENTOR_VERSION" --entrypoint' in workflow,
        "ez2_wp_runtime_probe.php" in workflow,
        "READY_FOR_MANUAL_ELEMENTOR_FEATURE_TEST" in workflow,
        '"slideshow_ken_burns_verified": false' in workflow and '"deployment_authorized": false' in workflow,
        all(x not in workflow for x in ("ezbns.com.au", "ez-bns-new-dev.local", "t2-ez-blinds-shutters.local", "secrets.")),
        "EZ2_ELEMENTOR_RUNTIME_VERSION_PASS version=$EZ2_ELEMENTOR_VERSION" in workflow,
    ]
    return [index + 1 for index, ok in enumerate(checks) if not ok], len(checks)

if __name__ == "__main__":
    workflow = (ROOT / ".github/workflows/ez2-elementor-ephemeral.yml").read_text()
    candidate = json.loads((ROOT / "design/ez2-home-hero-candidate.json").read_text())
    failed, count = check_contract(workflow, candidate)
    if failed:
        raise AssertionError("EZ2 ephemeral CI guard failed checks: " + str(failed))
    print(f"EZ2_ELEMENTOR_EPHEMERAL_GUARD_PASS cases={count}")
