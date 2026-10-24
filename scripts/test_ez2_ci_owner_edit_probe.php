<?php
/** Offline regression for the disposable-only Owner-edit conflict probe gate. */
define('EZ2_CI_OWNER_EDIT_PROBE_LIBRARY_ONLY', true);
require_once __DIR__ . '/ez2_ci_owner_edit_probe.php';
$facts = [
    'wp_cli' => true, 'opt_in' => 'YES_SYNTHETIC_ONLY',
    'expected_host' => 'ez2-review.local', 'home' => 'http://ez2-review.local',
    'siteurl' => 'http://ez2-review.local', 'identity' => 'ez2-isolated-only',
    'environment' => 'development', 'multisite' => false,
    'elementor_active' => true, 'elementor_loaded' => true,
    'expected_version' => '4.3.4', 'elementor_version' => '4.3.4',
];
$cases = 0;
foreach (['4.3.4', '4.3.5'] as $version) {
    $f = $facts;
    $f['expected_version'] = $f['elementor_version'] = $version;
    foreach (['prepare', 'verify'] as $phase) {
        if (Ez2CiOwnerEditProbe::gate($f, $phase, 'YES_DISPOSABLE_CONFLICT_ONLY')) {
            throw new RuntimeException('valid gate rejected');
        }
        $cases++;
    }
}
foreach ([
    ['wp_cli', false], ['opt_in', ''], ['expected_host', 'ez-bns-new-dev.local'],
    ['home', 'https://ezbns.com.au'], ['siteurl', 'http://t2-ez-blinds-shutters.local'],
    ['identity', 'production'], ['environment', 'production'], ['multisite', true],
    ['elementor_active', false], ['elementor_loaded', false],
    ['expected_version', 'latest'], ['elementor_version', '4.3.5'],
] as [$key, $value]) {
    $f = $facts;
    $f[$key] = $value;
    if (!Ez2CiOwnerEditProbe::gate($f, 'prepare', 'YES_DISPOSABLE_CONFLICT_ONLY')) {
        throw new RuntimeException('unsafe gate accepted: ' . $key);
    }
    $cases++;
}
foreach (['', 'YES', 'verify-later'] as $optIn) {
    if (!Ez2CiOwnerEditProbe::gate($facts, 'prepare', $optIn)) {
        throw new RuntimeException('unsafe opt-in accepted');
    }
    $cases++;
}
foreach (['', 'run', 'rollback'] as $phase) {
    if (!Ez2CiOwnerEditProbe::gate($facts, $phase, 'YES_DISPOSABLE_CONFLICT_ONLY')) {
        throw new RuntimeException('unsafe phase accepted');
    }
    $cases++;
}
if ($cases !== 22) throw new RuntimeException('case count ' . $cases);
echo "EZ2_CI_OWNER_EDIT_PROBE_GUARD_PASS cases=$cases\n";
