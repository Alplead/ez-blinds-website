<?php
/** Read-only synthetic attachment-to-Elementor slot map for disposable EZ2 CI.
 * NEVER a LocalWP updater, media exporter or publication mechanism.
 */
if (!defined('EZ2_DISPOSABLE_IMPORT_LIBRARY_ONLY')) define('EZ2_DISPOSABLE_IMPORT_LIBRARY_ONLY', true);
require_once __DIR__ . '/ez2_disposable_import.php';
require_once __DIR__ . '/ez2_ci_import_reuse.php';
final class Ez2CiMediaInventory {
 public static function map(array $facts, array $snapshot, string $fingerprint): array {
  if ($bad = Ez2DisposableImport::gate($facts)) throw new RuntimeException('DISPOSABLE_GATE:' . implode(',', $bad));
  Ez2CiImportReuse::verify($snapshot, $fingerprint, $facts['expected_version']);
  $media = $snapshot['media'];
  if (count($media) !== count(Ez2DisposableImport::SLOTS)) throw new RuntimeException('MEDIA_COUNT');
  $slots = [];
  foreach (Ez2DisposableImport::SLOTS as $i => $slot) {
   $entry = $media[$i];
   $slots[$slot] = ['id' => $entry['id'], 'url' => $entry['url'], 'mime' => $entry['mime']];
  }
  return ['schema_version' => 1, 'target_site' => 'ez2-isolated-only',
   'host' => Ez2DisposableImport::HOST, 'slots' => $slots];
 }

 /**
  * Verify that every synthetic attachment resolves to an actual, regular PNG
  * inside the disposable WordPress uploads directory. This never exports
  * bytes, reads Owner media, or authorizes a LocalWP installation.
  */
 public static function verifyFiles(array $snapshot, string $uploadRoot, callable $resolve): void {
  $root=realpath($uploadRoot);
  if ($root===false || is_link($uploadRoot) || !is_dir($root) || basename($root)!=='uploads') {
   throw new RuntimeException('UNSAFE_UPLOAD_ROOT');
  }
  $media=$snapshot['media']??null;
  if (!is_array($media) || count($media)!==count(Ez2DisposableImport::SLOTS)) {
   throw new RuntimeException('UNEXPECTED_ATTACHMENT_COUNT');
  }
  $seen=[];
  foreach (array_values($media) as $index=>$entry) {
   $id=$entry['id']??null;
   if (!is_int($id) || $id<1 || ($entry['parent']??null)!==($snapshot['post_id']??null)
       || ($entry['mime']??null)!=='image/png' || ($entry['exists']??null)!==true) {
    throw new RuntimeException('UNSAFE_ATTACHMENT_METADATA');
   }
   $file=$resolve($id);
   if (!is_string($file) || is_link($file) || !is_file($file)) {
    throw new RuntimeException('MISSING_OR_LINKED_ATTACHMENT');
   }
   $real=realpath($file);
   $stat=lstat($file);
   if ($real===false || $stat===false || !str_starts_with($real,$root.DIRECTORY_SEPARATOR)
       || ($stat['mode'] & 0170000)!==0100000 || $stat['nlink']!==1
       || basename($real)!=='ez2-ci-synthetic-hero-'.($index+1).'.png'
       || isset($seen[$real]) || $stat['size']<32 || $stat['size']>20971520) {
    throw new RuntimeException('UNSAFE_ATTACHMENT_FILE');
   }
   // A valid attachment ID is not enough: the public URL must name the
   // exact regular file WordPress resolves inside this disposable uploads root.
   // Otherwise a valid image can be silently assigned to the wrong hero slot.
   $relative=substr($real,strlen($root)+1);
   $urlPath=is_string($entry['url']??null) ? parse_url($entry['url'],PHP_URL_PATH) : false;
   if (!is_string($urlPath) ||
       $urlPath!=='/wp-content/uploads/'.str_replace(DIRECTORY_SEPARATOR,'/',$relative)) {
    throw new RuntimeException('ATTACHMENT_URL_FILE_MISMATCH');
   }
   $image=@getimagesize($real);
   if ($image===false || ($image['mime']??null)!=='image/png'
       || ($image[0]??0)<1 || ($image[1]??0)<1) {
    throw new RuntimeException('INVALID_ATTACHMENT_IMAGE');
   }
   $seen[$real]=true;
  }
 }
 public static function execute(): void {
  if (!defined('WP_CLI') || !WP_CLI || !function_exists('get_option')) throw new RuntimeException('NO_WORDPRESS');
  if (!function_exists('is_plugin_active')) require_once ABSPATH . 'wp-admin/includes/plugin.php';
  $facts = ['wp_cli' => true, 'opt_in' => getenv('EZ2_DISPOSABLE_IMPORT'),
   'expected_host' => getenv('EZ2_EXPECTED_HOST'), 'home' => get_option('home'),
   'siteurl' => get_option('siteurl'), 'identity' => get_option('ez2_site_identity'),
   'environment' => wp_get_environment_type(), 'multisite' => is_multisite(),
   'elementor_active' => is_plugin_active('elementor/elementor.php'),
   'elementor_loaded' => did_action('elementor/loaded') > 0,
   'expected_version' => getenv('EZ2_EXPECTED_ELEMENTOR_VERSION'),
   'elementor_version' => defined('ELEMENTOR_VERSION') ? ELEMENTOR_VERSION : null];
  if ($bad = Ez2DisposableImport::gate($facts)) throw new RuntimeException('DISPOSABLE_GATE:' . implode(',', $bad));
  $statuses = ['publish', 'future', 'draft', 'pending', 'private', 'trash'];
  $byTitle = get_posts(['post_type' => 'page', 'post_status' => $statuses,
   'title' => Ez2CiImportReuse::TITLE, 'posts_per_page' => 3, 'fields' => 'ids']);
  $byMarker = get_posts(['post_type' => 'page', 'post_status' => $statuses,
   'meta_key' => '_ez2_ci_import_fingerprint', 'posts_per_page' => 3, 'fields' => 'ids']);
  $found = Ez2CiImportReuse::candidates($byTitle, $byMarker);
  if (count($found) !== 1) throw new RuntimeException('DRAFT_NOT_UNIQUE');
  $id = (int) $found[0];
  $snapshot = Ez2CiImportReuse::capture($id);
  $fingerprint = (string) get_post_meta($id, '_ez2_ci_import_fingerprint', true);
  $map = self::map($facts, $snapshot, $fingerprint);
  self::verifyFiles($snapshot, (string)(wp_upload_dir()['basedir']??''),
   static fn(int $attachmentId) => get_attached_file($attachmentId));
  echo wp_json_encode($map, JSON_THROW_ON_ERROR | JSON_UNESCAPED_SLASHES) . "\n";
 }
}
if (!defined('EZ2_CI_MEDIA_INVENTORY_LIBRARY_ONLY')) {
 try { Ez2CiMediaInventory::execute(); }
 catch (Throwable $e) {
  fwrite(STDERR, 'EZ2_CI_MEDIA_INVENTORY_FAIL: ' . $e->getMessage() . "\n");
  exit(1);
 }
}
