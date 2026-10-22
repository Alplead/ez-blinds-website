<?php
require_once __DIR__.'/ez2_ci_import_reuse.php';
$media=[];$gallery=[];
for($i=1;$i<=4;$i++){
 $url='http://ez2-review.local/wp-content/uploads/2026/10/synthetic-'.$i.'.png';
 $media[]=['id'=>$i,'url'=>$url,'mime'=>'image/png','parent'=>10,'exists'=>true];
 $gallery[]=['id'=>$i,'url'=>$url];
}
$state=['post_id'=>10,'status'=>'draft','title'=>Ez2CiImportReuse::TITLE,'body'=>'',
 'mode'=>'builder','version'=>'4.3.4','settings'=>['hide_title'=>'yes'],
 'data'=>json_encode([['settings'=>['background_slideshow_gallery'=>$gallery]]],JSON_THROW_ON_ERROR),
 'media'=>$media,'source_sha256'=>str_repeat('a',64)];
$stamp=Ez2CiImportReuse::digest($state);$cases=0;
if(!Ez2CiImportReuse::verify($state,$stamp,'4.3.4'))throw new RuntimeException('valid repeat');$cases++;
function reject($state,$stamp){global $cases;try{Ez2CiImportReuse::verify($state,$stamp,'4.3.4');}catch(RuntimeException $e){$cases++;return;}throw new RuntimeException('unsafe reuse');}
reject($state,'');
$x=$state;$x['status']='publish';reject($x,$stamp);
$x=$state;$x['title']='Owner edited';reject($x,$stamp);
$x=$state;$x['body']='Owner notes';reject($x,$stamp);
$x=$state;$x['version']='4.3.5';reject($x,$stamp);
$x=$state;$x['settings']['hide_title']='no';reject($x,$stamp);
$x=$state;$x['data']='invalid json';reject($x,$stamp);
$x=$state;$x['media'][0]['parent']=11;reject($x,$stamp);
$x=$state;$x['media'][0]['exists']=false;reject($x,$stamp);
$x=$state;$x['media'][0]['url']='http://ezbns.com.au/private.png';reject($x,$stamp);
$x=$state;array_pop($x['media']);reject($x,$stamp);
$x=$state;$x['media'][1]['id']=1;reject($x,$stamp);
$x=$state;$x['data']=json_encode([['settings'=>['background_slideshow_gallery'=>[]]]]);reject($x,$stamp);
$x=$state;$x['media'][0]['mime']='image/webp';reject($x,$stamp);
$x=$state;$x['media'][0]['url']='http://ez2-review.local.evil.invalid/wp-content/uploads/s.png';reject($x,$stamp);
$x=$state;$x['source_sha256']=str_repeat('b',64);reject($x,$stamp);
if($cases!==17)throw new RuntimeException('cases='.$cases);
echo 'EZ2_CI_IMPORT_REUSE_PASS cases='.$cases."\n";
