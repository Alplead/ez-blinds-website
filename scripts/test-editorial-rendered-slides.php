<?php
// Standalone synthetic test for missing WordPress image renditions.
define('ABSPATH', '/');
$GLOBALS['shortcodes'] = array();
$GLOBALS['mode'] = 'first_missing';
function add_shortcode($name, $callback) { $GLOBALS['shortcodes'][$name] = $callback; }
function ezb_find_attachment_by_basename($name) {
    static $ids = array();
    if (!isset($ids[$name])) { $ids[$name] = count($ids) + 1; }
    return $ids[$name];
}
function get_post_mime_type($id) { return 'image/webp'; }
$GLOBALS['missing_ids'] = array();
$GLOBALS['file_overrides'] = array();
$GLOBALS['uploads_override'] = null;
function wp_get_upload_dir() {
    return $GLOBALS['uploads_override'] ?? array('basedir' => __DIR__, 'error' => false);
}
function get_attached_file($id) {
    if (in_array($id, $GLOBALS['missing_ids'], true)) return '/nonexistent/ez2-stale-media.webp';
    return $GLOBALS['file_overrides'][$id] ?? __FILE__;
}
function wp_get_attachment_image($id, $size, $icon, $attributes) {
    $mode = $GLOBALS['mode'];
    if ($mode === 'all_missing' || ($mode === 'first_missing' && $id === 1) ||
        ($mode === 'single' && $id !== 2)) { return ''; }
    $alt = htmlspecialchars($attributes['alt'] ?? '', ENT_QUOTES, 'UTF-8');
    return '<img alt="' . $alt . '">';
}
function esc_attr__($value, $domain) { return $value; }
function esc_html__($value, $domain) { return $value; }
function esc_attr($value) { return $value; }
function esc_html($value) { return $value; }
function esc_url($value) { return $value; }
function home_url($path) { return $path; }
require __DIR__ . '/../wp-content/plugins/ezb-core/includes/ezb-editorial-visuals.php';
$render = $GLOBALS['shortcodes']['ezb_editorial_hero'];
$html = $render();
if (substr_count($html, 'data-ezb-slide') !== 3 ||
    strpos($html, 'ezb-cinema__slide is-active" data-ezb-slide aria-hidden="false"') === false ||
    strpos($html, '01 / 03') === false ||
    substr_count($html, 'data-ezb-announcement') !== 1) {
    throw new Exception('Partial media failure must preserve the first visible frame and accurate count.');
}
if (strpos($html, 'alt="Roller Blinds installation photograph"') === false ||
    strpos($html, 'alt="Sheer Curtains installation photograph"') !== false) {
    throw new Exception('First successfully rendered image must describe its actual product.');
}
$GLOBALS['mode'] = 'all_available';
$html = $render();
if (substr_count($html, 'data-ezb-slide') !== 4 ||
    strpos($html, 'alt="Sheer Curtains installation photograph"') === false ||
    strpos($html, 'aria-pressed=') !== false) {
    throw new Exception('Complete gallery must describe its first sheer curtain photo.');
}
// A stale attachment row must not produce a broken image or the wrong first-slide label.
$GLOBALS['missing_ids'] = array(1);
$html = $render();
if (substr_count($html, 'data-ezb-slide') !== 3 ||
    strpos($html, 'alt="Roller Blinds installation photograph"') === false ||
    strpos($html, 'alt="Sheer Curtains installation photograph"') !== false) {
    throw new Exception('Missing local media must be excluded from the slideshow.');
}
$GLOBALS['missing_ids'] = array();
$GLOBALS['mode'] = 'single';
$html = $render();
if (substr_count($html, 'data-ezb-slide') !== 1 ||
    strpos($html, 'ezb-cinema__slide is-active" data-ezb-slide aria-hidden="false"') === false ||
    strpos($html, 'data-ezb-toggle') !== false ||
    strpos($html, 'alt="Roller Blinds installation photograph"') === false) {
    throw new Exception('One rendered frame must not show autoplay controls.');
}
$GLOBALS['mode'] = 'all_missing';
$html = $render();
if (strpos($html, 'ezb-cinema--missing-media') === false ||
    strpos($html, 'data-ezb-slide') !== false ||
    strpos($html, 'data-ezb-toggle') !== false) {
    throw new Exception('No images must display the safe text-only hero.');
}
// An attachment row pointing outside this site's uploads must not appear.
$GLOBALS['mode'] = 'all_available';
$GLOBALS['file_overrides'][1] = dirname(__DIR__) . '/wp-content/plugins/ezb-core/ezb-core.php';
$html = $render();
if (substr_count($html, 'data-ezb-slide') !== 3 ||
    strpos($html, 'alt="Sheer Curtains installation photograph"') !== false) {
    throw new Exception('An outside-uploads attachment must not render.');
}
unset($GLOBALS['file_overrides'][1]);

// Even an in-uploads symlink is not an approved physical media file.
$link = __DIR__ . '/.ezb-editorial-link-' . getmypid();
if (file_exists($link) || is_link($link) || !symlink(__FILE__, $link)) {
    throw new Exception('Cannot create synthetic media symlink fixture.');
}
try {
    $GLOBALS['file_overrides'][1] = $link;
    $html = $render();
    if (substr_count($html, 'data-ezb-slide') !== 3 ||
        strpos($html, 'alt="Sheer Curtains installation photograph"') !== false) {
        throw new Exception('An in-uploads symlink must not render.');
    }
} finally {
    unset($GLOBALS['file_overrides'][1]);
    unlink($link);
}

// A failed WordPress upload-directory lookup must fail closed.
$GLOBALS['uploads_override'] = array('basedir' => __DIR__, 'error' => 'unavailable');
$html = $render();
if (strpos($html, 'ezb-cinema--missing-media') === false ||
    strpos($html, 'data-ezb-slide') !== false) {
    throw new Exception('Upload-directory errors must not render media.');
}
$GLOBALS['uploads_override'] = null;
echo "EZB_EDITORIAL_RENDERED_SLIDES_PASS cases=8\n";
