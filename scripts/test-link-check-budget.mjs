import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const script = fileURLToPath(new URL('./link-check.mjs', import.meta.url));
const invalidBudgets = ['NaN', 'Infinity', '-1', '0', '1.5', '10001', ' '];

for (const budget of invalidBudgets) {
  const result = spawnSync(process.execPath, [script], {
    encoding: 'utf8',
    timeout: 5000,
    env: {
      ...process.env,
      EZB_BASE_URL: 'http://127.0.0.1:1',
      EZB_LINK_CHECK_MAX: budget
    }
  });
  assert.equal(result.status, 2, 'invalid budget should fail closed: ' + JSON.stringify(budget));
  assert.match(result.stderr, /EZB_LINK_CHECK_MAX must be a finite integer/);
}
console.log('EZB_LINK_CHECK_BUDGET_TEST_PASS cases=7');
