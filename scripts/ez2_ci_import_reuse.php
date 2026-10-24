<?php
/** Idempotency guard for disposable synthetic Elementor CI drafts, not LP deployment. */
final class Ez2CiImportReuse {
 const TITLE = 'EZ2 synthetic CI Elementor hero - NOT FOR PUBLICATION';
 public static function candidates(array $byTitle, array $byFingerprint): array {
  $found=[];
  foreach (array_merge($byTitle,$byFingerprint) as $id) {
   if (!is_int($id) || $id<1) throw new RuntimeException('INVALID_DRAFT_ID');
   $found[$id]=$id;
  }
  if (count($found)>1) throw new RuntimeException('DUPLICATE_DRAFT_CONFLICT');
  return array_values($found);
 }
 public static function verifyFreshRollback(array $snapshot, string $fingerprint, string $version): bool {
  // Only the draft created by this invocation, before its marker was committed,
  // may be deleted. An existing marked/edited Owner draft is never rollback scope.
  if ($fingerprint !== '') throw new RuntimeException('MARKED_DRAFT_NOT_ROLLBACK_SCOPE');
  return self::verify($snapshot, self::digest($snapshot), $version);
 }
 public static function rollbackFresh(int $post): void {
  $snapshot=self::capture($post);
  self::verifyFreshRollback($snapshot,(string)get_post_meta($post,'_ez2_ci_import_fingerprint',true),ELEMENTOR_VERSION);
  $uploads=wp_upload_dir();
  $root=realpath($uploads['basedir']??'');
  if ($root===false) throw new RuntimeException('ROLLBACK_UPLOAD_ROOT');
  $paths=[];
  foreach ($snapshot['media'] as $media) {
   $path=get_attached_file($media['id']);
   $real=is_string($path)?realpath($path):false;
   if ($real===false || !str_starts_with($real,$root.DIRECTORY_SEPARATOR)
    || is_link($path) || !preg_match('/^ez2-ci-synthetic-hero-[1-4]\\.png$/D',basename($real))) {
    throw new RuntimeException('ROLLBACK_UNSAFE_ATTACHMENT');
   }
   $paths[]=$real;
  }
  $failed=false;
  foreach (array_reverse($snapshot['media']) as $media) {
   if (wp_delete_attachment($media['id'],true)===false) $failed=true;
  }
  foreach ($paths as $path) {
   if (is_file($path) && !@unlink($path)) $failed=true;
  }
  if (wp_delete_post($post,true)===false) $failed=true;
  if (get_post($post)) $failed=true;
  foreach ($snapshot['media'] as $media) if (get_post($media['id'])) $failed=true;
  foreach ($paths as $path) if (file_exists($path)) $failed=true;
  if ($failed) throw new RuntimeException('SYNTHETIC_POST_IMPORT_ROLLBACK_INCOMPLETE');
 }
 public static function capture(int $post): array {
  $page = get_post($post);
  if (!$page) throw new RuntimeException('DRAFT_MISSING');
  $ids = get_posts(['post_type'=>'attachment','post_status'=>'inherit','post_parent'=>$post,
   'posts_per_page'=>10,'fields'=>'ids','orderby'=>'ID','order'=>'ASC']);
  $media = [];
  foreach ($ids as $id) {
   $item = get_post((int)$id);
   $path = get_attached_file((int)$id);
   $media[] = ['id'=>(int)$id,'url'=>wp_get_attachment_url((int)$id),
    'mime'=>get_post_mime_type((int)$id),'parent'=>(int)$item->post_parent,
    'exists'=>is_string($path) && is_file($path)];
  }
  return ['post_id'=>$post,'status'=>$page->post_status,'title'=>$page->post_title,
   'body'=>$page->post_content,'mode'=>get_post_meta($post,'_elementor_edit_mode',true),
   'version'=>get_post_meta($post,'_elementor_version',true),
   'settings'=>get_post_meta($post,'_elementor_page_settings',true),
   'data'=>get_post_meta($post,'_elementor_data',true),'media'=>$media,
   'source_sha256'=>hash_file('sha256','/opt/ezb-design/ez2-home-hero-candidate.json')];
 }
 public static function digest(array $snapshot): string {
  return hash('sha256', json_encode($snapshot, JSON_THROW_ON_ERROR | JSON_UNESCAPED_SLASHES));
 }
 public static function verify(array $s, string $stored, string $expectedVersion): bool {
  if (!preg_match('/^[a-f0-9]{64}$/D', $stored)) throw new RuntimeException('UNMARKED_DRAFT');
  if (!is_string($s['source_sha256']??null) || !preg_match('/^[a-f0-9]{64}$/D',$s['source_sha256'])) throw new RuntimeException('SOURCE_CHANGED');
  if (!is_int($s['post_id']??null) || $s['post_id']<1 || ($s['status']??null)!=='draft'
   || ($s['title']??null)!==self::TITLE || ($s['body']??null)!==''
   || ($s['mode']??null)!=='builder' || ($s['version']??null)!==$expectedVersion
   || ($s['settings']??null)!==['hide_title'=>'yes'] || !is_string($s['data']??null)) {
   throw new RuntimeException('DRAFT_CHANGED');
  }
  try {$nodes=json_decode($s['data'],true,32,JSON_THROW_ON_ERROR);}
  catch (Throwable $e) {throw new RuntimeException('DRAFT_DATA_CHANGED');}
  if (!is_array($nodes) || count($nodes)!==1 || !is_array($nodes[0]['settings']['background_slideshow_gallery']??null)) {
   throw new RuntimeException('DRAFT_GALLERY_CHANGED');
  }
  $media=$s['media']??null;
  if (!is_array($media) || count($media)!==4) throw new RuntimeException('DRAFT_MEDIA_CHANGED');
  $gallery=[];$seen=[];
  foreach ($media as $item) {
   if (!is_array($item) || !is_int($item['id']??null) || $item['id']<1
    || isset($seen[$item['id']]) || ($item['parent']??null)!==$s['post_id']
    || ($item['mime']??null)!=='image/png' || ($item['exists']??null)!==true
    || !is_string($item['url']??null)
    || !preg_match('~^http://ez2-review\\.local/wp-content/uploads/[a-zA-Z0-9/_-]+\\.png$~D',$item['url'])) {
    throw new RuntimeException('DRAFT_MEDIA_CHANGED');
   }
   $seen[$item['id']]=true;
   $gallery[]=['id'=>$item['id'],'url'=>$item['url']];
  }
  if ($nodes[0]['settings']['background_slideshow_gallery']!==$gallery) {
   throw new RuntimeException('DRAFT_GALLERY_CHANGED');
  }
  if (!hash_equals($stored,self::digest($s))) throw new RuntimeException('DRAFT_OWNER_EDIT_CONFLICT');
  return true;
 }
}
