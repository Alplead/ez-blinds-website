<?php
/**
 * Read-only, fail-closed composition of EZ2's isolated-site delivery evidence.
 *
 * A release passing CI, a writable backup destination, an inventory, and a
 * locally authenticated receipt are four DIFFERENT facts. None is a completed
 * installation. This class intentionally has no write API or apply permit.
 * The future transactional installer must provide independent backup/restore,
 * dependency, content, media, and installed-release attestation before writing.
 */
require_once __DIR__ . '/ez2-managed-inventory-diff.php';

final class EZ2_Transaction_Readiness {
    private static function sha($value): bool {
        return is_string($value) && preg_match('/^[0-9a-f]{40}$/D', $value) === 1;
    }

    /** All inputs are read-only reports, never authorization tokens. */
    public static function evaluate($site, $release, $backup, $inventory, $baseline): array {
        $issues = [];
        $siteReady = is_array($site)
            && ($site['status'] ?? null) === 'READ_ONLY_PREVIEW_READY'
            && ($site['target_site'] ?? null) === 'ez2-isolated-only'
            && ($site['mode'] ?? null) === 'read-only'
            && ($site['can_apply'] ?? null) === false
            && ($site['site_modified'] ?? null) === false
            && ($site['issues'] ?? null) === [];
        if (!$siteReady) $issues[] = 'ISOLATED_SITE_NOT_VERIFIED';

        $sha = is_array($release) ? ($release['source_sha'] ?? null) : null;
        $releaseReady = is_array($release)
            && ($release['status'] ?? null) === 'CI_AND_ARTIFACTS_VERIFIED_READ_ONLY'
            && ($release['issues'] ?? null) === []
            && self::sha($sha)
            && ($release['workflow_count'] ?? null) === 5
            && ($release['artifact_count'] ?? null) === 6
            && ($release['mode'] ?? null) === 'read-only'
            && ($release['can_apply'] ?? null) === false
            && ($release['site_modified'] ?? null) === false;
        if (!$releaseReady) $issues[] = 'EXACT_HEAD_RELEASE_NOT_VERIFIED';

        $backupLocation = is_array($backup)
            && ($backup['status'] ?? null) === 'BACKUP_LOCATION_CANDIDATE_ONLY'
            && ($backup['issues'] ?? null) === []
            && ($backup['mode'] ?? null) === 'read-only'
            && ($backup['source_sha'] ?? null) === $sha
            && self::sha($sha)
            && ($backup['backup_created'] ?? null) === false
            && ($backup['backup_verified'] ?? null) === false
            && ($backup['restore_rehearsed'] ?? null) === false
            && ($backup['site_modified'] ?? null) === false
            && ($backup['can_apply'] ?? null) === false;
        if (!$backupLocation) $issues[] = 'BACKUP_LOCATION_NOT_READY';

        $inventoryReady = false;
        if (is_array($inventory)) {
            $diff = EZ2_Managed_Inventory_Diff::compare($inventory, $inventory);
            $inventoryReady = ($inventory['managed_count'] ?? 0) > 0
                && $diff['status'] === 'NO_MANAGED_CHANGES_UNTRUSTED_BASELINE'
                && $diff['issues'] === [];
        }
        if (!$inventoryReady) $issues[] = 'MANAGED_CONTENT_NOT_OBSERVED';

        $receiptAuthenticated = is_array($baseline)
            && ($baseline['receipt_authenticated'] ?? null) === true
            && ($baseline['issues'] ?? null) === []
            && in_array($baseline['status'] ?? null,
                ['AUTHENTICATED_RECEIPT_UNATTESTED', 'AUTHENTICATED_RECEIPT_LOCAL_DRIFT'], true)
            && ($baseline['mode'] ?? null) === 'read-only'
            && ($baseline['baseline_trusted'] ?? null) === false
            && ($baseline['installed_release_attested'] ?? null) === false
            && ($baseline['can_apply'] ?? null) === false
            && ($baseline['site_modified'] ?? null) === false
            && is_int($baseline['local_drift_count'] ?? null)
            && $baseline['local_drift_count'] >= 0
            && (($baseline['status'] === 'AUTHENTICATED_RECEIPT_LOCAL_DRIFT')
                === ($baseline['local_drift_count'] > 0));
        if (!$receiptAuthenticated) $issues[] = 'AUTHENTICATED_BASELINE_NOT_AVAILABLE';
        if ($receiptAuthenticated && $baseline['local_drift_count'] > 0)
            $issues[] = 'LOCAL_CONTENT_CHANGES_REQUIRE_REVIEW';

        // These stages are intentionally unavailable. In particular, never
        // promote a caller's boolean claims or an HMAC to install attestation.
        $issues[] = 'PRIVATE_BACKUP_AND_RESTORE_NOT_PROVEN';
        $issues[] = 'DEPENDENCY_CONTENT_MEDIA_TRANSACTION_NOT_IMPLEMENTED';
        $issues[] = 'INSTALLED_RELEASE_NOT_ATTESTED';
        return [
            'status' => 'BLOCKED_TRANSACTION_NOT_IMPLEMENTED',
            'issues' => $issues,
            'mode' => 'read-only',
            'target_site' => 'ez2-isolated-only',
            'source_sha' => $releaseReady ? $sha : null,
            'isolated_site_observed' => $siteReady,
            'exact_head_release_observed' => $releaseReady,
            'backup_location_observed' => $backupLocation,
            'managed_pages_observed' => $inventoryReady,
            'receipt_integrity_observed' => $receiptAuthenticated,
            'local_changes_observed' => $receiptAuthenticated
                ? $baseline['local_drift_count'] : null,
            'private_backup_verified' => false,
            'restore_rehearsed' => false,
            'installed_release_attested' => false,
            'private_content_emitted' => false,
            'site_modified' => false,
            'can_apply' => false,
            'one_click_complete' => false,
        ];
    }
}
