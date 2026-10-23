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
