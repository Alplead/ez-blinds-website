<?php
/** Repeat-safe entrypoint for disposable synthetic Elementor CI, never a LocalWP updater. */
define('EZ2_DISPOSABLE_IMPORT_LIBRARY_ONLY', true);
require_once __DIR__.'/ez2_disposable_import.php';
require_once __DIR__.'/ez2_ci_import_reuse.php';
try {
 if (!defined('WP_CLI') || !WP_CLI || !function_exists('get_option')) throw new RuntimeException('NO_WORDPRESS');
 if (!function_exists('is_plugin_active')) require_once ABSPATH.'wp-admin/includes/plugin.php';
 $facts=['wp_cli'=>true,'opt_in'=>getenv('EZ2_DISPOSABLE_IMPORT'),
  'expected_host'=>getenv('EZ2_EXPECTED_HOST'),'home'=>get_option('home'),'siteurl'=>get_option('siteurl'),
  'identity'=>get_option('ez2_site_identity'),'environment'=>wp_get_environment_type(),
  'multisite'=>is_multisite(),'elementor_active'=>is_plugin_active('elementor/elementor.php'),
  'elementor_loaded'=>did_action('elementor/loaded')>0,
  'expected_version'=>getenv('EZ2_EXPECTED_ELEMENTOR_VERSION'),
  'elementor_version'=>defined('ELEMENTOR_VERSION')?ELEMENTOR_VERSION:null];
 if ($bad=Ez2DisposableImport::gate($facts)) throw new RuntimeException('DISPOSABLE_GATE:'.implode(',',$bad));
 $source='/opt/ezb-design/ez2-home-hero-candidate.json';
 if(is_link($source)||!is_file($source)||filesize($source)>256000)throw new RuntimeException('CANDIDATE_SOURCE');
 $design=json_decode(file_get_contents($source),true,32,JSON_THROW_ON_ERROR);
 $fake=[];foreach(Ez2DisposableImport::SLOTS as $i=>$slot){$fake[$slot]=['id'=>$i+1,'url'=>'http://ez2-review.local/wp-content/uploads/synthetic-'.($i+1).'.png'];}
 Ez2DisposableImport::compile($design,$fake);
 $find=function():array{
  $statuses=['publish','future','draft','pending','private','trash'];
  $title=get_posts(['post_type'=>'page','post_status'=>$statuses,
   'title'=>Ez2CiImportReuse::TITLE,'posts_per_page'=>3,'fields'=>'ids']);
  // A renamed draft must still be found by its fingerprint marker and rejected, not duplicated.
  $marked=get_posts(['post_type'=>'page','post_status'=>$statuses,
   'meta_key'=>'_ez2_ci_import_fingerprint','posts_per_page'=>3,'fields'=>'ids']);
  return Ez2CiImportReuse::candidates($title,$marked);
 };
 $existing=$find();
 if (count($existing)>1) throw new RuntimeException('DUPLICATE_DRAFT_CONFLICT');
 if (count($existing)===1) {
  $post=(int)$existing[0];
  Ez2CiImportReuse::verify(Ez2CiImportReuse::capture($post),
   (string)get_post_meta($post,'_ez2_ci_import_fingerprint',true),ELEMENTOR_VERSION);
  echo 'EZ2_ELEMENTOR_SYNTHETIC_DRAFT_IMPORT_PASS version='.ELEMENTOR_VERSION.
   ' draft=true attachments=4 gallery=4 frontend_text=true reused=true visual_qa_verified=false localwp_installed=false deployment_authorized=false'."\n";
 } else {
  ob_start();
  try {Ez2DisposableImport::execute();$log=ob_get_clean();}
  catch(Throwable $e){ob_end_clean();throw $e;}
  $created=$find();
  if(count($created)!==1)throw new RuntimeException('DRAFT_LOOKUP_CONFLICT');
  $post=(int)$created[0];$state=Ez2CiImportReuse::capture($post);
  Ez2CiImportReuse::verify($state,Ez2CiImportReuse::digest($state),ELEMENTOR_VERSION);
  if(!update_post_meta($post,'_ez2_ci_import_fingerprint',Ez2CiImportReuse::digest($state)))
   throw new RuntimeException('DRAFT_FINGERPRINT_WRITE');
  echo str_replace(' visual_qa_verified=false',' reused=false visual_qa_verified=false',$log);
 }
} catch(Throwable $e) {
 fwrite(STDERR,'EZ2_ELEMENTOR_SYNTHETIC_DRAFT_IMPORT_FAIL: '.$e->getMessage()."\n");
 exit(1);
}
