<?php
/** Synthetic receipt authentication tests. Never writes to WordPress or LP. */
require_once __DIR__ . '/../tools/ez2-delivery-agent/includes/ez2-managed-inventory.php';
require_once __DIR__ . '/../tools/ez2-delivery-agent/includes/ez2-installed-baseline-receipt.php';
$cases = 0;
$check = static function(bool $ok, string $name) use (&$cases): void {
    if (!$ok) throw new RuntimeException('Baseline receipt regression: ' . $name);
    ++$cases;
};
$facts = ['site_status' => 'READ_ONLY_PREVIEW_READY', 'elementor_active' => true,
    'elementor_loaded' => true, 'elementor_version' => '4.3.4'];
$row = ['id' => 12, 'key' => 'ez2-home', 'post_type' => 'page', 'status' => 'draft',
    'title' => 'Synthetic', 'slug' => 'synthetic', 'body' => 'SYNTHETIC_PRIVATE_BODY',
    'elementor_data' => '[{"id":"abc","elType":"container","settings":{},"elements":[]}]',
    'page_settings' => ['hide_title' => 'yes'], 'elementor_version' => '4.3.4'];
$observation = EZ2_Managed_Inventory::evaluate($facts, [$row]);
$secret = str_repeat('s', 40);
$now = 1793030400; // Synthetic clock; independent of CI wall clock.
$host = 'ez2-review.local';
$payload = ['schema_version' => 1, 'target_site' => 'ez2-isolated-only',
    'site_host' => $host, 'source_sha' => str_repeat('a', 40),
    'installed_at_utc' => '2026-10-26T08:00:00Z',
    'baseline_observation' => $observation];
$sign = static function(array $p) use ($secret): array {
    return $p + ['mac_sha256' => hash_hmac('sha256', "EZ2_INSTALLED_BASELINE_V1\n" .
        json_encode($p, JSON_THROW_ON_ERROR | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE), $secret)];
};
$receipt = $sign($payload);
$verify = static fn($r, $o = null, $h = null, $s = null): array =>
    EZ2_Installed_Baseline_Receipt::verify($r, $o ?? $observation, $h ?? $host, $s ?? $secret, $now);
$ok = $verify($receipt);
$check($ok['status'] === 'AUTHENTICATED_RECEIPT_UNATTESTED'
    && $ok['receipt_authenticated'] && !$ok['baseline_trusted']
    && !$ok['installed_release_attested'] && !$ok['can_apply']
    && !$ok['site_modified'] && !$ok['private_content_emitted'], 'authenticated is not installed');
$check($ok['source_sha'] === str_repeat('a', 40) && $ok['local_drift_count'] === 0,
    'exact source and clean observation');
$edited = EZ2_Managed_Inventory::evaluate($facts, [array_replace($row, ['body' => 'owner edited'])]);
$drift = $verify($receipt, $edited);
$check($drift['status'] === 'AUTHENTICATED_RECEIPT_LOCAL_DRIFT'
    && $drift['local_drift_count'] === 1 && !$drift['can_apply'], 'local drift is blocked');
$empty = EZ2_Managed_Inventory::evaluate($facts, []);
$check($verify($receipt, $empty)['local_drift_count'] === 1, 'missing managed page');
$check(!str_contains(json_encode($ok), 'SYNTHETIC_PRIVATE_BODY'), 'no private content in result');
$check($verify(null)['issues'] === ['NO_INSTALLED_BASELINE_RECEIPT'], 'no receipt');
$check($verify($receipt, $observation, 'ez-bns-new-dev.local')['issues'] === ['ISOLATED_SITE_REQUIRED'], 'old dev site');
$check($verify($receipt, $observation, 't2-ez-blinds-shutters.local')['issues'] === ['ISOLATED_SITE_REQUIRED'], 'T2');
$check($verify($receipt, $observation, 'ezbns.com.au')['issues'] === ['ISOLATED_SITE_REQUIRED'], 'production');
$check($verify($receipt, $observation, $host, 'weak')['issues'] === ['LOCAL_RECEIPT_SECRET_UNAVAILABLE'], 'weak secret');
$check(EZ2_Installed_Baseline_Receipt::verify($receipt, null, $host, $secret, $now)['issues'] === ['INVALID_CURRENT_OBSERVATION'], 'missing observation');
$invalid = $observation; $invalid['entries'][0]['raw_content'] = 'secret';
$check($verify($receipt, $invalid)['issues'] === ['INVALID_CURRENT_OBSERVATION'], 'extra observation data');
$bad = $receipt; $bad['private_media'] = 'leak';
$check($verify($bad)['issues'] === ['INVALID_RECEIPT_SCHEMA'], 'extra receipt field');
$bad = $receipt; unset($bad['source_sha']);
$check($verify($bad)['issues'] === ['INVALID_RECEIPT_SCHEMA'], 'missing receipt field');
foreach ([
    ['site_host', 'ez-bns-new-dev.local'],
    ['target_site', 'ez-bns-new-dev.local'],
    ['source_sha', str_repeat('z', 40)],
    ['schema_version', true],
    ['baseline_observation', $invalid],
    ['mac_sha256', 'bad'],
] as [$field, $value]) {
    $bad = $receipt; $bad[$field] = $value;
    $check($verify($bad)['status'] === 'BLOCKED_BASELINE_RECEIPT', 'reject ' . $field);
}
foreach (['2026-02-30T08:00:00Z', '2026-10-26T08:00:00+00:00', 'not-a-date'] as $date) {
    $bad = $sign(array_replace($payload, ['installed_at_utc' => $date]));
    $check($verify($bad)['issues'] === ['INVALID_INSTALL_TIMESTAMP'], 'invalid timestamp');
}
$future = $sign(array_replace($payload, ['installed_at_utc' => '2026-10-28T08:00:00Z']));
$check($verify($future)['issues'] === ['IMPOSSIBLE_INSTALL_TIMESTAMP'], 'future receipt');
$old = $sign(array_replace($payload, ['installed_at_utc' => '2025-12-31T23:59:59Z']));
$check($verify($old)['issues'] === ['IMPOSSIBLE_INSTALL_TIMESTAMP'], 'old receipt');
$bad = $receipt; $bad['source_sha'] = str_repeat('b', 40);
$check($verify($bad)['issues'] === ['RECEIPT_AUTHENTICATION_FAILED'], 'tampered SHA');
$bad = $receipt; $bad['mac_sha256'] = str_repeat('0', 64);
$check($verify($bad)['issues'] === ['RECEIPT_AUTHENTICATION_FAILED'], 'tampered signature');
$bad = $receipt; $bad['baseline_observation'] = $edited;
$check($verify($bad)['issues'] === ['RECEIPT_AUTHENTICATION_FAILED'], 'tampered baseline');
$bad = $sign(array_replace($payload, ['site_host' => 'ez2-another.local']));
$check($verify($bad)['issues'] === ['INVALID_RECEIPT_FIELDS'], 'cross-site replay');
$bad = $sign(array_replace($payload, ['baseline_observation' => $empty]));
$check($verify($bad)['status'] === 'AUTHENTICATED_RECEIPT_LOCAL_DRIFT', 'signed empty baseline detects addition');
$check($cases === 30, 'regression count');
echo "EZ2_BASELINE_RECEIPT_GUARD_PASS cases={$cases} authenticated_not_installed=true can_apply=false\n";
