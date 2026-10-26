<?php
/** Synthetic read-only integration tests; no WordPress writes or remote calls. */
require_once __DIR__ . '/../tools/ez2-delivery-agent/includes/ez2-transaction-readiness.php';
$cases = 0;
$check = static function (bool $pass, string $message) use (&$cases): void {
    if (!$pass) throw new RuntimeException('Transaction readiness: ' . $message);
    ++$cases;
};
$sha = str_repeat('a', 40);
$site = [
    'status' => 'READ_ONLY_PREVIEW_READY', 'issues' => [],
    'target_site' => 'ez2-isolated-only', 'mode' => 'read-only',
    'can_apply' => false, 'site_modified' => false,
];
$release = [
    'status' => 'CI_AND_ARTIFACTS_VERIFIED_READ_ONLY', 'issues' => [],
    'source_sha' => $sha, 'workflow_count' => 5, 'artifact_count' => 6,
    'mode' => 'read-only', 'can_apply' => false, 'site_modified' => false,
];
$backup = [
    'status' => 'BACKUP_LOCATION_CANDIDATE_ONLY', 'issues' => [],
    'source_sha' => $sha, 'mode' => 'read-only',
    'backup_created' => false, 'backup_verified' => false,
    'restore_rehearsed' => false, 'site_modified' => false, 'can_apply' => false,
];
$inventory = [
    'status' => 'MANAGED_DIGESTS_OBSERVED', 'issues' => [],
    'mode' => 'read-only', 'target_site' => 'ez2-isolated-only',
    'managed_count' => 1,
    'entries' => [['key' => 'ez2-home', 'post_id' => 7,
        'content_sha256' => str_repeat('c', 64)]],
    'private_content_emitted' => false,
    'installed_release_attested' => false,
    'owner_edit_baseline_trusted' => false,
    'can_apply' => false, 'site_modified' => false,
];
$baseline = [
    'status' => 'AUTHENTICATED_RECEIPT_UNATTESTED', 'issues' => [],
    'receipt_authenticated' => true, 'mode' => 'read-only',
    'baseline_trusted' => false, 'installed_release_attested' => false,
    'can_apply' => false, 'site_modified' => false, 'local_drift_count' => 0,
];
$media = [
    'status' => 'PRIVATE_MEDIA_REFERENCES_VERIFIED_READ_ONLY', 'issues' => [],
    'mode' => 'read-only', 'target_site' => 'ez2-isolated-only',
    'slot_count' => 1, 'verified_count' => 1, 'unresolved_count' => 0,
    'private_content_emitted' => false, 'media_publication_authorized' => false,
    'byte_integrity_verified' => true,
    'can_apply' => false, 'site_modified' => false,
];
$plugin = [
    'status' => 'LOCAL_PLUGIN_MATCH_UNATTESTED', 'issues' => [],
    'checked_count' => 1, 'matching_count' => 1,
    'mode' => 'read-only', 'candidate_lock_attested' => false,
    'can_apply' => false, 'site_modified' => false,
];
$plan = static fn($s = null, $r = null, $b = null, $i = null, $l = null, $m = null, $p = null) =>
    EZ2_Transaction_Readiness::evaluate($s ?? $site, $r ?? $release,
        $b ?? $backup, $i ?? $inventory, $l ?? $baseline, $m ?? $media, $p ?? $plugin);
$ok = $plan();
$check($ok['status'] === 'BLOCKED_TRANSACTION_NOT_IMPLEMENTED', 'always blocked');
$check($ok['isolated_site_observed'] && $ok['exact_head_release_observed']
    && $ok['backup_location_observed'] && $ok['managed_pages_observed']
    && $ok['receipt_integrity_observed'] && $ok['private_media_observed'], 'read-only evidence composed');
$check(!$ok['private_backup_verified'] && !$ok['restore_rehearsed']
    && !$ok['installed_release_attested'] && !$ok['can_apply']
    && !$ok['one_click_complete'] && !$ok['site_modified'], 'never grants write');
$check(in_array('INSTALLED_RELEASE_NOT_ATTESTED', $ok['issues'], true), 'receipt not attestation');
$check(in_array('DEPENDENCY_CONTENT_MEDIA_TRANSACTION_NOT_IMPLEMENTED', $ok['issues'], true), 'no fake migration');
$check(!str_contains(json_encode($ok), 'PRIVATE_SYNTHETIC_TEXT'), 'no private content');
$check($ok['source_sha'] === $sha && $ok['local_changes_observed'] === 0, 'public SHA and count only');
$check($ok['local_plugin_observed'] && !in_array('LOCAL_ELEMENTOR_RUNTIME_NOT_MATCHED', $ok['issues'], true),
    'local Elementor match is observed, not installation authority');
