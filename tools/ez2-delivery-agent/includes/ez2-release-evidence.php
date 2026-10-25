<?php
/**
 * Exact-head public GitHub CI/artifact evidence, for an isolated EZ2 preview.
 * Read-only: a successful report is NEVER installation or publication approval.
 */
final class EZ2_Release_Evidence {
    private const REPO = 'Alplead/ez-blinds-website';
    private const BRANCH = 'feature/vertical-slice-v1';
    private const WORKFLOWS = [
        'Quality', 'Runtime Smoke', 'Release Install Smoke',
        'EZ2 Elementor Ephemeral Runtime (No Deployment)',
        'EZ2 Hero Candidate (No Deployment)',
    ];
    private const ARTIFACT_PREFIXES = [
        'Release Install Smoke' => [
            'ezb-release-', 'ez2-release-set-evidence-', 'ez2-public-content-candidate-',
        ],
        'EZ2 Elementor Ephemeral Runtime (No Deployment)' => [
            'ez2-synthetic-browser-4.3.4-', 'ez2-synthetic-browser-4.3.5-',
        ],
        'EZ2 Hero Candidate (No Deployment)' => ['ez2-hero-review-'],
    ];

    public static function evaluate(array $pr, array $runs, array $artifactSets): array {
        $issues = [];
        $sha = $pr['head']['sha'] ?? null;
        if (!is_string($sha) || !preg_match('/^[0-9a-f]{40}$/D', $sha)) {
            $issues[] = 'INVALID_PR_HEAD';
        }
        if (($pr['state'] ?? null) !== 'open' || ($pr['draft'] ?? null) !== true
            || ($pr['merged_at'] ?? null) !== null
            || ($pr['number'] ?? null) !== 1
            || ($pr['head']['ref'] ?? null) !== self::BRANCH
            || ($pr['head']['repo']['full_name'] ?? null) !== self::REPO
            || ($pr['base']['repo']['full_name'] ?? null) !== self::REPO
            || ($pr['base']['ref'] ?? null) !== 'main') {
            $issues[] = 'UNEXPECTED_DRAFT_PR';
        }
        $selected = [];
        foreach (self::WORKFLOWS as $name) {
            foreach ($runs as $run) {
                if (!is_array($run) || ($run['name'] ?? null) !== $name
                    || ($run['head_sha'] ?? null) !== $sha
                    || ($run['head_branch'] ?? null) !== self::BRANCH
                    || ($run['event'] ?? null) !== 'pull_request'
                    || !is_int($run['id'] ?? null) || $run['id'] < 1) {
                    continue;
                }
                if (!isset($selected[$name]) || $run['id'] > $selected[$name]['id']) {
                    $selected[$name] = $run;
                }
            }
            if (!isset($selected[$name])) {
                $issues[] = 'MISSING_WORKFLOW_' . $name;
            } elseif (($selected[$name]['status'] ?? null) !== 'completed'
                      || ($selected[$name]['conclusion'] ?? null) !== 'success') {
                $issues[] = 'WORKFLOW_NOT_PASS_' . $name;
            }
        }
        $artifactIds = [];
        foreach (self::ARTIFACT_PREFIXES as $name => $prefixes) {
            $set = $artifactSets[$name] ?? null;
            if (!is_array($set)) {
                $issues[] = 'MISSING_ARTIFACT_SET_' . $name;
                continue;
            }
            foreach ($prefixes as $prefix) {
                $matches = [];
                foreach ($set as $artifact) {
                    if (!is_array($artifact) || ($artifact['name'] ?? null) !== $prefix . $sha) continue;
                    $matches[] = $artifact;
                }
                if (count($matches) !== 1) {
                    $issues[] = 'ARTIFACT_MISSING_OR_DUPLICATE_' . $prefix;
                    continue;
                }
                $a = $matches[0];
                if (($a['expired'] ?? null) !== false
                    || !is_int($a['id'] ?? null) || $a['id'] < 1
                    || ($a['workflow_run']['head_sha'] ?? null) !== $sha
                    || ($a['workflow_run']['id'] ?? null) !== ($selected[$name]['id'] ?? null)) {
                    $issues[] = 'ARTIFACT_NOT_EXACT_HEAD_' . $prefix;
                } else {
                    $artifactIds[$prefix] = $a['id'];
                }
            }
        }
        return [
            'status' => $issues ? 'BLOCKED_REMOTE_EVIDENCE' : 'CI_AND_ARTIFACTS_VERIFIED_READ_ONLY',
            'source_sha' => is_string($sha) ? $sha : null,
            'issues' => $issues,
            'workflow_count' => count($selected),
            'artifact_count' => count($artifactIds),
            'artifact_ids' => $artifactIds,
            'mode' => 'read-only',
            'can_apply' => false,
            'one_click_complete' => false,
            'localwp_installed' => false,
            'site_modified' => false,
        ];
    }

