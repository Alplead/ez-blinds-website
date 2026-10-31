<?php
/**
 * Offline regression for the actual EZB development seed functions.
 * Synthetic WordPress stubs only: no database, media, site or mail access.
 */
define('OBJECT', 'OBJECT');
$GLOBALS['ezb_test_env'] = 'development';
$GLOBALS['ezb_test_pages'] = [];
$GLOBALS['ezb_test_meta'] = [];
$GLOBALS['ezb_test_next_id'] = 1;
$GLOBALS['ezb_test_updates'] = 0;
$GLOBALS['ezb_test_fail_meta'] = null;
$cases = 0;

function wp_get_environment_type() { return $GLOBALS['ezb_test_env']; }
function get_page_by_path($slug, $output = OBJECT, $type = 'page') {
    return $GLOBALS['ezb_test_pages'][$slug] ?? null;
}
function wp_insert_post($data) {
    $id = $GLOBALS['ezb_test_next_id']++;
    $GLOBALS['ezb_test_pages'][$data['post_name']] = (object) [
        'ID' => $id, 'post_excerpt' => $data['post_excerpt'] ?? '',
        'post_content' => $data['post_content'] ?? ''
    ];
    return $id;
}
function add_post_meta($id, $key, $value, $unique = false) {
    if ($GLOBALS['ezb_test_fail_meta'] === $key
        || ($unique && isset($GLOBALS['ezb_test_meta'][$id][$key]))) return false;
    $GLOBALS['ezb_test_meta'][$id][$key] = $value;
    return true;
}
function get_post_meta($id, $key, $single = false) {
    return $GLOBALS['ezb_test_meta'][$id][$key] ?? '';
}
function wp_update_post($data) {
    foreach ($GLOBALS['ezb_test_pages'] as $page) {
        if ($page->ID !== $data['ID']) continue;
        foreach ($data as $field => $value) if ($field !== 'ID') $page->$field = $value;
        $GLOBALS['ezb_test_updates']++;
        return $page->ID;
    }
    return 0;
}
function esc_html($text) { return htmlspecialchars($text, ENT_QUOTES, 'UTF-8'); }

$source = file_get_contents(__DIR__ . '/../wp-content/plugins/ezb-core/ezb-core.php');
foreach (['ezb_seed_prototype_pages', 'ezb_claim_initial_page_seed',
          'ezb_seed_product_intro_excerpts', 'ezb_seed_product_faq_content'] as $name) {
    if (!preg_match('/function ' . $name . '\\([^)]*\\)\\s*\\{[\\s\\S]*?\\n\\}/', $source, $match)) {
        throw new RuntimeException('Cannot extract actual production function: ' . $name);
    }
    eval($match[0]);
}
function check($condition, $message) {
    global $cases;
    if (!$condition) throw new RuntimeException($message);
    $cases++;
}

// Pre-existing pages are Owner-controlled even when their fields are empty.
$manual = wp_insert_post(['post_name' => 'roller-blinds']);
$custom = wp_insert_post(['post_name' => 'sheer-curtains',
    'post_excerpt' => 'Owner introduction', 'post_content' => 'Owner FAQ']);
ezb_seed_prototype_pages();
check(count($GLOBALS['ezb_test_pages']) === 12, 'Only missing prototype pages created');
$generated = $GLOBALS['ezb_test_pages']['motorised-blinds'];
check(get_post_meta($generated->ID, '_ezb_prototype_created_v1', true) === '1',
    'Generated page must have provenance marker');
check(get_post_meta($manual, '_ezb_prototype_created_v1', true) === '',
    'Pre-existing Owner page must not gain a seed marker');

ezb_seed_product_intro_excerpts();
ezb_seed_product_faq_content();
check($generated->post_excerpt !== '' && $generated->post_content !== '',
    'Generated page should receive initial intro and FAQ');
check($GLOBALS['ezb_test_pages']['roller-blinds']->post_excerpt === ''
    && $GLOBALS['ezb_test_pages']['roller-blinds']->post_content === '',
    'Existing empty Owner page must stay empty');
check($GLOBALS['ezb_test_pages']['sheer-curtains']->post_excerpt === 'Owner introduction'
    && $GLOBALS['ezb_test_pages']['sheer-curtains']->post_content === 'Owner FAQ',
    'Existing Owner content must stay unchanged');

$writes = $GLOBALS['ezb_test_updates'];
ezb_seed_product_intro_excerpts();
ezb_seed_product_faq_content();
check($GLOBALS['ezb_test_updates'] === $writes, 'Repeat seeding must be idempotent');
$generated->post_excerpt = '';
$generated->post_content = '';
ezb_seed_product_intro_excerpts();
ezb_seed_product_faq_content();
check($generated->post_excerpt === '' && $generated->post_content === ''
    && $GLOBALS['ezb_test_updates'] === $writes,
    'Owner-cleared fields must never be resurrected');

// Failure to record a one-time claim must prevent any automatic field write.
$another = $GLOBALS['ezb_test_pages']['plantation-shutters'];
$another->post_excerpt = '';
unset($GLOBALS['ezb_test_meta'][$another->ID]['_ezb_intro_seed_attempted_v1']);
$GLOBALS['ezb_test_fail_meta'] = '_ezb_intro_seed_attempted_v1';
ezb_seed_product_intro_excerpts();
check($another->post_excerpt === '', 'Metadata write failure must fail closed');
$GLOBALS['ezb_test_fail_meta'] = null;

$GLOBALS['ezb_test_env'] = 'production';
$before = count($GLOBALS['ezb_test_pages']);
ezb_seed_prototype_pages();
ezb_seed_product_intro_excerpts();
ezb_seed_product_faq_content();
check(count($GLOBALS['ezb_test_pages']) === $before
    && $GLOBALS['ezb_test_updates'] === $writes,
    'No development seeding on production environment');

echo 'EZB_DEV_SEED_OWNER_EDIT_GUARD_PASS cases=' . $cases . PHP_EOL;
