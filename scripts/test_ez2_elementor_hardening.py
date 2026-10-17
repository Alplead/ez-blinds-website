"""Regression tests for unsafe URI schemes and non-finite Elementor settings."""
import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ez2_elementor_export_check import check

SAMPLE = {"title": "Synthetic", "type": "page", "version": "3.31.1",
          "page_settings": {}, "content": [
              {"id": "abcdef12", "elType": "container", "settings": {}, "elements": []}]}

count = 0
for unsafe in ("javascript:alert(1)", "data:image/svg+xml,<svg></svg>",
               "vbscript:MsgBox(1)", "file:/etc/passwd",
               "mailto:foo@example.com", "  javascript:alert(1)",
               "//untrusted.invalid/img.png", "https://untrusted.invalid"):
    data = copy.deepcopy(SAMPLE)
    data['content'][0]['settings']['background_image'] = {'url': unsafe}
    try:
        check(data)
    except ValueError:
        count += 1
    else:
        raise AssertionError('Unsafe URI accepted: ' + unsafe)

for unsafe in (float('nan'), float('inf'), -float('inf')):
    data = copy.deepcopy(SAMPLE)
    data['content'][0]['settings']['opacity'] = unsafe
    try:
        check(data)
    except ValueError:
        count += 1
    else:
        raise AssertionError('Non-finite number accepted')

with tempfile.TemporaryDirectory() as tmp:
    path = Path(tmp) / 'bad.json'
    path.write_text(json.dumps({**SAMPLE, 'page_settings': {'opacity': float('nan')}}), encoding='utf-8')
    script = Path(__file__).parent / 'ez2_elementor_export_check.py'
    run = subprocess.run([sys.executable, str(script), str(path)], capture_output=True, text=True)
    assert run.returncode == 1 and 'Non-finite JSON number' in run.stderr
    count += 1

assert count == 12, count
print(f'EZ2_ELEMENTOR_HARDENING_PASS cases={count}')
