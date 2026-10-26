<?php
/**
 * Read-only private WordPress attachment-to-Elementor-slot integrity audit.
 * No URLs, file paths, IDs, image bytes or private map values are emitted.
 * This is neither a media publisher nor an installer.
 */
final class EZ2_Private_Media_Readiness {
    private const HOST = '/^ez2(?:-[a-z0-9]+)*\.local$/D';
    private const SLOT = '/^[a-z0-9][a-z0-9-]{0,79}$/D';
    private const MIME = ['image/webp' => '.webp', 'image/jpeg' => '.jpg', 'image/png' => '.png'];

    private static function result(string $status, array $issues, int $slots = 0, int $verified = 0): array {
        return [
            'status' => $status, 'issues' => $issues, 'mode' => 'read-only',
            'target_site' => 'ez2-isolated-only', 'slot_count' => $slots,
            'verified_count' => $verified, 'unresolved_count' => $slots - $verified,
            'private_content_emitted' => false, 'media_publication_authorized' => false,
            'site_modified' => false, 'can_apply' => false,
        ];
    }

    private static function blocked(string $issue, int $slots = 0, int $verified = 0): array {
        return self::result('BLOCKED_PRIVATE_MEDIA_READINESS', [$issue], $slots, $verified);
    }

    private static function safeUrl($url, string $host, string $extension): bool {
        if (!is_string($url) || strlen($url) > 1000 || preg_match('/[^\x21-\x7e]/', $url)
            || str_contains($url, '\\') || str_contains($url, '%')) return false;
        $parts = parse_url($url);
        if (!is_array($parts) || !in_array($parts['scheme'] ?? null, ['http', 'https'], true)
            || ($parts['host'] ?? null) !== $host || isset($parts['port'])
            || isset($parts['user']) || isset($parts['pass'])
            || isset($parts['query']) || isset($parts['fragment'])) return false;
        $path = $parts['path'] ?? '';
        if (!str_starts_with($path, '/wp-content/uploads/')) return false;
        $segments = explode('/', substr($path, strlen('/wp-content/uploads/')));
        if (count($segments) < 3 || count($segments) > 8) return false;
        foreach ($segments as $segment) {
            if ($segment === '.' || $segment === '..'
                || !preg_match('/^[A-Za-z0-9][A-Za-z0-9._-]{0,200}$/D', $segment)) return false;
        }
        return str_ends_with(strtolower(end($segments)), $extension);
    }

