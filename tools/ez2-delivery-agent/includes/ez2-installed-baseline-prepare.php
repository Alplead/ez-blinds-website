<?php
/**
 * Prepare an UNATTESTED installed-baseline receipt for a future transactional
 * installer. This library does not write WordPress options or certify an install.
 *
 * The boolean facts are caller claims, NOT independent proof. Only a future
 * installer that independently verifies release, checkpoint, post-install state
 * and rollback may call this after a successful transaction. The read-only
 * delivery agent must never expose this helper as a UI action.
 */
require_once __DIR__ . '/ez2-installed-baseline-receipt.php';

final class EZ2_Installed_Baseline_Prepare {
    private const FACT_KEYS = [
        'site_status', 'site_host', 'source_sha', 'release_sha',
        'release_verified', 'checkpoint_verified', 'postinstall_verified',
        'rollback_verified', 'owner_conflicts', 'media_unresolved',
        'installed_at_utc',
    ];

    private static function blocked(string $issue): array {
        return [
            'status' => 'BLOCKED_RECEIPT_PREPARATION', 'issues' => [$issue],
            'receipt' => null, 'receipt_authenticated' => false,
            'installed_release_attested' => false, 'baseline_trusted' => false,
            'can_apply' => false, 'site_modified' => false,
            'private_content_emitted' => false,
        ];
    }

    public static function prepare(array $facts, $observation, $secret, ?int $now = null): array {
        if (array_keys($facts) !== self::FACT_KEYS)
            return self::blocked('INVALID_TRANSACTION_FACT_SCHEMA');
        if ($facts['site_status'] !== 'READ_ONLY_PREVIEW_READY'
            || !is_string($facts['site_host'])
            || !preg_match('/^ez2(?:-[a-z0-9]+)*\\.local$/D', $facts['site_host']))
            return self::blocked('ISOLATED_SITE_REQUIRED');
        if (!is_string($secret) || strlen($secret) < 32)
            return self::blocked('LOCAL_RECEIPT_SECRET_UNAVAILABLE');
        foreach (['source_sha', 'release_sha'] as $key) {
            if (!is_string($facts[$key]) || !preg_match('/^[a-f0-9]{40}$/D', $facts[$key]))
                return self::blocked('INVALID_EXACT_RELEASE_SHA');
        }
        if ($facts['source_sha'] !== $facts['release_sha'])
            return self::blocked('RELEASE_SHA_MISMATCH');
        foreach (['release_verified', 'checkpoint_verified', 'postinstall_verified', 'rollback_verified'] as $key) {
            if ($facts[$key] !== true)
                return self::blocked('TRANSACTION_PREREQUISITE_MISSING');
        }
        if ($facts['owner_conflicts'] !== 0 || $facts['media_unresolved'] !== 0)
            return self::blocked('CONTENT_OR_MEDIA_CONFLICT');
        $observationCheck = EZ2_Managed_Inventory_Diff::compare($observation, $observation);
        if ($observationCheck['status'] !== 'NO_MANAGED_CHANGES_UNTRUSTED_BASELINE'
            || $observationCheck['issues'] !== []
            || ($observation['managed_count'] ?? 0) < 1)
            return self::blocked('INVALID_MANAGED_BASELINE');
        $timestamp = $facts['installed_at_utc'];
        if (!is_string($timestamp)
            || !preg_match('/^20[2-9][0-9]-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$/D', $timestamp))
            return self::blocked('INVALID_INSTALL_TIMESTAMP');
        $date = DateTimeImmutable::createFromFormat('!Y-m-d\\TH:i:s\\Z', $timestamp, new DateTimeZone('UTC'));
        if ($date === false || $date->format('Y-m-d\\TH:i:s\\Z') !== $timestamp)
            return self::blocked('INVALID_INSTALL_TIMESTAMP');
        $time = $now ?? time();
        if ($date->getTimestamp() > $time + 300 || $date->getTimestamp() < 1767225600)
            return self::blocked('IMPOSSIBLE_INSTALL_TIMESTAMP');
        $payload = [
            'schema_version' => 1, 'target_site' => 'ez2-isolated-only',
            'site_host' => $facts['site_host'], 'source_sha' => $facts['source_sha'],
            'installed_at_utc' => $timestamp, 'baseline_observation' => $observation,
        ];
        try {
            $json = json_encode($payload, JSON_THROW_ON_ERROR | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
            $receipt = $payload + ['mac_sha256' => hash_hmac('sha256', "EZ2_INSTALLED_BASELINE_V1\\n" . $json, $secret)];
        } catch (Throwable $e) {
            return self::blocked('RECEIPT_SERIALIZATION_FAILED');
        }
        // Even an authenticated receipt is not proof that a real install occurred.
        $check = EZ2_Installed_Baseline_Receipt::verify(
            $receipt, $observation, $facts['site_host'], $secret, $time);
        if (!$check['receipt_authenticated'] || $check['local_drift_count'] !== 0)
            return self::blocked('RECEIPT_SELF_CHECK_FAILED');
        return [
            'status' => 'UNATTESTED_RECEIPT_PREPARED', 'issues' => [],
            'receipt' => $receipt, 'receipt_authenticated' => true,
            'installed_release_attested' => false, 'baseline_trusted' => false,
            'can_apply' => false, 'site_modified' => false,
            'private_content_emitted' => false,
        ];
    }
}
