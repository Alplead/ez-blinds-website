<?php
/**
 * Keep unapproved prototype content out of search indexes when a non-public
 * WordPress environment is accidentally reachable. This is defence in depth,
 * not access control: a robots directive does not make a site private.
 */
if ( ! defined( 'ABSPATH' ) && ! defined( 'EZB_PREVIEW_ROBOTS_TEST' ) ) {
	exit;
}

/**
 * LocalWP does not necessarily set WP_ENVIRONMENT_TYPE. Recognise only
 * explicitly non-public WordPress environments or local/test HOME hosts;
 * never trust the incoming HTTP Host header to make this decision.
 */
function ezb_preview_robots_is_nonpublic() {
	if ( function_exists( 'wp_get_environment_type' ) && in_array( wp_get_environment_type(), array( 'local', 'development', 'staging' ), true ) ) {
		return true;
	}
	if ( ! function_exists( 'home_url' ) || ! function_exists( 'wp_parse_url' ) ) {
		return false;
	}
	$host = wp_parse_url( home_url( '/' ), PHP_URL_HOST );
	if ( ! is_string( $host ) ) {
		return false;
	}
	$host = strtolower( rtrim( $host, '.' ) );
	return 'localhost' === $host || str_ends_with( $host, '.localhost' ) || str_ends_with( $host, '.local' ) || str_ends_with( $host, '.test' );
}

function ezb_preview_robots_guard( $robots ) {
	if ( ! is_array( $robots ) || ! ezb_preview_robots_is_nonpublic() ) {
		return $robots;
	}
	// Existing index/follow instructions must not override the preview guard.
	unset( $robots['index'], $robots['follow'], $robots['archive'] );
	$robots['noindex']   = true;
	$robots['nofollow']  = true;
	$robots['noarchive'] = true;
	return $robots;
}
add_filter( 'wp_robots', 'ezb_preview_robots_guard', PHP_INT_MAX );

/** Dynamic WordPress responses get a matching header (static files do not). */
function ezb_preview_robots_header_value() {
	return ezb_preview_robots_is_nonpublic() ? 'noindex, nofollow, noarchive' : '';
}
function ezb_preview_robots_send_headers() {
	$value = ezb_preview_robots_header_value();
	if ( '' !== $value && ! headers_sent() ) {
		header( 'X-Robots-Tag: ' . $value, true );
	}
}
add_action( 'send_headers', 'ezb_preview_robots_send_headers', PHP_INT_MAX );
