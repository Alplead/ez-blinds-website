<?php
/** Pure stubs + synthetic-only regression of the EZ2 WordPress preflight gate. */
define( 'ABSPATH', '/synthetic/' );
class WP_Error {
    private $code;
    private $message;
    public function __construct( $code, $message ) { $this->code = $code; $this->message = $message; }
    public function get_error_code() { return $this->code; }
    public function get_error_message() { return $this->message; }
}
function is_wp_error( $value ) { return $value instanceof WP_Error; }
function is_multisite() { return $GLOBALS['multisite']; }
function wp_get_environment_type() { return $GLOBALS['environment']; }
function get_option( $key, $default = '' ) { return $key === 'ez2_site_identity' ? $GLOBALS['site_identity'] : $default; }
function home_url( $path = '/' ) { return $GLOBALS['home']; }
function site_url( $path = '/' ) { return $GLOBALS['site']; }
function wp_parse_url( $url ) { return parse_url( $url ); }
function add_action( $action, $callback ) {}
function wp_remote_get( $url, $options ) {
    $GLOBALS['urls'][] = $url;
    if ( empty( $GLOBALS['responses'] ) ) { throw new RuntimeException( 'Unexpected request ' . $url ); }
    $r = array_shift( $GLOBALS['responses'] );
    if ( isset( $r['http'] ) ) {
        return array( 'code' => $r['http'], 'body' => '{}' );
    }
    if ( isset( $r['error'] ) ) { return new WP_Error( 'offline', 'offline' ); }
    return array( 'code' => 200, 'body' => json_encode( $r ) );
}
function wp_remote_retrieve_response_code( $r ) { return $r['code']; }
function wp_remote_retrieve_body( $r ) { return $r['body']; }

function get_plugins() { return $GLOBALS['installed_plugins']; }
function is_plugin_active( $slug ) { return in_array( $slug, $GLOBALS['active_plugins'], true ); }
function get_posts( $args ) { return $GLOBALS['page_ids']; }
function get_post_meta( $id, $key, $single ) { return $GLOBALS['page_meta'][$id][$key] ?? ''; }
function get_post_field( $key, $id ) { return $GLOBALS['page_fields'][$id][$key] ?? ''; }
function wp_json_encode( $value ) { return json_encode( $value ); }

