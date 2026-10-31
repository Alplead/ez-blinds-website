<?php
/** Read-only post-install integrity gate for the disposable release WordPress CI stack.
 * Checks the real WordPress runtime after the exact-head Elementor candidate
 * roundtrip, including cleanup of temporary drafts and synthetic media.
 * This is NOT an EZ2 LocalWP updater or evidence of Owner visual acceptance.
 */
final class Ez2CiPostinstallIntegrity {
    public const HOME = 'http://localhost:8081';
    public static function evaluate(array $f): array {
        $expected = [
            'wp_cli' => true,
            'opt_in' => 'YES_DISPOSABLE_RELEASE_ONLY',
            'home' => self::HOME, 'siteurl' => self::HOME,
            'environment' => 'staging', 'multisite' => false,
            'theme' => 'ezb-theme', 'core_active' => true,
            'elementor_active' => true, 'elementor_loaded' => true,
            'elementor_version' => '4.3.4',
            'show_on_front' => 'page', 'blog_public' => '0',
            'front_title' => 'Home', 'front_status' => 'publish',
            'permalink_structure' => '/%postname%/',
            'candidate_title_count' => 0, 'candidate_marker_count' => 0,
            'synthetic_attachment_count' => 0, 'synthetic_file_count' => 0,
        ];
        $issues = [];
        foreach ($expected as $key => $value) {
            if (!array_key_exists($key, $f) || $f[$key] !== $value) $issues[] = $key;
        }
        if (!is_int($f['front_id'] ?? null) || $f['front_id'] < 1) $issues[] = 'front_id';
        foreach (['expected_sha','release_sha'] as $key) {
            if (!is_string($f[$key] ?? null) ||
                !preg_match('/^[0-9a-f]{40}$/D', $f[$key])) $issues[] = $key;
        }
        if (!in_array('expected_sha', $issues) && !in_array('release_sha', $issues)
            && $f['expected_sha'] !== $f['release_sha']) $issues[] = 'sha_mismatch';
        return [
            'status' => $issues ? 'BLOCKED' : 'DISPOSABLE_POSTINSTALL_INTEGRITY_PASS',
            'issues' => $issues, 'read_only' => true, 'publication' => false,
            'localwp_touched' => false, 'one_click_complete' => false,
        ];
    }
    public static function collect(): array {
        if (!defined('WP_CLI') || !WP_CLI || !function_exists('get_option'))
            throw new RuntimeException('WP_CLI_ONLY');
        if (!function_exists('is_plugin_active'))
            require_once ABSPATH . 'wp-admin/includes/plugin.php';
        $metadata = '/release/RELEASE_METADATA.txt';
        if (is_link($metadata) || !is_file($metadata) || filesize($metadata) > 4096)
            throw new RuntimeException('RELEASE_METADATA_UNSAFE');
        $raw = file_get_contents($metadata);
        if (!is_string($raw) || !preg_match('/^commit=([0-9a-f]{40})$/m', $raw, $m))
            throw new RuntimeException('RELEASE_METADATA_SHA_MISSING');
        $statuses = ['publish','future','draft','pending','private','trash'];
        $find = static function (array $query) use ($statuses): int {
            $ids = get_posts(array_merge([
                'post_type' => 'page', 'post_status' => $statuses,
                'posts_per_page' => 1, 'fields' => 'ids',
                'suppress_filters' => true,
            ], $query));
            if (!is_array($ids)) throw new RuntimeException('CANDIDATE_QUERY_FAILED');
            return count($ids);
        };
        $front_id = (int) get_option('page_on_front');
        $front = $front_id > 0 ? get_post($front_id) : null;
        $uploads = wp_upload_dir(null, false);
        if (!is_array($uploads) || !empty($uploads['error']) ||
            !is_string($uploads['basedir'] ?? null))
            throw new RuntimeException('UPLOAD_DIRECTORY_UNAVAILABLE');
        $base = $uploads['basedir'];
        if (is_link($base)) throw new RuntimeException('LINKED_UPLOAD_ROOT');
        $files = glob($base . '/*/*/ez2-ci-release-*.png', GLOB_NOSORT);
        if ($files === false) throw new RuntimeException('UPLOAD_FILE_QUERY_FAILED');
        $attachments = get_posts([
            'post_type' => 'attachment', 'post_status' => 'inherit',
            'posts_per_page' => 1, 'fields' => 'ids',
            's' => 'Synthetic CI image', 'suppress_filters' => true,
        ]);
        if (!is_array($attachments)) throw new RuntimeException('ATTACHMENT_QUERY_FAILED');
        return [
            'wp_cli' => true, 'opt_in' => getenv('EZ2_CI_POSTINSTALL'),
            'home' => get_option('home'), 'siteurl' => get_option('siteurl'),
            'environment' => wp_get_environment_type(), 'multisite' => is_multisite(),
            'theme' => get_option('stylesheet'),
            'core_active' => is_plugin_active('ezb-core/ezb-core.php'),
            'elementor_active' => is_plugin_active('elementor/elementor.php'),
            'elementor_loaded' => did_action('elementor/loaded') > 0,
            'elementor_version' => defined('ELEMENTOR_VERSION') ? ELEMENTOR_VERSION : null,
            'show_on_front' => get_option('show_on_front'),
            'blog_public' => (string) get_option('blog_public'),
            'front_id' => $front_id,
            'front_title' => $front ? $front->post_title : null,
            'front_status' => $front ? $front->post_status : null,
            'permalink_structure' => get_option('permalink_structure'),
            'candidate_title_count' => $find(['title' => 'EZ2 synthetic release candidate - NEVER PUBLISH']),
            'candidate_marker_count' => $find(['meta_key' => '_ez2_ci_release_candidate_source_sha']),
            'synthetic_attachment_count' => count($attachments),
            'synthetic_file_count' => count($files),
            'expected_sha' => getenv('EZB_EXPECTED_SHA'),
            'release_sha' => $m[1],
        ];
    }
}
if (!defined('EZ2_CI_POSTINSTALL_LIBRARY_ONLY')) {
    try {
        $result = Ez2CiPostinstallIntegrity::evaluate(Ez2CiPostinstallIntegrity::collect());
        if ($result['status'] !== 'DISPOSABLE_POSTINSTALL_INTEGRITY_PASS')
            throw new RuntimeException('POSTINSTALL_INVARIANT_FAILED');
        echo "EZ2_CI_POSTINSTALL_INTEGRITY_PASS runtime=real_wordpress candidate_cleanup=true "
            . "uploads_clean=true publication=false localwp_touched=false one_click_complete=false\n";
    } catch (Throwable $e) {
        fwrite(STDERR, "EZ2_CI_POSTINSTALL_INTEGRITY_FAIL: " . $e->getMessage() . "\n");
        exit(1);
    }
}
