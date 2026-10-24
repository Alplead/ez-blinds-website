<?php
/** Offline regression for read-only compiled-to-WordPress draft comparison. */
define('EZ2_CI_COMPILED_ROUNDTRIP_LIBRARY_ONLY', true);
require_once __DIR__ . '/ez2_ci_compiled_roundtrip.php';
$facts = ['wp_cli' => true, 'opt_in' => 'YES_SYNTHETIC_ONLY',
 'expected_host' => 'ez2-review.local', 'home' => 'http://ez2-review.local',
 'siteurl' => 'http://ez2-review.local', 'identity' => 'ez2-isolated-only',
 'environment' => 'development', 'multisite' => false,
 'elementor_active' => true, 'elementor_loaded' => true,
 'expected_version' => '4.3.4', 'elementor_version' => '4.3.4'];
$media=[];$gallery=[];
for($i=1;$i<=4;$i++){
 $url='http://ez2-review.local/wp-content/uploads/2026/10/synthetic-'.$i.'.png';
 $media[]=['id'=>$i,'url'=>$url,'mime'=>'image/png','parent'=>10,'exists'=>true];
 $gallery[]=['id'=>$i,'url'=>$url];
}
$nodes=[['id'=>'e2a10001','elType'=>'container','settings'=>['background_slideshow_gallery'=>$gallery],'elements'=>[]]];
$compiled=['title'=>'EZ2 Home Hero - Unpublished Owner Review Candidate','type'=>'page',
 'version'=>'4.3.4','page_settings'=>['hide_title'=>'yes'],'content'=>$nodes];
$state=['post_id'=>10,'status'=>'draft','title'=>Ez2CiImportReuse::TITLE,'body'=>'',
 'mode'=>'builder','version'=>'4.3.4','settings'=>['hide_title'=>'yes'],
 'data'=>json_encode($nodes,JSON_THROW_ON_ERROR),'media'=>$media,'source_sha256'=>str_repeat('a',64)];
$stamp=Ez2CiImportReuse::digest($state);$cases=0;
$report=Ez2CiCompiledRoundtrip::check($facts,$state,$stamp,$compiled);
if($report['status']!=='DISPOSABLE_COMPILED_WORDPRESS_ROUNDTRIP_PASS'
 || $report['media_slots']!==4 || $report['applied']!==false
 || $report['deployment_authorized']!==false)throw new RuntimeException('VALID_REJECTED');
$cases++;
function rejectRoundtrip($facts,$state,$stamp,$compiled) {
 global $cases;
 try { Ez2CiCompiledRoundtrip::check($facts,$state,$stamp,$compiled); }
 catch(Throwable $e){$cases++;return;}
 throw new RuntimeException('UNSAFE_ROUNDTRIP_ACCEPTED');
}
$x=$facts;$x['home']='https://ezbns.com.au';rejectRoundtrip($x,$state,$stamp,$compiled);
$x=$facts;$x['expected_host']='ez-bns-new-dev.local';rejectRoundtrip($x,$state,$stamp,$compiled);
$x=$facts;$x['environment']='production';rejectRoundtrip($x,$state,$stamp,$compiled);
$x=$facts;$x['wp_cli']=false;rejectRoundtrip($x,$state,$stamp,$compiled);
rejectRoundtrip($facts,$state,'',$compiled);
$x=$state;$x['title']='Owner edit';rejectRoundtrip($facts,$x,$stamp,$compiled);
$x=$compiled;$x['content'][0]['settings']['background_slideshow_gallery'][0]['id']=99;rejectRoundtrip($facts,$state,$stamp,$x);
$x=$compiled;$x['content'][0]['settings']['background_slideshow_gallery'][0]['url']='http://ezbns.com.au/a.png';rejectRoundtrip($facts,$state,$stamp,$x);
$x=$compiled;$x['content'][0]['settings']['background_slideshow_gallery'][0]['url']='ez2-media://home-hero-one';rejectRoundtrip($facts,$state,$stamp,$x);
$x=$compiled;$x['version']='4.3.5';rejectRoundtrip($facts,$state,$stamp,$x);
$x=$compiled;$x['extra']=true;rejectRoundtrip($facts,$state,$stamp,$x);
$x=$state;$x['media'][0]['exists']=false;rejectRoundtrip($facts,$x,$stamp,$compiled);
$x=$state;$x['data']=json_encode([]);rejectRoundtrip($facts,$x,$stamp,$compiled);
$x=$compiled;array_pop($x['content'][0]['settings']['background_slideshow_gallery']);rejectRoundtrip($facts,$state,$stamp,$x);
if($cases!==15)throw new RuntimeException('cases='.$cases);
echo "EZ2_CI_COMPILED_ROUNDTRIP_GUARD_PASS cases=$cases\n";