require dirname( __DIR__ ) . '/wp-content/plugins/ez2-local-delivery-gate/ez2-local-delivery-gate.php';
$GLOBALS['home'] = 'http://ez2-review.local/';
$GLOBALS['site'] = 'http://ez2-review.local/';
$GLOBALS['site_identity'] = 'ez2-isolated-only';
$GLOBALS['environment'] = 'local';
$GLOBALS['multisite'] = false;
$GLOBALS['responses'] = array();
$GLOBALS['urls'] = array();
$count = 0;
function accept( $value, $label ) {
    global $count;
    if ( ! $value ) { throw new RuntimeException( 'TEST FAILED: ' . $label ); }
    $count++;
}
function reject( $value, $code, $label ) {
    accept( is_wp_error( $value ) && $value->get_error_code() === $code, $label );
}
function pr_fixture( $sha ) {
    return array( 'state' => 'open', 'draft' => true, 'merged_at' => null,
        'head' => array( 'repo' => array( 'full_name' => EZ2_GATE_REPO ),
            'ref' => EZ2_GATE_BRANCH, 'sha' => $sha ),
        'base' => array( 'ref' => 'main' ) );
}
function run_fixture( $sha ) {
    $out = array();
    foreach ( EZ2_GATE_REQUIRED_RUNS as $i => $name ) {
        $out[] = array( 'name' => $name, 'head_sha' => $sha,
            'event' => 'pull_request', 'id' => 100 + $i,
            'status' => 'completed', 'conclusion' => 'success' );
    }
    return array( 'workflow_runs' => $out );
}
$sha = str_repeat( 'a', 40 );
accept( ez2_gate_site_guard(), 'eligible isolated site' );
$GLOBALS['site_identity'] = '';
accept( ! ez2_gate_site_guard(), 'explicit identity required' );
$GLOBALS['site_identity'] = 'ez2-isolated-only';
$GLOBALS['home'] = 'http://ez-bns-new-dev.local/';
$GLOBALS['site'] = $GLOBALS['home'];
accept( ! ez2_gate_site_guard(), 'legacy site must be blocked' );
$GLOBALS['home'] = 'http://t2-ez-blinds-shutters.local/';
$GLOBALS['site'] = $GLOBALS['home'];
accept( ! ez2_gate_site_guard(), 'T2 must be blocked' );
$GLOBALS['home'] = 'https://ezbns.com.au/';
$GLOBALS['site'] = $GLOBALS['home'];
accept( ! ez2_gate_site_guard(), 'production host must be blocked' );
$GLOBALS['home'] = 'http://ez2-review.local/';
$GLOBALS['site'] = 'http://ez2-other.local/';
accept( ! ez2_gate_site_guard(), 'home/site host mismatch blocked' );
$GLOBALS['site'] = $GLOBALS['home'];
$GLOBALS['environment'] = 'production';
accept( ! ez2_gate_site_guard(), 'production environment blocked' );
$GLOBALS['environment'] = 'local';
$GLOBALS['multisite'] = true;
accept( ! ez2_gate_site_guard(), 'multisite blocked' );
$GLOBALS['multisite'] = false;
$GLOBALS['site'] = 'http://ez2-review.local:8080/';
accept( ! ez2_gate_site_guard(), 'noncanonical port blocked' );
$GLOBALS['site'] = $GLOBALS['home'];
accept( ez2_gate_site_guard(), 'restored isolation' );
$p = pr_fixture( $sha );
accept( ez2_gate_pr_sha( $p ) === $sha, 'exact draft branch match' );
$q = $p; $q['draft'] = false;
reject( ez2_gate_pr_sha( $q ), 'ez2_pr_identity', 'non-draft blocked' );
$q = $p; $q['head']['repo']['full_name'] = 'attacker/repo';
reject( ez2_gate_pr_sha( $q ), 'ez2_pr_identity', 'fork blocked' );
$q = $p; $q['base']['ref'] = 'other';
reject( ez2_gate_pr_sha( $q ), 'ez2_pr_identity', 'wrong base blocked' );
$q = $p; $q['merged_at'] = '2026-10-25';
reject( ez2_gate_pr_sha( $q ), 'ez2_pr_identity', 'merged source blocked' );
$q = $p; $q['head']['sha'] = 'truncated';
reject( ez2_gate_pr_sha( $q ), 'ez2_pr_sha', 'invalid SHA blocked' );
$r = run_fixture( $sha );
accept( ez2_gate_run_checks( $r, $sha ) === true, 'five passing checks' );
$q = $r; array_pop( $q['workflow_runs'] );
reject( ez2_gate_run_checks( $q, $sha ), 'ez2_ci_blocked', 'missing fifth check blocked' );
$q = $r; $q['workflow_runs'][0]['conclusion'] = 'failure';
reject( ez2_gate_run_checks( $q, $sha ), 'ez2_ci_blocked', 'failed check blocked' );
$q = $r; $q['workflow_runs'][0]['status'] = 'queued';
reject( ez2_gate_run_checks( $q, $sha ), 'ez2_ci_blocked', 'queued check blocked' );
$q = $r; $q['workflow_runs'][] = array( 'name' => EZ2_GATE_REQUIRED_RUNS[0],
    'head_sha' => $sha, 'event' => 'pull_request', 'id' => 900,
    'status' => 'completed', 'conclusion' => 'failure' );
reject( ez2_gate_run_checks( $q, $sha ), 'ez2_ci_blocked', 'newer failed retry blocks older PASS' );
$q = $r; $q['workflow_runs'][0]['event'] = 'push';
reject( ez2_gate_run_checks( $q, $sha ), 'ez2_ci_blocked', 'non-PR check refused' );
$q = $r; $q['workflow_runs'][0]['head_sha'] = str_repeat( 'b', 40 );
reject( ez2_gate_run_checks( $q, $sha ), 'ez2_ci_blocked', 'other SHA refused' );
$GLOBALS['urls'] = array();
$GLOBALS['responses'] = array( $p, $r, $p );
$result = ez2_gate_preflight();
accept( is_array( $result ) && $result['source_sha'] === $sha
    && $result['source_ci_pass'] === true && $result['one_click_ready'] === false
    && $result['site_modified'] === false && $result['content_media_imported'] === false,
    'read-only success cannot assert install' );
accept( count( $GLOBALS['urls'] ) === 3
    && $GLOBALS['urls'][0] === EZ2_GATE_API . '/pulls/1'
    && strpos( $GLOBALS['urls'][1], 'head_sha=' . $sha ) !== false,
    'fixed API only' );
$GLOBALS['responses'] = array( $p, $r, pr_fixture( str_repeat( 'b', 40 ) ) );
reject( ez2_gate_preflight(), 'ez2_sha_moved', 'TOCTOU source change blocked' );
$GLOBALS['responses'] = array( $p, array( 'http' => 503 ) );
reject( ez2_gate_preflight(), 'ez2_api_http', 'API failure must fail closed' );
$GLOBALS['site_identity'] = '';
$GLOBALS['responses'] = array();
reject( ez2_gate_preflight(), 'ez2_wrong_site', 'site failure before network' );
accept( count( $GLOBALS['responses'] ) === 0, 'no queued network work on wrong site' );
$GLOBALS['installed_plugins'] = array();
$GLOBALS['active_plugins'] = array();
$GLOBALS['page_ids'] = array();
$GLOBALS['page_meta'] = array();
$GLOBALS['page_fields'] = array();
$GLOBALS['site_identity'] = 'ez2-isolated-only';
$inventory = ez2_gate_local_snapshot();
accept( is_array( $inventory ) && $inventory['isolated_site'] === true
    && $inventory['elementor_installed'] === false
    && $inventory['managed_page_count'] === 0 && $inventory['one_click_ready'] === false,
    'empty isolated site still not approved for delivery' );
