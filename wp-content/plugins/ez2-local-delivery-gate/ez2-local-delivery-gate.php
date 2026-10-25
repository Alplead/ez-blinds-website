<?php
/**
 * Plugin Name: EZ2 Local Delivery Gate
 * Description: Strictly read-only, isolated LocalWP gate for future verified EZ2 delivery. This version NEVER installs, downloads, imports, or modifies site content.
 * Version: 0.1.0
 * Requires PHP: 8.2
 * Text Domain: ez2-local-delivery
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

require_once __DIR__ . '/includes/content-plan.php';

const EZ2_GATE_REPO = 'Alplead/ez-blinds-website';
const EZ2_GATE_PR = 1;
const EZ2_GATE_BRANCH = 'feature/vertical-slice-v1';
const EZ2_GATE_API = 'https://api.github.com/repos/Alplead/ez-blinds-website';
const EZ2_GATE_REQUIRED_RUNS = array(
    'Quality',
    'Runtime Smoke',
    'Release Install Smoke',
    'EZ2 Hero Candidate (No Deployment)',
    'EZ2 Elementor Ephemeral Runtime (No Deployment)',
);

/**
 * Fail closed. Both WordPress URLs must point at the same isolated EZ2 .local
 * host, and the new site's explicit identity must have been set separately.
 * This cannot be enabled accidentally on T2, EZ BNS New Dev or production.
 */
function ez2_gate_site_guard() {
    if ( is_multisite() || ! in_array( wp_get_environment_type(), array( 'local', 'development' ), true ) ) {
        return false;
    }
    if ( get_option( 'ez2_site_identity', '' ) !== 'ez2-isolated-only' ) {
        return false;
    }
    $home = wp_parse_url( home_url( '/' ) );
    $site = wp_parse_url( site_url( '/' ) );
    if ( ! is_array( $home ) || ! is_array( $site ) ) {
        return false;
    }
    $home_host = strtolower( (string) ( $home['host'] ?? '' ) );
    $site_host = strtolower( (string) ( $site['host'] ?? '' ) );
    if ( ! preg_match( '/\\Aez2(?:-[a-z0-9]+)*\\.local\\z/D', $home_host ) || $site_host !== $home_host ) {
        return false;
    }
    foreach ( array( $home, $site ) as $parts ) {
        if ( ! in_array( $parts['scheme'] ?? '', array( 'http', 'https' ), true )
            || isset( $parts['user'] ) || isset( $parts['pass'] )
            || isset( $parts['port'] ) || isset( $parts['query'] ) || isset( $parts['fragment'] ) ) {
            return false;
        }
    }
    return true;
}

/** Check the exact approved development PR, never main or a forged branch. */
function ez2_gate_pr_sha( $pr ) {
    if ( ! is_array( $pr )
        || ( $pr['state'] ?? '' ) !== 'open'
        || ( $pr['draft'] ?? false ) !== true
        || ! empty( $pr['merged_at'] )
        || ( $pr['head']['repo']['full_name'] ?? '' ) !== EZ2_GATE_REPO
        || ( $pr['head']['ref'] ?? '' ) !== EZ2_GATE_BRANCH
        || ( $pr['base']['ref'] ?? '' ) !== 'main' ) {
        return new WP_Error( 'ez2_pr_identity', 'The protected source PR has changed. No delivery permitted.' );
    }
    $sha = $pr['head']['sha'] ?? '';
    if ( ! is_string( $sha ) || ! preg_match( '/\\A[a-f0-9]{40}\\z/D', $sha ) ) {
        return new WP_Error( 'ez2_pr_sha', 'Invalid exact source commit.' );
    }
    return $sha;
}

/** Refuse if the latest required workflow run is failed, queued or absent. */
function ez2_gate_run_checks( $runs, $sha ) {
    if ( ! is_array( $runs ) || ! isset( $runs['workflow_runs'] ) || ! is_array( $runs['workflow_runs'] ) ) {
        return new WP_Error( 'ez2_runs_missing', 'No auditable GitHub workflow results.' );
    }
    $latest = array();
    foreach ( $runs['workflow_runs'] as $run ) {
        if ( ! is_array( $run ) || ( $run['head_sha'] ?? '' ) !== $sha
            || ( $run['event'] ?? '' ) !== 'pull_request' ) {
            continue;
        }
        $name = $run['name'] ?? '';
        $id = $run['id'] ?? null;
        if ( ! is_string( $name ) || ! in_array( $name, EZ2_GATE_REQUIRED_RUNS, true )
            || ! is_int( $id ) || $id < 1 ) {
            continue;
        }
        if ( ! isset( $latest[ $name ] ) || $id > $latest[ $name ]['id'] ) {
            $latest[ $name ] = $run;
        }
    }
    foreach ( EZ2_GATE_REQUIRED_RUNS as $name ) {
        if ( ! isset( $latest[ $name ] )
            || ( $latest[ $name ]['status'] ?? '' ) !== 'completed'
            || ( $latest[ $name ]['conclusion'] ?? '' ) !== 'success' ) {
            return new WP_Error( 'ez2_ci_blocked', $name . ' is not green on the exact commit.' );
        }
    }
    return true;
}