foreach (['status' => 'BLOCKED_PRIVATE_MEDIA_READINESS', 'verified_count' => 0,
          'unresolved_count' => 1, 'can_apply' => true,
          'private_content_emitted' => true, 'byte_integrity_verified' => false] as $key => $value) {
    $bad = $media; $bad[$key] = $value;
    $result = $plan(null, null, null, null, null, $bad);
    $check(!$result['private_media_observed']
        && in_array('PRIVATE_MEDIA_SLOTS_NOT_VERIFIED', $result['issues'], true),
        'private media ' . $key);
}
foreach (['status' => 'BLOCKED', 'target_site' => 'ez-bns-new-dev.local',
          'mode' => 'write', 'can_apply' => true, 'site_modified' => true] as $key => $value) {
    $bad = $site; $bad[$key] = $value;
    $result = $plan($bad);
    $check(!$result['isolated_site_observed']
        && in_array('ISOLATED_SITE_NOT_VERIFIED', $result['issues'], true), 'site ' . $key);
}
foreach (['status' => 'BLOCKED_REMOTE_EVIDENCE', 'source_sha' => str_repeat('z', 40),
          'workflow_count' => 3, 'artifact_count' => 5, 'can_apply' => true] as $key => $value) {
    $bad = $release; $bad[$key] = $value;
    $result = $plan(null, $bad);
    $check(!$result['exact_head_release_observed'] && $result['source_sha'] === null,
        'release ' . $key);
}
foreach (['status' => 'BLOCKED_BACKUP_PREPARATION', 'source_sha' => str_repeat('b', 40),
          'backup_created' => true, 'backup_verified' => true,
          'restore_rehearsed' => true, 'can_apply' => true] as $key => $value) {
    $bad = $backup; $bad[$key] = $value;
    $result = $plan(null, null, $bad);
    $check(!$result['backup_location_observed'], 'backup ' . $key);
}
$bad = $inventory; $bad['entries'][0]['private_media'] = 'secret';
$invalidResult = $plan(null, null, null, $bad);
$check(!$invalidResult['managed_pages_observed']
    && !str_contains(json_encode($invalidResult), 'secret'), 'invalid inventory and private field redacted');
$bad = $inventory; $bad['entries'] = [];
$check(!$plan(null, null, null, $bad)['managed_pages_observed'], 'inconsistent inventory');
$empty = $inventory; $empty['status'] = 'NO_MANAGED_PAGES';
$empty['managed_count'] = 0; $empty['entries'] = [];
$check(!$plan(null, null, null, $empty)['managed_pages_observed'], 'no managed pages');
$drift = $baseline; $drift['status'] = 'AUTHENTICATED_RECEIPT_LOCAL_DRIFT'; $drift['local_drift_count'] = 2;
$result = $plan(null, null, null, null, $drift);
$check($result['receipt_integrity_observed'] && $result['local_changes_observed'] === 2
    && in_array('LOCAL_CONTENT_CHANGES_REQUIRE_REVIEW', $result['issues'], true), 'local drift');
foreach (['receipt_authenticated' => false, 'baseline_trusted' => true,
          'installed_release_attested' => true, 'can_apply' => true,
          'site_modified' => true, 'local_drift_count' => -1] as $key => $value) {
    $bad = $baseline; $bad[$key] = $value;
    $check(!$plan(null, null, null, null, $bad)['receipt_integrity_observed'], 'receipt ' . $key);
}
$bad = $baseline; $bad['status'] = 'AUTHENTICATED_RECEIPT_LOCAL_DRIFT';
$check(!$plan(null, null, null, null, $bad)['receipt_integrity_observed'], 'drift status mismatch');
$bad = $baseline; $bad['local_drift_count'] = 1;
$check(!$plan(null, null, null, null, $bad)['receipt_integrity_observed'], 'drift count mismatch');
$check(!$plan(null, null, null, null, [])['receipt_integrity_observed'], 'missing receipt');
$check(!$plan(null, null, null, null, ['issues' => ['BAD']])['receipt_integrity_observed'], 'blocked receipt');
foreach (['status' => 'BLOCKED_PLUGIN_RUNTIME', 'issues' => ['BAD'],
          'checked_count' => 0, 'matching_count' => 0,
          'mode' => 'write', 'candidate_lock_attested' => true,
          'can_apply' => true, 'site_modified' => true] as $key => $value) {
    $bad = $plugin; $bad[$key] = $value;
    $result = $plan(null, null, null, null, null, null, $bad);
    $check(!$result['local_plugin_observed']
        && in_array('LOCAL_ELEMENTOR_RUNTIME_NOT_MATCHED', $result['issues'], true)
        && !$result['can_apply'] && !$result['site_modified'], 'plugin ' . $key);
}
$missing = $plan(null, null, null, null, null, null, []);
$check(!$missing['local_plugin_observed']
    && in_array('LOCAL_ELEMENTOR_RUNTIME_NOT_MATCHED', $missing['issues'], true), 'missing plugin report');
$check($cases === 53, 'regression case count');
echo "EZ2_TRANSACTION_READINESS_PASS cases={$cases} read_only=true can_apply=false localwp_touched=false\n";
