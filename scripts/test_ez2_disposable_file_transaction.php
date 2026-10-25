<?php
/** Real file operations, but strictly disposable PHP runner fixtures. */
define( 'EZ2_CI_DISPOSABLE_ONLY', true );
putenv( 'EZ2_DISPOSABLE_FS_SWAP=YES_TEST_TEMP_ONLY' );
require dirname( __DIR__ ) . '/wp-content/plugins/ez2-local-delivery-gate/includes/disposable-file-transaction.php';

$cases = 0;
function must( $condition, $reason ) {
    global $cases;
    if ( ! $condition ) { throw new RuntimeException( 'FAILED: ' . $reason ); }
    $cases++;
}
function fails( $callback, $contains, $reason ) {
    global $cases;
    try {
        $callback();
    } catch ( Throwable $e ) {
        if ( strpos( $e->getMessage(), $contains ) === false ) {
            throw new RuntimeException( $reason . ': ' . $e->getMessage() );
        }
        $cases++;
        return;
    }
    throw new RuntimeException( 'Unblocked: ' . $reason );
}
function fixture() {
    $base = realpath( sys_get_temp_dir() );
    $root = $base . '/ez2-ci-' . bin2hex( random_bytes( 7 ) );
    if ( ! mkdir( $root, 0700 ) ) { throw new RuntimeException( 'Cannot create fixture.' ); }
    file_put_contents( $root . '/.ez2-disposable-fixture', "SYNTHETIC ONLY\n" );
    foreach ( array( 'installed', 'incoming' ) as $side ) {
        mkdir( $root . '/' . $side );
        foreach ( ez2_ci_fs_targets() as $target ) {
            mkdir( $root . '/' . $side . '/' . $target );
            file_put_contents( $root . '/' . $side . '/' . $target . '/main.php',
                ( $side === 'installed' ? 'OLD:' : 'NEW:' ) . $target );
            mkdir( $root . '/' . $side . '/' . $target . '/assets' );
            file_put_contents( $root . '/' . $side . '/' . $target . '/assets/style.css',
                ( $side === 'installed' ? 'OLD CSS:' : 'NEW CSS:' ) . $target );
        }
    }
    return $root;
}
function matches( $root, $side, $prefix ) {
    foreach ( ez2_ci_fs_targets() as $target ) {
        $got = file_get_contents( $root . '/' . $side . '/' . $target . '/main.php' );
        if ( $got !== $prefix . ':' . $target ) { return false; }
        $css = file_get_contents( $root . '/' . $side . '/' . $target . '/assets/style.css' );
        if ( $css !== $prefix . ' CSS:' . $target ) { return false; }
    }
    return true;
}
foreach ( array(
    'after_backup_1', 'after_install_1', 'after_backup_2',
    'after_install_2', 'after_backup_3', 'after_install_3',
) as $fault ) {
    $root = fixture();
    fails( fn() => ez2_ci_fs_swap( $root, $fault ), 'SAFE_ROLLBACK_COMPLETE',
        'Cannot recover injected ' . $fault );
    must( matches( $root, 'installed', 'OLD' ), 'Old code survives ' . $fault );
    must( matches( $root, 'incoming', 'NEW' ), 'New candidate isolated ' . $fault );
    must( ! file_exists( $root . '/recovery-backup' ), 'Temporary rollback dir cleaned ' . $fault );
    ez2_ci_fs_remove_tree( $root );
}
$root = fixture();
$result = ez2_ci_fs_swap( $root );
must( $result['status'] === 'SYNTHETIC_FILE_SWAP_ONLY'
    && $result['components'] === 3 && $result['one_click_ready'] === false
    && $result['db_backup_verified'] === false
    && $result['owner_localwp_changed'] === false, 'Successful scoped code-only swap' );
must( matches( $root, 'installed', 'NEW' ), 'New code in three installed locations' );
must( matches( $root, 'recovery-backup', 'OLD' ), 'Old versions retained privately' );
fails( fn() => ez2_ci_fs_swap( $root ), 'Unsafe component directory',
    'Cannot repeat without explicit new candidate' );
must( ez2_ci_fs_restore( $root ) === 'SYNTHETIC_RESTORE_PASS',
    'Manually invoked fixture restore succeeds' );
must( matches( $root, 'installed', 'OLD' ), 'After restore all old code returns' );
must( matches( $root, 'incoming', 'NEW' ), 'After restore all new code isolated' );
must( ! file_exists( $root . '/recovery-backup' ), 'After restore backup dir cleaned' );
ez2_ci_fs_remove_tree( $root );
$root = fixture();
file_put_contents( $root . '/incoming/elementor/untrusted-link-source.php', 'unsafe' );
symlink( '/etc/passwd', $root . '/incoming/elementor/link.php' );
fails( fn() => ez2_ci_fs_swap( $root ), 'Invalid or symbolic component entry',
    'Symlink must be refused before any mutation' );
must( matches( $root, 'installed', 'OLD' ), 'Unsafe candidate left original installation intact' );
ez2_ci_fs_remove_tree( $root );
$root = fixture();
file_put_contents( $root . '/incoming/ezb-theme/wp-config.php', str_repeat( 'x', 9 * 1024 * 1024 ) );
fails( fn() => ez2_ci_fs_swap( $root ), 'Component size or file-count limit',
    'Oversized component must be refused before mutation' );
must( matches( $root, 'installed', 'OLD' ), 'Oversized candidate left original installation intact' );
ez2_ci_fs_remove_tree( $root );
$root = fixture();
file_put_contents( $root . '/.ez2-disposable-fixture', 'NO AUTHORIZATION' );
fails( fn() => ez2_ci_fs_swap( $root ), 'Unsafe filesystem fixture path',
    'Missing isolated marker blocks all writes' );
must( matches( $root, 'installed', 'OLD' ), 'Incorrect marker preserved original installation' );
ez2_ci_fs_remove_tree( $root );
$root = fixture();
$outside = dirname( $root ) . '/no-ez2-fixture';
fails( fn() => ez2_ci_fs_swap( $outside ), 'CI-only filesystem transaction gate closed',
    'No arbitrary destination accepted' );
ez2_ci_fs_remove_tree( $root );
$root = fixture();
putenv( 'EZ2_DISPOSABLE_FS_SWAP=OFF' );
fails( fn() => ez2_ci_fs_swap( $root ), 'CI-only filesystem transaction gate closed',
    'Missing explicit opt-in refuses write' );
must( matches( $root, 'installed', 'OLD' ), 'Disabled gate never changes files' );
ez2_ci_fs_remove_tree( $root );
echo 'EZ2_CI_FILE_TRANSACTION_PASS cases=' . $cases . "\n";
