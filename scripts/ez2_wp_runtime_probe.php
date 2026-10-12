<?php
/** Read-only EZ2 isolated WordPress + Elementor runtime gate.
 * WP-CLI: EZ2_EXPECTED_HOST=ez2-review.local EZ2_EXPECTED_ELEMENTOR_VERSION=3.31.1 wp eval-file scripts/ez2_wp_runtime_probe.php
 * Never installs plugins, imports content, modifies options, or verifies visual effects.
 */
final class Ez2RuntimeProbe {
    private const IDENTITY = 'ez2-isolated-only';
    private const ELEMENTOR = 'elementor/elementor.php';
    public static function evaluate(array $facts): array {
        $issues = [];
        $host = $facts['expected_host'] ?? null;
        $version = $facts['expected_elementor_version'] ?? null;
        if (!is_string($host) || !preg_match('/^ez2(?:-[a-z0-9]+)*\\.local$/D', $host)) $issues[] = 'INVALID_ISOLATED_EXPECTED_HOST';
        if (!is_string($version) || !preg_match('/^[1-9][0-9]{0,2}\\.[0-9]{1,3}\\.[0-9]{1,3}$/D', $version)) $issues[] = 'INVALID_EXACT_ELEMENTOR_VERSION';
        foreach (['home', 'siteurl'] as $key) {
            if (!is_string($facts[$key] ?? null) || !self::safeUrl($facts[$key], $host)) $issues[] = 'UNSAFE_' . strtoupper($key);
        }
        if (($facts['identity'] ?? null) !== self::IDENTITY) $issues[] = 'MISSING_EZ2_SITE_IDENTITY';
        if (($facts['multisite'] ?? null) !== false) $issues[] = 'MULTISITE_NOT_SUPPORTED';
        if (($facts['elementor_active'] ?? null) !== true) $issues[] = 'ELEMENTOR_NOT_ACTIVE';
        if (($facts['elementor_loaded'] ?? null) !== true) $issues[] = 'ELEMENTOR_NOT_LOADED';
        if (!is_string($facts['elementor_version'] ?? null) || $facts['elementor_version'] !== $version) $issues[] = 'ELEMENTOR_VERSION_MISMATCH';
        return [
            'status' => $issues ? 'BLOCKED_RUNTIME_GATE' : 'READY_FOR_MANUAL_ELEMENTOR_FEATURE_TEST',
            'mode' => 'read-only', 'target_site' => self::IDENTITY, 'expected_host' => is_string($host) ? $host : null,
            'expected_elementor_version' => is_string($version) ? $version : null, 'issues' => $issues,
            'site_modified' => false, 'plugin_installed' => false, 'template_imported' => false,
            'source_sha_verified' => false, 'slideshow_ken_burns_verified' => false,
            'localwp_visual_qa_verified' => false, 'deployment_authorized' => false,
        ];
    }
    private static function safeUrl(string $url, $host): bool {
        if (!is_string($host) || !preg_match('/^ez2(?:-[a-z0-9]+)*\\.local$/D', $host)) return false;
        if (preg_match('/[\\x00-\\x20\\\\\\\\]/', $url)) return false;
        $p = parse_url($url);
        if (!is_array($p) || !in_array($p['scheme'] ?? null, ['http', 'https'], true)
            || ($p['host'] ?? null) !== $host || isset($p['user']) || isset($p['pass'])
            || isset($p['port']) || isset($p['query']) || isset($p['fragment'])) return false;
        return !isset($p['path']) || $p['path'] === '' || $p['path'] === '/';
    }
    public static function collect(): array {
        if (!function_exists('get_option') || !function_exists('is_multisite')
            || !function_exists('did_action') || !defined('ABSPATH')) throw new RuntimeException('WORDPRESS_NOT_LOADED');
        if (!function_exists('is_plugin_active')) {
            $api = ABSPATH . 'wp-admin/includes/plugin.php';
            if (!is_file($api)) throw new RuntimeException('WORDPRESS_PLUGIN_API_MISSING');
            require_once $api;
        }
        return [
            'expected_host' => getenv('EZ2_EXPECTED_HOST') ?: null,
            'expected_elementor_version' => getenv('EZ2_EXPECTED_ELEMENTOR_VERSION') ?: null,
            'home' => get_option('home'), 'siteurl' => get_option('siteurl'),
            'identity' => get_option('ez2_site_identity'), 'multisite' => is_multisite(),
            'elementor_active' => is_plugin_active(self::ELEMENTOR),
            'elementor_loaded' => did_action('elementor/loaded') > 0,
            'elementor_version' => defined('ELEMENTOR_VERSION') ? ELEMENTOR_VERSION : null,
        ];
    }
}
if (!defined('EZ2_RUNTIME_PROBE_LIBRARY_ONLY')) {
    try {
        $result = Ez2RuntimeProbe::evaluate(Ez2RuntimeProbe::collect());
        echo json_encode($result, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR) . "\n";
        if ($result['status'] !== 'READY_FOR_MANUAL_ELEMENTOR_FEATURE_TEST') exit(2);
    } catch (Throwable $e) {
        fwrite(STDERR, "EZ2_RUNTIME_GATE_FAIL: " . $e->getMessage() . "\n");
        exit(1);
    }
}
