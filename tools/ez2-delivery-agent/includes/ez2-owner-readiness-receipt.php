<?php
/**
 * A deliberately redacted, read-only Owner evidence receipt.
 *
 * Never export attachment identifiers, local paths, page text, site URLs,
 * plugin configuration, WordPress salts, or raw report objects. This receipt
 * does not attest installation, visual QA, restore, or publication authority.
 */
final class EZ2_Owner_Readiness_Receipt {
    private static function status($report): string {
        $value = is_array($report) ? ($report['status'] ?? null) : null;
        return is_string($value) && preg_match('/^[A-Z][A-Z0-9_]{0,79}$/D', $value) === 1
            ? $value : 'UNAVAILABLE';
    }

    private static function count($report, string $key): ?int {
        $value = is_array($report) ? ($report[$key] ?? null) : null;
        return is_int($value) && $value >= 0 && $value <= 100000 ? $value : null;
    }

    public static function build($site, $release, $backup, $inventory, $baseline,
                                 $media, $plugin, $transaction): array {
        $sha = is_array($release) ? ($release['source_sha'] ?? null) : null;
        if (!is_string($sha) || preg_match('/^[0-9a-f]{40}$/D', $sha) !== 1
            || self::status($release) !== 'CI_AND_ARTIFACTS_VERIFIED_READ_ONLY') {
            $sha = null;
        }
        return [
            'schema_version' => 1,
            'kind' => 'EZ2_ISOLATED_READINESS_RECEIPT',
            'scope' => 'owner-review-read-only-not-install-proof',
            'target_site' => 'ez2-isolated-only',
            'source_sha' => $sha,
            'site_status' => self::status($site),
            'release_status' => self::status($release),
            'workflow_count' => self::count($release, 'workflow_count'),
            'artifact_count' => self::count($release, 'artifact_count'),
            'backup_status' => self::status($backup),
            'managed_page_count' => self::count($inventory, 'managed_count'),
            'baseline_status' => self::status($baseline),
            'local_drift_count' => self::count($baseline, 'local_drift_count'),
            'media_status' => self::status($media),
            'media_slot_count' => self::count($media, 'slot_count'),
            'media_verified_count' => self::count($media, 'verified_count'),
            'plugin_status' => self::status($plugin),
            'plugin_matching_count' => self::count($plugin, 'matching_count'),
            'transaction_status' => self::status($transaction),
            'private_media_exported' => false,
            'localwp_visual_qa_verified' => false,
            'backup_restore_verified' => false,
            'installed_release_attested' => false,
            'can_apply' => false,
            'site_modified' => false,
            'publication_authorized' => false,
        ];
    }
}
