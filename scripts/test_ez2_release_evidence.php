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
                          'workflow_run' => ['head_sha' => $sha, 'id' => $run['id']]];
    }
}
$cases = 0;
function expect_evidence(array $pr, array $runs, array $sets, bool $pass): void {
    global $cases;
    $out = EZ2_Release_Evidence::evaluate($pr, $runs, $sets);
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
$s = $sets; unset($s['Release Install Smoke'][1]); expect_evidence($pr, $runs, $s, false);
$s = $sets; $s['EZ2 Hero Candidate (No Deployment)'][0]['workflow_run']['id'] = 99; expect_evidence($pr, $runs, $s, false);
$s = $sets; $s['EZ2 Elementor Ephemeral Runtime (No Deployment)'][0]['workflow_run']['head_sha'] = str_repeat('b', 40); expect_evidence($pr, $runs, $s, false);
$r = $runs; $r[] = array_merge($r[0], ['id' => 999, 'conclusion' => 'failure']); expect_evidence($pr, $r, $sets, false);
if ($cases !== 13) throw new RuntimeException('Unexpected case count');
echo "EZ2_RELEASE_EVIDENCE_GUARD_PASS cases={$cases} apply_disabled=true\n";