    /** Callbacks supply local WordPress metadata; never fetch the public URL. */
    public static function evaluate($site, $mapping, $host, $uploadRoot, callable $attachment): array {
        if (!is_array($site) || ($site['status'] ?? null) !== 'READ_ONLY_PREVIEW_READY'
            || ($site['target_site'] ?? null) !== 'ez2-isolated-only'
            || ($site['mode'] ?? null) !== 'read-only'
            || ($site['can_apply'] ?? null) !== false
            || ($site['site_modified'] ?? null) !== false
            || !is_string($host) || !preg_match(self::HOST, $host))
            return self::blocked('ISOLATED_SITE_REQUIRED');
        if (!is_array($mapping) || array_keys($mapping) !== ['schema_version', 'target_site', 'host', 'slots']
            || $mapping['schema_version'] !== 1
            || $mapping['target_site'] !== 'ez2-isolated-only'
            || $mapping['host'] !== $host
            || !is_array($mapping['slots'])
            || count($mapping['slots']) < 1 || count($mapping['slots']) > 100)
            return self::blocked('PRIVATE_MEDIA_MAP_UNAVAILABLE_OR_INVALID');
        if (!is_string($uploadRoot) || is_link($uploadRoot))
            return self::blocked('UNSAFE_UPLOAD_ROOT');
        $root = realpath($uploadRoot);
        if ($root === false || !is_dir($root) || basename($root) !== 'uploads')
            return self::blocked('UNSAFE_UPLOAD_ROOT');
        $rootPrefix = rtrim($root, DIRECTORY_SEPARATOR) . DIRECTORY_SEPARATOR;
        $seenIds = []; $seenUrls = [];
        $verified = 0; $count = count($mapping['slots']);
        foreach ($mapping['slots'] as $slot => $item) {
            if (!is_string($slot) || !preg_match(self::SLOT, $slot)
                || !is_array($item) || array_keys($item) !== ['id', 'url', 'mime']
                || !is_int($item['id']) || $item['id'] < 1 || $item['id'] > 2147483647
                || !is_string($item['mime']) || !isset(self::MIME[$item['mime']])
                || !self::safeUrl($item['url'], $host, self::MIME[$item['mime']]))
                return self::blocked('INVALID_PRIVATE_MEDIA_SLOT', $count, $verified);
            $id = $item['id']; $url = $item['url'];
            if ((isset($seenIds[$id]) && $seenIds[$id] !== $url)
                || (isset($seenUrls[$url]) && $seenUrls[$url] !== $id))
                return self::blocked('CONFLICTING_PRIVATE_MEDIA_MAPPING', $count, $verified);
            $seenIds[$id] = $url; $seenUrls[$url] = $id;
            try {
                $actual = $attachment($id);
            } catch (Throwable $e) {
                return self::blocked('ATTACHMENT_LOOKUP_FAILED', $count, $verified);
            }
            if (!is_array($actual) || array_keys($actual) !== ['post_type', 'status', 'mime', 'url', 'file']
                || $actual['post_type'] !== 'attachment' || $actual['status'] !== 'inherit'
                || $actual['mime'] !== $item['mime'] || $actual['url'] !== $url
                || !is_string($actual['file']) || is_link($actual['file']) || !is_file($actual['file']))
                return self::blocked('ATTACHMENT_MISSING_OR_MISMATCHED', $count, $verified);
            $real = realpath($actual['file']);
            $stat = lstat($actual['file']);
            if ($real === false || $stat === false || !str_starts_with($real, $rootPrefix)
                || ($stat['mode'] & 0170000) !== 0100000 || $stat['nlink'] !== 1
                || $stat['size'] < 32 || $stat['size'] > 20971520)
                return self::blocked('UNSAFE_PRIVATE_MEDIA_FILE', $count, $verified);
            $relative = str_replace(DIRECTORY_SEPARATOR, '/', substr($real, strlen($rootPrefix)));
            if (parse_url($url, PHP_URL_PATH) !== '/wp-content/uploads/' . $relative)
                return self::blocked('MEDIA_URL_FILE_MISMATCH', $count, $verified);
            $image = @getimagesize($real);
            if ($image === false || ($image['mime'] ?? null) !== $item['mime']
                || ($image[0] ?? 0) < 1 || ($image[1] ?? 0) < 1)
                return self::blocked('INVALID_PRIVATE_MEDIA_IMAGE', $count, $verified);
            ++$verified;
        }
        return self::result('PRIVATE_MEDIA_REFERENCES_VERIFIED_READ_ONLY', [], $count, $verified);
    }

    public static function observe(array $site): array {
        if (($site['status'] ?? null) !== 'READ_ONLY_PREVIEW_READY')
            return self::blocked('ISOLATED_SITE_REQUIRED');
        if (!function_exists('get_option') || !function_exists('get_post')
            || !function_exists('get_post_mime_type') || !function_exists('wp_get_attachment_url')
            || !function_exists('get_attached_file') || !function_exists('wp_upload_dir'))
            return self::blocked('WORDPRESS_READ_API_UNAVAILABLE');
        $home = get_option('home');
        $parts = is_string($home) ? parse_url($home) : false;
        $host = is_array($parts) ? ($parts['host'] ?? null) : null;
        $uploads = wp_upload_dir(null, false);
        $root = is_array($uploads) ? ($uploads['basedir'] ?? null) : null;
        return self::evaluate($site, get_option('ez2_private_media_slot_map', null), $host, $root,
            static function (int $id): ?array {
                $post = get_post($id);
                if (!is_object($post)) return null;
                return [
                    'post_type' => $post->post_type, 'status' => $post->post_status,
                    'mime' => get_post_mime_type($id), 'url' => wp_get_attachment_url($id),
                    'file' => get_attached_file($id),
                ];
            });
    }
}
