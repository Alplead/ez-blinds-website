<?php
/**
 * EZ2 private-preview PHOTO gate. Run only with:
 *   wp eval-file scripts/ez2-photo-readiness.php
 *
 * READ ONLY. NEVER imports content, never modifies a WP option or posts.
 * The gate prevents repeating the Owner-visible mistake of showcasing a
 * WordPress site before its genuine photos are present.
 *
 * This is a visual-preview preflight, NOT a licence to publish customer media
 * and NOT an approval for production cutover.
 */
if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

function ez2_photo_readiness() {
    $hostname = strtolower( (string) wp_parse_url( home_url( '/' ), PHP_URL_HOST ) );
    if ( ! preg_match( '/\A(?:sb-[a-z0-9]+\.vercel\.run|ez2(?:-[a-z0-9]+)*\.local)\z/D', $hostname ) ) {
        return new WP_Error( 'ez2_photo_wrong_host', 'This private-preview check is not permitted on production.' );
    }
    if ( ! function_exists( 'ezb_media_slot_candidates' )
        || ! function_exists( 'ezb_find_attachment_by_basename' )
        || ! function_exists( 'ezb_featured_image_for_page_slug' ) ) {
        return new WP_Error( 'ez2_photo_missing_core', 'EZB Core is not active.' );
    }

    $library = get_posts( array(
        'post_type' => 'attachment',
        'post_status' => 'inherit',
        'post_mime_type' => 'image/webp',
        'posts_per_page' => 250,
        'fields' => 'ids',
        'suppress_filters' => true,
    ) );
    if ( ! is_array( $library ) || count( $library ) < 23 || count( $library ) > 249 ) {
        return new WP_Error( 'ez2_photo_library_incomplete', 'Private site does not have its full WebP photo library.' );
    }

    $uploads = wp_upload_dir();
    if ( ! is_array( $uploads ) || ! empty( $uploads['error'] ) ) {
        return new WP_Error( 'ez2_photo_upload_error', 'WordPress upload location cannot be verified.' );
    }
    $base_dir = realpath( (string) ( $uploads['basedir'] ?? '' ) );
    if ( false === $base_dir || ! is_dir( $base_dir ) ) {
        return new WP_Error( 'ez2_photo_upload_path', 'Upload root is missing.' );
    }

    $slots = ezb_media_slot_candidates();
    $required = array( 'home-hero', 'roller-hero', 'sheer-hero', 'shutters-hero', 'rfs-hero' );
    $resolved = array();
    foreach ( $required as $key ) {
        if ( ! isset( $slots[ $key ] ) || ! is_array( $slots[ $key ] )
            || empty( $slots[ $key ]['filename'] ) || empty( $slots[ $key ]['page_slug'] ) ) {
            return new WP_Error( 'ez2_photo_slot_missing', 'A mandatory EZ2 photo slot is undefined.' );
        }
        $slot = $slots[ $key ];
        $owner_id = ezb_featured_image_for_page_slug( $slot['page_slug'] );
        $id = $owner_id ? (int) $owner_id : (int) ezb_find_attachment_by_basename( $slot['filename'] );
        if ( ! $id || 'image/webp' !== get_post_mime_type( $id ) ) {
            return new WP_Error( 'ez2_photo_slot_unresolved', 'At least one curated photo slot has no real WebP.' );
        }
        $attached = get_post( $id );
        if ( ! $attached || 'attachment' !== $attached->post_type || 'inherit' !== $attached->post_status ) {
            return new WP_Error( 'ez2_photo_attachment_invalid', 'Photo slot does not point to a live media attachment.' );
        }

        $file = get_attached_file( $id );
        $path = is_string( $file ) ? realpath( $file ) : false;
        if ( ! is_string( $path ) || is_link( $file ) || ! is_file( $path )
            || strpos( $path, $base_dir . DIRECTORY_SEPARATOR ) !== 0
            || filesize( $path ) < 1024 ) {
            return new WP_Error( 'ez2_photo_file_missing', 'Media file is unavailable or outside private uploads.' );
        }
        $fh = fopen( $path, 'rb' );
        $header = $fh ? fread( $fh, 12 ) : '';
        if ( $fh ) { fclose( $fh ); }
        if ( ! is_string( $header ) || strlen( $header ) !== 12
            || substr( $header, 0, 4 ) !== 'RIFF' || substr( $header, 8, 4 ) !== 'WEBP' ) {
            return new WP_Error( 'ez2_photo_file_format', 'WebP file signature did not match.' );
        }
        $info = wp_get_attachment_metadata( $id );
        if ( ! is_array( $info ) || (int) ( $info['width'] ?? 0 ) < 640
            || (int) ( $info['height'] ?? 0 ) < 480 ) {
            return new WP_Error( 'ez2_photo_resolution', 'A curated photo is too small for the visual layout.' );
        }
        $url = wp_get_attachment_url( $id );
        if ( ! is_string( $url ) || strtolower( (string) wp_parse_url( $url, PHP_URL_HOST ) ) !== $hostname
            || ! in_array( strtolower( (string) wp_parse_url( $url, PHP_URL_SCHEME ) ),
                array( 'http', 'https' ), true ) ) {
            return new WP_Error( 'ez2_photo_remote_media', 'A photo URL points outside the private review site.' );
        }
        $resolved[] = $id;
    }
    if ( count( array_unique( $resolved ) ) < 4 ) {
        return new WP_Error( 'ez2_photo_repeated_media', 'The five photo roles must not all reuse the same image.' );
    }
    return array(
        'status' => 'READY_FOR_PRIVATE_VISUAL_REVIEW_ONLY',
        'media_library_webp_count' => count( $library ),
        'curated_photo_slots' => count( $required ),
        'distinct_curated_photos' => count( array_unique( $resolved ) ),
        'private_media_published' => false,
        'public_release_authorized' => false,
        'site_modified' => false,
    );
}

if ( defined( 'WP_CLI' ) && WP_CLI ) {
    $report = ez2_photo_readiness();
    if ( is_wp_error( $report ) ) {
        WP_CLI::error( $report->get_error_code() . ': ' . $report->get_error_message() );
    }
    WP_CLI::log( wp_json_encode( $report ) );
}
