<?php
/** Read-only isolated Elementor control registration check; no content writes. */
if (!defined('WP_CLI') || !WP_CLI || !function_exists('get_option')
    || getenv('EZ2_EXPECTED_HOST') !== 'ez2-review.local'
    || get_option('home') !== 'http://ez2-review.local'
    || get_option('siteurl') !== 'http://ez2-review.local'
    || get_option('ez2_site_identity') !== 'ez2-isolated-only'
    || is_multisite()
    || !defined('ELEMENTOR_VERSION')
    || !in_array(getenv('EZ2_EXPECTED_ELEMENTOR_VERSION'), ['4.3.4', '4.3.5'], true)
    || ELEMENTOR_VERSION !== getenv('EZ2_EXPECTED_ELEMENTOR_VERSION')
    || did_action('elementor/loaded') < 1) {
    fwrite(STDERR, "EZ2_ELEMENTOR_CONTROL_GATE_BLOCKED\n");
    exit(1);
}
$container = \Elementor\Plugin::instance()->elements_manager->get_element_types('container');
if (!$container || !method_exists($container, 'get_controls')) {
    fwrite(STDERR, "EZ2_ELEMENTOR_CONTAINER_NOT_REGISTERED\n");
    exit(1);
}
$controls = $container->get_controls();
$required = [
    'background_background', 'background_slideshow_gallery',
    'background_slideshow_slide_duration', 'background_slideshow_slide_transition',
    'background_slideshow_transition_duration', 'background_slideshow_ken_burns',
    'background_slideshow_ken_burns_zoom_direction', 'background_overlay_background',
    'background_overlay_opacity',
];
$missing = array_values(array_diff($required, array_keys($controls)));
if ($missing) {
    fwrite(STDERR, 'EZ2_ELEMENTOR_MISSING_CONTROLS: ' . implode(',', $missing) . "\n");
    exit(1);
}
echo 'EZ2_ELEMENTOR_CONTROLS_PASS version=' . ELEMENTOR_VERSION
    . ' registered=' . count($required)
    . ' template_imported=false visual_qa_verified=false' . "\n";
