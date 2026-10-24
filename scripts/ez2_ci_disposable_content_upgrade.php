<?php
/** CI-only Elementor managed draft upgrade + rollback. NEVER run on LocalWP. */
define('EZ2_DISPOSABLE_IMPORT_LIBRARY_ONLY', true);
require_once __DIR__ . '/ez2_disposable_import.php';
require_once __DIR__ . '/ez2_ci_import_reuse.php';

final class Ez2CiDisposableContentUpgrade {
    const ORIGINAL = 'Blinds & Shutters';
    const UPGRADED = 'Blinds & Shutters - Synthetic CI Upgrade';

    public static function gate(array $facts, string $optIn, string $fault): array {
        $bad = Ez2DisposableImport::gate($facts);
        if ($optIn !== 'YES_DISPOSABLE_UPDATE_ONLY') $bad[] = 'upgrade_opt_in';
        if (!in_array($fault, ['', 'AFTER_DATA_WRITE', 'AFTER_FINGERPRINT_WRITE'], true))
            $bad[] = 'fault_mode';
        return $bad;
    }

    public static function transform(array $nodes): array {
        if (count($nodes) !== 1 || !isset($nodes[0]['elements']) ||
            !is_array($nodes[0]['elements']) || count($nodes[0]['elements']) !== 2 ||
            ($nodes[0]['elType'] ?? null) !== 'container' ||
            ($nodes[0]['elements'][0]['elType'] ?? null) !== 'widget' ||
            ($nodes[0]['elements'][0]['widgetType'] ?? null) !== 'heading' ||
            ($nodes[0]['elements'][1]['widgetType'] ?? null) !== 'button' ||
            ($nodes[0]['elements'][1]['settings']['link']['url'] ?? null) !== '/contact/') {
            throw new RuntimeException('UNEXPECTED_SYNTHETIC_CANDIDATE');
        }
        $heading = $nodes[0]['elements'][0]['settings']['title'] ?? null;
        if ($heading === self::UPGRADED) return ['changed' => false, 'nodes' => $nodes];
        if ($heading !== self::ORIGINAL) throw new RuntimeException('UNRECOGNISED_OWNER_CONTENT');
        $nodes[0]['elements'][0]['settings']['title'] = self::UPGRADED;
        return ['changed' => true, 'nodes' => $nodes];
    }

    public static function execute(): void {
        if (!defined('WP_CLI') || !WP_CLI || !function_exists('get_option'))
            throw new RuntimeException('WORDPRESS_CLI_REQUIRED');
        if (!function_exists('is_plugin_active'))
            require_once ABSPATH . 'wp-admin/includes/plugin.php';
        $facts = [
            'wp_cli' => true, 'opt_in' => getenv('EZ2_DISPOSABLE_IMPORT'),
            'expected_host' => getenv('EZ2_EXPECTED_HOST'),
            'home' => get_option('home'), 'siteurl' => get_option('siteurl'),
            'identity' => get_option('ez2_site_identity'),
            'environment' => wp_get_environment_type(), 'multisite' => is_multisite(),
            'elementor_active' => is_plugin_active('elementor/elementor.php'),
            'elementor_loaded' => did_action('elementor/loaded') > 0,
            'expected_version' => getenv('EZ2_EXPECTED_ELEMENTOR_VERSION'),
            'elementor_version' => defined('ELEMENTOR_VERSION') ? ELEMENTOR_VERSION : null,
        ];
        $fault = getenv('EZ2_CI_CONTENT_UPGRADE_FAULT') ?: '';
        if ($bad = self::gate($facts, getenv('EZ2_CI_CONTENT_UPGRADE') ?: '', $fault))
            throw new RuntimeException('DISPOSABLE_UPDATE_GATE:' . implode(',', $bad));
        $ids = get_posts(['post_type' => 'page',
            'post_status' => ['publish','future','draft','pending','private','trash'],
            'meta_key' => '_ez2_ci_import_fingerprint', 'posts_per_page' => 3,
            'fields' => 'ids']);
        if (!is_array($ids) || count($ids) !== 1)
            throw new RuntimeException('MARKED_DRAFT_COUNT');
        $post = (int) $ids[0];
        $before = Ez2CiImportReuse::capture($post);
        $stored = (string) get_post_meta($post, '_ez2_ci_import_fingerprint', true);
        Ez2CiImportReuse::verify($before, $stored, ELEMENTOR_VERSION);
        $nodes = json_decode($before['data'], true, 32, JSON_THROW_ON_ERROR);
        $plan = self::transform($nodes);
        if (!$plan['changed'] && $fault !== '')
            throw new RuntimeException('FAULT_REQUIRES_NEW_UPGRADE');
        $written = false;
        try {
            if ($plan['changed']) {
                $json = wp_json_encode($plan['nodes'], JSON_THROW_ON_ERROR);
                if (!update_post_meta($post, '_elementor_data', wp_slash($json)))
                    throw new RuntimeException('SYNTHETIC_DATA_UPDATE_FAILED');
                $written = true;
                if ($fault === 'AFTER_DATA_WRITE')
                    throw new RuntimeException('INJECTED_CI_CONTENT_UPGRADE_FAULT');
                $middle = Ez2CiImportReuse::capture($post);
                if (!update_post_meta($post, '_ez2_ci_import_fingerprint',
                        Ez2CiImportReuse::digest($middle)))
                    throw new RuntimeException('SYNTHETIC_FINGERPRINT_UPDATE_FAILED');
                if ($fault === 'AFTER_FINGERPRINT_WRITE')
                    throw new RuntimeException('INJECTED_CI_CONTENT_UPGRADE_FAULT');
            }
            $after = Ez2CiImportReuse::capture($post);
            Ez2CiImportReuse::verify($after,
                (string) get_post_meta($post, '_ez2_ci_import_fingerprint', true),
                ELEMENTOR_VERSION);
            if ($after['media'] !== $before['media'] ||
                $after['post_id'] !== $before['post_id'] ||
                $after['status'] !== 'draft' ||
                self::transform(json_decode($after['data'], true, 32, JSON_THROW_ON_ERROR))['changed'])
                throw new RuntimeException('SYNTHETIC_UPGRADE_POSTCHECK_FAILED');
            echo 'EZ2_CI_CONTENT_UPGRADE_PASS changed=' .
                ($plan['changed'] ? 'true' : 'false') .
                ' draft=true attachments_preserved=true rollback_ready=true localwp_touched=false' . "\n";
        } catch (Throwable $e) {
            if ($written) {
                update_post_meta($post, '_elementor_data', wp_slash($before['data']));
                update_post_meta($post, '_ez2_ci_import_fingerprint', $stored);
                $restored = Ez2CiImportReuse::capture($post);
                if (Ez2CiImportReuse::digest($restored) !== Ez2CiImportReuse::digest($before) ||
                    (string) get_post_meta($post, '_ez2_ci_import_fingerprint', true) !== $stored)
                    throw new RuntimeException('SYNTHETIC_CONTENT_ROLLBACK_FAILED', 0, $e);
            }
            throw $e;
        }
    }
}
if (!defined('EZ2_CI_DISPOSABLE_CONTENT_UPGRADE_LIBRARY_ONLY')) {
    try { Ez2CiDisposableContentUpgrade::execute(); }
    catch (Throwable $e) {
        fwrite(STDERR, 'EZ2_CI_CONTENT_UPGRADE_FAIL: ' . $e->getMessage() . "\n");
        exit(1);
    }
}
