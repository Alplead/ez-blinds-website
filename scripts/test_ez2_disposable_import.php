<?php
define('EZ2_DISPOSABLE_IMPORT_LIBRARY_ONLY',true);require_once __DIR__.'/ez2_disposable_import.php';
$cases=0;$good=['wp_cli'=>true,'opt_in'=>'YES_SYNTHETIC_ONLY','expected_host'=>'ez2-review.local','home'=>'http://ez2-review.local','siteurl'=>'http://ez2-review.local','identity'=>'ez2-isolated-only','environment'=>'development','multisite'=>false,'elementor_active'=>true,'elementor_loaded'=>true,'expected_version'=>'4.3.4','elementor_version'=>'4.3.4'];
foreach(['4.3.4','4.3.5'] as $v){$f=$good;$f['expected_version']=$f['elementor_version']=$v;if(Ez2DisposableImport::gate($f))throw new RuntimeException('valid gate');$cases++;}
foreach([['wp_cli',false],['opt_in',''],['expected_host','ez-bns-new-dev.local'],['home','https://ezbns.com.au'],['siteurl','http://t2-ez-blinds-shutters.local'],['identity','production'],['environment','production'],['multisite',true],['elementor_active',false],['elementor_loaded',false],['expected_version','latest'],['elementor_version','4.3.5']] as [$k,$v]){$f=$good;$f[$k]=$v;if(!Ez2DisposableImport::gate($f))throw new RuntimeException('unsafe gate '.$k);$cases++;}
$d=json_decode(file_get_contents(__DIR__.'/../design/ez2-home-hero-candidate.json'),true,32,JSON_THROW_ON_ERROR);$m=[];
foreach(Ez2DisposableImport::SLOTS as $i=>$s)$m[$s]=['id'=>$i+1,'url'=>'http://ez2-review.local/wp-content/uploads/synthetic-'.($i+1).'.png'];
if(Ez2DisposableImport::compile($d,$m)['content'][0]['settings']['background_slideshow_gallery']!==array_values($m))throw new RuntimeException('gallery');$cases++;
function rejectDoc($d,$m){global $cases;try{Ez2DisposableImport::compile($d,$m);}catch(RuntimeException $e){$cases++;return;}throw new RuntimeException('unsafe compile');}
$b=$d;$b['content'][0]['settings']['background_slideshow_slide_duration']=100;rejectDoc($b,$m);
$b=$d;$b['content'][0]['settings']['background_slideshow_gallery'][0]['url']='https://example.org/a.png';rejectDoc($b,$m);
$b=$d;$b['content'][0]['elements'][1]['settings']['link']['url']='https://example.org';rejectDoc($b,$m);
$b=$m;$b['home-hero-one']['url']='https://ezbns.com.au/customer.jpg';rejectDoc($d,$b);
$b=$m;$b['home-hero-one']['url']='http://ez2-review.local.evil.invalid/wp-content/uploads/a.png';rejectDoc($d,$b);
$b=$m;unset($b['home-hero-two']);rejectDoc($d,$b);
$b=$m;$b['home-hero-one']['id']='1';rejectDoc($d,$b);
$b=$d;$b['content'][0]['elements'][]=$d['content'][0]['elements'][0];rejectDoc($b,$m);
$source=file_get_contents(__DIR__.'/ez2_disposable_import.php');
if(str_contains($source,'wp_get_post_status(')||!str_contains($source,'get_post_status($post)'))throw new RuntimeException('post status API regression');$cases++;
if(!str_contains($source,"'AFTER_ELEMENTOR_META'")||!str_contains($source,"if(\$fault==='AFTER_ELEMENTOR_META')"))throw new RuntimeException('late fault injection guard');$cases++;
if($cases!==25)throw new RuntimeException('case count '.$cases);echo "EZ2_DISPOSABLE_IMPORT_GUARD_PASS cases=$cases\n";
