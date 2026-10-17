<?php
/** Synthetic no-network WordPress runtime gate regressions. */
define('EZ2_RUNTIME_PROBE_LIBRARY_ONLY', true);
require_once __DIR__ . '/ez2_wp_runtime_probe.php';
function check_gate(array $facts, string $status, ?string $issue = null): void {
    $r = Ez2RuntimeProbe::evaluate($facts);
    if ($r['status'] !== $status || ($issue !== null && !in_array($issue, $r['issues'], true)))
        throw new RuntimeException('Unexpected result ' . json_encode($r));
    foreach (['site_modified', 'plugin_installed', 'template_imported', 'source_sha_verified',
              'slideshow_ken_burns_verified', 'localwp_visual_qa_verified', 'deployment_authorized'] as $key)
        if ($r[$key] !== false) throw new RuntimeException('False success claim: ' . $key);
}
$base = [
    'expected_host' => 'ez2-review.local', 'expected_elementor_version' => '3.31.1',
    'home' => 'http://ez2-review.local', 'siteurl' => 'http://ez2-review.local',
    'identity' => 'ez2-isolated-only', 'multisite' => false,
    'elementor_active' => true, 'elementor_loaded' => true, 'elementor_version' => '3.31.1',
];
$cases = 0;
check_gate($base, 'READY_FOR_MANUAL_ELEMENTOR_FEATURE_TEST'); $cases++;
$good = $base; $good['home'] = 'https://ez2-review.local/';
check_gate($good, 'READY_FOR_MANUAL_ELEMENTOR_FEATURE_TEST'); $cases++;
$bad = [
    ['expected_host', 'ez-bns-new-dev.local', 'INVALID_ISOLATED_EXPECTED_HOST'],
    ['expected_host', 't2-ez-blinds-shutters.local', 'INVALID_ISOLATED_EXPECTED_HOST'],
    ['home', 'https://ezbns.com.au', 'UNSAFE_HOME'],
    ['siteurl', 'http://ez-bns-new-dev.local', 'UNSAFE_SITEURL'],
    ['home', 'http://ez2-review.local.evil.invalid', 'UNSAFE_HOME'],
    ['home', 'http://ez2-review.local:8080', 'UNSAFE_HOME'],
    ['home', 'http://user@ez2-review.local', 'UNSAFE_HOME'],
    ['home', 'http://ez2-review.local/wp-admin', 'UNSAFE_HOME'],
    ['home', 'http://ez2-review.local?debug=1', 'UNSAFE_HOME'],
    ['home', 'javascript:alert(1)', 'UNSAFE_HOME'],
    ['identity', 'EZ BNS New Dev', 'MISSING_EZ2_SITE_IDENTITY'],
    ['identity', null, 'MISSING_EZ2_SITE_IDENTITY'],
    ['multisite', true, 'MULTISITE_NOT_SUPPORTED'],
    ['elementor_active', false, 'ELEMENTOR_NOT_ACTIVE'],
    ['elementor_loaded', false, 'ELEMENTOR_NOT_LOADED'],
    ['elementor_version', '4.3.4', 'ELEMENTOR_VERSION_MISMATCH'],
    ['expected_elementor_version', 'latest', 'INVALID_EXACT_ELEMENTOR_VERSION'],
    ['expected_elementor_version', null, 'INVALID_EXACT_ELEMENTOR_VERSION'],
];
foreach ($bad as [$field, $value, $issue]) {
    $facts = $base; $facts[$field] = $value;
    check_gate($facts, 'BLOCKED_RUNTIME_GATE', $issue); $cases++;
}
check_gate([], 'BLOCKED_RUNTIME_GATE', 'INVALID_ISOLATED_EXPECTED_HOST'); $cases++;
if ($cases !== 21) throw new RuntimeException('Wrong test count: ' . $cases);
echo "EZ2_WP_RUNTIME_GATE_PASS cases=$cases\n";
