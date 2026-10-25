<?php
/** Offline unit tests for isolated delivery agent (no WordPress required). */
define('ABSPATH', '/synthetic/');
define('EZ2_DELIVERY_AGENT_LIBRARY_ONLY', true);
require_once __DIR__ . '/../tools/ez2-delivery-agent/ez2-delivery-agent.php';
$cases = 0;
$valid = [
    'host' => 'ez2-review.local',
    'home' => 'http://ez2-review.local/',
    'siteurl' => 'http://ez2-review.local/',
    'identity' => 'ez2-isolated-only',
    'environment' => 'development',
    'multisite' => false,
];
$ok = EZ2_Isolated_Delivery_Agent::validate($valid);
if ($ok['status'] !== 'READ_ONLY_PREVIEW_READY' || $ok['can_apply'] !== false
    || $ok['site_modified'] !== false || $ok['one_click_complete'] !== false
    || $ok['source_sha_verified'] !== false || $ok['backup_verified'] !== false) {
    throw new RuntimeException('Safe preview incorrectly authorises installation');
}
$cases++;
function reject_agent(array $base, string $field, $value, string $expected): void {
    global $cases;
    $base[$field] = $value;
    $result = EZ2_Isolated_Delivery_Agent::validate($base);
    if ($result['status'] !== 'BLOCKED' || !in_array($expected, $result['issues'], true)
        || $result['can_apply'] !== false || $result['site_modified'] !== false) {
        throw new RuntimeException('Unsafe site accepted: ' . $field . '=' . json_encode($value));
    }
    $cases++;
}
reject_agent($valid, 'host', 'ez-bns-new-dev.local', 'ISOLATED_HOST_REQUIRED');
reject_agent($valid, 'host', 't2-ez-blinds-shutters.local', 'ISOLATED_HOST_REQUIRED');
reject_agent($valid, 'host', 'ezbns.com.au', 'ISOLATED_HOST_REQUIRED');
reject_agent($valid, 'host', 'ez2-review.local.evil.example', 'ISOLATED_HOST_REQUIRED');
reject_agent($valid, 'host', 'EZ2-REVIEW.local', 'ISOLATED_HOST_REQUIRED');
reject_agent($valid, 'home', 'https://ezbns.com.au/', 'UNSAFE_HOME');
reject_agent($valid, 'siteurl', 'https://ezbns.com.au/', 'UNSAFE_SITEURL');
reject_agent($valid, 'home', 'http://ez2-review.local:8080/', 'UNSAFE_HOME');
reject_agent($valid, 'home', 'http://ez2-review.local/wp-admin', 'UNSAFE_HOME');
reject_agent($valid, 'home', 'http://ez2-review.local/?preview=1', 'UNSAFE_HOME');
reject_agent($valid, 'home', 'http://user@ez2-review.local/', 'UNSAFE_HOME');
reject_agent($valid, 'home', 'http://ez2-review.local/\n', 'UNSAFE_HOME');
reject_agent($valid, 'identity', 'ez-bns-new-dev.local', 'ISOLATED_SITE_IDENTITY_MISSING');
reject_agent($valid, 'identity', null, 'ISOLATED_SITE_IDENTITY_MISSING');
reject_agent($valid, 'environment', 'production', 'DEVELOPMENT_ONLY');
reject_agent($valid, 'environment', 'staging', 'DEVELOPMENT_ONLY');
reject_agent($valid, 'multisite', true, 'MULTISITE_PROHIBITED');
if ($cases !== 18) throw new RuntimeException('Unexpected regression count: ' . $cases);
echo "EZ2_DELIVERY_AGENT_GUARD_PASS cases={$cases} apply_disabled=true\n";
