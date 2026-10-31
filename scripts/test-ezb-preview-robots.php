<?php
/** No WordPress, network, database, or real website required. */
define( 'EZB_PREVIEW_ROBOTS_TEST', true );
$GLOBALS['ezb_test_environment'] = 'production';
$GLOBALS['ezb_registered_robots_filter'] = null;
function wp_get_environment_type() {
	return $GLOBALS['ezb_test_environment'];
}
function add_filter( $hook, $callback, $priority ) {
	if ( 'wp_robots' !== $hook || PHP_INT_MAX !== $priority ) {
		throw new RuntimeException( 'Unexpected robots filter registration.' );
	}
	$GLOBALS['ezb_registered_robots_filter'] = $callback;
}
require __DIR__ . '/../wp-content/plugins/ezb-core/includes/ezb-preview-robots.php';
if ( 'ezb_preview_robots_guard' !== $GLOBALS['ezb_registered_robots_filter'] ) {
	throw new RuntimeException( 'Preview guard must be registered with WordPress.' );
}
$cases = 0;
foreach ( array( 'local', 'development', 'staging' ) as $environment ) {
	$GLOBALS['ezb_test_environment'] = $environment;
	$actual = ezb_preview_robots_guard( array( 'index' => true, 'follow' => true, 'archive' => true, 'max-image-preview' => 'large' ) );
	if ( ! isset( $actual['noindex'], $actual['nofollow'], $actual['noarchive'] ) ||
		true !== $actual['noindex'] || true !== $actual['nofollow'] || true !== $actual['noarchive'] ||
		isset( $actual['index'] ) || isset( $actual['follow'] ) || isset( $actual['archive'] ) ||
		'large' !== $actual['max-image-preview'] ) {
		throw new RuntimeException( 'Preview robots directives not fail-closed for ' . $environment );
	}
	$cases++;
}
$GLOBALS['ezb_test_environment'] = 'production';
$original = array( 'index' => true, 'follow' => true, 'max-snippet' => 0 );
if ( $original !== ezb_preview_robots_guard( $original ) ) {
	throw new RuntimeException( 'Production robots policy must remain untouched.' );
}
$cases++;
$GLOBALS['ezb_test_environment'] = 'unexpected';
if ( $original !== ezb_preview_robots_guard( $original ) ) {
	throw new RuntimeException( 'Unknown environments must not be treated as approved staging.' );
}
$cases++;
$GLOBALS['ezb_test_environment'] = 'development';
if ( 'malformed' !== ezb_preview_robots_guard( 'malformed' ) ) {
	throw new RuntimeException( 'Unexpected robots filter input must not cause a PHP error.' );
}
$cases++;
echo 'EZB_PREVIEW_ROBOTS_GUARD_PASS cases=' . $cases . PHP_EOL;