    private static function api(string $path): array {
        // The URL is assembled exclusively from fixed paths and validated run IDs.
        $url = 'https://api.github.com/repos/' . self::REPO . $path;
        $response = wp_safe_remote_get($url, [
            'timeout' => 8,
            'redirection' => 0,
            'limit_response_size' => 1048576,
            'headers' => [
                'Accept' => 'application/vnd.github+json',
                'User-Agent' => 'EZ2-Isolated-ReadOnly-Delivery-Preview',
                'X-GitHub-Api-Version' => '2022-11-28',
            ],
        ]);
        if (is_wp_error($response) || wp_remote_retrieve_response_code($response) !== 200) {
            throw new RuntimeException('GITHUB_API_UNAVAILABLE');
        }
        $body = wp_remote_retrieve_body($response);
        if (!is_string($body) || strlen($body) > 1048576) {
            throw new RuntimeException('GITHUB_RESPONSE_TOO_LARGE');
        }
        $data = json_decode($body, true, 32, JSON_THROW_ON_ERROR);
        if (!is_array($data)) throw new RuntimeException('GITHUB_RESPONSE_NOT_OBJECT');
        return $data;
    }

    public static function live(): array {
        try {
            $pr = self::api('/pulls/1');
            $sha = $pr['head']['sha'] ?? null;
            if (!is_string($sha) || !preg_match('/^[0-9a-f]{40}$/D', $sha)) {
                throw new RuntimeException('INVALID_PR_HEAD');
            }
            $runs = self::api('/actions/runs?head_sha=' . $sha . '&per_page=100');
            if (!is_array($runs['workflow_runs'] ?? null)
                || ($runs['total_count'] ?? 0) > 100) {
                throw new RuntimeException('WORKFLOW_RESULTS_INCOMPLETE');
            }
            $selected = [];
            foreach ($runs['workflow_runs'] as $run) {
                $name = $run['name'] ?? null;
                if (!in_array($name, self::WORKFLOWS, true) || !is_int($run['id'] ?? null)) continue;
                if (!isset($selected[$name]) || $run['id'] > $selected[$name]['id']) $selected[$name] = $run;
            }
            $sets = [];
            foreach (array_keys(self::ARTIFACT_PREFIXES) as $name) {
                $id = $selected[$name]['id'] ?? null;
                if (!is_int($id) || $id < 1) continue;
                $page = self::api('/actions/runs/' . $id . '/artifacts?per_page=100');
                if (!is_array($page['artifacts'] ?? null)
                    || ($page['total_count'] ?? 0) > 100) {
                    throw new RuntimeException('ARTIFACT_RESULTS_INCOMPLETE');
                }
                $sets[$name] = $page['artifacts'];
            }
            return self::evaluate($pr, $runs['workflow_runs'], $sets);
        } catch (Throwable $e) {
            return [
                'status' => 'BLOCKED_REMOTE_EVIDENCE',
                'source_sha' => null,
                'issues' => ['REMOTE_EVIDENCE_UNAVAILABLE'],
                'workflow_count' => 0, 'artifact_count' => 0,
                'mode' => 'read-only', 'can_apply' => false,
                'one_click_complete' => false, 'localwp_installed' => false,
                'site_modified' => false,
            ];
        }
    }
}
