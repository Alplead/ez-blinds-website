#!/usr/bin/env python3
"""Protect runtime redirect registry checks from grep -q / pipefail SIGPIPE."""
import re
import subprocess
from pathlib import Path

workflow = (Path(__file__).resolve().parents[1] /
            ".github/workflows/runtime-smoke.yml").read_text(encoding="utf-8")
start = workflow.index("      - name: Verify legacy redirect and retirement registry")
end = workflow.index("\n      - name:", start + 12)
block = workflow[start:end]
lines = [line.strip() for line in block.splitlines()]
checks = [line for line in lines if line.startswith("grep -Fxq ") and
          '<<< "$REDIRECT_MAP"' in line]
assert len(checks) == 9, f"Expected 9 safe registry checks, got {len(checks)}"
assert not re.search(r'printf\s+[^\n]*\$REDIRECT_MAP[^\n]*\|\s*grep\s+-[^\n]*q', block), (
    "Piping a large registry to grep -q under pipefail can cause SIGPIPE")
assert any("'COUNTS|verified=7|gone=7'" in line for line in checks)
assert any('"$source|gone|||gone"' in line for line in checks)
# Stress a long registry with an early matching row. The here-string
# must complete without a producer receiving SIGPIPE.
payload = "MATCH|verified_redirect|/projects/\n" + ("unrelated-entry\n" * 40000)
command = ('set -euo pipefail; REDIRECT_MAP="$(cat)"; '
           'grep -Fxq "MATCH|verified_redirect|/projects/" <<< "$REDIRECT_MAP"')
result = subprocess.run(["bash", "-c", command], input=payload, text=True,
                        capture_output=True, timeout=15)
assert result.returncode == 0, result.stderr
print("EZ2_REDIRECT_PIPEFAIL_REGRESSION_PASS cases=11")
