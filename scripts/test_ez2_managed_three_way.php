<?php
/** Synthetic-only three-way content safety tests; no WordPress or private data. */
require_once __DIR__ . '/../tools/ez2-delivery-agent/includes/ez2-managed-inventory.php';
require_once __DIR__ . '/../tools/ez2-delivery-agent/includes/ez2-managed-three-way.php';
$cases = 0;
$check = static function(bool $ok, string $name) use (&$cases): void {
    if (!$ok) throw new RuntimeException('Three-way regression: ' . $name);
    ++$cases;
};
$facts = [
    'site_status' => 'READ_ONLY_PREVIEW_READY', 'elementor_active' => true,
    'elementor_loaded' => true, 'elementor_version' => '4.3.4',
];
$row = [
    'id' => 12, 'key' => 'ez2-home', 'post_type' => 'page',
    'status' => 'draft', 'title' => 'Synthetic', 'slug' => 'synthetic',
    'body' => 'SYNTHETIC_PRIVATE_BODY',
    'elementor_data' => '[{"id":"abc","elType":"container","settings":{},"elements":[]}]',
    'page_settings' => ['hide_title' => 'yes'], 'elementor_version' => '4.3.4',
];
$observe = static fn(array $rows): array => EZ2_Managed_Inventory::evaluate($facts, $rows);
$base = $observe([$row]);
$changed = static fn(string $body): array => array_replace($row, ['body' => $body]);
$run = static fn($b, $l, $n): array => EZ2_Managed_Three_Way::compare($b, $l, $n);
$clean = $run($base, $base, $base);
$check($clean['status'] === 'THREE_WAY_PREVIEW_UNTRUSTED_BASELINE'
    && $clean['changes'] === [] && $clean['can_apply'] === false
    && $clean['baseline_trusted'] === false && $clean['candidate_release_verified'] === false,
    'matching observations never authorise apply');
foreach ([
    [null, $base, $base, 'NO_INSTALLED_BASELINE_OBSERVATION'],
    [$base, $base, null, 'NO_CANDIDATE_OBSERVATION'],
] as [$b, $l, $n, $reason]) {
    $r = $run($b, $l, $n);
    $check($r['status'] === 'BLOCKED_THREE_WAY_PREVIEW' && $r['issues'] === [$reason],
        'missing input');
}
$next = $observe([$changed('candidate v2')]);
$local = $observe([$changed('local edit')]);
foreach ([
    [$base, $next, 'candidate_update_review'],
    [$local, $base, 'local_drift_preserve'],
    [$local, $next, 'local_candidate_conflict'],
    [$next, $next, 'already_matches_candidate_unverified'],
] as [$l, $n, $kind]) {
    $r = $run($base, $l, $n);
    $check($r['changes'] === [['key' => 'ez2-home', 'kind' => $kind]]
        && $r['can_apply'] === false && $r['owner_edits_proven'] === false
        && !str_contains(json_encode($r), 'SYNTHETIC_PRIVATE_BODY'),
        $kind);
}
$empty = $observe([]);
$check($run($empty, $empty, $base)['changes'][0]['kind'] === 'candidate_addition_review',
    'candidate addition');
$check($run($base, $base, $empty)['changes'][0]['kind'] === 'candidate_removal_review',
    'candidate removal');
$check($run($base, $empty, $base)['changes'][0]['kind'] === 'local_missing_review',
    'local deletion');
$renumbered = $observe([array_replace($row, ['id' => 99])]);
$check($run($base, $renumbered, $base)['changes'][0]['kind'] === 'local_identity_conflict',
    'local post id change');
// Independent CI WordPress and LocalWP assign different numeric post IDs.
// Candidate IDs must not create false conflicts for the same managed key.
$check($run($base, $base, $renumbered)['changes'] === [],
    'candidate post id is not portable identity');
$candidateFromOtherDb = $observe([array_replace($changed('candidate v2'), ['id' => 99])]);
$check($run($base, $base, $candidateFromOtherDb)['changes'][0]['kind'] === 'candidate_update_review',
    'candidate content change with independent post id');
$check($run($base, $local, $candidateFromOtherDb)['changes'][0]['kind'] === 'local_candidate_conflict',
    'local edit and independent candidate conflict');
$check($run($base, $local, $renumbered)['changes'][0]['kind'] === 'local_drift_preserve',
    'local edit remains protected when candidate id differs');
$check($run($empty, $base, $empty)['changes'][0]['kind'] === 'local_only_preserve',
    'local only');
$check($run($empty, $base, $base)['changes'][0]['kind'] === 'untracked_local_candidate_collision',
    'untracked collision');
$other = array_replace($row, ['id' => 22, 'key' => 'ez2-about']);
$many = $observe([$row, $other]);
$multiple = $run($empty, $many, $many);
$check($multiple['change_count'] === 2 && $multiple['changes'][0]['key'] === 'ez2-about'
    && $multiple['changes'][1]['key'] === 'ez2-home', 'deterministic ordering');
$bad = $base; $bad['entries'][0]['private_body'] = 'SYNTHETIC_PRIVATE_BODY';
$check($run($bad, $base, $base)['status'] === 'BLOCKED_THREE_WAY_PREVIEW',
    'invalid baseline');
$check($run($base, $bad, $base)['status'] === 'BLOCKED_THREE_WAY_PREVIEW',
    'invalid local');
$check($run($base, $base, $bad)['status'] === 'BLOCKED_THREE_WAY_PREVIEW',
    'invalid candidate');
$blocked = $observe([array_replace($row, ['key' => 'private'])]);
$check($run($base, $blocked, $base)['status'] === 'BLOCKED_THREE_WAY_PREVIEW',
    'blocked observation');
$check($run($base, $base, $blocked)['status'] === 'BLOCKED_THREE_WAY_PREVIEW',
    'blocked candidate');
echo "EZ2_MANAGED_THREE_WAY_PASS cases={$cases} read_only=true can_apply=false\n";
