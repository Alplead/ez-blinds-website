<?php
/** Offline regression suite for the read-only EZ2 delivery runtime gate. */
define('EZ2_DELIVERY_RUNTIME_GATE_LIBRARY_ONLY', true);
require_once __DIR__ . '/ez2_wp_delivery_runtime_gate.php';
$base = [
    'wp_cli' => true, 'environment' => 'development',
    'expected_host' => 'ez2-review.local', 'expected_elementor_version' => '4.3.4',
    'home' => 'http://ez2-review.local', 'siteurl' => 'http://ez2-review.local',
    'identity' => 'ez2-isolated-only', 'multisite' => false,
    'elementor_active' => true, 'elementor_loaded' => true,
    'elementor_version' => '4.3.4',
    'expected_release_sha' => str_repeat('a', 40),
    'active_theme' => 'ezb-theme', 'ezb_core_active' => true,
    'theme_entrypoint_regular' => true, 'core_entrypoint_regular' => true,
    'elementor_entrypoint_regular' => true, 'maintenance_mode' => false,
    'uploads_dir_regular' => true,
];
$cases = 0;
function assertGate(array $facts, string $status, ?string $issue = null): void {
    global $cases;
    $r = Ez2DeliveryRuntimeGate::evaluate($facts);
    if ($r['status'] !== $status || ($issue !== null && !in_array($issue, $r['issues'], true))) {
        throw new RuntimeException('Unexpected gate result: ' . json_encode($r));
    }
    foreach (['release_bytes_verified','github_checks_verified',
              'localwp_identity_independently_attested','backup_verified',
              'content_conflicts_resolved','private_media_verified','can_apply',
              'site_modified','one_click_complete','deployment_authorized'] as $flag) {
        if ($r[$flag] !== false) throw new RuntimeException('False deployment claim: ' . $flag);
    }
    if ($r['mode'] !== 'read-only' || $r['target_site'] !== 'ez2-isolated-only') {
        throw new RuntimeException('Unsafe target or mode');
    }
    $cases++;
}
assertGate($base, 'READY_FOR_BACKUP_REHEARSAL_ONLY');
$good = $base;
$good['home'] = 'https://ez2-review.local/';
$good['siteurl'] = 'https://ez2-review.local/';
assertGate($good, 'READY_FOR_BACKUP_REHEARSAL_ONLY');
$bad = [
    ['wp_cli', false, 'WP_CLI_REQUIRED'],
    ['environment', 'staging', 'NON_DEVELOPMENT_ENVIRONMENT'],
    ['environment', 'production', 'NON_DEVELOPMENT_ENVIRONMENT'],
    ['expected_host', 'ez-bns-new-dev.local', 'INVALID_ISOLATED_EXPECTED_HOST'],
    ['expected_host', 't2-ez-blinds-shutters.local', 'INVALID_ISOLATED_EXPECTED_HOST'],
    ['expected_host', 'ezbns.com.au', 'INVALID_ISOLATED_EXPECTED_HOST'],
    ['home', 'https://ezbns.com.au', 'UNSAFE_HOME'],
    ['siteurl', 'http://ez-bns-new-dev.local', 'UNSAFE_SITEURL'],
    ['home', 'https://ez2-review.local', 'HOME_SITEURL_SCHEME_MISMATCH'],
    ['siteurl', 'https://ez2-review.local', 'HOME_SITEURL_SCHEME_MISMATCH'],
    ['identity', null, 'MISSING_EZ2_SITE_IDENTITY'],
    ['multisite', true, 'MULTISITE_NOT_SUPPORTED'],
    ['elementor_active', false, 'ELEMENTOR_NOT_ACTIVE'],
    ['elementor_loaded', false, 'ELEMENTOR_NOT_LOADED'],
    ['elementor_version', '4.3.5', 'ELEMENTOR_VERSION_MISMATCH'],
    ['expected_release_sha', null, 'INVALID_EXPECTED_RELEASE_SHA'],
    ['expected_release_sha', str_repeat('f', 39), 'INVALID_EXPECTED_RELEASE_SHA'],
    ['expected_release_sha', str_repeat('F', 40), 'INVALID_EXPECTED_RELEASE_SHA'],
    ['active_theme', 'twentytwentysix', 'UNEXPECTED_ACTIVE_THEME'],
    ['ezb_core_active', false, 'EZB_CORE_NOT_ACTIVE'],
    ['theme_entrypoint_regular', false, 'THEME_ENTRYPOINT_UNSAFE'],
    ['core_entrypoint_regular', false, 'CORE_ENTRYPOINT_UNSAFE'],
    ['elementor_entrypoint_regular', false, 'ELEMENTOR_ENTRYPOINT_UNSAFE'],
    ['maintenance_mode', true, 'MAINTENANCE_MODE_UNKNOWN_OR_ACTIVE'],
    ['uploads_dir_regular', false, 'UPLOADS_DIRECTORY_UNSAFE'],
];
foreach ($bad as [$key, $value, $issue]) {
    $facts = $base;
    $facts[$key] = $value;
    assertGate($facts, 'BLOCKED_DELIVERY_RUNTIME_GATE', $issue);
}
assertGate([], 'BLOCKED_DELIVERY_RUNTIME_GATE', 'INVALID_EXPECTED_RELEASE_SHA');
if ($cases !== 28) throw new RuntimeException('Unexpected test count: ' . $cases);
echo 'EZ2_DELIVERY_RUNTIME_GATE_PASS cases=' . $cases . "\n";
