<?php
/**
 * Read-only managed Elementor content fingerprint inventory for the isolated EZ2
 * WordPress admin. Never returns page text, media URLs, or customer data.
 * A fingerprint is NOT proof of an installed release or authority to overwrite.
 */
final class EZ2_Managed_Inventory {
    private const VERSION = '4.3.4';
    private const FIELDS = [
        'id', 'key', 'post_type', 'status', 'title', 'slug', 'body',
        'elementor_data', 'page_settings', 'elementor_version'
    ];

    private static function canonical($value) {
        if (!is_array($value)) return $value;
        if (!array_is_list($value)) ksort($value, SORT_STRING);
        foreach ($value as $key => $child) $value[$key] = self::canonical($child);
        return $value;
    }

    private static function digest($value): string {
        return hash('sha256', json_encode(self::canonical($value),
            JSON_THROW_ON_ERROR | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE));
    }

    private static function blocked(string $issue): array {
        return [
            'status' => 'BLOCKED_MANAGED_CONTENT_INVENTORY', 'issues' => [$issue],
            'mode' => 'read-only', 'target_site' => 'ez2-isolated-only',
            'managed_count' => 0, 'entries' => [], 'private_content_emitted' => false,
            'installed_release_attested' => false, 'owner_edit_baseline_trusted' => false,
            'can_apply' => false, 'site_modified' => false,
        ];
    }

    public static function evaluate(array $facts, array $rows): array {
        if (($facts['site_status'] ?? null) !== 'READ_ONLY_PREVIEW_READY'
            || ($facts['elementor_active'] ?? null) !== true
            || ($facts['elementor_loaded'] ?? null) !== true
            || ($facts['elementor_version'] ?? null) !== self::VERSION) {
            return self::blocked('ISOLATED_ELEMENTOR_RUNTIME_REQUIRED');
        }
        if (count($rows) > 100) return self::blocked('TOO_MANY_MANAGED_PAGES');
        $seenIds = []; $entries = [];
        try {
            foreach ($rows as $row) {
                if (!is_array($row) || array_keys($row) !== self::FIELDS)
                    throw new RuntimeException('INVALID_MANAGED_RECORD');
                $id = $row['id']; $key = $row['key'];
                if (!is_int($id) || $id < 1 || isset($seenIds[$id])
                    || !is_string($key) || !preg_match('/^ez2-[a-z0-9-]{1,80}$/D', $key)
                    || isset($entries[$key]) || $row['post_type'] !== 'page'
                    || !in_array($row['status'],
                        ['publish', 'future', 'draft', 'pending', 'private', 'trash'], true)
                    || !is_string($row['title']) || strlen($row['title']) > 1000
                    || !is_string($row['slug']) || strlen($row['slug']) > 200
                    || !is_string($row['body']) || strlen($row['body']) > 2000000
                    || !is_string($row['elementor_data'])
                    || strlen($row['elementor_data']) < 2
                    || strlen($row['elementor_data']) > 256000
                    || !is_array($row['page_settings'])
                    || $row['elementor_version'] !== self::VERSION)
                    throw new RuntimeException('UNSAFE_MANAGED_RECORD');
                $nodes = json_decode($row['elementor_data'], true, 32, JSON_THROW_ON_ERROR);
                if (!is_array($nodes) || !array_is_list($nodes) || !$nodes)
                    throw new RuntimeException('UNSUPPORTED_ELEMENTOR_DATA');
                $seenIds[$id] = true;
                $entries[$key] = [
                    'key' => $key,
                    'post_id' => $id,
                    'content_sha256' => self::digest([
                        'title' => $row['title'], 'slug' => $row['slug'],
                        'status' => $row['status'], 'body' => $row['body'],
                        'elementor_data' => $nodes,
                        // PHP JSON decoding collapses duplicate keys. Preserve a
                        // digest of the original bytes so local edits cannot hide
                        // behind equivalent decoded Elementor structures.
                        // Harmless reserialization deliberately counts as drift.
                        'elementor_data_raw_sha256' => hash('sha256', $row['elementor_data']),
                        'page_settings' => $row['page_settings'],
                        'elementor_version' => $row['elementor_version'],
                    ]),
                ];
            }
        } catch (Throwable $e) {
            return self::blocked('INVALID_MANAGED_RECORD');
        }
        ksort($entries, SORT_STRING);
        return [
            'status' => $entries ? 'MANAGED_DIGESTS_OBSERVED' : 'NO_MANAGED_PAGES',
            'issues' => [], 'mode' => 'read-only', 'target_site' => 'ez2-isolated-only',
            'managed_count' => count($entries), 'entries' => array_values($entries),
            'private_content_emitted' => false, 'installed_release_attested' => false,
            'owner_edit_baseline_trusted' => false, 'can_apply' => false,
            'site_modified' => false,
        ];
    }

    public static function observe(string $siteStatus): array {
        // Do not even query content on WPC, T2, EZ BNS New Dev or an unverified site.
        if ($siteStatus !== 'READ_ONLY_PREVIEW_READY')
            return self::blocked('ISOLATED_ELEMENTOR_RUNTIME_REQUIRED');
        try {
            if (!function_exists('get_posts') || !function_exists('get_post_meta')
                || !function_exists('get_post') || !function_exists('is_plugin_active')
                || !function_exists('did_action'))
                return self::blocked('WORDPRESS_READ_API_UNAVAILABLE');
            $facts = [
                'site_status' => $siteStatus,
                'elementor_active' => is_plugin_active('elementor/elementor.php'),
                'elementor_loaded' => did_action('elementor/loaded') > 0,
                'elementor_version' => defined('ELEMENTOR_VERSION') ? ELEMENTOR_VERSION : null,
            ];
            if ($facts['elementor_active'] !== true || $facts['elementor_loaded'] !== true
                || $facts['elementor_version'] !== self::VERSION)
                return self::blocked('ISOLATED_ELEMENTOR_RUNTIME_REQUIRED');
            $ids = get_posts([
                'post_type' => 'any',
                'post_status' => ['publish', 'future', 'draft', 'pending', 'private', 'trash'],
                'meta_key' => '_ez2_managed_key', 'posts_per_page' => 101,
                'fields' => 'ids', 'orderby' => 'ID', 'order' => 'ASC',
                'suppress_filters' => true,
            ]);
            if (!is_array($ids) || count($ids) > 100)
                return self::blocked('TOO_MANY_OR_INVALID_MANAGED_PAGES');
            $rows = [];
            foreach ($ids as $id) {
                $id = (int) $id; $post = get_post($id);
                if (!$post) return self::blocked('MANAGED_POST_DISAPPEARED');
                $meta = [];
                foreach (['_ez2_managed_key', '_elementor_data',
                          '_elementor_page_settings', '_elementor_version'] as $name) {
                    $values = get_post_meta($id, $name, false);
                    if (!is_array($values) || count($values) !== 1)
                        return self::blocked('MISSING_OR_DUPLICATE_MANAGED_METADATA');
                    $meta[$name] = $values[0];
                }
                $rows[] = [
                    'id' => $id, 'key' => $meta['_ez2_managed_key'],
                    'post_type' => $post->post_type, 'status' => $post->post_status,
                    'title' => $post->post_title, 'slug' => $post->post_name,
                    'body' => $post->post_content,
                    'elementor_data' => $meta['_elementor_data'],
                    'page_settings' => $meta['_elementor_page_settings'],
                    'elementor_version' => $meta['_elementor_version'],
                ];
            }
            return self::evaluate($facts, $rows);
        } catch (Throwable $e) {
            return self::blocked('MANAGED_INVENTORY_READ_FAILED');
        }
    }
}
