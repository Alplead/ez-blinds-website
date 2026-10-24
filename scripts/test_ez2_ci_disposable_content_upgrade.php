<?php
/** Offline guard tests for the CI-only executable content-upgrade path. */
define('EZ2_CI_DISPOSABLE_CONTENT_UPGRADE_LIBRARY_ONLY', true);
require_once __DIR__ . '/ez2_ci_disposable_content_upgrade.php';
$cases = 0;
$facts = ['wp_cli'=>true,'opt_in'=>'YES_SYNTHETIC_ONLY',
 'expected_host'=>'ez2-review.local','home'=>'http://ez2-review.local',
 'siteurl'=>'http://ez2-review.local','identity'=>'ez2-isolated-only',
 'environment'=>'development','multisite'=>false,'elementor_active'=>true,
 'elementor_loaded'=>true,'expected_version'=>'4.3.4','elementor_version'=>'4.3.4'];
if (Ez2CiDisposableContentUpgrade::gate($facts,'YES_DISPOSABLE_UPDATE_ONLY','')) throw new Exception('Valid CI gate rejected');
++$cases;
foreach ([['home'=>'https://ezbns.com.au'],['expected_host'=>'ez-bns-new-dev.local'],
 ['identity'=>'wrong'],['environment'=>'production'],['wp_cli'=>false],
 ['elementor_active'=>false],['elementor_version'=>'4.3.5']] as $patch) {
 if (!Ez2CiDisposableContentUpgrade::gate(array_replace($facts,$patch),'YES_DISPOSABLE_UPDATE_ONLY',''))
  throw new Exception('Unsafe CI environment accepted');
 ++$cases;
}
foreach (['','YES', 'YES_DISPOSABLE_CONFLICT_ONLY'] as $opt) {
 if (!Ez2CiDisposableContentUpgrade::gate($facts,$opt,'')) throw new Exception('Missing opt-in accepted');
 ++$cases;
}
if (!Ez2CiDisposableContentUpgrade::gate($facts,'YES_DISPOSABLE_UPDATE_ONLY','DELETE_ALL'))
 throw new Exception('Unapproved fault accepted');
++$cases;
foreach (['AFTER_DATA_WRITE','AFTER_FINGERPRINT_WRITE'] as $fault) {
 if (Ez2CiDisposableContentUpgrade::gate($facts,'YES_DISPOSABLE_UPDATE_ONLY',$fault))
  throw new Exception('Approved synthetic fault rejected');
 ++$cases;
}
$nodes = [['elType'=>'container','elements'=>[
 ['elType'=>'widget','widgetType'=>'heading','settings'=>['title'=>'Blinds & Shutters']],
 ['elType'=>'widget','widgetType'=>'button','settings'=>['link'=>['url'=>'/contact/']]]]]];
$r = Ez2CiDisposableContentUpgrade::transform($nodes);
if (!$r['changed'] || $r['nodes'][0]['elements'][0]['settings']['title'] !== Ez2CiDisposableContentUpgrade::UPGRADED)
 throw new Exception('Synthetic update failed');
++$cases;
$r2 = Ez2CiDisposableContentUpgrade::transform($r['nodes']);
if ($r2['changed'] || $r2['nodes'] !== $r['nodes']) throw new Exception('Update not idempotent');
++$cases;
foreach ([
 [], array_merge($nodes,$nodes),
 [['elType'=>'section','elements'=>$nodes[0]['elements']]],
 [['elType'=>'container','elements'=>[$nodes[0]['elements'][0]]]],
 [['elType'=>'container','elements'=>[
  ['elType'=>'widget','widgetType'=>'heading','settings'=>['title'=>'Owner edit']],
  $nodes[0]['elements'][1]]]],
 [['elType'=>'container','elements'=>[
  $nodes[0]['elements'][0],
  ['elType'=>'widget','widgetType'=>'button','settings'=>['link'=>['url'=>'https://example.invalid']]]]],
] as $bad) {
 try { Ez2CiDisposableContentUpgrade::transform($bad); }
 catch (RuntimeException $e) { ++$cases; continue; }
 throw new Exception('Unexpected content accepted');
}
if ($cases !== 22) throw new Exception("Unexpected case count: $cases");
echo "EZ2_CI_CONTENT_UPGRADE_GUARD_PASS cases=$cases synthetic_only=true\n";
