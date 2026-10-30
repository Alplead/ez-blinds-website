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
$inventory = ['status' => 'MANAGED_DIGESTS_OBSERVED', 'managed_count' => 3, 'page_text' => $private];
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
$check($receipt['site_status'] === 'READ_ONLY_PREVIEW_READY'
    && $receipt['release_status'] === 'CI_AND_ARTIFACTS_VERIFIED_READ_ONLY'
    && $receipt['backup_status'] === 'BACKUP_LOCATION_CANDIDATE_ONLY'
    && $receipt['baseline_status'] === 'AUTHENTICATED_RECEIPT_LOCAL_DRIFT'
    && $receipt['media_status'] === 'PRIVATE_MEDIA_REFERENCES_VERIFIED_READ_ONLY'
    && $receipt['plugin_status'] === 'LOCAL_PLUGIN_MATCH_UNATTESTED'
    && $receipt['transaction_status'] === 'BLOCKED_TRANSACTION_NOT_IMPLEMENTED',
    'known component statuses preserved');
$invented = $site; $invented['status'] = 'READY';
$check($build($invented)['site_status'] === 'UNAVAILABLE',
    'plausible but unknown status not exported');
// This secret is intentionally valid under the former generic status regex.
$reports = [$site, $release, $backup, $inventory, $baseline, $media, $plugin, $transaction];
$fields = ['site_status', 'release_status', 'backup_status', 'managed_page_count',
    'baseline_status', 'media_status', 'plugin_status', 'transaction_status'];
foreach (array_keys($reports) as $index) {
    $probeReports = $reports;
    $probeReports[$index]['status'] = $private;
    $probe = EZ2_Owner_Readiness_Receipt::build(...$probeReports);
    $check(!str_contains(json_encode($probe), $private)
        && ($index === 3 || $probe[$fields[$index]] === 'UNAVAILABLE'),
        'uppercase private status blocked in component ' . $index);
}
// Blocked or contradictory probes must not export reassuring stale counts.
$blockedRelease = $release; $blockedRelease['status'] = 'BLOCKED_REMOTE_EVIDENCE';
$check($build(null, $blockedRelease)['workflow_count'] === null
    && $build(null, $blockedRelease)['artifact_count'] === null,
    'blocked release counts withheld');
$blockedInventory = $inventory; $blockedInventory['status'] = 'BLOCKED_MANAGED_CONTENT_INVENTORY';
$check($build(null, null, null, $blockedInventory)['managed_page_count'] === null,
    'blocked inventory count withheld');
$emptyInventory = $inventory; $emptyInventory['status'] = 'NO_MANAGED_PAGES';
$emptyInventory['managed_count'] = 0;
$check($build(null, null, null, $emptyInventory)['managed_page_count'] === 0,
    'empty inventory count preserved');
$emptyInventory['managed_count'] = 3;
$check($build(null, null, null, $emptyInventory)['managed_page_count'] === null,
    'contradictory empty inventory count withheld');
$blockedBaseline = $baseline; $blockedBaseline['status'] = 'BLOCKED_BASELINE_RECEIPT';
$check($build(null, null, null, null, $blockedBaseline)['local_drift_count'] === null,
    'blocked baseline drift count withheld');
$badBaseline = $baseline; $badBaseline['status'] = 'AUTHENTICATED_RECEIPT_UNATTESTED';
$check($build(null, null, null, null, $badBaseline)['local_drift_count'] === null,
    'contradictory baseline drift count withheld');
$blockedMedia = $media; $blockedMedia['status'] = 'BLOCKED_PRIVATE_MEDIA_READINESS';
$check($build(null, null, null, null, null, $blockedMedia)['media_slot_count'] === null
    && $build(null, null, null, null, null, $blockedMedia)['media_verified_count'] === null,
    'blocked media counts withheld');
$badMedia = $media; $badMedia['verified_count'] = 5;
$check($build(null, null, null, null, null, $badMedia)['media_slot_count'] === null
    && $build(null, null, null, null, null, $badMedia)['media_verified_count'] === null,
    'impossible media counts withheld');
$blockedPlugin = $plugin; $blockedPlugin['status'] = 'BLOCKED_PLUGIN_RUNTIME';
$check($build(null, null, null, null, null, null, $blockedPlugin)['plugin_matching_count'] === null,
    'blocked plugin count withheld');
// A success status alone must never turn partial or contradictory observations
// into an Owner-facing PASS or a supposedly verified release SHA.
$badWorkflow = $release; $badWorkflow['workflow_count'] = 4;
$probe = $build(null, $badWorkflow);
$check($probe['release_status'] === 'UNAVAILABLE' && $probe['source_sha'] === null
    && $probe['workflow_count'] === null && $probe['artifact_count'] === null,
    'missing workflow suppresses release proof');
$badArtifact = $release; $badArtifact['artifact_count'] = 5;
$check($build(null, $badArtifact)['release_status'] === 'UNAVAILABLE'
    && $build(null, $badArtifact)['source_sha'] === null,
    'missing artifact suppresses release proof');
$badWorkflow = $release; $badWorkflow['workflow_count'] = '5';
$check($build(null, $badWorkflow)['release_status'] === 'UNAVAILABLE',
    'string workflow count is not verified');
$badArtifact = $release; $badArtifact['artifact_count'] = 999;
$check($build(null, $badArtifact)['artifact_count'] === null,
    'inflated artifact count is not verified');
$zeroInventory = $inventory; $zeroInventory['managed_count'] = 0;
$check($build(null, null, null, $zeroInventory)['managed_page_count'] === null
    && $build(null, null, null, $zeroInventory)['managed_page_count'] !== 0,
    'nonempty inventory status cannot claim zero pages');
$hugeInventory = $inventory; $hugeInventory['managed_count'] = 101;
$check($build(null, null, null, $hugeInventory)['managed_page_count'] === null,
    'inventory count respects managed page limit');
$badBaseline = $baseline; $badBaseline['status'] = 'AUTHENTICATED_RECEIPT_UNATTESTED';
$check($build(null, null, null, null, $badBaseline)['baseline_status'] === 'UNAVAILABLE',
    'contradictory baseline status is demoted');
$partialMedia = $media; $partialMedia['verified_count'] = 3;
$probe = $build(null, null, null, null, null, $partialMedia);
$check($probe['media_status'] === 'UNAVAILABLE'
    && $probe['media_slot_count'] === null && $probe['media_verified_count'] === null,
    'partial media cannot be reported fully verified');
$hugeMedia = $media; $hugeMedia['slot_count'] = 101; $hugeMedia['verified_count'] = 101;
$check($build(null, null, null, null, null, $hugeMedia)['media_status'] === 'UNAVAILABLE',
    'media slot count respects local probe limit');
$badPlugin = $plugin; $badPlugin['checked_count'] = 2;
$check($build(null, null, null, null, null, null, $badPlugin)['plugin_status'] === 'UNAVAILABLE',
    'plugin check count must match single pinned dependency');
$badPlugin = $plugin; $badPlugin['matching_count'] = 0;
$check($build(null, null, null, null, null, null, $badPlugin)['plugin_matching_count'] === null,
    'zero plugin matches cannot claim a local match');
$badPlugin = $plugin; unset($badPlugin['checked_count']);
$check($build(null, null, null, null, null, null, $badPlugin)['plugin_status'] === 'UNAVAILABLE',
    'missing plugin check count is not verified');
$check(count($receipt) === 26, 'strict allowlisted field count');
echo "EZ2_OWNER_READINESS_RECEIPT_PASS cases={$cases} read_only=true private_bytes_exported=false can_apply=false\n";
