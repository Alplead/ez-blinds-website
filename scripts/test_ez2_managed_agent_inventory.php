<?php
/** Offline isolated-EZ2 managed inventory tests. No WordPress or private media. */
require_once __DIR__ . '/../tools/ez2-delivery-agent/includes/ez2-managed-inventory.php';
$cases = 0;
$facts = [
    'site_status' => 'READ_ONLY_PREVIEW_READY', 'elementor_active' => true,
    'elementor_loaded' => true, 'elementor_version' => '4.3.4',
];
$row = [
    'id' => 12, 'key' => 'ez2-home', 'post_type' => 'page',
    'status' => 'draft', 'title' => 'Synthetic', 'slug' => 'synthetic',
    'body' => 'synthetic private body',
    'elementor_data' => '[{"id":"abc","elType":"container","settings":{},"elements":[]}]',
    'page_settings' => ['hide_title' => 'yes'], 'elementor_version' => '4.3.4',
];
$assertBlocked = static function(array $f, array $rows) use (&$cases): void {
    $result = EZ2_Managed_Inventory::evaluate($f, $rows);
    if ($result['status'] !== 'BLOCKED_MANAGED_CONTENT_INVENTORY'
        || $result['entries'] !== [] || $result['can_apply'] !== false
        || $result['site_modified'] !== false || $result['private_content_emitted'] !== false)
        throw new RuntimeException('Unsafe inventory accepted');
    ++$cases;
};
$valid = EZ2_Managed_Inventory::evaluate($facts, [$row]);
if ($valid['status'] !== 'MANAGED_DIGESTS_OBSERVED' || $valid['managed_count'] !== 1
    || strlen($valid['entries'][0]['content_sha256']) !== 64
    || str_contains(json_encode($valid), 'synthetic private body')
    || $valid['can_apply'] !== false || $valid['installed_release_attested'] !== false)
    throw new RuntimeException('Valid inventory failed or leaked private data');
++$cases;
$empty = EZ2_Managed_Inventory::evaluate($facts, []);
if ($empty['status'] !== 'NO_MANAGED_PAGES' || $empty['managed_count'] !== 0)
    throw new RuntimeException('Empty inventory failed');
++$cases;
foreach ([
    ['title' => 'Owner title edit'],
    ['page_settings' => ['hide_title' => 'no']],
    ['body' => 'Owner content edit'],
    ['elementor_data' => '[{"id":"abc","settings":{"title":"changed"}}]'],
] as $patch) {
    $changed = EZ2_Managed_Inventory::evaluate($facts, [array_replace($row, $patch)]);
    if ($changed['entries'][0]['content_sha256'] === $valid['entries'][0]['content_sha256'])
        throw new RuntimeException('Owner edit fingerprint unchanged');
    ++$cases;
}
$other = array_replace($row, ['id' => 13, 'key' => 'ez2-about']);
$sorted = EZ2_Managed_Inventory::evaluate($facts, [$row, $other]);
if ($sorted['entries'][0]['key'] !== 'ez2-about' || $sorted['managed_count'] !== 2)
    throw new RuntimeException('Inventory ordering failed');
++$cases;
foreach ([
    ['site_status' => 'BLOCKED'],
    ['elementor_active' => false],
    ['elementor_loaded' => false],
    ['elementor_version' => '4.3.5'],
] as $patch) $assertBlocked(array_replace($facts, $patch), [$row]);
$assertBlocked($facts, [$row, $row]);
$assertBlocked($facts, [$row, array_replace($row, ['key' => 'ez2-other'])]);
foreach ([
    ['id' => 0], ['key' => 'owner-private'], ['post_type' => 'post'],
    ['status' => 'inherit'], ['elementor_version' => '4.3.5'],
    ['elementor_data' => '[]'], ['elementor_data' => '{'],
    ['page_settings' => 'bad'], ['title' => str_repeat('x', 1001)],
] as $patch) $assertBlocked($facts, [array_replace($row, $patch)]);
$extra = $row; $extra['customer_email'] = 'not-for-export';
$assertBlocked($facts, [$extra]);
$assertBlocked($facts, array_fill(0, 101, $row));
if ($cases !== 24) throw new RuntimeException("Unexpected case count: $cases");
echo "EZ2_MANAGED_AGENT_INVENTORY_PASS cases={$cases} private_content_emitted=false can_apply=false\n";
