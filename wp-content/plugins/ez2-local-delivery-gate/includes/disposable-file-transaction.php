<?php
/**
 * Disposable-EZ2 filesystem transaction prototype. NOT A LOCALWP INSTALLER.
 *
 * Performs REAL directory swaps and rollback in a synthetic temp fixture ONLY.
 * The production-facing EZ2 plugin does not call this; requires test opt-in.
 * Used to prove that first-party theme, EZB core and Elementor directories
 * are moved together and restored when any part of the move fails.
 *
 * Deliberately excludes all databases, real WordPress, media uploads,
 * credentials, internet downloads and Owner's LocalWP.
 */
function ez2_ci_fs_root( $root ) {
    if ( ! defined( 'EZ2_CI_DISPOSABLE_ONLY' )
        || EZ2_CI_DISPOSABLE_ONLY !== true
        || getenv( 'EZ2_DISPOSABLE_FS_SWAP' ) !== 'YES_TEST_TEMP_ONLY'
        || ! is_string( $root ) || ! is_dir( $root ) || is_link( $root ) ) {
        throw new RuntimeException( 'CI-only filesystem transaction gate closed.' );
    }
    $real = realpath( $root );
    $tmp = realpath( sys_get_temp_dir() );
    if ( ! is_string( $real ) || ! is_string( $tmp )
        || $real !== $root || strpos( $real, $tmp . DIRECTORY_SEPARATOR . 'ez2-ci-' ) !== 0
        || ! is_file( $root . '/.ez2-disposable-fixture' )
        || is_link( $root . '/.ez2-disposable-fixture' )
        || file_get_contents( $root . '/.ez2-disposable-fixture' ) !== "SYNTHETIC ONLY\n" ) {
        throw new RuntimeException( 'Unsafe filesystem fixture path or identity.' );
    }
    foreach ( array( 'installed', 'incoming' ) as $dir ) {
        if ( ! is_dir( $real . '/' . $dir ) || is_link( $real . '/' . $dir ) ) {
            throw new RuntimeException( 'Synthetic directory is not isolated.' );
        }
    }
    return $real;
}

function ez2_ci_fs_targets() {
    return array( 'ezb-theme', 'ezb-core', 'elementor' );
}

/** Fully inspect source AND installed directories before the first rename. */
function ez2_ci_fs_inventory( $directory ) {
    if ( is_link( $directory ) || ! is_dir( $directory ) ) {
        throw new RuntimeException( 'Unsafe component directory.' );
    }
    $entries = array();
    $total = 0;
    $walk = function ( $path, $prefix, $depth ) use ( &$walk, &$entries, &$total ) {
        if ( $depth > 14 ) { throw new RuntimeException( 'Excessive nesting.' ); }
        $items = new DirectoryIterator( $path );
        foreach ( $items as $item ) {
            if ( $item->isDot() ) { continue; }
            $name = $item->getFilename();
            if ( ! preg_match( '/\\A[A-Za-z0-9._-]{1,100}\\z/D', $name )
                || $name === '.' || $name === '..' || $item->isLink() ) {
                throw new RuntimeException( 'Invalid or symbolic component entry.' );
            }
            $full = $item->getPathname();
            $relative = $prefix . $name;
            if ( $item->isDir() ) {
                $walk( $full, $relative . '/', $depth + 1 );
            } elseif ( $item->isFile() ) {
                if ( count( $entries ) >= 500
                    || $item->getSize() > 8 * 1024 * 1024
                    || $total + $item->getSize() > 32 * 1024 * 1024 ) {
                    throw new RuntimeException( 'Component size or file-count limit.' );
                }
                $total += $item->getSize();
                $digest = hash_file( 'sha256', $full );
                if ( ! is_string( $digest ) ) {
                    throw new RuntimeException( 'Component cannot be fingerprinted.' );
                }
                $entries[ $relative ] = $digest;
            } else {
                throw new RuntimeException( 'Unsupported filesystem entry.' );
            }
        }
    };
    $walk( $directory, '', 0 );
    if ( count( $entries ) < 1 ) { throw new RuntimeException( 'Empty component.' ); }
    ksort( $entries, SORT_STRING );
    return $entries;
}

function ez2_ci_fs_remove_tree( $path ) {
    if ( is_link( $path ) || is_file( $path ) ) {
        if ( ! unlink( $path ) ) { throw new RuntimeException( 'Cannot remove scratch file.' ); }
        return;
    }
    if ( ! is_dir( $path ) ) { return; }
    foreach ( new DirectoryIterator( $path ) as $item ) {
        if ( ! $item->isDot() ) {
            ez2_ci_fs_remove_tree( $item->getPathname() );
        }
    }
    if ( ! rmdir( $path ) ) { throw new RuntimeException( 'Cannot remove scratch directory.' ); }
}

