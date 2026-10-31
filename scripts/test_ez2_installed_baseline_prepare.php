<?php
/** Offline synthetic receipt preparation regression. No WordPress writes. */
require_once __DIR__ . '/../tools/ez2-delivery-agent/includes/ez2-managed-inventory.php';
require_once __DIR__ . '/../tools/ez2-delivery-agent/includes/ez2-installed-baseline-prepare.php';
$cases = 0;
$check = static function (bool $pass, string $reason) use (&$cases): void {
    if (!$pass) throw new RuntimeException('Receipt preparation: ' . $reason);
    ++$cases;
};
$row = [
    'id' => 7, 'key' => 'ez2-home', 'post_type' => 'page', 'status' => 'draft',
    'title' => 'Synthetic', 'slug' => 'synthetic', 'body' => 'SYNTHETIC_PRIVATE_TEXT',
    'elementor_data' => '[{"id":"abc","elType":"container","settings":{},"elements":[]}]',
    'page_settings' => ['hide_title' => 'yes'], 'elementor_version' => '4.3.4',
];
$runtime = [
    'site_status' => 'READ_ONLY_PREVIEW_READY', 'elementor_active' => true,
    'elementor_loaded' => true, 'elementor_version' => '4.3.4',
];
$observation = EZ2_Managed_Inventory::evaluate($runtime, [$row]);
$secret = str_repeat('s', 40);
$now = 1793030400;
$facts = [
    'site_status' => 'READ_ONLY_PREVIEW_READY', 'site_host' => 'ez2-review.local',
    'source_sha' => str_repeat('a', 40), 'release_sha' => str_repeat('a', 40),
    'release_verified' => true, 'checkpoint_verified' => true,
    'postinstall_verified' => true, 'rollback_verified' => true,
    'owner_conflicts' => 0, 'media_unresolved' => 0,
    'installed_at_utc' => '2026-10-26T08:00:00Z',
];
$prepare = static fn($f = null, $o = null, $s = null): array =>
    EZ2_Installed_Baseline_Prepare::prepare($f ?? $facts, $o ?? $observation, $s ?? $secret, $now);
$ok = $prepare();
$check($ok['status'] === 'UNATTESTED_RECEIPT_PREPARED' && $ok['issues'] === [], 'candidate prepared');
$check($ok['receipt_authenticated'] && !$ok['installed_release_attested']
    && !$ok['baseline_trusted'] && !$ok['can_apply'] && !$ok['site_modified'], 'no false install claim');
$check(!$ok['private_content_emitted']
    && !str_contains(json_encode($ok, JSON_THROW_ON_ERROR), 'SYNTHETIC_PRIVATE_TEXT'), 'no private content');
$check(array_keys($ok['receipt']) === [
    'schema_version', 'target_site', 'site_host', 'source_sha',
    'installed_at_utc', 'baseline_observation', 'mac_sha256'], 'exact receipt schema');
$verify = EZ2_Installed_Baseline_Receipt::verify(
    $ok['receipt'], $observation, 'ez2-review.local', $secret, $now);
$check($verify['status'] === 'AUTHENTICATED_RECEIPT_UNATTESTED'
    && !$verify['installed_release_attested'] && !$verify['can_apply'], 'receipt roundtrip is untrusted');
$check($ok['receipt']['source_sha'] === str_repeat('a', 40), 'exact source SHA');
$bad = $facts; $bad['unexpected'] = 'secret';
$check($prepare($bad)['issues'] === ['INVALID_TRANSACTION_FACT_SCHEMA'], 'extra transaction fact');
$bad = $facts; unset($bad['rollback_verified']);
$check($prepare($bad)['issues'] === ['INVALID_TRANSACTION_FACT_SCHEMA'], 'missing transaction fact');
foreach (['ezbns.com.au', 't2-ez-blinds-shutters.local', 'ez-bns-new-dev.local',
          'ez2-review.local.evil.com'] as $host) {
    $bad = $facts; $bad['site_host'] = $host;
    $check($prepare($bad)['issues'] === ['ISOLATED_SITE_REQUIRED'], 'forbidden host');
}
$bad = $facts; $bad['site_status'] = 'BLOCKED';
$check($prepare($bad)['issues'] === ['ISOLATED_SITE_REQUIRED'], 'blocked site');
$check($prepare(null, null, 'weak')['issues'] === ['LOCAL_RECEIPT_SECRET_UNAVAILABLE'], 'weak secret');
foreach (['source_sha', 'release_sha'] as $field) {
    $bad = $facts; $bad[$field] = str_repeat('z', 40);
    $check($prepare($bad)['issues'] === ['INVALID_EXACT_RELEASE_SHA'], 'invalid ' . $field);
}
$bad = $facts; $bad['release_sha'] = str_repeat('b', 40);
$check($prepare($bad)['issues'] === ['RELEASE_SHA_MISMATCH'], 'mismatched release');
foreach (['release_verified', 'checkpoint_verified', 'postinstall_verified', 'rollback_verified'] as $field) {
    $bad = $facts; $bad[$field] = false;
    $check($prepare($bad)['issues'] === ['TRANSACTION_PREREQUISITE_MISSING'], 'missing ' . $field);
}
foreach (['owner_conflicts', 'media_unresolved'] as $field) {
    $bad = $facts; $bad[$field] = 1;
    $check($prepare($bad)['issues'] === ['CONTENT_OR_MEDIA_CONFLICT'], 'conflict ' . $field);
}
$bad = $observation; $bad['entries'][0]['raw_media'] = 'secret';
$check($prepare(null, $bad)['issues'] === ['INVALID_MANAGED_BASELINE'], 'private field rejected');
$empty = EZ2_Managed_Inventory::evaluate($runtime, []);
$check($prepare(null, $empty)['issues'] === ['INVALID_MANAGED_BASELINE'], 'empty managed baseline');
foreach (['2026-02-30T08:00:00Z', 'invalid'] as $stamp) {
    $bad = $facts; $bad['installed_at_utc'] = $stamp;
    $check($prepare($bad)['issues'] === ['INVALID_INSTALL_TIMESTAMP'], 'bad timestamp');
}
$bad = $facts; $bad['installed_at_utc'] = '2026-10-28T08:00:00Z';
$check($prepare($bad)['issues'] === ['IMPOSSIBLE_INSTALL_TIMESTAMP'], 'future timestamp');
$bad = $facts; $bad['installed_at_utc'] = '2025-12-31T23:59:59Z';
$check($prepare($bad)['issues'] === ['IMPOSSIBLE_INSTALL_TIMESTAMP'], 'old timestamp');
echo "EZ2_BASELINE_PREPARE_PASS cases={$cases} candidate_only=true can_apply=false localwp_touched=false\n";
