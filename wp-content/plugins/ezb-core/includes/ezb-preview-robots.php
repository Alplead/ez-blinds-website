<?php
/**
 * Keep unapproved prototype content out of search indexes when a non-public
 * WordPress environment is accidentally reachable. This is defence in depth,
 * not access control: a robots directive does not make a site private.
 */
if ( ! defined( 'ABSPATH' ) && ! defined( 'EZB_PREVIEW_ROBOTS_TEST' ) ) {
	exit;
}

function ezb_preview_robots_guard( $robots ) {
	if ( ! is_array( $robots ) || ! function_exists( 'wp_get_environment_type' ) ) {
		return $robots;
	}
	if ( ! in_array( wp_get_environment_type(), array( 'local', 'development', 'staging' ), true ) ) {
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
