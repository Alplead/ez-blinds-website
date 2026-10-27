<?php
/** Synthetic, read-only EZ2 photo readiness regression. Never use Owner media. */
define( 'ABSPATH', '/synthetic/' );
class WP_Error {
    private $code;
    private $message;
    public function __construct( $code, $message ) { $this->code = $code; $this->message = $message; }
    public function get_error_code() { return $this->code; }
    public function get_error_message() { return $this->message; }
}
function is_wp_error( $x ) { return $x instanceof WP_Error; }
function wp_parse_url( $url, $part ) { return parse_url( $url, $part ); }
function home_url( $path = '/' ) { return $GLOBALS['home']; }
function get_posts( $query ) { return $GLOBALS['library_ids']; }
function wp_upload_dir() { return array( 'basedir' => $GLOBALS['upload_dir'], 'error' => false ); }
function ezb_media_slot_candidates() {
    return array(
        'home-hero' => array( 'filename'=>'A.jpg', 'page_slug'=>'home' ),
        'roller-hero' => array( 'filename'=>'B.jpg', 'page_slug'=>'roller-blinds' ),
        'sheer-hero' => array( 'filename'=>'A.jpg', 'page_slug'=>'sheer-curtains' ),
        'shutters-hero' => array( 'filename'=>'C.jpg', 'page_slug'=>'plantation-shutters' ),
        'rfs-hero' => array( 'filename'=>'D.jpg', 'page_slug'=>'retractable-flyscreens' ),
    );
}
function ezb_editorial_image_choices() {
    return array( 'sheer'=>array(), 'roller'=>array(), 'flyscreen'=>array(), 'shutters'=>array() );
}
function ezb_editorial_image_id( $key ) { return $GLOBALS['editorial_ids'][ $key ] ?? 0; }
function ezb_featured_image_for_page_slug( $slug ) { return $GLOBALS['owner_featured'][ $slug ] ?? 0; }
function ezb_find_attachment_by_basename( $filename ) { return array( 'A.jpg'=>11,'B.jpg'=>12,'C.jpg'=>13,'D.jpg'=>14 )[ $filename ] ?? 0; }
function get_post_mime_type( $id ) { return $GLOBALS['media'][ $id ]['mime']; }
function get_post( $id ) { return (object) array( 'post_type'=>'attachment', 'post_status'=>'inherit' ); }
function get_attached_file( $id ) { return $GLOBALS['media'][ $id ]['file']; }
function wp_get_attachment_metadata( $id ) { return $GLOBALS['media'][ $id ]['meta']; }
function wp_get_attachment_url( $id ) { return $GLOBALS['media'][ $id ]['url']; }
require dirname( __DIR__ ) . '/scripts/ez2-photo-readiness.php';

