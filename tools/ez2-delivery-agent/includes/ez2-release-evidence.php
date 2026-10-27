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

    /**
     * GitHub's expired=false flag is not a freshness or byte-presence proof.
     * Validate the actual expiry instant and bounded nonempty artifact size.
     * This remains metadata-only evidence, never a verified download.
     */
    private static function artifactLive(array $artifact, DateTimeImmutable $now): bool {
        $size = $artifact['size_in_bytes'] ?? null;
        $raw = $artifact['expires_at'] ?? null;
        if (!is_int($size) || $size < 1 || $size > 268435456
            || !is_string($raw)
            || !preg_match('/^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$/D', $raw)) {
            return false;
        }
        $expiry = DateTimeImmutable::createFromFormat('!Y-m-d\\TH:i:s\\Z',
            $raw, new DateTimeZone('UTC'));
        return $expiry instanceof DateTimeImmutable
            && $expiry->format('Y-m-d\\TH:i:s\\Z') === $raw
            && $expiry > $now;
    }

    public static function evaluate(array $pr, array $runs, array $artifactSets,
                                    ?DateTimeImmutable $now = null): array {
        $now = $now ?? new DateTimeImmutable('now', new DateTimeZone('UTC'));
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
                    || !self::artifactLive($a, $now)
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
        return self::live_with_reader([self::class, 'api']);
    }

    /**
     * Recheck the mutable PR and branch after fetching workflow/artifact evidence.
     * Reader injection permits offline regression tests; production uses api().
     * This remains strictly read-only and is not an installation authorisation.
     */
    public static function live_with_reader(callable $read): array {
        try {
            $pr = $read('/pulls/1');
            $sha = $pr['head']['sha'] ?? null;
            if (!is_string($sha) || !preg_match('/^[0-9a-f]{40}$/D', $sha)) {
                throw new RuntimeException('INVALID_PR_HEAD');
            }
            $runs = $read('/actions/runs?head_sha=' . $sha . '&per_page=100');
            if (!is_array($runs['workflow_runs'] ?? null)
                || ($runs['total_count'] ?? 0) > 100) {
                throw new RuntimeException('WORKFLOW_RESULTS_INCOMPLETE');
            }
            $selected = [];
            foreach ($runs['workflow_runs'] as $run) {
                $name = $run['name'] ?? null;
                // The SHA query can include other events or unrelated runs. Select
                // only the exact PR event and feature branch, just as evaluate()
                // does; a newer push run must not shadow the valid PR run.
                if (!in_array($name, self::WORKFLOWS, true)
                    || !is_int($run['id'] ?? null) || $run['id'] < 1
                    || ($run['head_sha'] ?? null) !== $sha
                    || ($run['head_branch'] ?? null) !== self::BRANCH
                    || ($run['event'] ?? null) !== 'pull_request') continue;
                if (!isset($selected[$name]) || $run['id'] > $selected[$name]['id']) $selected[$name] = $run;
            }
            $sets = [];
            foreach (array_keys(self::ARTIFACT_PREFIXES) as $name) {
                $id = $selected[$name]['id'] ?? null;
                if (!is_int($id) || $id < 1) continue;
                $page = $read('/actions/runs/' . $id . '/artifacts?per_page=100');
                if (!is_array($page['artifacts'] ?? null)
                    || ($page['total_count'] ?? 0) > 100) {
                    throw new RuntimeException('ARTIFACT_RESULTS_INCOMPLETE');
                }
                $sets[$name] = $page['artifacts'];
            }
            // CI/artifact reads are not an atomic GitHub snapshot. Refuse a
            // release if the branch or PR moved while the evidence was fetched.
            $branch = $read('/branches/feature/vertical-slice-v1');
            if (($branch['commit']['sha'] ?? null) !== $sha) {
                throw new RuntimeException('BRANCH_HEAD_CHANGED_DURING_CHECK');
            }
            $freshPr = $read('/pulls/1');
            if (($freshPr['head']['sha'] ?? null) !== $sha) {
                throw new RuntimeException('PR_HEAD_CHANGED_DURING_CHECK');
            }
            return self::evaluate($freshPr, $runs['workflow_runs'], $sets);
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
