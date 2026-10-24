<?php
/**
 * Read-only integration proof: privately compiled synthetic Elementor media
 * must match the actual disposable WordPress draft and its attachments.
 * Never an importer, LocalWP updater or production command.
 */
define('EZ2_DISPOSABLE_IMPORT_LIBRARY_ONLY', true);
require_once __DIR__ . '/ez2_disposable_import.php';
require_once __DIR__ . '/ez2_ci_import_reuse.php';

final class Ez2CiCompiledRoundtrip {
    public static function check(array $facts, array $snapshot, string $fingerprint, array $compiled): array {
        if ($bad = Ez2DisposableImport::gate($facts)) {
            throw new RuntimeException('DISPOSABLE_GATE:' . implode(',', $bad));
        }
        Ez2CiImportReuse::verify($snapshot, $fingerprint, $facts['expected_version']);
        if (array_keys($compiled) !== ['title', 'type', 'version', 'page_settings', 'content']
            || $compiled['title'] !== 'EZ2 Home Hero - Unpublished Owner Review Candidate'
            || $compiled['type'] !== 'page' || $compiled['version'] !== '4.3.4'
            || $compiled['page_settings'] !== ['hide_title' => 'yes']
            || !is_array($compiled['content']) || count($compiled['content']) !== 1
            || str_contains(json_encode($compiled, JSON_THROW_ON_ERROR), 'ez2-media://')) {
            throw new RuntimeException('UNSAFE_COMPILED_CANDIDATE');
        }
        $stored = json_decode($snapshot['data'], true, 32, JSON_THROW_ON_ERROR);
        if ($stored !== $compiled['content']) {
            throw new RuntimeException('COMPILED_WORDPRESS_ROUNDTRIP_MISMATCH');
        }
        $gallery = $compiled['content'][0]['settings']['background_slideshow_gallery'] ?? null;
        if (!is_array($gallery) || count($gallery) !== 4 || count($snapshot['media']) !== 4) {
            throw new RuntimeException('COMPILED_GALLERY_COUNT');
        }
        foreach ($gallery as $index => $image) {
            $actual = $snapshot['media'][$index];
            if (!is_array($image) || array_keys($image) !== ['id', 'url']
                || !is_int($image['id']) || $image['id'] !== $actual['id']
                || !is_string($image['url']) || $image['url'] !== $actual['url']
                || $actual['mime'] !== 'image/png' || $actual['exists'] !== true
                || $actual['parent'] !== $snapshot['post_id']) {
                throw new RuntimeException('COMPILED_ATTACHMENT_MISMATCH');
            }
        }
        return ['status' => 'DISPOSABLE_COMPILED_WORDPRESS_ROUNDTRIP_PASS',
            'media_slots' => 4, 'elementor_version' => $facts['expected_version'],
            'read_only' => true, 'localwp_verified' => false,
            'deployment_authorized' => false, 'applied' => false];
    }

    public static function execute(): void {
        if (!defined('WP_CLI') || !WP_CLI || !function_exists('get_option')
            || getenv('EZ2_CI_COMPILED_ROUNDTRIP') !== 'YES_DISPOSABLE_COMPARE_ONLY') {
            throw new RuntimeException('DISPOSABLE_CLI_OPT_IN_REQUIRED');
        }
        if (!function_exists('is_plugin_active')) require_once ABSPATH . 'wp-admin/includes/plugin.php';
        $facts = ['wp_cli' => true, 'opt_in' => getenv('EZ2_DISPOSABLE_IMPORT'),
            'expected_host' => getenv('EZ2_EXPECTED_HOST'), 'home' => get_option('home'),
            'siteurl' => get_option('siteurl'), 'identity' => get_option('ez2_site_identity'),
            'environment' => wp_get_environment_type(), 'multisite' => is_multisite(),
            'elementor_active' => is_plugin_active('elementor/elementor.php'),
            'elementor_loaded' => did_action('elementor/loaded') > 0,
            'expected_version' => getenv('EZ2_EXPECTED_ELEMENTOR_VERSION'),
            'elementor_version' => defined('ELEMENTOR_VERSION') ? ELEMENTOR_VERSION : null];
        if ($bad = Ez2DisposableImport::gate($facts)) {
            throw new RuntimeException('DISPOSABLE_GATE:' . implode(',', $bad));
        }
        $path = '/tmp/ez2-ci-compiled-private.json'; // Read-only bind mount, outside Git checkout.
        if (is_link($path) || !is_file($path) || filesize($path) < 1 || filesize($path) > 256000) {
            throw new RuntimeException('PRIVATE_COMPILED_INPUT');
        }
        $compiled = json_decode(file_get_contents($path), true, 32, JSON_THROW_ON_ERROR);
        if (!is_array($compiled)) throw new RuntimeException('COMPILED_NOT_OBJECT');
        $statuses = ['publish', 'future', 'draft', 'pending', 'private', 'trash'];
        $byTitle = get_posts(['post_type' => 'page', 'post_status' => $statuses,
            'title' => Ez2CiImportReuse::TITLE, 'posts_per_page' => 3, 'fields' => 'ids']);
        $byMarker = get_posts(['post_type' => 'page', 'post_status' => $statuses,
            'meta_key' => '_ez2_ci_import_fingerprint', 'posts_per_page' => 3, 'fields' => 'ids']);
        $found = Ez2CiImportReuse::candidates($byTitle, $byMarker);
        if (count($found) !== 1) throw new RuntimeException('DRAFT_NOT_UNIQUE');
        $post = (int) $found[0];
        $report = self::check($facts, Ez2CiImportReuse::capture($post),
            (string) get_post_meta($post, '_ez2_ci_import_fingerprint', true), $compiled);
        echo wp_json_encode($report, JSON_THROW_ON_ERROR | JSON_UNESCAPED_SLASHES) . "\n";
    }
}
if (!defined('EZ2_CI_COMPILED_ROUNDTRIP_LIBRARY_ONLY')) {
    try { Ez2CiCompiledRoundtrip::execute(); }
    catch (Throwable $e) {
        fwrite(STDERR, 'EZ2_CI_COMPILED_ROUNDTRIP_FAIL: ' . $e->getMessage() . "\n");
        exit(1);
    }
}
