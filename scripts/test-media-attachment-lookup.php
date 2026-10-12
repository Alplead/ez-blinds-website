<?php
/**
 * Synthetic regression for exact media-attachment lookup. No WordPress, DB or
 * customer images are needed: this exercises the real production resolver.
 */
$source = file_get_contents( __DIR__ . '/../wp-content/plugins/ezb-core/ezb-core.php' );
if ( ! preg_match( '/function ezb_find_attachment_by_basename\([^)]*\)\s*\{[\s\S]*?\n\}/', $source, $match ) ) {
    throw new RuntimeException( 'Cannot locate production media resolver.' );
}

class EZB_Fake_WPDB {
    public $postmeta = 'wp_postmeta';
    public $posts = 'wp_posts';
    public $rows = array();
    private $last = null;

    public function esc_like( $value ) { return addcslashes( $value, '%_\\' ); }
    public function prepare( $sql, ...$args ) {
        $required = array(
            'INNER JOIN', 'attachment.ID = pm.post_id',
            "attachment.post_type = 'attachment'",
            "attachment.post_status <> 'trash'",
            'attachment.post_mime_type = %s',
            'pm.meta_value LIKE %s',
        );
        foreach ( $required as $clause ) {
            if ( ! str_contains( $sql, $clause ) ) {
                throw new RuntimeException( 'Media query missing safety clause: ' . $clause );
            }
        }
        if ( 2 !== count( $args ) ) {
            throw new RuntimeException( 'Expected filename and exact MIME parameters.' );
        }
        $this->last = array( 'sql' => $sql, 'args' => $args );
        return $sql;
    }
    public function get_var( $sql ) {
        if ( ! $this->last || $sql !== $this->last['sql'] ) {
            throw new RuntimeException( 'Unexpected database query.' );
        }
        $suffix = substr( $this->last['args'][0], 1 );
        $mime = $this->last['args'][1];
        $found = array();
        foreach ( $this->rows as $row ) {
            if ( 'attachment' !== $row['type'] || 'trash' === $row['status'] ||
                $mime !== $row['mime'] || ! str_ends_with( $row['file'], $suffix ) ) {
                continue;
            }
            $found[] = $row['id'];
        }
        return $found ? max( $found ) : null;
    }
}
function wp_basename( $filename ) { return basename( $filename ); }
function sanitize_file_name( $filename ) { return preg_replace( '/\s+/', '-', $filename ); }
function ezb_test_row( $id, $file, $mime, $type = 'attachment', $status = 'inherit' ) {
    return compact( 'id', 'file', 'mime', 'type', 'status' );
}
function ezb_expect_id( $filename, $expected ) {
    $actual = ezb_find_attachment_by_basename( $filename );
    if ( $actual !== $expected ) {
        throw new RuntimeException( "$filename resolved to $actual, expected $expected" );
    }
}

$GLOBALS['wpdb'] = new EZB_Fake_WPDB();
$wpdb->rows = array(
    ezb_test_row( 50, '2026/10/test-case.webp', 'image/webp' ),
    ezb_test_row( 99, '2026/10/test-case.webp', 'image/webp', 'post' ),
    ezb_test_row( 100, '2026/10/test-case.webp', 'image/webp', 'attachment', 'trash' ),
    ezb_test_row( 101, '2026/10/test-case.webp', 'image/svg+xml' ),
    ezb_test_row( 60, '2026/10/test-case.jpg', 'image/jpeg' ),
    ezb_test_row( 70, '2026/10/only-jpg.jpg', 'image/jpeg' ),
    ezb_test_row( 80, '2026/10/clip.mp4', 'video/mp4' ),
    ezb_test_row( 90, '2026/10/clip.webp', 'image/webp' ),
    ezb_test_row( 120, '2026/10/space-name.webp', 'image/webp' ),
    ezb_test_row( 130, '2026/10/recent.webp', 'image/webp' ),
    ezb_test_row( 131, '2026/11/recent.webp', 'image/webp' ),
    ezb_test_row( 140, '2026/10/mismatch.jpg', 'image/png' ),
);
eval( $match[0] );

ezb_expect_id( 'test-case.jpg', 50 ); // Prefer approved derivative; ignore forged newer rows.
ezb_expect_id( 'only-jpg.jpg', 70 ); // Graceful legacy JPEG fallback.
ezb_expect_id( 'clip.mp4', 80 ); // Never silently replace video with a still image.
ezb_expect_id( 'ghost.jpg', 0 ); // Missing media must fail closed.
$wpdb->rows[] = ezb_test_row( 150, '2026/10/ghost.webp', 'image/webp' );
ezb_expect_id( 'ghost.jpg', 150 ); // A miss must not be cached across a later import.
ezb_expect_id( 'payload.svg', 0 ); // Unsupported requested extension is rejected.
ezb_expect_id( 'space name.jpg', 120 ); // WordPress-sanitised filenames still resolve.
ezb_expect_id( 'recent.jpg', 131 ); // Newest valid attachment wins.

ezb_expect_id( 'mismatch.jpg', 0 ); // MIME must agree with extension.
echo "EZB_MEDIA_ATTACHMENT_LOOKUP_PASS cases=9\n";
