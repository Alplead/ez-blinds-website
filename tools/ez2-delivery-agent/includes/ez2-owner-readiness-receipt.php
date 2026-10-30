<?php
/**
 * A deliberately redacted, read-only Owner evidence receipt.
 *
 * Never export attachment identifiers, local paths, page text, site URLs,
 * plugin configuration, WordPress salts, or raw report objects. This receipt
 * does not attest installation, visual QA, restore, or publication authority.
 */
final class EZ2_Owner_Readiness_Receipt {
    // A syntactically safe status can still be a private identifier or token.
    // Export only statuses that the corresponding read-only probe can produce.
    private const STATUSES = [
        'site' => ['READ_ONLY_PREVIEW_READY', 'BLOCKED'],
        'release' => ['CI_AND_ARTIFACTS_VERIFIED_READ_ONLY', 'BLOCKED_REMOTE_EVIDENCE'],
        'backup' => ['BACKUP_LOCATION_CANDIDATE_ONLY', 'BLOCKED_BACKUP_PREPARATION'],
        'inventory' => ['MANAGED_DIGESTS_OBSERVED', 'NO_MANAGED_PAGES', 'BLOCKED_MANAGED_CONTENT_INVENTORY'],
        'baseline' => ['AUTHENTICATED_RECEIPT_LOCAL_DRIFT', 'AUTHENTICATED_RECEIPT_UNATTESTED', 'BLOCKED_BASELINE_RECEIPT'],
        'media' => ['PRIVATE_MEDIA_REFERENCES_VERIFIED_READ_ONLY', 'BLOCKED_PRIVATE_MEDIA_READINESS'],
        'plugin' => ['LOCAL_PLUGIN_MATCH_UNATTESTED', 'BLOCKED_PLUGIN_RUNTIME'],
        'transaction' => ['BLOCKED_TRANSACTION_NOT_IMPLEMENTED'],
    ];

    private static function status($report, string $component): string {
        $value = is_array($report) ? ($report['status'] ?? null) : null;
        return is_string($value) && in_array($value, self::STATUSES[$component] ?? [], true)
            ? $value : 'UNAVAILABLE';
    }

    private static function count($report, string $key): ?int {
        $value = is_array($report) ? ($report[$key] ?? null) : null;
        return is_int($value) && $value >= 0 && $value <= 100000 ? $value : null;
    }

    public static function build($site, $release, $backup, $inventory, $baseline,
                                 $media, $plugin, $transaction): array {
        $releaseStatus = self::status($release, 'release');
        // A success label with incomplete CI or artifact counts is not a
        // verified release. Do not export its SHA or reassuring counts.
        if ($releaseStatus === 'CI_AND_ARTIFACTS_VERIFIED_READ_ONLY'
            && (self::count($release, 'workflow_count') !== 5
                || self::count($release, 'artifact_count') !== 6)) {
            $releaseStatus = 'UNAVAILABLE';
        }
        $sha = is_array($release) ? ($release['source_sha'] ?? null) : null;
        if (!is_string($sha) || preg_match('/^[0-9a-f]{40}$/D', $sha) !== 1
            || $releaseStatus !== 'CI_AND_ARTIFACTS_VERIFIED_READ_ONLY') {
            $sha = null;
        }
        $inventoryStatus = self::status($inventory, 'inventory');
        $baselineStatus = self::status($baseline, 'baseline');
        $mediaStatus = self::status($media, 'media');
        $pluginStatus = self::status($plugin, 'plugin');

        // A blocked probe may retain stale counts. Only export observations
        // from an allowed successful probe status, with consistent totals.
        $workflowCount = $releaseStatus === 'CI_AND_ARTIFACTS_VERIFIED_READ_ONLY'
            ? self::count($release, 'workflow_count') : null;
        $artifactCount = $releaseStatus === 'CI_AND_ARTIFACTS_VERIFIED_READ_ONLY'
            ? self::count($release, 'artifact_count') : null;
        $managedCount = in_array($inventoryStatus,
            ['MANAGED_DIGESTS_OBSERVED', 'NO_MANAGED_PAGES'], true)
            ? self::count($inventory, 'managed_count') : null;
        if (($inventoryStatus === 'NO_MANAGED_PAGES' && $managedCount !== 0)
            || ($inventoryStatus === 'MANAGED_DIGESTS_OBSERVED'
                && ($managedCount === null || $managedCount < 1 || $managedCount > 100))) {
            $managedCount = null;
            $inventoryStatus = 'UNAVAILABLE';
        }
        $localDrift = in_array($baselineStatus,
            ['AUTHENTICATED_RECEIPT_UNATTESTED', 'AUTHENTICATED_RECEIPT_LOCAL_DRIFT'], true)
            ? self::count($baseline, 'local_drift_count') : null;
        if (($baselineStatus === 'AUTHENTICATED_RECEIPT_UNATTESTED' && $localDrift !== 0)
            || ($baselineStatus === 'AUTHENTICATED_RECEIPT_LOCAL_DRIFT'
                && ($localDrift === null || $localDrift === 0))) {
            $localDrift = null;
            $baselineStatus = 'UNAVAILABLE';
        }
        $mediaSlots = $mediaStatus === 'PRIVATE_MEDIA_REFERENCES_VERIFIED_READ_ONLY'
            ? self::count($media, 'slot_count') : null;
        $mediaVerified = $mediaStatus === 'PRIVATE_MEDIA_REFERENCES_VERIFIED_READ_ONLY'
            ? self::count($media, 'verified_count') : null;
        if ($mediaSlots === null || $mediaSlots < 1 || $mediaSlots > 100
            || $mediaVerified === null || $mediaVerified !== $mediaSlots) {
            $mediaSlots = null;
            $mediaVerified = null;
            if ($mediaStatus === 'PRIVATE_MEDIA_REFERENCES_VERIFIED_READ_ONLY') {
                $mediaStatus = 'UNAVAILABLE';
            }
        }
        $pluginMatches = $pluginStatus === 'LOCAL_PLUGIN_MATCH_UNATTESTED'
            ? self::count($plugin, 'matching_count') : null;
        if ($pluginStatus === 'LOCAL_PLUGIN_MATCH_UNATTESTED'
            && (self::count($plugin, 'checked_count') !== 1 || $pluginMatches !== 1)) {
            $pluginMatches = null;
            $pluginStatus = 'UNAVAILABLE';
        }

        return [
            'schema_version' => 1,
            'kind' => 'EZ2_ISOLATED_READINESS_RECEIPT',
            'scope' => 'owner-review-read-only-not-install-proof',
            'target_site' => 'ez2-isolated-only',
            'source_sha' => $sha,
            'site_status' => self::status($site, 'site'),
            'release_status' => $releaseStatus,
            'workflow_count' => $workflowCount,
            'artifact_count' => $artifactCount,
            'backup_status' => self::status($backup, 'backup'),
            'managed_page_count' => $managedCount,
            'baseline_status' => $baselineStatus,
            'local_drift_count' => $localDrift,
            'media_status' => $mediaStatus,
            'media_slot_count' => $mediaSlots,
            'media_verified_count' => $mediaVerified,
            'plugin_status' => $pluginStatus,
            'plugin_matching_count' => $pluginMatches,
            'transaction_status' => self::status($transaction, 'transaction'),
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
