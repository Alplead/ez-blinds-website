<?php
/** Synthetic only; no WP, customer media, network or filesystem mutations. */
require_once __DIR__.'/../tools/ez2-delivery-agent/includes/ez2-plugin-runtime-readiness.php';
$cases=0;$check=static function($ok,$why)use(&$cases){if(!$ok)throw new RuntimeException($why);++$cases;};
$s=['status'=>'READ_ONLY_PREVIEW_READY','target_site'=>'ez2-isolated-only','mode'=>'read-only','issues'=>[],'can_apply'=>false,'site_modified'=>false];
$l=['schema_version'=>1,'target_site'=>'ez2-isolated-only','plugins'=>[[
'slug'=>'elementor','version'=>'4.3.4','entrypoint'=>'elementor/elementor.php',
'source'=>'wordpress.org','archive_sha256'=>str_repeat('a',64),'activate'=>true]]];
$i=['elementor/elementor.php'=>['version'=>'4.3.4','active'=>true,'network_active'=>false]];
$run=static fn($site=null,$lock=null,$installed=null)=>EZ2_Plugin_Runtime_Readiness::evaluate($site??$s,$lock??$l,$installed??$i);
$r=$run();$check($r['status']==='LOCAL_PLUGIN_MATCH_UNATTESTED' && $r['matching_count']===1,'match');
$check(!$r['candidate_lock_attested'] && !$r['can_apply'] && !$r['site_modified'],'read only');
$check(!str_contains(json_encode($r),str_repeat('a',64)),'digest redacted');
foreach(['status'=>'BLOCKED','target_site'=>'ez-bns-new-dev.local','mode'=>'write','issues'=>['bad'],'can_apply'=>true,'site_modified'=>true]as$k=>$v){
$b=$s;$b[$k]=$v;$check($run($b)['issues']===['ISOLATED_SITE_REQUIRED'],'site '.$k);}
foreach(['schema_version'=>2,'target_site'=>'ezbns.com.au','plugins'=>[]]as$k=>$v){
$b=$l;$b[$k]=$v;$check($run(null,$b)['issues']===['CANDIDATE_DEPENDENCY_LOCK_UNAVAILABLE'],'lock '.$k);}
foreach(['slug'=>'elementor-pro','version'=>'latest','entrypoint'=>'../bad.php','source'=>'evil.invalid','archive_sha256'=>str_repeat('0',64),'activate'=>false]as$k=>$v){
$b=$l;$b['plugins'][0][$k]=$v;$check($run(null,$b)['issues']===['INVALID_CANDIDATE_DEPENDENCY_LOCK'],'plugin '.$k);}
$b=$l;$b['plugins'][0]['extra']=1;$check($run(null,$b)['status']==='BLOCKED_PLUGIN_RUNTIME','extra');
$check($run(null,null,[])['issues']===['REQUIRED_PLUGIN_NOT_INSTALLED'],'missing');
foreach(['version'=>'4.3.5','active'=>false,'network_active'=>true]as$k=>$v){
$b=$i;$b['elementor/elementor.php'][$k]=$v;$check($run(null,null,$b)['issues']===['PLUGIN_VERSION_OR_ACTIVATION_MISMATCH'],'installed '.$k);}
$b=$l;$b['plugins'][0]['version']='4.3.5';$j=$i;$j['elementor/elementor.php']['version']='4.3.5';
$check($run(null,$b,$j)['status']==='LOCAL_PLUGIN_MATCH_UNATTESTED','pinned version');
echo "EZ2_PLUGIN_RUNTIME_READINESS_PASS cases={$cases} read_only=true can_apply=false localwp_touched=false\n";