$GLOBALS['installed_plugins'] = array( 'elementor/elementor.php' => array( 'Version' => '4.3.4' ) );
$GLOBALS['active_plugins'] = array( 'elementor/elementor.php' );
$GLOBALS['page_ids'] = array( 123 );
$GLOBALS['page_meta'][123] = array(
    '_ez2_managed_key' => 'ez2-home-hero',
    '_elementor_data' => 'PRIVATE_IMAGE_INTERNAL_PATH',
    '_elementor_page_settings' => 'private settings',
    '_thumbnail_id' => '19',
);
$GLOBALS['page_fields'][123] = array( 'post_title' => 'MY PRIVATE TITLE', 'post_content' => 'MY PRIVATE PAGE' );
$inventory = ez2_gate_local_snapshot();
accept( $inventory['elementor_installed'] === true && $inventory['elementor_active'] === true
    && $inventory['elementor_version'] === '4.3.4'
    && $inventory['managed_page_count'] === 1
    && strlen( $inventory['managed_page_digests']['ez2-home-hero'] ) === 64,
    'local content fingerprint and plugin status collected' );
$public = json_encode( $inventory );
accept( strpos( $public, 'MY PRIVATE' ) === false && strpos( $public, 'PRIVATE_IMAGE' ) === false,
    'private page text and URLs never leave local snapshot' );
$first = $inventory['managed_page_digests']['ez2-home-hero'];
$GLOBALS['page_fields'][123]['post_content'] = 'EDITED PRIVATE PAGE';
$changed = ez2_gate_local_snapshot();
accept( $changed['managed_page_digests']['ez2-home-hero'] !== $first,
    'Owner manual edit visibly changes digest' );
$GLOBALS['page_fields'][123]['post_content'] = 'MY PRIVATE PAGE';
$GLOBALS['page_ids'] = array( 123, 124 );
$GLOBALS['page_meta'][124] = $GLOBALS['page_meta'][123];
reject( ez2_gate_local_snapshot(), 'ez2_managed_key', 'duplicated managed key blocked' );
$GLOBALS['page_ids'] = array( 123 );
$GLOBALS['page_meta'][123]['_ez2_managed_key'] = 'path/unsafe';
reject( ez2_gate_local_snapshot(), 'ez2_managed_key', 'unsafe managed key blocked' );
$GLOBALS['page_meta'][123]['_ez2_managed_key'] = 'ez2-home-hero';
$GLOBALS['page_ids'] = array_fill( 0, 101, 123 );
reject( ez2_gate_local_snapshot(), 'ez2_managed_pages_limit', 'oversized managed set blocked' );
$GLOBALS['page_ids'] = array( 123 );
$GLOBALS['site_identity'] = '';
reject( ez2_gate_local_snapshot(), 'ez2_wrong_site', 'inventory blocked for wrong site' );


/** Digest-only protected content planning; never touches real WordPress. */
$GLOBALS['site_identity'] = 'ez2-isolated-only';
$GLOBALS['page_ids'] = array( 123 );
$GLOBALS['page_meta'][123]['_ez2_managed_key'] = 'ez2-home-hero';
$local = ez2_gate_local_snapshot();
$baseline = $local['managed_page_digests']['ez2-home-hero'];
$desired = str_repeat( 'b', 64 );
$source = array( 'source_sha' => $sha, 'source_ci_pass' => true,
    'site_modified' => false, 'one_click_ready' => false );
$candidate = array(
    'schema_version' => 1, 'target_site' => 'ez2-isolated-only',
    'source_sha' => $sha, 'snapshot_schema' => 'wp-fields-v1',
    'pages' => array(
        array( 'key' => 'ez2-home-hero', 'baseline_sha256' => $baseline,
            'desired_sha256' => $desired ),
        array( 'key' => 'ez2-products', 'baseline_sha256' => null,
            'desired_sha256' => str_repeat( 'c', 64 ) ),
    ),
);
$plan = ez2_gate_content_plan( $candidate, $local, $source );
accept( is_array( $plan ) && $plan['status'] === 'PREVIEW_ONLY'
    && $plan['actions']['update'] === array( 'ez2-home-hero' )
    && $plan['actions']['create'] === array( 'ez2-products' )
    && $plan['site_modified'] === false && $plan['one_click_ready'] === false,
    'safe create/update preview without installation' );
