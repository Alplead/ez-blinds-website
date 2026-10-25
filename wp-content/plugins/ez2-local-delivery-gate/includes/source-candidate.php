<?php
/**
 * Read an immutable, PUBLIC-SAFE design candidate directly from GitHub's
 * official Contents API after the exact source PR has passed all five CI gates.
 * This is NOT a release installer, a media downloader, or publication approval.
 */
function ez2_gate_fetch_public_candidate( $source ) {
    if ( ! ez2_gate_site_guard() ) {
        return new WP_Error( 'ez2_wrong_site', 'Design source lookup restricted to isolated EZ2.' );
    }
    $sha = $source['source_sha'] ?? null;
    if ( ! is_array( $source ) || ( $source['source_ci_pass'] ?? null ) !== true
        || ( $source['site_modified'] ?? null ) !== false
        || ( $source['one_click_ready'] ?? null ) !== false
        || ! is_string( $sha ) || ! preg_match( '/\\A[a-f0-9]{40}\\z/D', $sha ) ) {
        return new WP_Error( 'ez2_source_unverified', 'A fresh exact-SHA CI report is required.' );
    }
    $path = 'design/ez2-home-hero-candidate.json';
    $response = ez2_gate_github_get( EZ2_GATE_API . '/contents/' . $path . '?ref=' . rawurlencode( $sha ) );
    if ( is_wp_error( $response ) ) {
        return $response;
    }
    if ( ! is_array( $response )
        || ( $response['type'] ?? '' ) !== 'file'
        || ( $response['name'] ?? '' ) !== 'ez2-home-hero-candidate.json'
        || ( $response['path'] ?? '' ) !== $path
        || ( $response['encoding'] ?? '' ) !== 'base64'
        || ! is_int( $response['size'] ?? null )
        || $response['size'] < 1 || $response['size'] > 256000
        || ! is_string( $response['sha'] ?? null )
        || ! preg_match( '/\\A[a-f0-9]{40}\\z/D', $response['sha'] )
        || ! is_string( $response['content'] ?? null )
        || strlen( $response['content'] ) > 400000 ) {
        return new WP_Error( 'ez2_design_source_metadata', 'Unexpected GitHub file metadata.' );
    }
    $encoded = preg_replace( '/\\s+/', '', $response['content'] );
    $raw = base64_decode( $encoded, true );
    if ( ! is_string( $raw ) || strlen( $raw ) !== $response['size'] ) {
        return new WP_Error( 'ez2_design_source_bytes', 'Truncated or improperly encoded design candidate.' );
    }
    // GitHub's 40-hex blob object ID binds these bytes to the requested commit.
    $blob_sha = sha1( 'blob ' . strlen( $raw ) . "\0" . $raw );
    if ( ! hash_equals( $response['sha'], $blob_sha ) ) {
        return new WP_Error( 'ez2_design_source_hash', 'Design bytes do not match the pinned GitHub blob.' );
    }
    $doc = json_decode( $raw, true, 32 );
    if ( ! is_array( $doc ) || json_last_error() !== JSON_ERROR_NONE
        || array_keys( $doc ) !== array( 'title', 'type', 'version', 'page_settings', 'content' )
        || ( $doc['type'] ?? '' ) !== 'page'
        || ! in_array( $doc['version'] ?? '', array( '4.3.4', '4.3.5' ), true )
        || ! is_array( $doc['content'] ) || count( $doc['content'] ) !== 1 ) {
        return new WP_Error( 'ez2_design_schema', 'Invalid or unsupported Elementor review candidate.' );
    }
    $hero = $doc['content'][0];
    $settings = $hero['settings'] ?? null;
    $gallery = is_array( $settings ) ? ( $settings['background_slideshow_gallery'] ?? null ) : null;
    if ( ( $hero['elType'] ?? '' ) !== 'container'
        || ! is_array( $gallery ) || count( $gallery ) !== 4
        || ( $settings['background_background'] ?? '' ) !== 'slideshow'
        || ( $settings['background_slideshow_ken_burns'] ?? '' ) !== 'yes'
        || ( $settings['background_slideshow_ken_burns_zoom_direction'] ?? '' ) !== 'in'
        || ( $settings['background_slideshow_slide_transition'] ?? '' ) !== 'fade'
        || ( $settings['background_slideshow_slide_duration'] ?? null ) !== 5000
        || ( $settings['background_slideshow_transition_duration'] ?? null ) !== 1200
        || ( $settings['min_height']['unit'] ?? '' ) !== 'vh'
        || ( $settings['min_height']['size'] ?? null ) !== 90 ) {
        return new WP_Error( 'ez2_design_motion', 'T2-inspired slideshow settings are not as expected.' );
    }
    foreach ( array( 'one', 'two', 'three', 'four' ) as $i => $word ) {
        $image = $gallery[ $i ];
        if ( ! is_array( $image ) || array_keys( $image ) !== array( 'id', 'url' )
            || $image['id'] !== ''
            || $image['url'] !== 'ez2-media://home-hero-' . $word ) {
            return new WP_Error( 'ez2_design_media', 'Only symbolic approved photo slots are allowed.' );
        }
    }
    if ( preg_match( '~https?://|images\\.unsplash\\.com~i', $raw ) ) {
        return new WP_Error( 'ez2_design_external_media', 'Remote or stock photo URLs are not approved.' );
    }
    return array(
        'status' => 'VERIFIED_PUBLIC_CANDIDATE_READ_ONLY',
        'source_sha' => $sha,
        'source_blob_sha' => $blob_sha,
        'candidate_sha256' => hash( 'sha256', $raw ),
        'elementor_version' => $doc['version'],
        'symbolic_photo_slots' => 4,
        'local_private_media_resolved' => false,
        'elementor_imported' => false,
        'visual_acceptance' => false,
        'one_click_ready' => false,
        'site_modified' => false,
    );
}
