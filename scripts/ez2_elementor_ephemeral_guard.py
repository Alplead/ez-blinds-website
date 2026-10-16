#!/usr/bin/env python3
"""Static no-network safety contract for isolated Elementor CI."""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
workflow = (root / ".github/workflows/ez2-elementor-ephemeral.yml").read_text()
candidate = json.loads((root / "design/ez2-home-hero-candidate.json").read_text())
checks = [
    workflow.startswith("name: EZ2 Elementor Ephemeral Runtime (No Deployment)"),
    "\non:\n  pull_request:\n" in workflow,
    all(x not in workflow for x in ("pull_request_target:", "workflow_dispatch:", "\n  push:", "\n  schedule:")),
    "permissions:\n  contents: read" in workflow,
    "ref: ${{ github.event.pull_request.head.sha }}" in workflow,
    'test "$(git rev-parse HEAD)" = "${{ github.event.pull_request.head.sha }}"' in workflow,
    'ez2ci${{ github.run_id }}' in workflow,
    'down -v --remove-orphans' in workflow and 'if: always()' in workflow,
    'option update ez2_site_identity ez2-isolated-only' in workflow,
    'http://ez2-review.local' in workflow,
    candidate["version"] == "4.3.4" and "plugin install elementor --version=4.3.4 --activate" in workflow,
    'EZ2_EXPECTED_ELEMENTOR_VERSION=4.3.4' in workflow,
    'ez2_wp_runtime_probe.php' in workflow,
    'READY_FOR_MANUAL_ELEMENTOR_FEATURE_TEST' in workflow,
    '"slideshow_ken_burns_verified": false' in workflow and '"deployment_authorized": false' in workflow,
    all(x not in workflow for x in ("ezbns.com.au", "ez-bns-new-dev.local", "t2-ez-blinds-shutters.local", "secrets.")),
]
if not all(checks):
    raise AssertionError("EZ2 ephemeral CI guard failed checks: " + str([i + 1 for i, x in enumerate(checks) if not x]))
print(f"EZ2_ELEMENTOR_EPHEMERAL_GUARD_PASS cases={len(checks)}")
