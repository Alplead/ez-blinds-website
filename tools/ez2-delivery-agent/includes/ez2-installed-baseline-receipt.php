<?php
/**
 * Read-only integrity check for a proposed EZ2 installed-baseline receipt.
 *
 * A valid HMAC only authenticates local receipt bytes. It cannot prove that
 * WordPress was installed, that a backup exists, or that a release passed CI.
 * No production code issues receipts yet; no result grants apply authority.
 */
require_once __DIR__ . '/ez2-managed-inventory-diff.php';

final class EZ2_Installed_Baseline_Receipt {
    private const PREFIX = "EZ2_INSTALLED_BASELINE_V1\n";
    private const RECEIPT_KEYS = [
        'schema_version', 'target_site', 'site_host', 'source_sha',
        'installed_at_utc', 'baseline_observation', 'mac_sha256',
    ];

    private static function blocked(string $issue): array {
        return [
            'status' => 'BLOCKED_BASELINE_RECEIPT', 'issues' => [$issue],
            'mode' => 'read-only', 'target_site' => 'ez2-isolated-only',
            'receipt_authenticated' => false, 'baseline_trusted' => false,
            'installed_release_attested' => false, 'local_drift_count' => 0,
            'source_sha' => null, 'private_content_emitted' => false,
            'can_apply' => false, 'site_modified' => false,
        ];
    }

    private static function validObservation($value): bool {
        if (!is_array($value)) return false;
        $report = EZ2_Managed_Inventory_Diff::compare($value, $value);
        return $report['status'] === 'NO_MANAGED_CHANGES_UNTRUSTED_BASELINE'
            && $report['issues'] === [];
    }

    public static function verify($receipt, $currentObservation, $siteHost, $secret, ?int $now = null): array {
        if ($receipt === null) return self::blocked('NO_INSTALLED_BASELINE_RECEIPT');
        if (!is_string($siteHost)
            || !preg_match('/^ez2(?:-[a-z0-9]+)*\.local$/D', $siteHost))
            return self::blocked('ISOLATED_SITE_REQUIRED');
        if (!is_string($secret) || strlen($secret) < 32)
            return self::blocked('LOCAL_RECEIPT_SECRET_UNAVAILABLE');
        if (!self::validObservation($currentObservation))
            return self::blocked('INVALID_CURRENT_OBSERVATION');
        if (!is_array($receipt) || array_keys($receipt) !== self::RECEIPT_KEYS)
            return self::blocked('INVALID_RECEIPT_SCHEMA');
        if ($receipt['schema_version'] !== 1
            || $receipt['target_site'] !== 'ez2-isolated-only'
            || $receipt['site_host'] !== $siteHost
            || !is_string($receipt['source_sha'])
            || !preg_match('/^[a-f0-9]{40}$/D', $receipt['source_sha'])
            || !is_string($receipt['mac_sha256'])
            || !preg_match('/^[a-f0-9]{64}$/D', $receipt['mac_sha256'])
            || !self::validObservation($receipt['baseline_observation']))
            return self::blocked('INVALID_RECEIPT_FIELDS');
        $timestamp = $receipt['installed_at_utc'];
        if (!is_string($timestamp) || !preg_match('/^20[2-9][0-9]-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$/D', $timestamp))
            return self::blocked('INVALID_INSTALL_TIMESTAMP');
        $utc = new DateTimeZone('UTC');
        $date = DateTimeImmutable::createFromFormat('!Y-m-d\TH:i:s\Z', $timestamp, $utc);
        if ($date === false || $date->format('Y-m-d\TH:i:s\Z') !== $timestamp)
            return self::blocked('INVALID_INSTALL_TIMESTAMP');
        $time = $now ?? time();
        if ($date->getTimestamp() > $time + 300 || $date->getTimestamp() < 1767225600)
            return self::blocked('IMPOSSIBLE_INSTALL_TIMESTAMP');
        $payload = array_slice($receipt, 0, -1, true);
        try {
            $json = json_encode($payload, JSON_THROW_ON_ERROR | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
        } catch (Throwable $e) {
            return self::blocked('INVALID_RECEIPT_PAYLOAD');
        }
        $expected = hash_hmac('sha256', self::PREFIX . $json, $secret);
        if (!hash_equals($expected, $receipt['mac_sha256']))
            return self::blocked('RECEIPT_AUTHENTICATION_FAILED');
        $drift = EZ2_Managed_Inventory_Diff::compare($receipt['baseline_observation'], $currentObservation);
        if ($drift['status'] === 'BLOCKED_MANAGED_OBSERVATION_DIFF')
            return self::blocked('INVALID_BASELINE_COMPARISON');
        return [
            'status' => $drift['change_count'] ? 'AUTHENTICATED_RECEIPT_LOCAL_DRIFT' : 'AUTHENTICATED_RECEIPT_UNATTESTED',
            'issues' => [], 'mode' => 'read-only', 'target_site' => 'ez2-isolated-only',
            'receipt_authenticated' => true, 'baseline_trusted' => false,
            'installed_release_attested' => false,
            'local_drift_count' => $drift['change_count'],
            'source_sha' => $receipt['source_sha'],
            'private_content_emitted' => false, 'can_apply' => false,
            'site_modified' => false,
        ];
    }
}