/** HTTPS-only read of one known public GitHub API, no tokens or redirects. */
function ez2_gate_github_get( $url ) {
    if ( ! is_string( $url ) || strpos( $url, EZ2_GATE_API . '/' ) !== 0 ) {
        return new WP_Error( 'ez2_api_scope', 'Unexpected API endpoint.' );
    }
    $response = wp_remote_get( $url, array(
        'timeout' => 15,
        'redirection' => 0,
        'headers' => array(
            'Accept' => 'application/vnd.github+json',
            'X-GitHub-Api-Version' => '2022-11-28',
            'User-Agent' => 'EZ2-Local-Delivery-Gate/0.1',
        ),
    ) );
    if ( is_wp_error( $response ) ) {
        return $response;
    }
    if ( 200 !== wp_remote_retrieve_response_code( $response ) ) {
        return new WP_Error( 'ez2_api_http', 'GitHub API unavailable. No delivery permitted.' );
    }
    $data = json_decode( wp_remote_retrieve_body( $response ), true );
    return is_array( $data ) ? $data : new WP_Error( 'ez2_api_json', 'Unexpected GitHub data.' );
}

/** Read-only; double-check PR HEAD after the five checks to catch drift. */
function ez2_gate_preflight() {
    if ( ! ez2_gate_site_guard() ) {
        return new WP_Error( 'ez2_wrong_site', 'This check is restricted to a separately provisioned EZ2 .local development site.' );
    }
    $first = ez2_gate_github_get( EZ2_GATE_API . '/pulls/' . EZ2_GATE_PR );
    if ( is_wp_error( $first ) ) { return $first; }
    $sha = ez2_gate_pr_sha( $first );
    if ( is_wp_error( $sha ) ) { return $sha; }
    $runs = ez2_gate_github_get(
        EZ2_GATE_API . '/actions/runs?head_sha=' . rawurlencode( $sha ) . '&event=pull_request&per_page=100'
    );
    if ( is_wp_error( $runs ) ) { return $runs; }
    $checks = ez2_gate_run_checks( $runs, $sha );
    if ( is_wp_error( $checks ) ) { return $checks; }
    $again = ez2_gate_github_get( EZ2_GATE_API . '/pulls/' . EZ2_GATE_PR );
    if ( is_wp_error( $again ) ) { return $again; }
    if ( ez2_gate_pr_sha( $again ) !== $sha ) {
        return new WP_Error( 'ez2_sha_moved', 'GitHub branch moved during checks. Try again later.' );
    }
    // This is source verification, NOT installed-site or package attestation.
    return array(
        'source_sha' => $sha,
        'required_workflow_count' => count( EZ2_GATE_REQUIRED_RUNS ),
        'source_ci_pass' => true,
        'source_release_installable' => false,
        'content_media_imported' => false,
        'backup_tested_on_localwp' => false,
        'one_click_ready' => false,
        'site_modified' => false,
    );
}

/**
 * Take a private, read-only baseline of managed Elementor pages in the
 * isolated LocalWP site. Never expose raw titles, post content or media URLs.
 * Digests can be compared against a future verified release to block Owner
 * edits from being silently overwritten.
 */