/** Injected failures exercise rollback, including after all 3 components. */
function ez2_ci_fs_swap( $root, $fault = null ) {
    $root = ez2_ci_fs_root( $root );
    if ( ! in_array( $fault, array( null, 'after_backup_1', 'after_install_1',
        'after_backup_2', 'after_install_2', 'after_backup_3',
        'after_install_3' ), true ) ) {
        throw new RuntimeException( 'Unknown fault-injection phase.' );
    }
    $targets = ez2_ci_fs_targets();
    $expected = array();
    $before = array();
    foreach ( $targets as $target ) {
        $before[ $target ] = ez2_ci_fs_inventory( $root . '/installed/' . $target );
        $expected[ $target ] = ez2_ci_fs_inventory( $root . '/incoming/' . $target );
    }
    $backup = $root . '/recovery-backup';
    if ( file_exists( $backup ) || is_link( $backup ) || ! mkdir( $backup, 0700 ) ) {
        throw new RuntimeException( 'Existing backup or unsafe backup path.' );
    }
    $moved = array();
    $installed = array();
    try {
        foreach ( $targets as $i => $target ) {
            $old = $root . '/installed/' . $target;
            $new = $root . '/incoming/' . $target;
            $saved = $backup . '/' . $target;
            if ( ! rename( $old, $saved ) ) {
                throw new RuntimeException( 'Could not back up old ' . $target );
            }
            $moved[] = $target;
            if ( $fault === 'after_backup_' . ( $i + 1 ) ) {
                throw new RuntimeException( 'INJECTED_AFTER_BACKUP_' . ( $i + 1 ) );
            }
            if ( ! rename( $new, $old ) ) {
                throw new RuntimeException( 'Could not install new ' . $target );
            }
            $installed[] = $target;
            if ( $fault === 'after_install_' . ( $i + 1 ) ) {
                throw new RuntimeException( 'INJECTED_AFTER_INSTALL_' . ( $i + 1 ) );
            }
        }
        foreach ( $expected as $target => $inventory ) {
            if ( ez2_ci_fs_inventory( $root . '/installed/' . $target ) !== $inventory ) {
                throw new RuntimeException( 'Post-install component mismatch.' );
            }
        }
        return array( 'status' => 'SYNTHETIC_FILE_SWAP_ONLY',
            'components' => count( $targets ), 'backups_retained' => true,
            'db_backup_verified' => false, 'owner_localwp_changed' => false,
            'one_click_ready' => false );
    } catch ( Throwable $error ) {
        $rollback_failures = array();
        foreach ( array_reverse( $moved ) as $target ) {
            $live = $root . '/installed/' . $target;
            $old = $backup . '/' . $target;
            try {
                if ( in_array( $target, $installed, true ) ) {
                    $abandoned = $root . '/incoming/' . $target;
                    if ( file_exists( $abandoned ) || ! rename( $live, $abandoned ) ) {
                        throw new RuntimeException( 'Could not isolate failed candidate.' );
                    }
                }
                if ( ! rename( $old, $live ) ) {
                    throw new RuntimeException( 'Could not restore prior installation.' );
                }
            } catch ( Throwable $restore_error ) {
                $rollback_failures[] = $target;
            }
        }
        foreach ( $before as $target => $inventory ) {
            try {
                if ( ez2_ci_fs_inventory( $root . '/installed/' . $target ) !== $inventory ) {
                    $rollback_failures[] = $target;
                }
            } catch ( Throwable $restore_error ) {
                $rollback_failures[] = $target;
            }
        }
        if ( $rollback_failures ) {
            // Crucial: preserve the backup for manual recovery, never delete it.
            throw new RuntimeException( 'CRITICAL: synthetic recovery incomplete; backups preserved.' );
        }
        rmdir( $backup );
        throw new RuntimeException( 'SAFE_ROLLBACK_COMPLETE: ' . $error->getMessage() );
    }
}

/** Deliberate second operation: restore a successful synthetic swap. */
function ez2_ci_fs_restore( $root ) {
    $root = ez2_ci_fs_root( $root );
    $backup = $root . '/recovery-backup';
    if ( ! is_dir( $backup ) || is_link( $backup ) ) {
        throw new RuntimeException( 'No verified synthetic backup.' );
    }
    foreach ( ez2_ci_fs_targets() as $target ) {
        ez2_ci_fs_inventory( $backup . '/' . $target );
        ez2_ci_fs_inventory( $root . '/installed/' . $target );
        if ( file_exists( $root . '/incoming/' . $target ) ) {
            throw new RuntimeException( 'Incoming component path is not empty.' );
        }
    }
    foreach ( ez2_ci_fs_targets() as $target ) {
        if ( ! rename( $root . '/installed/' . $target, $root . '/incoming/' . $target )
            || ! rename( $backup . '/' . $target, $root . '/installed/' . $target ) ) {
            throw new RuntimeException( 'Synthetic restore failed; preserve recovery files.' );
        }
    }
    rmdir( $backup );
    return 'SYNTHETIC_RESTORE_PASS';
}
