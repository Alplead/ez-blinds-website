<?php
/** Isolated synthetic Elementor draft import; NEVER a deployment path. */
final class Ez2DisposableImport {
const HOST='ez2-review.local', VERSIONS=['4.3.4','4.3.5'], SLOTS=['home-hero-one','home-hero-two','home-hero-three','home-hero-four'];
static function gate(array $f):array {
 $want=['wp_cli'=>true,'opt_in'=>'YES_SYNTHETIC_ONLY','expected_host'=>self::HOST,'home'=>'http://'.self::HOST,'siteurl'=>'http://'.self::HOST,'identity'=>'ez2-isolated-only','environment'=>'development','multisite'=>false,'elementor_active'=>true,'elementor_loaded'=>true];
 $bad=[];foreach($want as $k=>$v)if(($f[$k]??null)!==$v)$bad[]=$k;
 if(!in_array($f['expected_version']??null,self::VERSIONS,true)||($f['expected_version']??null)!==($f['elementor_version']??null))$bad[]='version';
 return $bad;
}
static function compile(array $d,array $media):array {
 if(array_keys($d)!==['title','type','version','page_settings','content']||$d['title']!=='EZ2 Home Hero - Unpublished Owner Review Candidate'||$d['type']!=='page'||$d['version']!=='4.3.4'||$d['page_settings']!==['hide_title'=>'yes']||count($d['content'])!==1)throw new RuntimeException('UNAPPROVED_DOCUMENT');
 $h=$d['content'][0];$settings=['content_width'=>'full','min_height'=>['unit'=>'vh','size'=>90],'background_background'=>'slideshow','background_slideshow_gallery'=>array_map(fn($s)=>['id'=>'','url'=>'ez2-media://'.$s],self::SLOTS),'background_slideshow_loop'=>'yes','background_slideshow_slide_duration'=>5000,'background_slideshow_slide_transition'=>'fade','background_slideshow_transition_duration'=>1200,'background_slideshow_ken_burns'=>'yes','background_slideshow_ken_burns_zoom_direction'=>'in','background_slideshow_size'=>'cover','background_overlay_background'=>'classic','background_overlay_color'=>'#000000','background_overlay_opacity'=>['unit'=>'px','size'=>0.45]];
 $heading=['id'=>'e2a10002','elType'=>'widget','widgetType'=>'heading','settings'=>['title'=>'Blinds & Shutters','header_size'=>'h1'],'elements'=>[]];
 $button=['id'=>'e2a10003','elType'=>'widget','widgetType'=>'button','settings'=>['text'=>'Request a Quote','link'=>['url'=>'/contact/']],'elements'=>[]];
 if(($h['id']??null)!=='e2a10001'||($h['elType']??null)!=='container'||($h['settings']??null)!==$settings||($h['elements']??null)!==[$heading,$button])throw new RuntimeException('UNAPPROVED_HERO');
 if(array_keys($media)!==self::SLOTS)throw new RuntimeException('MEDIA_SLOTS');
 foreach(self::SLOTS as $i=>$slot){$m=$media[$slot];if(!is_array($m)||array_keys($m)!==['id','url']||!is_int($m['id'])||$m['id']<1||!is_string($m['url'])||!preg_match('~^http://ez2-review\.local/wp-content/uploads/[a-zA-Z0-9/_-]+\.png$~D',$m['url']))throw new RuntimeException('UNSAFE_MEDIA');$h['settings']['background_slideshow_gallery'][$i]=$m;}
 $d['content'][0]=$h;return $d;
}
static function execute():void {
 if(!defined('ABSPATH')||!function_exists('get_option'))throw new RuntimeException('NO_WORDPRESS');
 if(!function_exists('is_plugin_active'))require_once ABSPATH.'wp-admin/includes/plugin.php';
 $f=['wp_cli'=>defined('WP_CLI')&&WP_CLI,'opt_in'=>getenv('EZ2_DISPOSABLE_IMPORT'),'expected_host'=>getenv('EZ2_EXPECTED_HOST'),'home'=>get_option('home'),'siteurl'=>get_option('siteurl'),'identity'=>get_option('ez2_site_identity'),'environment'=>wp_get_environment_type(),'multisite'=>is_multisite(),'elementor_active'=>is_plugin_active('elementor/elementor.php'),'elementor_loaded'=>did_action('elementor/loaded')>0,'expected_version'=>getenv('EZ2_EXPECTED_ELEMENTOR_VERSION'),'elementor_version'=>defined('ELEMENTOR_VERSION')?ELEMENTOR_VERSION:null];
 if($bad=self::gate($f))throw new RuntimeException('DISPOSABLE_GATE:'.implode(',',$bad));
 $path='/opt/ezb-design/ez2-home-hero-candidate.json';if(is_link($path)||!is_file($path)||filesize($path)>256000)throw new RuntimeException('CANDIDATE_SOURCE');
 $d=json_decode(file_get_contents($path),true,32,JSON_THROW_ON_ERROR);$fake=[];
 foreach(self::SLOTS as $i=>$s)$fake[$s]=['id'=>$i+1,'url'=>'http://'.self::HOST.'/wp-content/uploads/synthetic-'.($i+1).'.png'];
 self::compile($d,$fake); // Validate all design fields before first write.
 $post=wp_insert_post(['post_type'=>'page','post_status'=>'draft','post_title'=>'EZ2 synthetic CI Elementor hero - NOT FOR PUBLICATION','post_content'=>''],true);
 if(is_wp_error($post)||!$post)throw new RuntimeException('DRAFT_INSERT');
 $pixel=base64_decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/qX8AAAAASUVORK5CYII=',true);
 if(!$pixel)throw new RuntimeException('PIXEL');$media=[];
 foreach(self::SLOTS as $i=>$s){$upload=wp_upload_bits('ez2-ci-synthetic-hero-'.($i+1).'.png',null,$pixel);if(!empty($upload['error'])||empty($upload['file']))throw new RuntimeException('UPLOAD');
 $id=wp_insert_attachment(['post_mime_type'=>'image/png','post_title'=>'Synthetic CI image '.($i+1),'post_status'=>'inherit'],$upload['file'],$post,true);
 if(is_wp_error($id)||!$id)throw new RuntimeException('ATTACHMENT');
 $media[$s]=['id'=>(int)$id,'url'=>wp_get_attachment_url($id)];}
 $compiled=self::compile($d,$media);
 update_post_meta($post,'_elementor_edit_mode','builder');update_post_meta($post,'_elementor_version',ELEMENTOR_VERSION);
 update_post_meta($post,'_elementor_data',wp_slash(wp_json_encode($compiled['content'],JSON_THROW_ON_ERROR)));
 update_post_meta($post,'_elementor_page_settings',$compiled['page_settings']);
 $plugin=\Elementor\Plugin::instance();$document=$plugin->documents->get($post);
 if(!$document||!method_exists($document,'get_elements_data'))throw new RuntimeException('DOCUMENT');
 $loaded=$document->get_elements_data();
 if(!is_array($loaded)||count($loaded)!==1||($loaded[0]['settings']['background_slideshow_gallery']??null)!==$compiled['content'][0]['settings']['background_slideshow_gallery']||get_post_status($post)!=='draft')throw new RuntimeException('ROUNDTRIP');
 $html=$plugin->frontend->get_builder_content_for_display($post,true);
 if(!is_string($html)||!(str_contains($html,'Blinds &amp; Shutters')||str_contains($html,'Blinds & Shutters'))||!str_contains($html,'Request a Quote'))throw new RuntimeException('FRONTEND');
 echo 'EZ2_ELEMENTOR_SYNTHETIC_DRAFT_IMPORT_PASS version='.ELEMENTOR_VERSION.' draft=true attachments=4 gallery=4 frontend_text=true visual_qa_verified=false localwp_installed=false deployment_authorized=false'."\n";
}
}
if(!defined('EZ2_DISPOSABLE_IMPORT_LIBRARY_ONLY')){try{Ez2DisposableImport::execute();}catch(Throwable $e){fwrite(STDERR,'EZ2_ELEMENTOR_SYNTHETIC_DRAFT_IMPORT_FAIL: '.$e->getMessage()."\n");exit(1);}}
