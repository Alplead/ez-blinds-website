<?php
/**
 * Non-mutating WordPress backup destination and component readiness inspection.
 * A passing result is NOT a backup, restore rehearsal, or deployment permit.
 */
final class EZ2_Backup_Readiness {
    private const MIN_FREE_BYTES = 536870912; // 512 MiB is a floor, not a capacity estimate.

    private static function canonical($path): ?string {
        if (!is_string($path) || $path === '' || preg_match('/[\x00-\x1f\x7f]/', $path)) return null;
        $path = str_replace('\\', '/', $path);
        if (!preg_match('~^(?:/|[A-Za-z]:/)~D', $path) || str_contains($path, '//')) return null;
        $parts = explode('/', $path);
        if (in_array('..', $parts, true) || in_array('.', $parts, true)) return null;
        $path = rtrim($path, '/');
        if ($path === '') return '/';
        if (preg_match('~^[A-Za-z]:$~D', $path)) return $path . '/';
        return preg_match('~^[A-Za-z]:/~D', $path) ? strtolower($path) : $path;
    }

    private static function within(string $child, string $parent): bool {
        return $child === $parent || str_starts_with($child, rtrim($parent, '/') . '/');
    }

    /** Pure, deterministic guard: all facts are untrusted until checked. */
    public static function evaluate(array $facts): array {
        $issues = [];
        if (($facts['site_status'] ?? null) !== 'READ_ONLY_PREVIEW_READY') $issues[] = 'SITE_NOT_ISOLATED';
        if (!is_string($facts['source_sha'] ?? null)
            || !preg_match('/^[0-9a-f]{40}$/D', $facts['source_sha'])) $issues[] = 'EXACT_SHA_REQUIRED';
        $paths = [];
        foreach (['root', 'content', 'uploads', 'plugins', 'themes', 'backup'] as $key) {
            $paths[$key] = self::canonical($facts[$key] ?? null);
            if ($paths[$key] === null) $issues[] = 'UNSAFE_PATH_' . strtoupper($key);
        }
        if (!in_array(null, $paths, true)) {
            foreach (['content' => 'root', 'uploads' => 'content',
                      'plugins' => 'content', 'themes' => 'content'] as $child => $parent) {
                if ($paths[$child] === $paths[$parent]
                    || !self::within($paths[$child], $paths[$parent])) {
                    $issues[] = 'COMPONENT_OUTSIDE_' . strtoupper($parent);
                }
            }
            if (self::within($paths['backup'], $paths['root'])
                || self::within($paths['root'], $paths['backup'])) {
                $issues[] = 'BACKUP_OVERLAPS_WORDPRESS_ROOT';
            }
        }
        if (($facts['backup_exists'] ?? null) !== true
            || ($facts['backup_is_link'] ?? null) !== false
            || ($facts['backup_writable'] ?? null) !== true) {
            $issues[] = 'BACKUP_DESTINATION_UNSAFE';
        }
        if (($facts['db_connected'] ?? null) !== true) $issues[] = 'DATABASE_NOT_READY';
        $free = $facts['free_bytes'] ?? null;
        if ((!is_int($free) && !is_float($free)) || !is_finite((float) $free)
            || $free < self::MIN_FREE_BYTES) $issues[] = 'BACKUP_FREE_SPACE_INSUFFICIENT';
        return [
            'status' => $issues ? 'BLOCKED_BACKUP_PREPARATION' : 'BACKUP_LOCATION_CANDIDATE_ONLY',
            'issues' => $issues, 'mode' => 'read-only',
            'source_sha' => $facts['source_sha'] ?? null,
            'backup_created' => false, 'backup_verified' => false,
            'restore_rehearsed' => false, 'site_modified' => false,
            'can_apply' => false, 'one_click_complete' => false,
        ];
    }

    /** WordPress inspection deliberately avoids creating directories or reading secrets. */
    public static function observe(string $siteStatus, ?string $sourceSha): array {
        $backup = defined('EZ2_ISOLATED_BACKUP_DIR') ? EZ2_ISOLATED_BACKUP_DIR : null;
        $uploads = function_exists('wp_upload_dir') ? wp_upload_dir(null, false) : [];
        $db = $GLOBALS['wpdb'] ?? null;
        $dbh = is_object($db) ? ($db->dbh ?? null) : null;
        $backupReal = is_string($backup) ? realpath($backup) : false;
        $facts = [
            'site_status' => $siteStatus, 'source_sha' => $sourceSha,
            'root' => realpath(ABSPATH) ?: null,
            'content' => defined('WP_CONTENT_DIR') ? (realpath(WP_CONTENT_DIR) ?: null) : null,
            'uploads' => is_array($uploads) && isset($uploads['basedir'])
                ? (realpath($uploads['basedir']) ?: null) : null,
            'plugins' => defined('WP_PLUGIN_DIR') ? (realpath(WP_PLUGIN_DIR) ?: null) : null,
            'themes' => function_exists('get_theme_root') ? (realpath(get_theme_root()) ?: null) : null,
            'backup' => $backupReal ?: null,
            'backup_exists' => $backupReal !== false && is_dir($backupReal),
            'backup_is_link' => is_string($backup) && is_link($backup),
            'backup_writable' => $backupReal !== false && is_writable($backupReal),
            'db_connected' => is_object($dbh) || is_resource($dbh),
            'free_bytes' => $backupReal !== false ? disk_free_space($backupReal) : null,
        ];
        return self::evaluate($facts);
    }
}
