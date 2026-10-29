<?php
/**
 * Three-way, fingerprint-only preview of a managed Elementor content update.
 *
 * Inputs are observations, NOT verified installed-release receipts. The result
 * must never be used to authorise a write or infer who edited a page.
 */
require_once __DIR__ . '/ez2-managed-inventory-diff.php';

final class EZ2_Managed_Three_Way {
    private static function blocked(string $reason): array {
        return [
            'status' => 'BLOCKED_THREE_WAY_PREVIEW',
            'issues' => [$reason], 'mode' => 'read-only',
            'target_site' => 'ez2-isolated-only', 'change_count' => 0,
            'changes' => [], 'baseline_trusted' => false,
            'candidate_release_verified' => false, 'owner_edits_proven' => false,
            'private_content_emitted' => false, 'can_apply' => false,
            'site_modified' => false,
        ];
    }

    public static function compare($installedObservation, $localObservation, $candidateObservation): array {
        if ($installedObservation === null)
            return self::blocked('NO_INSTALLED_BASELINE_OBSERVATION');
        if ($candidateObservation === null)
            return self::blocked('NO_CANDIDATE_OBSERVATION');
        // Reuse the strict schema and duplicate-key checks. Neither observation
        // nor a matching fingerprint proves a release was installed.
        $localCheck = EZ2_Managed_Inventory_Diff::compare($installedObservation, $localObservation);
        $candidateCheck = EZ2_Managed_Inventory_Diff::compare($installedObservation, $candidateObservation);
        if ($localCheck['status'] === 'BLOCKED_MANAGED_OBSERVATION_DIFF'
            || $candidateCheck['status'] === 'BLOCKED_MANAGED_OBSERVATION_DIFF')
            return self::blocked('INVALID_OR_UNTRUSTED_THREE_WAY_INPUT');
        $before = array_column($installedObservation['entries'], null, 'key');
        $local = array_column($localObservation['entries'], null, 'key');
        $next = array_column($candidateObservation['entries'], null, 'key');
        $keys = array_unique(array_merge(array_keys($before), array_keys($local), array_keys($next)));
        sort($keys, SORT_STRING);
        $changes = [];
        foreach ($keys as $key) {
            $b = $before[$key] ?? null;
            $l = $local[$key] ?? null;
            $n = $next[$key] ?? null;
            if ($b === null) {
                if ($l !== null && $n !== null) $kind = 'untracked_local_candidate_collision';
                elseif ($l !== null) $kind = 'local_only_preserve';
                else $kind = 'candidate_addition_review';
            } elseif ($l === null) {
                // A missing local page is not equivalent to a safe removal.
                // Distinguish independent candidate changes from a shared
                // absence; neither observation authorises a delete or write.
                if ($n === null) $kind = 'local_and_candidate_missing_unverified';
                elseif ($n['content_sha256'] !== $b['content_sha256'])
                    $kind = 'local_missing_candidate_update_conflict';
                else $kind = 'local_missing_review';
            } elseif ($l['post_id'] !== $b['post_id']) {
                $kind = 'local_identity_conflict';
            } elseif ($n === null) {
                // A candidate removal must not hide edits made locally since
                // the observed baseline. Keep the conflict visible for review.
                $kind = $l['content_sha256'] !== $b['content_sha256']
                    ? 'local_drift_candidate_removal_conflict'
                    : 'candidate_removal_review';
            } else {
                // Candidate pages come from a separate disposable WordPress
                // database. Numeric post IDs are local identifiers, not
                // portable identities. The managed key and content digest
                // drive this preview; the local post ID remains protected
                // against changes relative to the installed observation.
                // No candidate observation grants write authority.
                $localChanged = $l['content_sha256'] !== $b['content_sha256'];
                $candidateChanged = $n['content_sha256'] !== $b['content_sha256'];
                if (!$localChanged && !$candidateChanged) continue;
                if (!$localChanged) $kind = 'candidate_update_review';
                elseif (!$candidateChanged) $kind = 'local_drift_preserve';
                elseif ($l['content_sha256'] === $n['content_sha256'])
                    $kind = 'already_matches_candidate_unverified';
                else $kind = 'local_candidate_conflict';
            }
            // Never emit post IDs, content digests, page text, URLs, or media.
            $changes[] = ['key' => $key, 'kind' => $kind];
        }
        return [
            'status' => 'THREE_WAY_PREVIEW_UNTRUSTED_BASELINE',
            'issues' => [], 'mode' => 'read-only',
            'target_site' => 'ez2-isolated-only', 'change_count' => count($changes),
            'changes' => $changes, 'baseline_trusted' => false,
            'candidate_release_verified' => false, 'owner_edits_proven' => false,
            'private_content_emitted' => false, 'can_apply' => false,
            'site_modified' => false,
        ];
    }
}
