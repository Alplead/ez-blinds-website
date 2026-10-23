<?php
/** Offline regression: no WordPress or private media required. */
define('EZ2_CI_MEDIA_INVENTORY_LIBRARY_ONLY', true);
require_once __DIR__ . '/ez2_ci_media_inventory.php';
$facts = ['wp_cli'=>true, 'opt_in'=>'YES_SYNTHETIC_ONLY',
 'expected_host'=>'ez2-review.local', 'home'=>'http://ez2-review.local',
 'siteurl'=>'http://ez2-review.local', 'identity'=>'ez2-isolated-only',
 'environment'=>'development', 'multisite'=>false, 'elementor_active'=>true,
 'elementor_loaded'=>true, 'expected_version'=>'4.3.4', 'elementor_version'=>'4.3.4'];
$media=[];$gallery=[];
for ($i=1;$i<=4;$i++) {
 $url='http://ez2-review.local/wp-content/uploads/2026/10/ez2-ci-synthetic-hero-'.$i.'.png';
 $media[]=['id'=>$i,'url'=>$url,'mime'=>'image/png','parent'=>10,'exists'=>true];
 $gallery[]=['id'=>$i,'url'=>$url];
}
$state=['post_id'=>10,'status'=>'draft','title'=>Ez2CiImportReuse::TITLE,'body'=>'',
 'mode'=>'builder','version'=>'4.3.4','settings'=>['hide_title'=>'yes'],
 'data'=>json_encode([['settings'=>['background_slideshow_gallery'=>$gallery]]],JSON_THROW_ON_ERROR),
 'media'=>$media,'source_sha256'=>str_repeat('a',64)];
$stamp=Ez2CiImportReuse::digest($state);
$map=Ez2CiMediaInventory::map($facts,$state,$stamp);
if ($map['schema_version']!==1 || $map['host']!=='ez2-review.local'
 || array_keys($map['slots'])!==Ez2DisposableImport::SLOTS
 || $map['slots']['home-hero-four']['id']!==4) throw new RuntimeException('valid map');
$cases=1;
function rejectInventory($facts,$state,$stamp) {
 global $cases;
 try { Ez2CiMediaInventory::map($facts,$state,$stamp); }
 catch (RuntimeException $e) { $cases++; return; }
 throw new RuntimeException('Unsafe synthetic media inventory accepted');
}
rejectInventory([...$facts,'identity'=>'ez-bns-new-dev.local'],$state,$stamp);
rejectInventory([...$facts,'home'=>'https://ezbns.com.au'],$state,$stamp);
rejectInventory([...$facts,'environment'=>'production'],$state,$stamp);
rejectInventory([...$facts,'opt_in'=>''],$state,$stamp);
rejectInventory([...$facts,'elementor_version'=>'4.3.5'],$state,$stamp);
rejectInventory($facts,$state,'');
$edited=$state;$edited['body']='Owner change';rejectInventory($facts,$edited,$stamp);
$edited=$state;$edited['media'][0]['url']='https://evil.invalid/p.png';rejectInventory($facts,$edited,$stamp);
$edited=$state;$edited['media'][1]['id']=1;rejectInventory($facts,$edited,$stamp);
$edited=$state;array_pop($edited['media']);rejectInventory($facts,$edited,$stamp);
$edited=$state;$edited['data']='[]';rejectInventory($facts,$edited,$stamp);
$edited=$state;$edited['status']='publish';rejectInventory($facts,$edited,$stamp);
if ($cases!==13) throw new RuntimeException('cases='.$cases);
echo 'EZ2_CI_MEDIA_INVENTORY_PASS cases='.$cases."\n";
