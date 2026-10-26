<?php
/**
 * Plugin Name: EZ2 Isolated Delivery Agent (Engineering Preview)
 * Description: Read-only delivery readiness panel for an independently approved EZ2 development site.
 * Version: 0.1.0
 * Requires PHP: 8.1
 */
require_once __DIR__ . '/includes/ez2-release-evidence.php';
require_once __DIR__ . '/includes/ez2-backup-readiness.php';
require_once __DIR__ . '/includes/ez2-managed-inventory.php';
if (!defined('ABSPATH')) {
    exit;
}
final class EZ2_Isolated_Delivery_Agent {
    private const IDENTITY = 'ez2-isolated-only';
    private const HOST_PATTERN = '/^ez2(?:-[a-z0-9]+)*\.local$/D';

    public static function validate(array $facts): array {
        $problems = [];
        $host = $facts['host'] ?? null;
        if (!is_string($host) || !preg_match(self::HOST_PATTERN, $host)) {
            $problems[] = 'ISOLATED_HOST_REQUIRED';
        }
        foreach (['home', 'siteurl'] as $field) {
            $value = $facts[$field] ?? null;
            if (!is_string($value) || preg_match('/[\x00-\x20\\\\]/', $value)) {
                $problems[] = 'UNSAFE_' . strtoupper($field);
                continue;
            }
            $parts = parse_url($value);
            if (!is_array($parts) || !in_array($parts['scheme'] ?? null, ['http', 'https'], true)
                || ($parts['host'] ?? null) !== $host || isset($parts['port'])
                || isset($parts['user']) || isset($parts['pass'])
                || isset($parts['query']) || isset($parts['fragment'])
                || !in_array($parts['path'] ?? '', ['', '/'], true)) {
                $problems[] = 'UNSAFE_' . strtoupper($field);
            }
        }
        if (($facts['identity'] ?? null) !== self::IDENTITY) {
            $problems[] = 'ISOLATED_SITE_IDENTITY_MISSING';
        }
        if (($facts['environment'] ?? null) !== 'development') {
            $problems[] = 'DEVELOPMENT_ONLY';
        }
        if (($facts['multisite'] ?? null) !== false) {
            $problems[] = 'MULTISITE_PROHIBITED';
        }
        return [
            'status' => $problems ? 'BLOCKED' : 'READ_ONLY_PREVIEW_READY',
            'issues' => $problems,
            'target_site' => self::IDENTITY,
            'mode' => 'read-only',
            'source_sha_verified' => false,
            'release_artifacts_verified' => false,
            'backup_verified' => false,
            'one_click_complete' => false,
            'can_apply' => false,
            'site_modified' => false,
        ];
    }

    public static function observe(): array {
        $home = get_option('home');
        $parts = is_string($home) ? parse_url($home) : false;
        return self::validate([
            'host' => is_array($parts) ? ($parts['host'] ?? null) : null,
            'home' => $home,
            'siteurl' => get_option('siteurl'),
            'identity' => get_option('ez2_site_identity'),
            'environment' => wp_get_environment_type(),
            'multisite' => is_multisite(),
        ]);
    }

    public static function register(): void {
        // Never expose a delivery control on the live, historical or current EZ New Dev sites.
        if (self::observe()['status'] !== 'READ_ONLY_PREVIEW_READY') return;
        add_management_page('EZ2 Delivery Readiness', 'EZ2 Delivery',
                            'manage_options', 'ez2-delivery-readiness', [self::class, 'render']);
    }

    public static function render(): void {
        if (!current_user_can('manage_options')) {
            wp_die(esc_html__('Permission denied.', 'ez2-delivery-agent'));
        }
        $report = self::observe();
        echo '<div class="wrap"><h1>EZ2 Delivery Readiness</h1>';
        echo '<p>Engineering preview only. This tool cannot install, update or publish a site.</p>';
        echo '<p><strong>Status:</strong> ' . esc_html($report['status']) . '</p>';
        if ($report['issues']) {
            echo '<ul>';
            foreach ($report['issues'] as $issue) {
                echo '<li>' . esc_html($issue) . '</li>';
            }
            echo '</ul>';
        }
        $remote = EZ2_Release_Evidence::live();
        echo '<h2>Public GitHub exact-head evidence (read-only)</h2>';
        echo '<p><strong>Status:</strong> ' . esc_html($remote['status']) . '</p>';
        echo '<p><strong>Source SHA:</strong> ' . esc_html($remote['source_sha'] ?? 'unavailable') . '</p>';
        echo '<p>Checked workflows: ' . esc_html((string) $remote['workflow_count'])
            . '; matching release artifacts: ' . esc_html((string) $remote['artifact_count']) . ' / 6.</p>';
        if ($remote['issues']) {
            echo '<ul>';
            foreach ($remote['issues'] as $issue) echo '<li>' . esc_html($issue) . '</li>';
            echo '</ul>';
        }
        $backup = EZ2_Backup_Readiness::observe($report['status'], $remote['source_sha'] ?? null);
        echo '<h2>Isolated rollback backup preparation (read-only)</h2>';
        echo '<p><strong>Status:</strong> ' . esc_html($backup['status']) . '</p>';
        echo '<p>Destination and component prerequisites only. No backup was created or verified.</p>';
        if ($backup['issues']) {
            echo '<ul>';
            foreach ($backup['issues'] as $issue) echo '<li>' . esc_html($issue) . '</li>';
            echo '</ul>';
        }
        $inventory = EZ2_Managed_Inventory::observe($report['status']);
        echo '<h2>Managed Elementor pages (read-only local fingerprints)</h2>';
        echo '<p><strong>Status:</strong> ' . esc_html($inventory['status']) . '</p>';
        echo '<p>Managed pages observed: ' . esc_html((string) $inventory['managed_count']) . '.</p>';
        echo '<p>Only fingerprints are calculated; no Owner page text or media leaves WordPress. '
            . 'An inventory does not authorise an update or prove that a release is installed.</p>';
        if ($inventory['issues']) {
            echo '<ul>';
            foreach ($inventory['issues'] as $issue) echo '<li>' . esc_html($issue) . '</li>';
            echo '</ul>';
        }
        echo '<p>Release verification, backup, media reconciliation, and rollback must pass before an apply control is implemented.</p>';
        echo '</div>';
    }
}
if (!defined('EZ2_DELIVERY_AGENT_LIBRARY_ONLY')) {
    add_action('admin_menu', ['EZ2_Isolated_Delivery_Agent', 'register']);
}
