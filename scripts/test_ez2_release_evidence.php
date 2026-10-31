<?php
/** Synthetic exact-head GitHub evidence guard. No network, WP or Owner site. */
require_once __DIR__ . '/../tools/ez2-delivery-agent/includes/ez2-release-evidence.php';
$sha = str_repeat('a', 40);
$pr = [
    'number' => 1, 'state' => 'open', 'draft' => true, 'merged_at' => null,
    'head' => ['sha' => $sha, 'ref' => 'feature/vertical-slice-v1',
               'repo' => ['full_name' => 'Alplead/ez-blinds-website']],
    'base' => ['ref' => 'main', 'repo' => ['full_name' => 'Alplead/ez-blinds-website']],
];
$names = ['Quality', 'Runtime Smoke', 'Release Install Smoke',
          'EZ2 Elementor Ephemeral Runtime (No Deployment)',
          'EZ2 Hero Candidate (No Deployment)'];
$runs = [];
foreach ($names as $i => $name) {
    $runs[] = ['name' => $name, 'id' => $i + 10, 'head_sha' => $sha,
               'head_branch' => 'feature/vertical-slice-v1',
               'event' => 'pull_request', 'status' => 'completed', 'conclusion' => 'success'];
}
$prefixes = [
    'Release Install Smoke' => ['ezb-release-', 'ez2-release-set-evidence-', 'ez2-public-content-candidate-'],
    'EZ2 Elementor Ephemeral Runtime (No Deployment)' => ['ez2-synthetic-browser-4.3.4-', 'ez2-synthetic-browser-4.3.5-'],
    'EZ2 Hero Candidate (No Deployment)' => ['ez2-hero-review-'],
];
$sets = [];
$n = 100;
foreach ($prefixes as $name => $items) {
    $run = current(array_values(array_filter($runs, fn($x) => $x['name'] === $name)));
    foreach ($items as $prefix) {
        $sets[$name][] = ['name' => $prefix . $sha, 'id' => $n++, 'expired' => false,
                          'size_in_bytes' => 1024, 'expires_at' => '2099-01-01T00:00:00Z',
                          'workflow_run' => ['head_sha' => $sha, 'id' => $run['id']]];
    }
}
$cases = 0;
function expect_evidence(array $pr, array $runs, array $sets, bool $pass): void {
    global $cases;
    $out = EZ2_Release_Evidence::evaluate($pr, $runs, $sets,
        new DateTimeImmutable('2026-10-27T00:00:00Z'));
    if (($out['status'] === 'CI_AND_ARTIFACTS_VERIFIED_READ_ONLY') !== $pass
        || $out['can_apply'] !== false || $out['site_modified'] !== false
        || $out['localwp_installed'] !== false || $out['one_click_complete'] !== false) {
        throw new RuntimeException('Unexpected evidence decision ' . json_encode($out));
    }
    if ($pass && ($out['artifact_count'] !== 6 || $out['workflow_count'] !== 5)) {
        throw new RuntimeException('Evidence count mismatch');
    }
    $cases++;
}
expect_evidence($pr, $runs, $sets, true);
$p = $pr; $p['draft'] = false; expect_evidence($p, $runs, $sets, false);
$p = $pr; $p['head']['ref'] = 'main'; expect_evidence($p, $runs, $sets, false);
$p = $pr; $p['head']['sha'] = str_repeat('f', 40); expect_evidence($p, $runs, $sets, false);
$p = $pr; $p['merged_at'] = '2026-10-25T00:00:00Z'; expect_evidence($p, $runs, $sets, false);
$r = $runs; $r[0]['conclusion'] = 'failure'; expect_evidence($pr, $r, $sets, false);
$r = $runs; $r[1]['event'] = 'push'; expect_evidence($pr, $r, $sets, false);
$r = $runs; $r[2]['head_sha'] = str_repeat('f', 40); expect_evidence($pr, $r, $sets, false);
$s = $sets; $s['Release Install Smoke'][0]['expired'] = true; expect_evidence($pr, $runs, $s, false);
$s = $sets; $s['Release Install Smoke'][0]['size_in_bytes'] = 0; expect_evidence($pr, $runs, $s, false);
$s = $sets; $s['Release Install Smoke'][0]['size_in_bytes'] = '1024'; expect_evidence($pr, $runs, $s, false);
$s = $sets; $s['Release Install Smoke'][0]['size_in_bytes'] = 268435457; expect_evidence($pr, $runs, $s, false);
$s = $sets; $s['Release Install Smoke'][0]['expires_at'] = '2020-01-01T00:00:00Z'; expect_evidence($pr, $runs, $s, false);
$s = $sets; $s['Release Install Smoke'][0]['expires_at'] = '2026-10-27T00:00:00Z'; expect_evidence($pr, $runs, $s, false);
$s = $sets; $s['Release Install Smoke'][0]['expires_at'] = '2099-02-30T00:00:00Z'; expect_evidence($pr, $runs, $s, false);
$s = $sets; unset($s['Release Install Smoke'][0]['expires_at']); expect_evidence($pr, $runs, $s, false);
$s = $sets; unset($s['Release Install Smoke'][1]); expect_evidence($pr, $runs, $s, false);
$s = $sets; $s['EZ2 Hero Candidate (No Deployment)'][0]['workflow_run']['id'] = 99; expect_evidence($pr, $runs, $s, false);
$s = $sets; $s['EZ2 Elementor Ephemeral Runtime (No Deployment)'][0]['workflow_run']['head_sha'] = str_repeat('b', 40); expect_evidence($pr, $runs, $s, false);
$r = $runs; $r[] = array_merge($r[0], ['id' => 999, 'conclusion' => 'failure']); expect_evidence($pr, $r, $sets, false);
/**
 * Offline mutable-PR race tests: no network, no WordPress and no writes.
 * GitHub can change the PR or branch between the first PR read and artifacts.
 */
