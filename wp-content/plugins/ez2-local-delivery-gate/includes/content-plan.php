<?php
/**
 * EZ2 v1 exact-SHA content-diff planner. Pure, read-only.
 *
 * Inputs are strictly digest-only. desired_sha256 and baseline_sha256 must be
 * hashes of the SAME WordPress managed-page snapshot representation produced
 * by ez2_gate_local_snapshot() (wp-fields-v1), not hashes of a raw Elementor
 * export. Never treat this plan as installed-site attestation or permission
 * to apply; the apply step must re-read all local hashes under its own lock.
 */

function ez2_gate_content_schema( $value, $expected ) {
    if ( ! is_array( $value ) || array_keys( $value ) !== $expected ) {
        return false;
    }
    return true;
}

function ez2_gate_content_sha( $value ) {
    return is_string( $value ) && 1 === preg_match( '/\\A[a-f0-9]{64}\\z/D', $value );
}

function ez2_gate_content_key( $value ) {
    return is_string( $value ) && 1 === preg_match( '/\\Aez2-[a-z0-9-]{1,63}\\z/D', $value );
}

/**
 * No SQL/HTML, title, URLs, media IDs or private Owner content may enter this
 * function; only managed keys and SHA-256 hashes. Any ambiguity fails closed.
 */
function ez2_gate_content_plan( $candidate, $local, $source ) {
    if ( ! ez2_gate_site_guard() ) {
        return new WP_Error( 'ez2_wrong_site', 'Content planning is restricted to an isolated EZ2 site.' );
    }
    if ( ! ez2_gate_content_schema( $candidate, array(
        'schema_version', 'target_site', 'source_sha', 'snapshot_schema', 'pages'
    ) ) || $candidate['schema_version'] !== 1
        || $candidate['target_site'] !== 'ez2-isolated-only'
        || $candidate['snapshot_schema'] !== 'wp-fields-v1'
        || ! is_array( $candidate['pages'] )
        || count( $candidate['pages'] ) < 1 || count( $candidate['pages'] ) > 100 ) {
        return new WP_Error( 'ez2_candidate_schema', 'Invalid or oversized delivery plan.' );
    }
    if ( ! is_array( $source ) || ( $source['source_ci_pass'] ?? null ) !== true
        || ( $source['site_modified'] ?? null ) !== false
        || ( $source['one_click_ready'] ?? null ) !== false
        || ! is_string( $source['source_sha'] ?? null )
        || ! preg_match( '/\\A[a-f0-9]{40}\\z/D', $source['source_sha'] )
        || $candidate['source_sha'] !== $source['source_sha'] ) {
        return new WP_Error( 'ez2_source_drift', 'Candidate does not match the checked exact GitHub SHA.' );
    }
    if ( ! is_array( $local ) || ( $local['isolated_site'] ?? null ) !== true
        || ( $local['site_modified'] ?? null ) !== false
        || ( $local['installed_release_attested'] ?? null ) !== false
        || ! is_array( $local['managed_page_digests'] ?? null )
        || count( $local['managed_page_digests'] ) > 100 ) {
        return new WP_Error( 'ez2_local_snapshot', 'No trusted read-only local snapshot.' );
    }
    $existing = $local['managed_page_digests'];
    foreach ( $existing as $key => $hash ) {
        if ( ! ez2_gate_content_key( $key ) || ! ez2_gate_content_sha( $hash ) ) {
            return new WP_Error( 'ez2_local_digest', 'Malformed local ownership/digest record.' );
        }
    }

    $seen = array();
    $actions = array(
        'create' => array(),
        'update' => array(),
        'unchanged' => array(),
        'blocked_owner_conflict' => array(),
        'preserved_existing' => array(),
    );
    $last = '';
    foreach ( $candidate['pages'] as $page ) {
        if ( ! ez2_gate_content_schema( $page, array(
            'key', 'baseline_sha256', 'desired_sha256'
        ) ) || ! ez2_gate_content_key( $page['key'] )
            || ! ez2_gate_content_sha( $page['desired_sha256'] )
            || ( null !== $page['baseline_sha256']
                && ! ez2_gate_content_sha( $page['baseline_sha256'] ) )
            || ( $last !== '' && strcmp( $last, $page['key'] ) >= 0 ) ) {
            return new WP_Error( 'ez2_candidate_page', 'Unsorted, duplicate or invalid managed page.' );
        }
        $key = $page['key'];
        $last = $key;
        $seen[ $key ] = true;
        $previous = $page['baseline_sha256'];
        $desired = $page['desired_sha256'];
        $current = $existing[ $key ] ?? null;
        if ( null === $current && null === $previous ) {
            $actions['create'][] = $key;
        } elseif ( null === $current || null === $previous ) {
            // Never adopt an existing Owner page without a verified baseline.
            $actions['blocked_owner_conflict'][] = $key;
        } elseif ( hash_equals( $current, $desired ) ) {
            $actions['unchanged'][] = $key;
        } elseif ( hash_equals( $current, $previous ) ) {
            $actions['update'][] = $key;
        } else {
            $actions['blocked_owner_conflict'][] = $key;
        }
    }
    foreach ( $existing as $key => $_ ) {
        if ( ! isset( $seen[ $key ] ) ) {
            $actions['preserved_existing'][] = $key;
        }
    }
    sort( $actions['preserved_existing'], SORT_STRING );

    return array(
        'status' => count( $actions['blocked_owner_conflict'] ) ? 'BLOCKED_OWNER_CONFLICT' : 'PREVIEW_ONLY',
        'source_sha' => $source['source_sha'],
        'snapshot_schema' => 'wp-fields-v1',
        'actions' => $actions,
        'private_page_data_returned' => false,
        'local_site_rechecked_at_apply' => false,
        'media_installed' => false,
        'plugins_installed' => false,
        'backup_restored_tested' => false,
        'one_click_ready' => false,
        'site_modified' => false,
    );
}