function ez2_gate_local_snapshot() {
    if ( ! ez2_gate_site_guard() ) {
        return new WP_Error( 'ez2_wrong_site', 'Only an isolated EZ2 site may be inspected.' );
    }
    if ( ! function_exists( 'get_plugins' ) || ! function_exists( 'is_plugin_active' ) ) {
        require_once ABSPATH . 'wp-admin/includes/plugin.php';
    }
    $plugins = get_plugins();
    $installed = $plugins['elementor/elementor.php'] ?? null;
    $ids = get_posts( array(
        'post_type' => 'page',
        'post_status' => array( 'publish', 'draft', 'private', 'pending', 'future' ),
        'meta_key' => '_ez2_managed_key',
        'posts_per_page' => 101,
        'fields' => 'ids',
        'suppress_filters' => true,
    ) );
    if ( ! is_array( $ids ) || count( $ids ) > 100 ) {
        return new WP_Error( 'ez2_managed_pages_limit', 'Managed pages exceeded the inspection limit.' );
    }
    $digest_by_key = array();
    foreach ( $ids as $id ) {
        if ( ! is_int( $id ) || $id < 1 ) {
            return new WP_Error( 'ez2_managed_id', 'Unexpected managed page identifier.' );
        }
        $key = get_post_meta( $id, '_ez2_managed_key', true );
        if ( ! is_string( $key ) || ! preg_match( '/\\Aez2-[a-z0-9-]{1,63}\\z/D', $key )
            || isset( $digest_by_key[ $key ] ) ) {
            return new WP_Error( 'ez2_managed_key', 'Invalid or duplicated managed page ownership.' );
        }
        // Elementor page settings can be an ARRAY, not just a string.
        // Preserve the raw stored structure before hashing; casting arrays to
        // "Array" would conceal Owner edits and cause false non-conflicts.
        $parts = array(
            get_post_field( 'post_title', $id ),
            get_post_field( 'post_content', $id ),
            get_post_meta( $id, '_elementor_data', true ),
            get_post_meta( $id, '_elementor_page_settings', true ),
            get_post_meta( $id, '_thumbnail_id', true ),
        );
        $serialized = wp_json_encode( $parts );
        if ( ! is_string( $serialized ) || strlen( $serialized ) > 8 * 1024 * 1024 ) {
            return new WP_Error( 'ez2_page_digest', 'Managed page data cannot be safely fingerprinted.' );
        }
        $digest_by_key[ $key ] = hash( 'sha256', $serialized );
    }
    ksort( $digest_by_key, SORT_STRING );
    return array(
        'isolated_site' => true,
        'elementor_installed' => is_array( $installed ),
        'elementor_version' => is_array( $installed ) ? (string) ( $installed['Version'] ?? '' ) : null,
        'elementor_active' => is_plugin_active( 'elementor/elementor.php' ),
        'managed_page_count' => count( $digest_by_key ),
        'managed_page_digests' => $digest_by_key,
        'installed_release_attested' => false,
        'private_content_returned' => false,
        'site_modified' => false,
        'one_click_ready' => false,
    );
}

add_action( 'admin_menu', function () {
    add_management_page( 'EZ2 Delivery Gate', 'EZ2 Delivery Gate',
        'manage_options', 'ez2-delivery-gate', 'ez2_gate_render_admin' );
} );

function ez2_gate_render_admin() {
    if ( ! current_user_can( 'manage_options' ) ) {
        wp_die( esc_html__( 'Insufficient permissions.' ) );
    }
    $report = null;
    if ( 'POST' === ( $_SERVER['REQUEST_METHOD'] ?? '' )
        && in_array( $_POST['ez2_gate_action'] ?? '', array( 'preflight', 'snapshot' ), true ) ) {
        check_admin_referer( 'ez2_gate_preflight', 'ez2_gate_nonce' );
        $report = ( $_POST['ez2_gate_action'] === 'snapshot' )
            ? ez2_gate_local_snapshot() : ez2_gate_preflight();
    }
    echo '<div class="wrap"><h1>EZ2 — Verified Delivery Gate</h1>';
    echo '<p><strong>SAFE PREVIEW ONLY.</strong> No button here installs plugins, imports pages, touches media, updates the database, or downloads release packages.</p>';
    if ( ! ez2_gate_site_guard() ) {
        echo '<div class="notice notice-error"><p>WRONG SITE: only an isolated EZ2 LocalWP clone with explicit site identity is eligible. No action allowed.</p></div>';
    } else {
        echo '<form method="post">';
        wp_nonce_field( 'ez2_gate_preflight', 'ez2_gate_nonce' );
        echo '<input type="hidden" name="ez2_gate_action" value="preflight">';
        submit_button( 'Check five GitHub tests (read-only)', 'secondary', 'submit', false );
        echo '</form><form method="post">';
        wp_nonce_field( 'ez2_gate_preflight', 'ez2_gate_nonce' );
        echo '<input type="hidden" name="ez2_gate_action" value="snapshot">';
        submit_button( 'Inspect protected local page and plugin state (read-only)', 'secondary', 'submit', false );
        echo '</form>';
    }
    if ( is_wp_error( $report ) ) {
        echo '<div class="notice notice-error"><p>' . esc_html( $report->get_error_message() ) . '</p></div>';
    } elseif ( is_array( $report ) && isset( $report['source_sha'] ) ) {
        echo '<div class="notice notice-info"><p>Source CI: verified at <code>'
             . esc_html( $report['source_sha'] ) . '</code>. <strong>Full LocalWP delivery: NOT READY.</strong></p></div>';
    } elseif ( is_array( $report ) ) {
        echo '<div class="notice notice-info"><p>Local Elementor installed: '
             . ( $report['elementor_installed'] ? 'yes' : 'no' )
             . '; active: ' . ( $report['elementor_active'] ? 'yes' : 'no' )
             . '; managed pages: ' . (int) $report['managed_page_count']
             . '. Owner content not displayed. <strong>Full delivery: NOT READY.</strong></p></div>';
    }
    echo '</div>';
}
