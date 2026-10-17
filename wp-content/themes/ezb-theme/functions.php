<?php
/**
 * EZB Theme bootstrap.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

add_action(
	'after_setup_theme',
	function () {
		add_theme_support( 'title-tag' );
		add_theme_support( 'post-thumbnails' );
		add_theme_support( 'responsive-embeds' );
		add_theme_support( 'editor-styles' );
		add_theme_support( 'wp-block-styles' );

		add_editor_style( 'style.css' );
	}
);

add_action(
	'wp_enqueue_scripts',
	function () {
		$stylesheet_path = get_stylesheet_directory() . '/style.css';
		$version = file_exists( $stylesheet_path ) ? (string) filemtime( $stylesheet_path ) : wp_get_theme()->get( 'Version' );

		wp_enqueue_style(
			'ezb-theme-style',
			get_stylesheet_uri(),
			array(),
			$version
		);

		$script_path = get_stylesheet_directory() . '/assets/js/site.js';
		$script_version = file_exists( $script_path ) ? (string) filemtime( $script_path ) : wp_get_theme()->get( 'Version' );

		wp_enqueue_script(
			'ezb-theme-site',
			get_stylesheet_directory_uri() . '/assets/js/site.js',
			array(),
			$script_version,
			array(
				'strategy'  => 'defer',
				'in_footer' => true,
			)
		);
	}
);

/**
 * Load photo-led editorial layout after the foundation stylesheet, keeping
 * media URLs in WordPress rather than the public source repository.
 */
add_action(
	'wp_enqueue_scripts',
	function () {
		$css_file = get_stylesheet_directory() . '/assets/css/editorial.css';
		$js_file  = get_stylesheet_directory() . '/assets/js/editorial.js';

		if ( file_exists( $css_file ) ) {
			wp_enqueue_style(
				'ezb-editorial',
				get_stylesheet_directory_uri() . '/assets/css/editorial.css',
				array( 'ezb-theme-style' ),
				(string) filemtime( $css_file )
			);
		}
		if ( file_exists( $js_file ) ) {
			wp_enqueue_script(
				'ezb-editorial-motion',
				get_stylesheet_directory_uri() . '/assets/js/editorial.js',
				array( 'ezb-theme-site' ),
				(string) filemtime( $js_file ),
				array(
					'strategy'  => 'defer',
					'in_footer' => true,
				)
			);
		}
	},
	20
);