function check_live_evidence(array $initial, array $runs, array $sets,
                             array $options, bool $expectedPass): void {
    global $cases, $sha;
    $calls = [];
    $reader = function (string $path) use ($initial, $runs, $sets, $options, &$calls, $sha): array {
        $calls[] = $path;
        if (($options['fail_path'] ?? null) === $path) {
            throw new RuntimeException('SIMULATED_GITHUB_UNAVAILABLE');
        }
        if ($path === '/pulls/1') {
            $count = count(array_filter($calls, fn($x) => $x === '/pulls/1'));
            return $count === 1 ? $initial : ($options['final_pr'] ?? $initial);
        }
        if ($path === '/actions/runs?head_sha=' . $sha . '&per_page=100') {
            return ['workflow_runs' => $runs, 'total_count' =>
                array_key_exists('run_total', $options) ? $options['run_total'] : count($runs)];
        }
        if ($path === '/branches/feature/vertical-slice-v1') {
            return ['commit' => ['sha' => $options['branch_sha'] ?? $sha]];
        }
        if (preg_match('~^/actions/runs/([0-9]+)/artifacts\?per_page=100$~D', $path, $match)) {
            foreach ($runs as $run) {
                if ($run['id'] === (int) $match[1]) {
                    $items = $sets[$run['name']] ?? [];
                    if (($options['drop_artifact'] ?? null) === $run['name']) $items = [];
                    return ['artifacts' => $items, 'total_count' =>
                        array_key_exists('artifact_total', $options)
                            ? $options['artifact_total'] : count($items)];
                }
            }
        }
        throw new RuntimeException('UNEXPECTED_TEST_API_PATH');
    };
    $out = EZ2_Release_Evidence::live_with_reader($reader);
    if (($out['status'] === 'CI_AND_ARTIFACTS_VERIFIED_READ_ONLY') !== $expectedPass
        || $out['can_apply'] !== false || $out['one_click_complete'] !== false
        || $out['site_modified'] !== false) {
        throw new RuntimeException('Mutable PR evidence race accepted: ' . json_encode($out));
    }
    if ($expectedPass && (!in_array('/branches/feature/vertical-slice-v1', $calls, true)
        || count(array_filter($calls, fn($x) => $x === '/pulls/1')) !== 2
        || $out['artifact_count'] !== 6)) {
        throw new RuntimeException('Missing final branch/PR consistency check');
    }
    $cases++;
}
check_live_evidence($pr, $runs, $sets, [], true);
// The GitHub head_sha filter is not an event/branch guarantee. A newer
// unrelated run with the same display name must not shadow valid PR CI.
$unrelated = $runs;
$unrelated[] = array_merge($runs[0], ['id' => 900, 'event' => 'push']);
check_live_evidence($pr, $unrelated, $sets, [], true);
$unrelated[] = array_merge($runs[1], ['id' => 901, 'head_branch' => 'main']);
check_live_evidence($pr, $unrelated, $sets, [], true);
$unrelated[] = array_merge($runs[2], ['id' => 902, 'head_sha' => str_repeat('b', 40)]);
check_live_evidence($pr, $unrelated, $sets, [], true);
// A newer *matching* PR failure must still block the release.
$unrelated[] = array_merge($runs[0], ['id' => 903, 'conclusion' => 'failure']);
check_live_evidence($pr, $unrelated, $sets, [], false);

check_live_evidence($pr, $runs, $sets, ['branch_sha' => str_repeat('b', 40)], false);
$p = $pr; $p['head']['sha'] = str_repeat('c', 40);
check_live_evidence($pr, $runs, $sets, ['final_pr' => $p], false);
$p = $pr; $p['draft'] = false;
check_live_evidence($pr, $runs, $sets, ['final_pr' => $p], false);
check_live_evidence($pr, $runs, $sets, ['drop_artifact' => 'Release Install Smoke'], false);
check_live_evidence($pr, $runs, $sets, ['fail_path' => '/pulls/1'], false);
check_live_evidence($pr, $runs, $sets, ['run_total' => 101], false);
// A truncated or uncounted first page must never become a release PASS.
check_live_evidence($pr, $runs, $sets, ['run_total' => count($runs) - 1], false);
check_live_evidence($pr, $runs, $sets, ['run_total' => null], false);
check_live_evidence($pr, $runs, $sets, ['artifact_total' => 99], false);
check_live_evidence($pr, $runs, $sets, ['artifact_total' => null], false);
$p = $pr; $p['base']['ref'] = 'release';
check_live_evidence($pr, $runs, $sets, ['final_pr' => $p], false);
check_live_evidence($pr, $runs, $sets, ['final_pr' => []], false);

if ($cases !== 37) throw new RuntimeException('Unexpected case count');
echo "EZ2_RELEASE_EVIDENCE_GUARD_PASS cases={$cases} apply_disabled=true\n";
