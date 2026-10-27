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
function get_attached_file($id) {
    return in_array($id, $GLOBALS['missing_ids'], true) ? '/nonexistent/ez2-stale-media.webp' : __FILE__;
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
echo "EZB_EDITORIAL_RENDERED_SLIDES_PASS cases=5\n";
