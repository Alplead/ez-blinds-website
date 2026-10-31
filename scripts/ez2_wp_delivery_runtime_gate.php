<?php
/**
 * Read-only, fail-closed WordPress preflight for a future isolated EZ2 updater.
 * Bootstrap mode recognises clean isolated WordPress before EZB/Elementor installation;\n * upgrade mode requires all three components. Neither mode installs, downloads,\n * backs up, changes options or authorises deployment.
 * Run with WP-CLI only after the Owner separately authorises an isolated EZ2 site.
 */
if (!defined('EZ2_RUNTIME_PROBE_LIBRARY_ONLY')) {
    define('EZ2_RUNTIME_PROBE_LIBRARY_ONLY', true);
}
require_once __DIR__ . '/ez2_wp_runtime_probe.php';

final class Ez2DeliveryRuntimeGate {
    public static function evaluate(array $facts): array {
        $mode = array_key_exists('delivery_mode', $facts) ? $facts['delivery_mode'] : 'upgrade';
        $base = Ez2RuntimeProbe::evaluate($facts);
        $issues = $base['issues'];
        $sha = $facts['expected_release_sha'] ?? null;
        if (!is_string($sha) || !preg_match('/^[0-9a-f]{40}$/D', $sha)) {
            $issues[] = 'INVALID_EXPECTED_RELEASE_SHA';
        }
        if (!in_array($mode, ['bootstrap', 'upgrade'], true)) {
            $issues[] = 'INVALID_DELIVERY_MODE';
        } elseif ($mode === 'bootstrap') {
            // Missing Elementor is expected on a clean first install; all
            // site identity, exact-version and environment checks still apply.
            $issues = array_values(array_diff($issues, [
                'ELEMENTOR_NOT_ACTIVE', 'ELEMENTOR_NOT_LOADED', 'ELEMENTOR_VERSION_MISMATCH'
            ]));
            foreach ([
                'ezb_core_active' => [false, 'CORE_ALREADY_ACTIVE'],
                'elementor_active' => [false, 'ELEMENTOR_ALREADY_ACTIVE'],
                'elementor_loaded' => [false, 'ELEMENTOR_ALREADY_LOADED'],
                'theme_dir_exists' => [false, 'THEME_ALREADY_PRESENT'],
                'core_dir_exists' => [false, 'CORE_ALREADY_PRESENT'],
                'elementor_dir_exists' => [false, 'ELEMENTOR_ALREADY_PRESENT'],
                'theme_entrypoint_regular' => [false, 'BOOTSTRAP_THEME_ENTRYPOINT_PRESENT'],
                'core_entrypoint_regular' => [false, 'BOOTSTRAP_CORE_ENTRYPOINT_PRESENT'],
                'elementor_entrypoint_regular' => [false, 'BOOTSTRAP_ELEMENTOR_ENTRYPOINT_PRESENT'],
            ] as $key => [$expected, $issue]) {
                if (($facts[$key] ?? null) !== $expected) $issues[] = $issue;
            }
            if (!is_string($facts['active_theme'] ?? null)
                || $facts['active_theme'] === '' || $facts['active_theme'] === 'ezb-theme') {
                $issues[] = 'BOOTSTRAP_THEME_NOT_CLEAN';
            }
            if (($facts['elementor_version'] ?? null) !== null) {
                $issues[] = 'BOOTSTRAP_ELEMENTOR_ALREADY_LOADED';
            }
        } else {
            foreach ([
                'active_theme' => ['ezb-theme', 'UNEXPECTED_ACTIVE_THEME'],
                'ezb_core_active' => [true, 'EZB_CORE_NOT_ACTIVE'],
                'theme_entrypoint_regular' => [true, 'THEME_ENTRYPOINT_UNSAFE'],
                'core_entrypoint_regular' => [true, 'CORE_ENTRYPOINT_UNSAFE'],
                'elementor_entrypoint_regular' => [true, 'ELEMENTOR_ENTRYPOINT_UNSAFE'],
                'theme_dir_exists' => [true, 'THEME_DIRECTORY_MISSING'],
                'core_dir_exists' => [true, 'CORE_DIRECTORY_MISSING'],
                'elementor_dir_exists' => [true, 'ELEMENTOR_DIRECTORY_MISSING'],
            ] as $key => [$expected, $issue]) {
                if (($facts[$key] ?? null) !== $expected) $issues[] = $issue;
            }
        }
        foreach ([
            'maintenance_mode' => [false, 'MAINTENANCE_MODE_UNKNOWN_OR_ACTIVE'],
            'uploads_dir_regular' => [true, 'UPLOADS_DIRECTORY_UNSAFE'],
            'elementor_pro_dir_exists' => [false, 'ELEMENTOR_PRO_PRESENT'],
        ] as $key => [$expected, $issue]) {
            if (($facts[$key] ?? null) !== $expected) $issues[] = $issue;
        }
        $home = $facts['home'] ?? null;
        $siteurl = $facts['siteurl'] ?? null;
        if (!is_string($home) || !is_string($siteurl)
            || parse_url($home, PHP_URL_SCHEME) !== parse_url($siteurl, PHP_URL_SCHEME)) {
            $issues[] = 'HOME_SITEURL_SCHEME_MISMATCH';
        }
        return [
            'schema_version' => 1,
            'status' => $issues ? 'BLOCKED_DELIVERY_RUNTIME_GATE' : 'READY_FOR_BACKUP_REHEARSAL_ONLY',
            'mode' => 'read-only', 'delivery_mode' => $mode,
            'target_site' => 'ez2-isolated-only',
            'expected_release_sha' => is_string($sha) ? $sha : null,
            'issues' => array_values(array_unique($issues)),
            'release_bytes_verified' => false, 'github_checks_verified' => false,
            'localwp_identity_independently_attested' => false,
            'backup_verified' => false, 'content_conflicts_resolved' => false,
            'private_media_verified' => false, 'can_apply' => false,
            'site_modified' => false, 'one_click_complete' => false,
            'deployment_authorized' => false,
        ];
    }

