<?php
/** Offline negative fixtures for the real-WordPress post-install CI integrity gate. */
define('EZ2_CI_POSTINSTALL_LIBRARY_ONLY', true);
require_once __DIR__ . '/ez2_ci_postinstall_integrity.php';
$sha = str_repeat('a', 40);
$good = [
    'wp_cli' => true, 'opt_in' => 'YES_DISPOSABLE_RELEASE_ONLY',
    'home' => 'http://localhost:8081', 'siteurl' => 'http://localhost:8081',
    'environment' => 'staging', 'multisite' => false, 'theme' => 'ezb-theme',
    'core_active' => true, 'elementor_active' => true, 'elementor_loaded' => true,
    'elementor_version' => '4.3.4', 'show_on_front' => 'page',
    'blog_public' => '0', 'front_id' => 17, 'front_title' => 'Home',
    'front_status' => 'publish', 'permalink_structure' => '/%postname%/',
    'candidate_title_count' => 0, 'candidate_marker_count' => 0,
    'synthetic_attachment_count' => 0, 'synthetic_file_count' => 0,
    'expected_sha' => $sha, 'release_sha' => $sha,
];
$cases = 0;
$accept = Ez2CiPostinstallIntegrity::evaluate($good);
if ($accept['status'] !== 'DISPOSABLE_POSTINSTALL_INTEGRITY_PASS'
    || $accept['issues'] || !$accept['read_only'] || $accept['publication']
    || $accept['localwp_touched'] || $accept['one_click_complete'])
    throw new RuntimeException('VALID_DISPOSABLE_POSTINSTALL_REJECTED');
$cases++;
foreach ([
    'wp_cli'=>false, 'opt_in'=>'YES', 'home'=>'https://ezbns.com.au',
    'siteurl'=>'http://ez-bns-new-dev.local', 'environment'=>'production',
    'multisite'=>true, 'theme'=>'twentytwentyfive', 'core_active'=>false,
    'elementor_active'=>false, 'elementor_loaded'=>false,
    'elementor_version'=>'4.3.5', 'show_on_front'=>'posts',
    'blog_public'=>'1', 'front_id'=>0, 'front_title'=>'Owner changed',
    'front_status'=>'draft', 'permalink_structure'=>'',
    'candidate_title_count'=>1, 'candidate_marker_count'=>1,
    'synthetic_attachment_count'=>1, 'synthetic_file_count'=>1,
    'expected_sha'=>str_repeat('b',40), 'release_sha'=>'invalid',
] as $field=>$bad) {
    $facts=$good; $facts[$field]=$bad;
    if (Ez2CiPostinstallIntegrity::evaluate($facts)['status'] !== 'BLOCKED')
        throw new RuntimeException('UNSAFE_POSTINSTALL_ACCEPTED:'.$field);
    $cases++;
}
foreach (['expected_sha','release_sha','candidate_marker_count'] as $field) {
    $facts=$good; unset($facts[$field]);
    if (Ez2CiPostinstallIntegrity::evaluate($facts)['status'] !== 'BLOCKED')
        throw new RuntimeException('MISSING_POSTINSTALL_FIELD_ACCEPTED:'.$field);
    $cases++;
}
echo "EZ2_CI_POSTINSTALL_GUARD_PASS cases=$cases read_only=true localwp_touched=false\n";
