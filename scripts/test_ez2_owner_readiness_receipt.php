<?php
/** Synthetic reports only. No WordPress instance, media, network or site writes. */
require_once __DIR__ . '/../tools/ez2-delivery-agent/includes/ez2-owner-readiness-receipt.php';
$cases = 0;
$check = static function (bool $ok, string $why) use (&$cases): void {
    if (!$ok) throw new RuntimeException('Owner readiness receipt: ' . $why);
    ++$cases;
};
$private = 'PRIVATE_CUSTOMER_PHOTO_SECRET_987';
$site = ['status' => 'READ_ONLY_PREVIEW_READY', 'host' => $private];
$release = ['status' => 'CI_AND_ARTIFACTS_VERIFIED_READ_ONLY',
    'source_sha' => str_repeat('a', 40), 'workflow_count' => 5,
    'artifact_count' => 6, 'raw_token' => $private];
$backup = ['status' => 'BACKUP_LOCATION_CANDIDATE_ONLY', 'path' => $private];
$inventory = ['status' => 'OBSERVED', 'managed_count' => 3, 'page_text' => $private];
$baseline = ['status' => 'AUTHENTICATED_RECEIPT_LOCAL_DRIFT',
    'local_drift_count' => 2, 'salt' => $private];
$media = ['status' => 'PRIVATE_MEDIA_REFERENCES_VERIFIED_READ_ONLY',
    'slot_count' => 4, 'verified_count' => 4, 'url' => $private];
$plugin = ['status' => 'LOCAL_PLUGIN_MATCH_UNATTESTED',
    'matching_count' => 1, 'config' => $private];
$transaction = ['status' => 'BLOCKED_TRANSACTION_NOT_IMPLEMENTED', 'issues' => [$private]];
$build = static fn($s = null, $r = null, $b = null, $i = null, $l = null, $m = null, $p = null, $t = null) =>
    EZ2_Owner_Readiness_Receipt::build($s ?? $site, $r ?? $release, $b ?? $backup,
        $i ?? $inventory, $l ?? $baseline, $m ?? $media, $p ?? $plugin, $t ?? $transaction);
$receipt = $build();
$check($receipt['schema_version'] === 1 && $receipt['kind'] === 'EZ2_ISOLATED_READINESS_RECEIPT',
    'fixed schema');
$check($receipt['target_site'] === 'ez2-isolated-only'
    && $receipt['scope'] === 'owner-review-read-only-not-install-proof', 'fixed scope');
$check($receipt['source_sha'] === str_repeat('a', 40), 'exact SHA when verified');
$check($receipt['workflow_count'] === 5 && $receipt['artifact_count'] === 6, 'CI counts');
$check($receipt['managed_page_count'] === 3 && $receipt['local_drift_count'] === 2,
    'managed counts');
$check($receipt['media_slot_count'] === 4 && $receipt['media_verified_count'] === 4,
    'media counts without identifiers');
$check($receipt['plugin_matching_count'] === 1, 'plugin count');
$check($receipt['transaction_status'] === 'BLOCKED_TRANSACTION_NOT_IMPLEMENTED',
    'truthful transaction status');
$check($receipt['can_apply'] === false && $receipt['site_modified'] === false
    && $receipt['publication_authorized'] === false && $receipt['installed_release_attested'] === false
    && $receipt['localwp_visual_qa_verified'] === false && $receipt['backup_restore_verified'] === false,
    'never assert deployment, restoration or visual QA');
$check(!str_contains(json_encode($receipt), $private), 'no private report content exported');
$badSha = $release; $badSha['source_sha'] = 'not-a-commit';
$check($build(null, $badSha)['source_sha'] === null, 'malformed SHA omitted');
$badStatus = $site; $badStatus['status'] = 'READY</textarea>' . $private;
$check($build($badStatus)['site_status'] === 'UNAVAILABLE', 'unsafe status redacted');
$badCounts = $media; $badCounts['verified_count'] = '4'; $badCounts['slot_count'] = -1;
$check($build(null, null, null, null, null, $badCounts)['media_verified_count'] === null
    && $build(null, null, null, null, null, $badCounts)['media_slot_count'] === null,
    'invalid counts not coerced');
$unverified = $release; $unverified['status'] = 'BLOCKED';
$check($build(null, $unverified)['source_sha'] === null, 'unverified SHA never attested');
$check(count($receipt) === 26, 'strict allowlisted field count');
echo "EZ2_OWNER_READINESS_RECEIPT_PASS cases={$cases} read_only=true private_bytes_exported=false can_apply=false\n";
