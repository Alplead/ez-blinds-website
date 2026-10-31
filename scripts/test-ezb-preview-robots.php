<?php
/** No WordPress, network, database, or real website required. */
define( 'EZB_PREVIEW_ROBOTS_TEST', true );
$GLOBALS['ezb_test_environment'] = 'production';
$GLOBALS['ezb_test_home'] = 'https://ezbns.com.au/';
$GLOBALS['ezb_registered_header_action'] = null;
$GLOBALS['ezb_registered_robots_filter'] = null;
function wp_get_environment_type() {
	return $GLOBALS['ezb_test_environment'];
}
function home_url( $path = '/' ) {
	return $GLOBALS['ezb_test_home'];
}
function wp_parse_url( $url, $component = -1 ) {
	return parse_url( $url, $component );
}
function add_action( $hook, $callback, $priority ) {
	if ( 'send_headers' !== $hook || PHP_INT_MAX !== $priority ) {
		throw new RuntimeException( 'Unexpected robots header action registration.' );
	}
	$GLOBALS['ezb_registered_header_action'] = $callback;
}
function add_filter( $hook, $callback, $priority ) {
	if ( 'wp_robots' !== $hook || PHP_INT_MAX !== $priority ) {
		throw new RuntimeException( 'Unexpected robots filter registration.' );
	}
	$GLOBALS['ezb_registered_robots_filter'] = $callback;
}
require __DIR__ . '/../wp-content/plugins/ezb-core/includes/ezb-preview-robots.php';
if ( 'ezb_preview_robots_guard' !== $GLOBALS['ezb_registered_robots_filter'] ||
	'ezb_preview_robots_send_headers' !== $GLOBALS['ezb_registered_header_action'] ) {
	throw new RuntimeException( 'Preview guard and header must be registered with WordPress.' );
}
$cases = 0;
$original = array( 'index' => true, 'follow' => true, 'archive' => true, 'max-image-preview' => 'large' );
$assert_guarded = static function ( $label ) use ( &$cases, $original ) {
	$actual = ezb_preview_robots_guard( $original );
	if ( ! isset( $actual['noindex'], $actual['nofollow'], $actual['noarchive'] ) ||
		true !== $actual['noindex'] || true !== $actual['nofollow'] || true !== $actual['noarchive'] ||
		isset( $actual['index'] ) || isset( $actual['follow'] ) || isset( $actual['archive'] ) ||
		'large' !== $actual['max-image-preview'] ||
		'noindex, nofollow, noarchive' !== ezb_preview_robots_header_value() ) {
		throw new RuntimeException( 'Preview robots directives not fail-closed for ' . $label );
	}
	$cases++;
};
foreach ( array( 'local', 'development', 'staging' ) as $environment ) {
	$GLOBALS['ezb_test_environment'] = $environment;
	$assert_guarded( $environment );
}
$GLOBALS['ezb_test_environment'] = 'production';
foreach ( array( 'http://ez-bns-new-dev.local/', 'http://ez2-review.local/', 'http://localhost:10005/', 'http://dev.localhost/', 'http://site.test/', 'HTTP://SITE.LOCAL./' ) as $url ) {
	$GLOBALS['ezb_test_home'] = $url;
	$assert_guarded( $url );
}
foreach ( array( 'https://ezbns.com.au/', 'https://example.com/', 'https://ez2-review.local.evil.invalid/', 'https://site.test.evil.invalid/', 'https://local.evil.invalid/', 'not-a-valid-url' ) as $url ) {
	$GLOBALS['ezb_test_home'] = $url;
	if ( $original !== ezb_preview_robots_guard( $original ) || '' !== ezb_preview_robots_header_value() ) {
		throw new RuntimeException( 'Public or unknown host must remain untouched: ' . $url );
	}
	$cases++;
}
$GLOBALS['ezb_test_environment'] = 'unexpected';
$GLOBALS['ezb_test_home'] = 'https://ezbns.com.au/';
if ( $original !== ezb_preview_robots_guard( $original ) || '' !== ezb_preview_robots_header_value() ) {
	throw new RuntimeException( 'Unknown environment must not be treated as staging.' );
}
$cases++;
$GLOBALS['ezb_test_environment'] = 'development';
if ( 'malformed' !== ezb_preview_robots_guard( 'malformed' ) ) {
	throw new RuntimeException( 'Unexpected robots filter input must not cause a PHP error.' );
}
$cases++;
echo 'EZB_PREVIEW_ROBOTS_GUARD_PASS cases=' . $cases . PHP_EOL;