$exposed = json_encode( $plan );
accept( strpos( $exposed, 'PRIVATE' ) === false && strpos( $exposed, 'EDITED' ) === false,
    'planned actions never leak Owner page text' );
$edited = $local;
$edited['managed_page_digests']['ez2-home-hero'] = str_repeat( 'f', 64 );
$blocked = ez2_gate_content_plan( $candidate, $edited, $source );
accept( $blocked['status'] === 'BLOCKED_OWNER_CONFLICT'
    && $blocked['actions']['blocked_owner_conflict'] === array( 'ez2-home-hero' ),
    'Owner edits block overwrite' );
$same = $candidate;
$same['pages'][0]['desired_sha256'] = $baseline;
$unchanged = ez2_gate_content_plan( $same, $local, $source );
accept( $unchanged['actions']['unchanged'] === array( 'ez2-home-hero' )
    && $unchanged['actions']['update'] === array(),
    'identical managed content remains untouched' );
$extra = $local;
$extra['managed_page_digests']['ez2-owner-note'] = str_repeat( 'd', 64 );
$preserved = ez2_gate_content_plan( $candidate, $extra, $source );
accept( $preserved['actions']['preserved_existing'] === array( 'ez2-owner-note' ),
    'unmentioned Owner pages preserved' );
$malformed = $candidate;
$malformed['source_sha'] = str_repeat( 'e', 40 );
reject( ez2_gate_content_plan( $malformed, $local, $source ), 'ez2_source_drift',
    'candidate SHA drift blocked' );
$malformed = $source;
$malformed['source_ci_pass'] = false;
reject( ez2_gate_content_plan( $candidate, $local, $malformed ), 'ez2_source_drift',
    'unverified CI source blocked' );
$malformed = $candidate;
$malformed['snapshot_schema'] = 'elementor-raw-json';
reject( ez2_gate_content_plan( $malformed, $local, $source ), 'ez2_candidate_schema',
    'incompatible snapshot format blocked' );
$malformed = $candidate;
$malformed['pages'][0]['baseline_sha256'] = null;
$unowned = ez2_gate_content_plan( $malformed, $local, $source );
accept( $unowned['status'] === 'BLOCKED_OWNER_CONFLICT',
    'existing page without prior baseline blocked' );
$malformed = $candidate;
$malformed['pages'][1]['baseline_sha256'] = str_repeat( 'd', 64 );
$missing = ez2_gate_content_plan( $malformed, $local, $source );
accept( $missing['actions']['blocked_owner_conflict'] === array( 'ez2-products' ),
    'missing expected page blocked' );
$malformed = $candidate;
$malformed['pages'] = array_reverse( $candidate['pages'] );
reject( ez2_gate_content_plan( $malformed, $local, $source ), 'ez2_candidate_page',
    'unsorted page list blocked' );
$malformed = $candidate;
$malformed['pages'][1] = $malformed['pages'][0];
reject( ez2_gate_content_plan( $malformed, $local, $source ), 'ez2_candidate_page',
    'duplicate managed page blocked' );
$malformed = $candidate;
$malformed['pages'][0]['extra_raw_content'] = 'LEAK';
reject( ez2_gate_content_plan( $malformed, $local, $source ), 'ez2_candidate_page',
    'unexpected raw content field blocked' );
$malformed = $candidate;
$malformed['pages'][0]['desired_sha256'] = 'invalid';
reject( ez2_gate_content_plan( $malformed, $local, $source ), 'ez2_candidate_page',
    'malformed desired hash blocked' );
$malformed = $candidate;
$malformed['pages'] = array_fill( 0, 101, $candidate['pages'][0] );
reject( ez2_gate_content_plan( $malformed, $local, $source ), 'ez2_candidate_schema',
    'oversized import list blocked' );
$malformed = $candidate;
$malformed['pages'] = array();
reject( ez2_gate_content_plan( $malformed, $local, $source ), 'ez2_candidate_schema',
    'zero-page release blocked' );
$malformed = $local;
$malformed['managed_page_digests']['ez2-home-hero'] = 'bad-hash';
reject( ez2_gate_content_plan( $candidate, $malformed, $source ), 'ez2_local_digest',
    'malformed local digest blocked' );
$malformed = $local;
$malformed['installed_release_attested'] = true;
reject( ez2_gate_content_plan( $candidate, $malformed, $source ), 'ez2_local_snapshot',
    'unexpected attestation claims blocked' );
$GLOBALS['site_identity'] = '';
reject( ez2_gate_content_plan( $candidate, $local, $source ), 'ez2_wrong_site',
    'content planning blocked for wrong site' );

echo 'EZ2_LP_DELIVERY_GATE_PASS cases=' . $count . "\n";
