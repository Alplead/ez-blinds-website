<?php
/**
 * Curated, image-led editorial presentation for EZB's local development site.
 * All photos are resolved from the WordPress Media Library. Never embed or
 * commit a customer's private media file into the public source repository.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/** Images selected from the already-reviewed EZB asset registry. */
function ezb_editorial_image_choices() {
	return array(
		'sheer' => array(
			'file'   => 'PXL_20231017_045427584~2.jpg',
			'label'  => 'Sheer Curtains',
			'link'   => '/sheer-curtains/',
		),
		'roller' => array(
			'file'   => 'EZ blinds and shutters Roller blinds 02.jpg',
			'label'  => 'Roller Blinds',
			'link'   => '/roller-blinds/',
		),
		'flyscreen' => array(
			'file'   => 'EZ blinds and shutters Retractable Flyscreen S 01.jpg',
			'label'  => 'Retractable Flyscreens',
			'link'   => '/retractable-flyscreens/',
		),
		'shutters' => array(
			'file'   => 'EZ blinds and shutters Plantation shutters 01.jpg',
			'label'  => 'Plantation Shutters',
			'link'   => '/plantation-shutters/',
		),
	);
}

function ezb_editorial_image_id( $selection ) {
	if ( ! function_exists( 'ezb_find_attachment_by_basename' ) ) {
		return 0;
	}
	$choices = ezb_editorial_image_choices();
	if ( ! isset( $choices[ $selection ] ) ) {
		return 0;
	}
	$id = (int) ezb_find_attachment_by_basename( $choices[ $selection ]['file'] );
	return $id && 'image' === substr( (string) get_post_mime_type( $id ), 0, 5 ) ? $id : 0;
}

add_shortcode(
	'ezb_editorial_hero',
	function () {
		$slides = array();
		foreach ( ezb_editorial_image_choices() as $slug => $data ) {
			$id = ezb_editorial_image_id( $slug );
			if ( $id ) {
				$slides[] = array( 'id' => $id, 'slug' => $slug, 'data' => $data );
			}
		}

		$images = '';
		$rendered_count = 0;
		foreach ( $slides as $slide ) {
			$active = 0 === $rendered_count;
			$image  = wp_get_attachment_image(
				$slide['id'],
				'full',
				false,
				array(
					'class'         => $active ? 'ezb-cinema__image ezb-media-slot__image' : 'ezb-cinema__image',
					'alt'           => $active ? $slide['data']['label'] . ' installation photograph' : '',
					'sizes'         => '100vw',
					'loading'       => $active ? 'eager' : 'lazy',
					'fetchpriority' => $active ? 'high' : 'auto',
					'decoding'      => 'async',
				)
			);
			if ( ! $image ) {
				continue;
			}
			$rendered_count++;
			$images .= sprintf(
				'<figure class="ezb-cinema__slide%1$s" data-ezb-slide aria-hidden="%2$s">%3$s<figcaption class="ezb-cinema__slide-label">%4$s</figcaption></figure>',
				$active ? ' is-active' : '',
				$active ? 'false' : 'true',
				$image,
				esc_html( $slide['data']['label'] )
			);
		}

		$controls = '';
		if ( $rendered_count > 1 ) {
			$controls = sprintf(
				'<nav class="ezb-cinema__controls" aria-label="%1$s"><button type="button" data-ezb-prev aria-label="%2$s">&#8592;</button><span class="ezb-cinema__progress" data-ezb-progress aria-live="off">01 / %3$02d</span><button type="button" data-ezb-next aria-label="%4$s">&#8594;</button><button type="button" class="ezb-cinema__pause" data-ezb-toggle aria-pressed="false">%5$s</button></nav>',
				esc_attr__( 'Photo slideshow', 'ezb-core' ),
				esc_attr__( 'Previous photo', 'ezb-core' ),
				$rendered_count,
				esc_attr__( 'Next photo', 'ezb-core' ),
				esc_html__( 'Pause slideshow', 'ezb-core' )
			);
		}

		// The copy and CTA must remain accessible even before any photos are imported.
		return sprintf(
			'<section class="ezb-cinema%1$s" data-ezb-cinema aria-label="%2$s"><div class="ezb-cinema__visuals" aria-hidden="true">%3$s</div><div class="ezb-cinema__veil" aria-hidden="true"></div><div class="ezb-cinema__content"><p class="ezb-cinema__eyebrow">%4$s</p><h1>%5$s</h1><p class="ezb-cinema__description">%6$s</p><div class="ezb-cinema__actions"><a class="ezb-cinema__primary" href="%7$s">%8$s</a><a class="ezb-cinema__secondary" href="%9$s">%10$s</a></div>%11$s</div></section>',
			$images ? '' : ' ezb-cinema--missing-media',
			esc_attr__( 'EZ Blinds and Shutters real installation showcase', 'ezb-core' ),
			$images,
			esc_html__( 'MELBOURNE  /  MEASURE  /  SUPPLY  /  INSTALL', 'ezb-core' ),
			esc_html__( 'Made for the light you live in.', 'ezb-core' ),
			esc_html__( 'Blinds, curtains, shutters and screening — measured and fitted for Melbourne homes.', 'ezb-core' ),
			esc_url( home_url( '/contact/' ) ),
			esc_html__( 'Free Measure & Quote', 'ezb-core' ),
			esc_url( home_url( '/projects/' ) ),
			esc_html__( 'Explore real projects', 'ezb-core' ),
			$controls
		);
	}
);

/**
 * Large photographic interludes between copy-rich homepage sections.
 * Selection is restricted to the curated first-party approved media registry.
 */
add_shortcode(
	'ezb_editorial_interlude',
	function ( $atts ) {
		$atts = shortcode_atts(
			array( 'photo' => 'flyscreen' ),
			$atts,
			'ezb_editorial_interlude'
		);
		$slug    = sanitize_key( $atts['photo'] );
		$choices = ezb_editorial_image_choices();
		if ( ! isset( $choices[ $slug ] ) ) {
			return '';
		}
		$id = ezb_editorial_image_id( $slug );
		if ( ! $id ) {
			return ''; // Missing photo: never pretend a real installation is loaded.
		}
		$image = wp_get_attachment_image(
			$id,
			'full',
			false,
			array(
				'class' => 'ezb-editorial-band__image',
				'alt' => '',
				'loading' => 'lazy',
				'sizes' => '100vw',
				'decoding' => 'async',
			)
		);
		if ( ! $image ) {
			return '';
		}
		return sprintf(
			'<section class="ezb-editorial-band" data-ezb-editorial-band><div class="ezb-editorial-band__photo" aria-hidden="true">%1$s</div><div class="ezb-editorial-band__overlay"></div><div class="ezb-editorial-band__content"><p class="ezb-editorial-band__kicker">%2$s</p><h2>%3$s</h2><a href="%4$s">%5$s <span aria-hidden="true">&#8594;</span></a></div></section>',
			$image,
			esc_html__( 'REAL EZ INSTALLATIONS', 'ezb-core' ),
			esc_html( $slug === 'flyscreen' ? 'A clearer connection to the outdoors.' : ( $slug === 'roller' ? 'Light, shaped for everyday living.' : 'The details make the room.' ) ),
			esc_url( home_url( $choices[ $slug ]['link'] ) ),
			esc_html( $choices[ $slug ]['label'] )
		);
	}
);
