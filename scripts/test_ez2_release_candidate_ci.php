<?php
define('EZ2_RELEASE_CANDIDATE_CI_LIBRARY_ONLY',true);
require_once __DIR__.'/ez2_release_candidate_ci.php';
$f=['wp_cli'=>true,'opt_in'=>'YES_DISPOSABLE_RELEASE_ONLY','home'=>'http://localhost:8081',
 'siteurl'=>'http://localhost:8081','environment'=>'staging','multisite'=>false,
 'theme'=>'ezb-theme','core'=>true,'elementor'=>true,'loaded'=>true,
 'version'=>'4.3.4','indexed'=>'0','sha'=>str_repeat('a',40),'digest'=>str_repeat('b',64)];
$n=0;if(Ez2ReleaseCandidateCi::gate($f))throw new RuntimeException('VALID_GATE');$n++;
foreach([['wp_cli',false],['opt_in',''],['home','https://ezbns.com.au'],
 ['siteurl','http://ez-bns-new-dev.local'],['environment','production'],
 ['multisite',true],['theme','other'],['core',false],['elementor',false],
 ['loaded',false],['version','4.3.5'],['indexed','1'],
 ['sha','latest'],['digest','bad']] as [$k,$v]){
 $b=$f;$b[$k]=$v;if(!Ez2ReleaseCandidateCi::gate($b))throw new RuntimeException('UNSAFE_'.$k);$n++;
}
$d=json_decode(file_get_contents(__DIR__.'/../design/ez2-home-hero-candidate.json'),true,32,JSON_THROW_ON_ERROR);
if(count(Ez2ReleaseCandidateCi::compile($d)['content'])!==1)throw new RuntimeException('VALID_DOC');$n++;
$b=$d;$b['content'][0]['settings']['background_slideshow_slide_duration']=1;
try{Ez2ReleaseCandidateCi::compile($b);throw new RuntimeException('ACCEPTED');}
catch(RuntimeException $e){if($e->getMessage()==='ACCEPTED')throw $e;$n++;}
$b=$d;$b['content'][0]['settings']['background_slideshow_gallery'][0]['url']='https://ezbns.com.au/private.webp';
try{Ez2ReleaseCandidateCi::compile($b);throw new RuntimeException('ACCEPTED');}
catch(RuntimeException $e){if($e->getMessage()==='ACCEPTED')throw $e;$n++;}
if($n!==18)throw new RuntimeException('COUNT_'.$n);
echo "EZ2_RELEASE_ELEMENTOR_GUARD_PASS cases=18\n";
