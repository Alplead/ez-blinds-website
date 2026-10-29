<?php
/** CI-only exact-head Elementor candidate roundtrip in disposable release WordPress. */
define('EZ2_DISPOSABLE_IMPORT_LIBRARY_ONLY',true);
define('EZ2_CI_BATCH_CONTENT_LIBRARY_ONLY',true);
require_once __DIR__.'/ez2_disposable_import.php';
require_once __DIR__.'/ez2_ci_batch_content.php';
final class Ez2ReleaseCandidateCi {
 const HOME='http://localhost:8081', TITLE='EZ2 synthetic release candidate - NEVER PUBLISH';
 const MARKER='_ez2_ci_release_candidate_source_sha';
 /** A renamed/Owner-edited CI draft must block re-import rather than be duplicated. */
 static function candidateConflicts(array $byTitle,array $byMarker):bool {
  foreach(array_merge($byTitle,$byMarker) as $id)
   if(!is_int($id)||$id<1)throw new RuntimeException('INVALID_EXISTING_CANDIDATE_ID');
  return count($byTitle)>0||count($byMarker)>0;
 }
 static function gate(array $f):array {
  $expected=['wp_cli'=>true,'opt_in'=>'YES_DISPOSABLE_RELEASE_ONLY','home'=>self::HOME,
   'siteurl'=>self::HOME,'environment'=>'staging','multisite'=>false,
   'theme'=>'ezb-theme','core'=>true,'elementor'=>true,'loaded'=>true,
   'version'=>'4.3.4','indexed'=>'0'];
  $bad=[];foreach($expected as $k=>$v)if(($f[$k]??null)!==$v)$bad[]=$k;
  if(!is_string($f['sha']??null)||!preg_match('/^[a-f0-9]{40}$/D',$f['sha']))$bad[]='sha';
  if(!is_string($f['digest']??null)||!preg_match('/^[a-f0-9]{64}$/D',$f['digest']))$bad[]='digest';
  return $bad;
 }
 static function compile(array $doc):array {
  $media=[];foreach(Ez2DisposableImport::SLOTS as $i=>$s)
   $media[$s]=['id'=>$i+1,'url'=>'http://ez2-review.local/wp-content/uploads/synthetic-'.($i+1).'.png'];
  return Ez2DisposableImport::compile($doc,$media);
 }
 static function execute():void {
  if(!defined('WP_CLI')||!WP_CLI||!function_exists('get_option'))throw new RuntimeException('CLI_ONLY');
  if(!function_exists('is_plugin_active'))require_once ABSPATH.'wp-admin/includes/plugin.php';
  $f=['wp_cli'=>true,'opt_in'=>getenv('EZ2_CI_RELEASE_IMPORT'),
   'home'=>get_option('home'),'siteurl'=>get_option('siteurl'),
   'environment'=>wp_get_environment_type(),'multisite'=>is_multisite(),
   'theme'=>get_option('stylesheet'),'core'=>is_plugin_active('ezb-core/ezb-core.php'),
   'elementor'=>is_plugin_active('elementor/elementor.php'),
   'loaded'=>did_action('elementor/loaded')>0,
   'version'=>defined('ELEMENTOR_VERSION')?ELEMENTOR_VERSION:null,
   'indexed'=>(string)get_option('blog_public'),
   'sha'=>getenv('EZ2_CI_RELEASE_SHA'),'digest'=>getenv('EZ2_CI_RELEASE_DIGEST')];
  if($bad=self::gate($f))throw new RuntimeException('CI_GATE:'.implode(',',$bad));
  $metadata='/release/RELEASE_METADATA.txt';$candidate='/release/ez2-runtime-candidate.json';
  foreach([$metadata,$candidate] as $path)
   if(is_link($path)||!is_file($path)||filesize($path)<1||filesize($path)>256000)
    throw new RuntimeException('RELEASE_INPUT');
  if(!preg_match('/^commit=([a-f0-9]{40})$/m',file_get_contents($metadata),$match)
   ||$match[1]!==$f['sha'])throw new RuntimeException('RELEASE_SHA');
  if(!hash_equals($f['digest'],hash_file('sha256',$candidate)))
   throw new RuntimeException('CANDIDATE_DIGEST');
  $doc=json_decode(file_get_contents($candidate),true,32,JSON_THROW_ON_ERROR);
  if(!is_array($doc))throw new RuntimeException('CANDIDATE_TYPE');
  self::compile($doc);
  $statuses=['publish','future','draft','pending','private','trash'];
  $byTitle=get_posts(['post_type'=>'page','post_status'=>$statuses,'title'=>self::TITLE,
   'posts_per_page'=>3,'fields'=>'ids']);
  $byMarker=get_posts(['post_type'=>'page','post_status'=>$statuses,'meta_key'=>self::MARKER,
   'posts_per_page'=>3,'fields'=>'ids']);
  if(self::candidateConflicts($byTitle,$byMarker))
   throw new RuntimeException('EXISTING_OR_OWNER_EDITED_CI_DRAFT');
  $fault=getenv('EZ2_CI_RELEASE_FAULT')?:'';
  if(!in_array($fault,['','AFTER_FIRST_ATTACHMENT','AFTER_META'],true))
   throw new RuntimeException('INVALID_FAULT');
  $pixel=base64_decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/qX8AAAAASUVORK5CYII=',true);
  if(!$pixel)throw new RuntimeException('SYNTHETIC_PIXEL');
  $post=0;$ids=[];$files=[];$ok=false;
  try {
   $post=wp_insert_post(['post_type'=>'page','post_status'=>'draft','post_title'=>self::TITLE],true);
   if(is_wp_error($post)||!$post)throw new RuntimeException('DRAFT_INSERT');
   if(!update_post_meta($post,self::MARKER,$f['sha']))
    throw new RuntimeException('DRAFT_SOURCE_MARKER');
   $media=[];
   foreach(Ez2DisposableImport::SLOTS as $i=>$slot){
    $upload=wp_upload_bits('ez2-ci-release-'.($i+1).'.png',null,$pixel);
    if(!empty($upload['error'])||empty($upload['file']))throw new RuntimeException('UPLOAD');
    $files[]=$upload['file'];
    $id=wp_insert_attachment(['post_mime_type'=>'image/png','post_status'=>'inherit',
     'post_title'=>'Synthetic CI image '.($i+1)],$upload['file'],$post,true);
    if(is_wp_error($id)||!$id)throw new RuntimeException('ATTACHMENT');
    $ids[]=(int)$id;$url=wp_get_attachment_url($id);
    if(!is_string($url)||!str_starts_with($url,self::HOME.'/wp-content/uploads/'))
     throw new RuntimeException('MEDIA_URL');
    $media[$slot]=['id'=>(int)$id,'url'=>$url];
    if($fault==='AFTER_FIRST_ATTACHMENT'&&count($ids)===1)
     throw new RuntimeException('INJECTED_CI_FAULT');
   }
   $compiled=self::compile($doc);
   $compiled['content'][0]['settings']['background_slideshow_gallery']=array_values($media);
   update_post_meta($post,'_elementor_edit_mode','builder');
   update_post_meta($post,'_elementor_version',ELEMENTOR_VERSION);
   update_post_meta($post,'_elementor_data',wp_slash(wp_json_encode($compiled['content'],JSON_THROW_ON_ERROR)));
   update_post_meta($post,'_elementor_page_settings',$compiled['page_settings']);
   if($fault==='AFTER_META')throw new RuntimeException('INJECTED_CI_FAULT');
   $elementor=\Elementor\Plugin::instance();$page=$elementor->documents->get($post);
   $loaded=$page?$page->get_elements_data():null;
   if(!is_array($loaded)||count($loaded)!==1
    ||($loaded[0]['settings']['background_slideshow_gallery']??null)!==array_values($media)
    ||get_post_status($post)!=='draft')throw new RuntimeException('ROUNDTRIP');
   $html=$elementor->frontend->get_builder_content_for_display($post,true);
   if(!is_string($html)||!str_contains($html,'Request a Quote'))
    throw new RuntimeException('FRONTEND');
   // Exercise the exact-head release candidate with real disposable WordPress
   // attachment IDs, page settings, and reversible metadata writes.
   $token=bin2hex(random_bytes(16));
   $renamed=wp_update_post(['ID'=>$post,'post_title'=>EZ2_CI_Batch_Content::TITLE],true);
   if(is_wp_error($renamed)||$renamed!==$post
    ||!update_post_meta($post,EZ2_CI_Batch_Content::MARK,$token))
    throw new RuntimeException('BATCH_DRAFT_SETUP');
   $original=EZ2_CI_Batch_Content::read($post,$token);
   $originalSettings=EZ2_CI_Batch_Content::settings($post,$token);
   $changed=$compiled['content'];
   $changed[0]['elements'][0]['settings']['title']='Blinds & Shutters - Synthetic CI Update';
   $next=wp_json_encode($changed,JSON_THROW_ON_ERROR);
   $nextSettings=['hide_title'=>'no'];
   $plan=[['id'=>$post,'expected'=>hash('sha256',$original),'next'=>$next,
    'settings_expected'=>hash('sha256',serialize($originalSettings)),
    'settings_next'=>$nextSettings]];
   try {
    EZ2_CI_Batch_Content::apply($plan,$token,'AFTER_FIRST');
    throw new RuntimeException('MEDIA_BATCH_FAULT_NOT_INJECTED');
   } catch(RuntimeException $error) {
    if($error->getMessage()!=='INJECTED_CI_BATCH_FAULT') throw $error;
   }
   if(EZ2_CI_Batch_Content::read($post,$token)!==$original
    ||EZ2_CI_Batch_Content::settings($post,$token)!==$originalSettings)
    throw new RuntimeException('MEDIA_BATCH_FAULT_ROLLBACK');
   if(EZ2_CI_Batch_Content::apply($plan,$token)!==1
    ||EZ2_CI_Batch_Content::read($post,$token)!==$next
    ||EZ2_CI_Batch_Content::settings($post,$token)!==$nextSettings
    ||($changed[0]['settings']['background_slideshow_gallery']??null)!==array_values($media))
    throw new RuntimeException('MEDIA_BATCH_APPLY');
   $same=[['id'=>$post,'expected'=>hash('sha256',$next),'next'=>$next,
    'settings_expected'=>hash('sha256',serialize($nextSettings)),
    'settings_next'=>$nextSettings]];
   if(EZ2_CI_Batch_Content::apply($same,$token)!==0)
    throw new RuntimeException('MEDIA_BATCH_NOT_IDEMPOTENT');
   $restore=[['id'=>$post,'expected'=>hash('sha256',$next),'next'=>$original,
    'settings_expected'=>hash('sha256',serialize($nextSettings)),
    'settings_next'=>$originalSettings]];
   if(EZ2_CI_Batch_Content::apply($restore,$token)!==1
    ||EZ2_CI_Batch_Content::read($post,$token)!==$original
    ||EZ2_CI_Batch_Content::settings($post,$token)!==$originalSettings)
    throw new RuntimeException('MEDIA_BATCH_RESTORE');
   $ok=true;
  } finally {
   $failed=false;
   foreach(array_reverse($ids) as $id)if(wp_delete_attachment($id,true)===false||get_post($id))$failed=true;
   foreach($files as $file){if(is_file($file)&&!@unlink($file))$failed=true;if(file_exists($file))$failed=true;}
   if(is_int($post)&&$post>0&&(wp_delete_post($post,true)===false||get_post($post)))$failed=true;
   if($failed)throw new RuntimeException('CI_ROLLBACK_INCOMPLETE');
  }
  if(!$ok)throw new RuntimeException('INCOMPLETE');
  echo "EZ2_RELEASE_ELEMENTOR_ROUNDTRIP_PASS exact_head=true gallery=4 draft_cleaned=true uploads_cleaned=true publication=false localwp_touched=false one_click_complete=false\n";
 }
}
if(!defined('EZ2_RELEASE_CANDIDATE_CI_LIBRARY_ONLY')){
 try{Ez2ReleaseCandidateCi::execute();}
 catch(Throwable $e){fwrite(STDERR,'EZ2_RELEASE_ELEMENTOR_ROUNDTRIP_FAIL: '.$e->getMessage()."\n");exit(1);}
}
