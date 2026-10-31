<?php
/**
 * Disposable CI only: simulate an Owner edit and verify a repeated Elementor
 * import fails closed without creating a second page or extra attachments.
 * NEVER invoke against LocalWP, production, or an Owner-managed site.
 */
define('EZ2_DISPOSABLE_IMPORT_LIBRARY_ONLY', true);
require_once __DIR__ . '/ez2_disposable_import.php';
require_once __DIR__ . '/ez2_ci_import_reuse.php';

final class Ez2CiOwnerEditProbe {
    public const EDITED_TITLE = 'EZ2 synthetic CI Elementor hero - OWNER EDIT PROBE';

    public static function gate(array $facts, string $phase, string $optIn): array {
        $bad = Ez2DisposableImport::gate($facts);
        if (!in_array($phase, ['prepare', 'verify'], true)) $bad[] = 'phase';
        if ($optIn !== 'YES_DISPOSABLE_CONFLICT_ONLY') $bad[] = 'probe_opt_in';
        return $bad;
    }

    public static function execute(string $phase): void {
        if (!defined('WP_CLI') || !WP_CLI || !function_exists('get_option')) {
            throw new RuntimeException('NO_DISPOSABLE_WORDPRESS');
        }
        if (!function_exists('is_plugin_active')) require_once ABSPATH . 'wp-admin/includes/plugin.php';
        $facts = [
            'wp_cli' => true,
            'opt_in' => getenv('EZ2_DISPOSABLE_IMPORT'),
            'expected_host' => getenv('EZ2_EXPECTED_HOST'),
            'home' => get_option('home'),
            'siteurl' => get_option('siteurl'),
            'identity' => get_option('ez2_site_identity'),
            'environment' => wp_get_environment_type(),
            'multisite' => is_multisite(),
            'elementor_active' => is_plugin_active('elementor/elementor.php'),
            'elementor_loaded' => did_action('elementor/loaded') > 0,
            'expected_version' => getenv('EZ2_EXPECTED_ELEMENTOR_VERSION'),
            'elementor_version' => defined('ELEMENTOR_VERSION') ? ELEMENTOR_VERSION : null,
        ];
        if ($bad = self::gate($facts, $phase, getenv('EZ2_CI_OWNER_EDIT_PROBE') ?: '')) {
            throw new RuntimeException('DISPOSABLE_PROBE_GATE:' . implode(',', $bad));
        }
        $ids = get_posts([
            'post_type' => 'page',
            'post_status' => ['publish', 'future', 'draft', 'pending', 'private', 'trash'],
            'meta_key' => '_ez2_ci_import_fingerprint',
            'posts_per_page' => 3,
            'fields' => 'ids',
        ]);
        if (count($ids) !== 1) throw new RuntimeException('MARKED_DRAFT_COUNT');
        $post = (int) $ids[0];
        $snapshot = Ez2CiImportReuse::capture($post);
        $stored = (string) get_post_meta($post, '_ez2_ci_import_fingerprint', true);
        if (count($snapshot['media'] ?? []) !== 4) throw new RuntimeException('MEDIA_COUNT');
        if ($phase === 'prepare') {
            Ez2CiImportReuse::verify($snapshot, $stored, ELEMENTOR_VERSION);
            $updated = wp_update_post(['ID' => $post, 'post_title' => self::EDITED_TITLE], true);
            if (is_wp_error($updated) || (int) $updated !== $post) {
                throw new RuntimeException('SIMULATED_EDIT_FAILED');
            }
            echo "EZ2_CI_OWNER_EDIT_PREPARED draft=true synthetic_only=true\n";
            return;
        }
        if (($snapshot['title'] ?? null) !== self::EDITED_TITLE) {
            throw new RuntimeException('OWNER_EDIT_MISSING');
        }
        // The original fingerprint must still match every original field other
        // than the deliberate title edit: a failed re-import must change nothing.
        $original = $snapshot;
        $original['title'] = Ez2CiImportReuse::TITLE;
        if (!hash_equals($stored, Ez2CiImportReuse::digest($original))) {
            throw new RuntimeException('FAILED_IMPORT_MUTATED_DRAFT');
        }
        $attachments = get_posts([
            'post_type' => 'attachment', 'post_status' => 'inherit',
            'posts_per_page' => 10, 'fields' => 'ids',
        ]);
        if (count($attachments) !== 4) throw new RuntimeException('FAILED_IMPORT_ADDED_MEDIA');
        $byTitle = get_posts([
            'post_type' => 'page',
            'post_status' => ['publish', 'future', 'draft', 'pending', 'private', 'trash'],
            'title' => Ez2CiImportReuse::TITLE,
            'posts_per_page' => 3, 'fields' => 'ids',
        ]);
        if (count($byTitle) !== 0) throw new RuntimeException('FAILED_IMPORT_DUPLICATED_DRAFT');
        echo "EZ2_CI_OWNER_EDIT_CONFLICT_PASS draft_preserved=true media_preserved=true synthetic_only=true\n";
    }
}

if (!defined('EZ2_CI_OWNER_EDIT_PROBE_LIBRARY_ONLY')) {
    try {
        Ez2CiOwnerEditProbe::execute(getenv('EZ2_CI_OWNER_EDIT_PHASE') ?: '');
    } catch (Throwable $e) {
        fwrite(STDERR, 'EZ2_CI_OWNER_EDIT_PROBE_FAIL: ' . $e->getMessage() . "\n");
        exit(1);
    }
}