$base = sys_get_temp_dir() . '/ez2-preview-photos-' . bin2hex( random_bytes( 5 ) );
$uploads = $base . '/uploads';
if ( ! mkdir( $base ) || ! mkdir( $uploads ) ) { throw new RuntimeException( 'Cannot build isolated fixture' ); }
$GLOBALS['upload_dir'] = $uploads;
$GLOBALS['home'] = 'https://sb-previewtest.vercel.run/';
$GLOBALS['owner_featured'] = array();
$GLOBALS['editorial_ids'] = array( 'sheer'=>11, 'roller'=>12, 'flyscreen'=>14, 'shutters'=>13 );
$GLOBALS['library_ids'] = range( 11, 33 );
$GLOBALS['media'] = array();
$fake_webp = 'RIFF' . pack( 'V', 2040 ) . 'WEBP' . str_repeat( 'x', 2032 );
foreach ( $GLOBALS['library_ids'] as $id ) {
    $file = $uploads . '/' . $id . '.webp';
    file_put_contents( $file, $fake_webp );
    $GLOBALS['media'][ $id ] = array(
        'mime' => 'image/webp',
        'file' => $file,
        'meta' => array( 'width'=>1200, 'height'=>820 ),
        'url' => 'https://sb-previewtest.vercel.run/wp-content/uploads/' . $id . '.webp',
    );
}
$tests = 0;
function checks( $value, $code, $label ) {
    global $tests;
    if ( ! is_wp_error( $value ) || $value->get_error_code() !== $code ) {
        throw new RuntimeException( 'Failed to block ' . $label );
    }
    $tests++;
}
try {
    $r = ez2_photo_readiness();
    if ( ! is_array( $r ) || $r['media_library_webp_count'] !== 23
        || $r['curated_photo_slots'] !== 5 || $r['editorial_hero_slides'] !== 4 || $r['distinct_curated_photos'] !== 4
        || $r['status'] !== 'READY_FOR_PRIVATE_VISUAL_REVIEW_ONLY'
        || $r['public_release_authorized'] !== false || $r['site_modified'] !== false ) {
        throw new RuntimeException( 'Complete private photo preview must pass without publication' );
    }
    $tests++;
    $GLOBALS['home'] = 'https://ezbns.com.au/';
    checks( ez2_photo_readiness(), 'ez2_photo_wrong_host', 'production site' );
    $GLOBALS['home'] = 'https://sb-previewtest.vercel.run/';
    $GLOBALS['library_ids'] = range( 11, 32 );
    checks( ez2_photo_readiness(), 'ez2_photo_library_incomplete', '22-image bare site' );
    $GLOBALS['library_ids'] = range( 11, 33 );
    $GLOBALS['media'][11]['mime'] = 'image/jpeg';
    checks( ez2_photo_readiness(), 'ez2_photo_slot_unresolved', 'wrong photo format' );
    $GLOBALS['media'][11]['mime'] = 'image/webp';
    $GLOBALS['media'][11]['meta']['width'] = 140;
    checks( ez2_photo_readiness(), 'ez2_photo_resolution', 'thumbnail substituted for hero' );
    $GLOBALS['media'][11]['meta']['width'] = 1200;
    $GLOBALS['media'][11]['url'] = 'https://outside.example/a.webp';
    checks( ez2_photo_readiness(), 'ez2_photo_remote_media', 'public external photo URL' );
    $GLOBALS['media'][11]['url'] = 'https://sb-previewtest.vercel.run/wp-content/uploads/11.webp';
    file_put_contents( $GLOBALS['media'][11]['file'], str_repeat( 'X', 2048 ) );
    checks( ez2_photo_readiness(), 'ez2_photo_file_format', 'fake image bytes' );
    file_put_contents( $GLOBALS['media'][11]['file'], $fake_webp );
    unlink( $GLOBALS['media'][11]['file'] );
    checks( ez2_photo_readiness(), 'ez2_photo_file_missing', 'missing image file' );
    file_put_contents( $GLOBALS['media'][11]['file'], $fake_webp );
    $GLOBALS['owner_featured']['roller-blinds'] = 11;
    $GLOBALS['owner_featured']['plantation-shutters'] = 11;
    $GLOBALS['owner_featured']['retractable-flyscreens'] = 11;
    checks( ez2_photo_readiness(), 'ez2_photo_repeated_media', 'one photo substituted for every product' );
    $GLOBALS['owner_featured'] = array();
    $GLOBALS['editorial_ids']['shutters'] = 0;
    checks( ez2_photo_readiness(), 'ez2_photo_editorial_unresolved',
        'missing fourth hero slideshow photograph' );
    $GLOBALS['editorial_ids']['shutters'] = 13;
    $GLOBALS['editorial_ids']['flyscreen'] = 13;
    checks( ez2_photo_readiness(), 'ez2_photo_editorial_duplicate',
        'reused identical carousel picture' );
    $GLOBALS['editorial_ids']['flyscreen'] = 14;
    if ( ! is_array( ez2_photo_readiness() ) ) { throw new RuntimeException( 'Fixture must recover after restoring images' ); }
    $tests++;
    echo 'EZ2_REAL_PHOTO_PREVIEW_GATE_PASS cases=' . $tests . "\n";
} finally {
    foreach ( glob( $uploads . '/*.webp' ) ?: array() as $file ) { unlink( $file ); }
    rmdir( $uploads ); rmdir( $base );
}
