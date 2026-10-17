<?php
/**
 * Verify that the approved first real-media batch is present in WordPress.
 *
 * Run with:
 *   wp eval-file scripts/media-library-readiness.php --allow-root
 *
 * This checks Media Library presence/resolution only. It does not prove
 * publication approval, visual quality, privacy approval or Owner acceptance.
 */

if ( ! function_exists( 'ezb_media_slot_candidates' ) ||
	! function_exists( 'ezb_project_media_groups' ) ||
	! function_exists( 'ezb_product_media_galleries' ) ||
	! function_exists( 'ezb_find_attachment_by_basename' )
) {
	fwrite( STDERR, "EZB_MEDIA_READINESS_FAIL plugin resolver functions are unavailable\n" );
	exit( 2 );
}

$expected = array();

foreach ( ezb_media_slot_candidates() as $slot => $candidate ) {
	if ( empty( $candidate['filename'] ) ) {
		fwrite( STDERR, "EZB_MEDIA_READINESS_FAIL media slot {$slot} has no filename\n" );
		exit( 3 );
	}

	$expected[ $candidate['filename'] ] = array(
		'source'  => 'slot',
		'context' => $slot,
	);
}

foreach ( ezb_project_media_groups() as $project_slug => $group ) {
	foreach ( isset( $group['images'] ) ? $group['images'] : array() as $index => $image ) {
		if ( empty( $image['filename'] ) ) {
			fwrite( STDERR, "EZB_MEDIA_READINESS_FAIL project {$project_slug} image {$index} has no filename\n" );
			exit( 4 );
		}

		if ( ! isset( $expected[ $image['filename'] ] ) ) {
			$expected[ $image['filename'] ] = array(
				'source'  => 'project',
				'context' => $project_slug,
			);
		}
	}
}

foreach ( ezb_product_media_galleries() as $product_slug => $group ) {
	foreach ( isset( $group['images'] ) ? $group['images'] : array() as $index => $image ) {
		if ( empty( $image['filename'] ) ) {
			fwrite( STDERR, "EZB_MEDIA_READINESS_FAIL product {$product_slug} image {$index} has no filename\n" );
			exit( 5 );
		}
		if ( ! isset( $expected[ $image['filename'] ] ) ) {
			$expected[ $image['filename'] ] = array(
				'source'  => 'product',
				'context' => $product_slug,
			);
		}
	}
}

ksort( $expected );

if ( 25 !== count( $expected ) ) {
	fwrite(
		STDERR,
		'EZB_MEDIA_READINESS_FAIL expected registry to resolve to 25 unique assets, got ' .
		count( $expected ) . "\n"
	);
	exit( 5 );
}

$used_ids = array();
$failures = array();

foreach ( $expected as $source_filename => $meta ) {
	$attachment_id = ezb_find_attachment_by_basename( $source_filename );

	if ( ! $attachment_id ) {
		$failures[] = "{$source_filename}: missing attachment";
		continue;
	}

	$post = get_post( $attachment_id );
	if ( ! $post || 'attachment' !== $post->post_type ) {
		$failures[] = "{$source_filename}: resolved ID {$attachment_id} is not an attachment";
		continue;
	}

	$mime = get_post_mime_type( $attachment_id );
	if ( 'image/webp' !== $mime ) {
		$failures[] = "{$source_filename}: expected image/webp, got {$mime}";
		continue;
	}

	$url = wp_get_attachment_url( $attachment_id );
	if ( ! $url ) {
		$failures[] = "{$source_filename}: attachment URL is empty";
		continue;
	}

	$file = get_attached_file( $attachment_id );
	if ( ! $file || ! is_file( $file ) ) {
		$failures[] = "{$source_filename}: attached file is unavailable";
		continue;
	}

	$file_size = filesize( $file );
	if ( false === $file_size || $file_size > 768000 ) {
		$failures[] = "{$source_filename}: source WebP exceeds 750KB media budget";
		continue;
	}

	$metadata = wp_get_attachment_metadata( $attachment_id );
	$width    = isset( $metadata['width'] ) ? (int) $metadata['width'] : 0;
	$height   = isset( $metadata['height'] ) ? (int) $metadata['height'] : 0;

	if ( $width <= 0 || $height <= 0 ) {
		$failures[] = "{$source_filename}: image dimensions are unavailable";
		continue;
	}

	if ( max( $width, $height ) > 2500 ) {
		$failures[] = "{$source_filename}: source image exceeds 2500px maximum dimension";
		continue;
	}

	if ( isset( $used_ids[ $attachment_id ] ) && $used_ids[ $attachment_id ] !== $source_filename ) {
		$failures[] = "{$source_filename}: attachment ID {$attachment_id} already resolved from {$used_ids[$attachment_id]}";
		continue;
	}

	$used_ids[ $attachment_id ] = $source_filename;

	printf(
		"MEDIA_OK|%s|id=%d|mime=%s|dimensions=%dx%d|bytes=%d|context=%s:%s|url=%s\n",
		$source_filename,
		$attachment_id,
		$mime,
		$width,
		$height,
		$file_size,
		$meta['source'],
		$meta['context'],
		$url
	);
}

if ( $failures ) {
	foreach ( $failures as $failure ) {
		fwrite( STDERR, "MEDIA_FAIL|{$failure}\n" );
	}
	fwrite( STDERR, 'EZB_MEDIA_READINESS_FAIL failures=' . count( $failures ) . "\n" );
	exit( 6 );
}

if ( 25 !== count( $used_ids ) ) {
	fwrite( STDERR, 'EZB_MEDIA_READINESS_FAIL unique_attachment_ids=' . count( $used_ids ) . "\n" );
	exit( 7 );
}

echo "EZB_MEDIA_LIBRARY_READINESS_PASS\n";
echo "expected_assets=25\n";
echo "resolved_unique_attachments=25\n";
echo "media_budget=max_2500px,max_750KB_per_source_webp\n";
echo "REAL_IMAGE_VISUAL_QA=MANUAL_GATE\n";
