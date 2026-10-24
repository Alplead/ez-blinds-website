<?php
/** Offline synthetic regression: never connects to a WordPress site. */
define('EZ2_MANAGED_SNAPSHOT_LIBRARY_ONLY', true);
require_once __DIR__ . '/ez2_wp_managed_snapshot.php';
$cases = 0;
$facts = [
 'wp_cli'=>true,'environment'=>'development','expected_host'=>'ez2-review.local',
 'expected_elementor_version'=>'4.3.4','home'=>'http://ez2-review.local',
 'siteurl'=>'http://ez2-review.local','identity'=>'ez2-isolated-only',
 'multisite'=>false,'elementor_active'=>true,'elementor_loaded'=>true,
 'elementor_version'=>'4.3.4'
];
$row = [
 'id'=>123,'key'=>'ez2-home-hero','post_type'=>'page','status'=>'draft',
 'title'=>'Synthetic candidate','slug'=>'synthetic-candidate','body'=>'',
 'elementor_data'=>'[{"id":"abc123","elType":"container","settings":{},"elements":[]}]',
 'page_settings'=>['hide_title'=>'yes'],'elementor_version'=>'4.3.4'
];
function rejectSnapshot(callable $call): void {
 global $cases;
 try { $call(); }
 catch (RuntimeException $e) { ++$cases; return; }
 throw new RuntimeException('Unsafe snapshot accepted');
}
$one = Ez2ManagedSnapshot::evaluate($facts, [$row]);
if ($one['status'] !== 'MANAGED_CONTENT_DIGESTS_COLLECTED' || $one['managed_count'] !== 1
 || strlen($one['entries'][0]['content_sha256']) !== 64)
 throw new RuntimeException('Basic snapshot failed');
foreach (['private_content_emitted','installed_release_attested','localwp_verified',
          'owner_edit_baseline_trusted','deployment_authorized','applied'] as $flag)
 if ($one[$flag] !== false) throw new RuntimeException('Unsafe evidence claim');
++$cases;
$empty = Ez2ManagedSnapshot::evaluate($facts, []);
if ($empty['status'] !== 'NO_MANAGED_PAGES' || $empty['managed_count'] !== 0)
 throw new RuntimeException('Empty inventory mislabelled');
++$cases;
$edit = array_replace($row, ['title'=>'Owner changed title']);
if (Ez2ManagedSnapshot::evaluate($facts, [$edit])['entries'][0]['content_sha256']
 === $one['entries'][0]['content_sha256']) throw new RuntimeException('Title edit missed');
++$cases;
$edit = array_replace($row, ['elementor_data'=>'[{"id":"abc123","settings":{"text":"edited"}}]']);
if (Ez2ManagedSnapshot::evaluate($facts, [$edit])['entries'][0]['elementor_data_sha256']
 === $one['entries'][0]['elementor_data_sha256']) throw new RuntimeException('Elementor edit missed');
++$cases;
$edit = array_replace($row, ['page_settings'=>['hide_title'=>'no']]);
if (Ez2ManagedSnapshot::evaluate($facts, [$edit])['entries'][0]['content_sha256']
 === $one['entries'][0]['content_sha256']) throw new RuntimeException('Settings edit missed');
++$cases;
$second = array_replace($row, ['id'=>124,'key'=>'ez2-another-page']);
$both = Ez2ManagedSnapshot::evaluate($facts, [$row,$second]);
if ($both['managed_count'] !== 2 || $both['entries'][0]['key'] !== 'ez2-another-page')
 throw new RuntimeException('Sorted inventory failed');
++$cases;
foreach ([
 ['home'=>'https://ezbns.com.au'],['expected_host'=>'ez-bns-new-dev.local'],
 ['identity'=>'not-ez2'],['environment'=>'production']
] as $patch)
 rejectSnapshot(fn() => Ez2ManagedSnapshot::evaluate(array_replace($facts,$patch),[$row]));
rejectSnapshot(fn() => Ez2ManagedSnapshot::evaluate($facts,[$row,$row]));
rejectSnapshot(fn() => Ez2ManagedSnapshot::evaluate($facts,[$row,
 array_replace($row,['key'=>'ez2-another','id'=>123])]));
foreach ([
 ['key'=>'owner-private'],['post_type'=>'post'],['status'=>'inherit'],
 ['elementor_version'=>'4.3.5'],['elementor_data'=>'not json'],
 ['elementor_data'=>'[]'],['elementor_data'=>'{}'],
 ['elementor_data'=>str_repeat('x',256001)],['page_settings'=>'serialized'],
 ['id'=>0],['title'=>str_repeat('a',1001)]
] as $patch)
 rejectSnapshot(fn() => Ez2ManagedSnapshot::evaluate($facts,[array_replace($row,$patch)]));
$extra = $row; $extra['private_data']='forbidden';
rejectSnapshot(fn() => Ez2ManagedSnapshot::evaluate($facts,[$extra]));
if ($cases !== 24) throw new RuntimeException("Wrong regression count: $cases");
echo "EZ2_MANAGED_SNAPSHOT_PASS cases=$cases read_only=true private_content_emitted=false\n";
