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
            'pm.meta_value = %s', 'pm.meta_value LIKE %s',
        );
        foreach ( $required as $clause ) {
            if ( ! str_contains( $sql, $clause ) ) {
                throw new RuntimeException( 'Media query missing safety clause: ' . $clause );
            }
        }
        if ( 3 !== count( $args ) ) {
            throw new RuntimeException( 'Expected exact root filename, slash-delimited suffix and MIME parameters.' );
        }
        $this->last = array( 'sql' => $sql, 'args' => $args );
        return $sql;
    }
    public function get_var( $sql ) {
        if ( ! $this->last || $sql !== $this->last['sql'] ) {
            throw new RuntimeException( 'Unexpected database query.' );
        }
        $exact = $this->last['args'][0];
        $suffix = substr( $this->last['args'][1], 1 );
        $mime = $this->last['args'][2];
        $found = array();
        foreach ( $this->rows as $row ) {
            if ( 'attachment' !== $row['type'] || 'trash' === $row['status'] ||
                $mime !== $row['mime'] ||
                ( $row['file'] !== $exact && ! str_ends_with( $row['file'], $suffix ) ) ) {
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

// All paths below are synthetic temporary fixtures, never customer media.
$fixture_root = sys_get_temp_dir() . '/ezb-media-lookup-' . bin2hex( random_bytes( 8 ) );
$GLOBALS['ezb_test_uploads'] = $fixture_root . '/uploads';
$GLOBALS['ezb_test_overrides'] = array();
if ( ! mkdir( $GLOBALS['ezb_test_uploads'], 0700, true ) ) {
    throw new RuntimeException( 'Cannot create isolated media fixture.' );
}
function wp_get_upload_dir() {
    return array( 'basedir' => $GLOBALS['ezb_test_uploads'] );
}
function get_attached_file( $id ) {
    if ( isset( $GLOBALS['ezb_test_overrides'][ $id ] ) ) {
        return $GLOBALS['ezb_test_overrides'][ $id ];
    }
    foreach ( $GLOBALS['wpdb']->rows as $row ) {
        if ( $row['id'] === $id ) {
            return $GLOBALS['ezb_test_uploads'] . '/' . $row['file'];
        }
    }
    return false;
}
function ezb_fixture_file( $path ) {
    if ( ! is_dir( dirname( $path ) ) ) {
        mkdir( dirname( $path ), 0700, true );
    }
    file_put_contents( $path, 'synthetic fixture' );
}
register_shutdown_function( function () use ( $fixture_root ) {
    if ( ! is_dir( $fixture_root ) ) return;
    $files = new RecursiveIteratorIterator(
        new RecursiveDirectoryIterator( $fixture_root, FilesystemIterator::SKIP_DOTS ),
        RecursiveIteratorIterator::CHILD_FIRST
    );
    foreach ( $files as $entry ) {
        if ( $entry->isLink() || $entry->isFile() ) unlink( $entry->getPathname() );
        else rmdir( $entry->getPathname() );
    }
    rmdir( $fixture_root );
} );

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
    ezb_test_row( 160, 'root-only.webp', 'image/webp' ),
    ezb_test_row( 161, 'root-jpg.jpg', 'image/jpeg' ),
    ezb_test_row( 170, 'mixed.webp', 'image/webp' ),
    ezb_test_row( 180, '2026/10/mixed.webp', 'image/webp' ),
    ezb_test_row( 190, 'near-root-only.webp', 'image/webp' ),
    ezb_test_row( 200, '2026/10/missing-on-disk.webp', 'image/webp' ),
    ezb_test_row( 201, '2026/10/outside-root.webp', 'image/webp' ),
    ezb_test_row( 202, '2026/10/linked-leaf.webp', 'image/webp' ),
    ezb_test_row( 203, 'linked-dir/linked-parent.webp', 'image/webp' ),
    ezb_test_row( 204, '2026/10/linked-base.webp', 'image/webp' ),
    ezb_test_row( 205, '2026/10/missing-base.webp', 'image/webp' ),
);
foreach ( $wpdb->rows as $row ) {
    if ( in_array( $row['id'], array( 200, 203 ), true ) ) continue;
    ezb_fixture_file( $GLOBALS['ezb_test_uploads'] . '/' . $row['file'] );
}
if ( ! preg_match( '/function ezb_attachment_is_local_media\([^)]*\)\s*\{[\s\S]*?\n\}/', $source, $guard_match ) ) {
    throw new RuntimeException( 'Cannot locate production attachment path guard.' );
}
eval( $guard_match[0] );
eval( $match[0] );

ezb_expect_id( 'test-case.jpg', 50 ); // Prefer approved derivative; ignore forged newer rows.
ezb_expect_id( 'only-jpg.jpg', 70 ); // Graceful legacy JPEG fallback.
ezb_expect_id( 'clip.mp4', 80 ); // Never silently replace video with a still image.
ezb_expect_id( 'ghost.jpg', 0 ); // Missing media must fail closed.
$wpdb->rows[] = ezb_test_row( 150, '2026/10/ghost.webp', 'image/webp' );
ezb_fixture_file( $GLOBALS['ezb_test_uploads'] . '/2026/10/ghost.webp' );
ezb_expect_id( 'ghost.jpg', 150 ); // A miss must not be cached across a later import.
ezb_expect_id( 'payload.svg', 0 ); // Unsupported requested extension is rejected.
ezb_expect_id( 'space name.jpg', 120 ); // WordPress-sanitised filenames still resolve.
ezb_expect_id( 'recent.jpg', 131 ); // Newest valid attachment wins.

ezb_expect_id( 'mismatch.jpg', 0 ); // MIME must agree with extension.
ezb_expect_id( 'root-only.jpg', 160 ); // WebP in upload root, without YYYY/MM path.
ezb_expect_id( 'root-jpg.jpg', 161 ); // Legacy JPEG in upload root.
ezb_expect_id( 'mixed.jpg', 180 ); // Newest valid match across root and dated folders.
ezb_expect_id( 'near-root-only.jpg', 190 ); // Exact near-name must resolve to itself.
// A database row cannot make a missing or external file safe to render.
ezb_expect_id( 'missing-on-disk.webp', 0 );
$outside = $fixture_root . '/outside-root.webp';
ezb_fixture_file( $outside );
$GLOBALS['ezb_test_overrides'][201] = $outside;
ezb_expect_id( 'outside-root.webp', 0 );

// Linked leaf and linked ancestor must fail even when they point back inside
// the approved uploads tree.
$linked_leaf = $GLOBALS['ezb_test_uploads'] . '/2026/10/linked-leaf.webp';
unlink( $linked_leaf );
if ( ! symlink( $GLOBALS['ezb_test_uploads'] . '/2026/10/test-case.webp', $linked_leaf ) ) {
    throw new RuntimeException( 'Cannot create symlink test fixture.' );
}
ezb_expect_id( 'linked-leaf.webp', 0 );
$real_dir = $GLOBALS['ezb_test_uploads'] . '/real-dir';
ezb_fixture_file( $real_dir . '/linked-parent.webp' );
if ( ! symlink( $real_dir, $GLOBALS['ezb_test_uploads'] . '/linked-dir' ) ) {
    throw new RuntimeException( 'Cannot create linked-parent fixture.' );
}
ezb_expect_id( 'linked-parent.webp', 0 );

// An uploads-root alias must not bypass the guard. Missing roots fail closed.
$original_uploads = $GLOBALS['ezb_test_uploads'];
$linked_uploads = $fixture_root . '/linked-uploads';
if ( ! symlink( $original_uploads, $linked_uploads ) ) {
    throw new RuntimeException( 'Cannot create linked-uploads fixture.' );
}
$GLOBALS['ezb_test_uploads'] = $linked_uploads;
ezb_expect_id( 'linked-base.webp', 0 );
$GLOBALS['ezb_test_uploads'] = $fixture_root . '/missing-uploads';
ezb_expect_id( 'missing-base.webp', 0 );
$GLOBALS['ezb_test_uploads'] = $original_uploads;

echo "EZB_MEDIA_ATTACHMENT_LOOKUP_PASS cases=19\n";