    private static function existsOrLink(string $path): bool {
        return file_exists($path) || is_link($path);
    }

    private static function regularEntrypoint(string $root, string $relative): bool {
        if ($root === '' || is_link($root) || !is_dir($root)) return false;
        $path = $root . '/' . $relative;
        if (is_link($path) || !is_file($path)) return false;
        $realRoot = realpath($root);
        $realPath = realpath($path);
        return is_string($realRoot) && is_string($realPath)
            && str_starts_with($realPath, $realRoot . DIRECTORY_SEPARATOR);
    }

    public static function collect(): array {
        if (!defined('ABSPATH') || !defined('WP_CONTENT_DIR')
            || !function_exists('get_option') || !function_exists('get_stylesheet')
            || !is_file(ABSPATH . 'wp-admin/includes/plugin.php')) {
            throw new RuntimeException('WORDPRESS_RUNTIME_REQUIRED');
        }
        if (!function_exists('is_plugin_active')) {
            require_once ABSPATH . 'wp-admin/includes/plugin.php';
        }
        $facts = Ez2RuntimeProbe::collect();
        $content = WP_CONTENT_DIR;
        $facts += [
            'delivery_mode' => getenv('EZ2_DELIVERY_MODE') ?: 'upgrade',
            'expected_release_sha' => getenv('EZ2_EXPECTED_RELEASE_SHA') ?: null,
            'active_theme' => get_stylesheet(),
            'ezb_core_active' => is_plugin_active('ezb-core/ezb-core.php'),
            'theme_dir_exists' => self::existsOrLink($content . '/themes/ezb-theme'),
            'core_dir_exists' => self::existsOrLink($content . '/plugins/ezb-core'),
            'elementor_dir_exists' => self::existsOrLink($content . '/plugins/elementor'),
            'elementor_pro_dir_exists' => self::existsOrLink($content . '/plugins/elementor-pro'),
            'theme_entrypoint_regular' => self::regularEntrypoint($content . '/themes/ezb-theme', 'style.css'),
            'core_entrypoint_regular' => self::regularEntrypoint($content . '/plugins/ezb-core', 'ezb-core.php'),
            'elementor_entrypoint_regular' => self::regularEntrypoint($content . '/plugins/elementor', 'elementor.php'),
            'maintenance_mode' => file_exists(ABSPATH . '.maintenance'),
            'uploads_dir_regular' => is_dir($content . '/uploads') && !is_link($content . '/uploads'),
        ];
        return $facts;
    }
}
if (!defined('EZ2_DELIVERY_RUNTIME_GATE_LIBRARY_ONLY')) {
    try {
        $result = Ez2DeliveryRuntimeGate::evaluate(Ez2DeliveryRuntimeGate::collect());
        echo json_encode($result, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR) . "\n";
        if ($result['status'] !== 'READY_FOR_BACKUP_REHEARSAL_ONLY') exit(2);
    } catch (Throwable $e) {
        fwrite(STDERR, 'EZ2_DELIVERY_RUNTIME_GATE_FAIL: ' . $e->getMessage() . "\n");
        exit(1);
    }
}
