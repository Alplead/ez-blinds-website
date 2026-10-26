<?php
/** Synthetic-only EZ2 managed content drift tests. No WordPress or private media. */
require_once __DIR__ . '/../tools/ez2-delivery-agent/includes/ez2-managed-inventory.php';
require_once __DIR__ . '/../tools/ez2-delivery-agent/includes/ez2-managed-inventory-diff.php';
$cases = 0;
$check = static function(bool $ok, string $name) use (&$cases): void {
    if (!$ok) throw new RuntimeException('Managed diff regression: ' . $name);
    ++$cases;
};
$facts = [
    'site_status' => 'READ_ONLY_PREVIEW_READY', 'elementor_active' => true,
    'elementor_loaded' => true, 'elementor_version' => '4.3.4',
];
$row = [
    'id' => 12, 'key' => 'ez2-home', 'post_type' => 'page',
    'status' => 'draft', 'title' => 'Synthetic', 'slug' => 'synthetic',
    'body' => 'PRIVATE_SYNTHETIC_BODY',
    'elementor_data' => '[{"id":"abc","elType":"container","settings":{},"elements":[]}]',
    'page_settings' => ['hide_title' => 'yes'], 'elementor_version' => '4.3.4',
];
$base = EZ2_Managed_Inventory::evaluate($facts, [$row]);
$diff = static function($before, $after): array {
    return EZ2_Managed_Inventory_Diff::compare($before, $after);
};
$clean = $diff($base, $base);
$check($clean['status'] === 'NO_MANAGED_CHANGES_UNTRUSTED_BASELINE'
    && $clean['change_count'] === 0 && $clean['can_apply'] === false
    && $clean['baseline_trusted'] === false && $clean['same_site_attested'] === false,
    'matching observations are not attestation');
$check($diff(null, $base)['status'] === 'BLOCKED_MANAGED_OBSERVATION_DIFF',
    'missing baseline');
foreach ([
    ['title' => 'Owner edit'], ['body' => 'Owner changed body'],
    ['elementor_data' => '[{"id":"abc","settings":{"text":"edited"}}]'],
    ['page_settings' => ['hide_title' => 'no']], ['status' => 'publish'],
] as $change) {
    $current = EZ2_Managed_Inventory::evaluate($facts, [array_replace($row, $change)]);
    $result = $diff($base, $current);
    $check($result['status'] === 'MANAGED_CHANGES_OBSERVED'
        && $result['changes'] === [['key' => 'ez2-home', 'kind' => 'content_fingerprint_changed']]
        && $result['owner_edits_proven'] === false
        && !str_contains(json_encode($result), 'Owner changed body'),
        'content fingerprint change');
}
$other = array_replace($row, ['id' => 13, 'key' => 'ez2-about']);
$withOther = EZ2_Managed_Inventory::evaluate($facts, [$row, $other]);
$added = $diff($base, $withOther);
$check($added['changes'] === [['key' => 'ez2-about', 'kind' => 'added_since_observation']],
    'added key');
$missing = $diff($withOther, $base);
$check($missing['changes'] === [['key' => 'ez2-about', 'kind' => 'missing_since_observation']],
    'missing key');
$renumbered = EZ2_Managed_Inventory::evaluate($facts, [array_replace($row, ['id' => 33])]);
$check($diff($base, $renumbered)['changes'][0]['kind'] === 'managed_identity_changed',
    'identity changed');
$empty = EZ2_Managed_Inventory::evaluate($facts, []);
$check($diff($empty, $empty)['status'] === 'NO_MANAGED_CHANGES_UNTRUSTED_BASELINE',
    'empty inventory');
$reject = static function($candidate, string $name) use ($base, $diff, $check): void {
    $result = $diff($base, $candidate);
    $check($result['status'] === 'BLOCKED_MANAGED_OBSERVATION_DIFF'
        && $result['changes'] === [] && $result['can_apply'] === false
        && $result['private_content_emitted'] === false, $name);
};
foreach ([
    ['field' => 'target_site', 'value' => 'ez-bns-new-dev.local'],
    ['field' => 'mode', 'value' => 'write'],
    ['field' => 'private_content_emitted', 'value' => true],
    ['field' => 'installed_release_attested', 'value' => true],
    ['field' => 'owner_edit_baseline_trusted', 'value' => true],
    ['field' => 'can_apply', 'value' => true],
    ['field' => 'site_modified', 'value' => true],
    ['field' => 'managed_count', 'value' => 2],
    ['field' => 'status', 'value' => 'READY_TO_APPLY'],
] as $mutation) {
    $bad = $base; $bad[$mutation['field']] = $mutation['value'];
    $reject($bad, 'unsafe flag ' . $mutation['field']);
}
$bad = $base; $bad['extra_private_body'] = 'secret'; $reject($bad, 'extra top-level field');
$bad = $base; $bad['entries'][0]['body'] = 'secret'; $reject($bad, 'extra entry field');
$bad = $base; $bad['entries'][0]['key'] = '../private'; $reject($bad, 'unsafe key');
$bad = $base; $bad['entries'][0]['post_id'] = true; $reject($bad, 'boolean post id');
$bad = $base; $bad['entries'][0]['content_sha256'] = str_repeat('A', 64);
$reject($bad, 'uppercase hash');
$bad = $withOther; $bad['entries'] = array_reverse($bad['entries']);
$reject($bad, 'unsorted keys');
$bad = $withOther; $bad['entries'][1]['post_id'] = $bad['entries'][0]['post_id'];
$reject($bad, 'duplicate post id');
$bad = $base; $bad['entries'] = array_fill(0, 101, $base['entries'][0]);
$bad['managed_count'] = 101; $reject($bad, 'oversized inventory');
$bad = $base; $bad['issues'] = ['private']; $reject($bad, 'blocked observation');
echo "EZ2_MANAGED_AGENT_DIFF_PASS cases={$cases} read_only=true can_apply=false private_content_emitted=false\n";
