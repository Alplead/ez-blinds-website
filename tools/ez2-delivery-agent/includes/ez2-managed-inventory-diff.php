<?php
/**
 * Compare two read-only EZ2 managed-page observations without exporting content.
 * A matching digest is NOT an attested installed release or an update permit.
 */
final class EZ2_Managed_Inventory_Diff {
    private static function blocked(string $reason): array {
        return [
            'status' => 'BLOCKED_MANAGED_OBSERVATION_DIFF',
            'issues' => [$reason], 'mode' => 'read-only',
            'target_site' => 'ez2-isolated-only',
            'change_count' => 0, 'changes' => [],
            'baseline_trusted' => false, 'same_site_attested' => false,
            'owner_edits_proven' => false, 'private_content_emitted' => false,
            'can_apply' => false, 'site_modified' => false,
        ];
    }

    private static function validate($snapshot): array {
        if (!is_array($snapshot) || array_keys($snapshot) !== [
            'status', 'issues', 'mode', 'target_site', 'managed_count', 'entries',
            'private_content_emitted', 'installed_release_attested',
            'owner_edit_baseline_trusted', 'can_apply', 'site_modified',
        ]) throw new RuntimeException('INVALID_OBSERVATION_SCHEMA');
        if ($snapshot['mode'] !== 'read-only'
            || $snapshot['target_site'] !== 'ez2-isolated-only'
            || $snapshot['issues'] !== []
            || $snapshot['private_content_emitted'] !== false
            || $snapshot['installed_release_attested'] !== false
            || $snapshot['owner_edit_baseline_trusted'] !== false
            || $snapshot['can_apply'] !== false
            || $snapshot['site_modified'] !== false)
            throw new RuntimeException('UNSAFE_OBSERVATION_CLAIM');
        $rows = $snapshot['entries']; $count = $snapshot['managed_count'];
        if (!is_int($count) || $count < 0 || $count > 100
            || !is_array($rows) || !array_is_list($rows)
            || count($rows) !== $count
            || $snapshot['status'] !== ($count ? 'MANAGED_DIGESTS_OBSERVED' : 'NO_MANAGED_PAGES'))
            throw new RuntimeException('INCONSISTENT_OBSERVATION');
        $out = []; $ids = []; $previous = '';
        foreach ($rows as $row) {
            if (!is_array($row) || array_keys($row) !== ['key', 'post_id', 'content_sha256'])
                throw new RuntimeException('INVALID_OBSERVATION_ENTRY');
            $key = $row['key']; $id = $row['post_id']; $digest = $row['content_sha256'];
            if (!is_string($key) || !preg_match('/^ez2-[a-z0-9-]{1,80}$/D', $key)
                || strcmp($key, $previous) <= 0
                || !is_int($id) || $id < 1 || isset($ids[$id])
                || !is_string($digest) || !preg_match('/^[a-f0-9]{64}$/D', $digest))
                throw new RuntimeException('UNSAFE_OR_DUPLICATE_ENTRY');
            $previous = $key; $ids[$id] = true; $out[$key] = $row;
        }
        return $out;
    }

    public static function compare($baseline, $current): array {
        if ($baseline === null) return self::blocked('NO_PREVIOUS_OBSERVATION');
        try {
            $before = self::validate($baseline);
            $after = self::validate($current);
            $changes = [];
            $keys = array_unique(array_merge(array_keys($before), array_keys($after)));
            sort($keys, SORT_STRING);
            foreach ($keys as $key) {
                $a = $before[$key] ?? null; $b = $after[$key] ?? null;
                if ($a === null) $kind = 'added_since_observation';
                elseif ($b === null) $kind = 'missing_since_observation';
                elseif ($a['post_id'] !== $b['post_id']) $kind = 'managed_identity_changed';
                elseif ($a['content_sha256'] !== $b['content_sha256'])
                    $kind = 'content_fingerprint_changed';
                else continue;
                $changes[] = ['key' => $key, 'kind' => $kind];
            }
            return [
                'status' => $changes ? 'MANAGED_CHANGES_OBSERVED' : 'NO_MANAGED_CHANGES_UNTRUSTED_BASELINE',
                'issues' => [], 'mode' => 'read-only', 'target_site' => 'ez2-isolated-only',
                'change_count' => count($changes), 'changes' => $changes,
                'baseline_trusted' => false, 'same_site_attested' => false,
                'owner_edits_proven' => false, 'private_content_emitted' => false,
                'can_apply' => false, 'site_modified' => false,
            ];
        } catch (Throwable $e) {
            return self::blocked('INVALID_OR_UNTRUSTED_OBSERVATION');
        }
    }
}
