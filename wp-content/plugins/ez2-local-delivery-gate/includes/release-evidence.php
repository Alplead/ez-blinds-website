<?php
/**
 * PHP-side exact-SHA release catalog integrity verifier for future EZ2 LocalWP.
 *
 * This only detects alteration AFTER a catalog has been authenticated through
 * a future trusted delivery channel. A checksum in an untrusted catalog does
 * NOT prove publisher identity; this function never authorises installation.
 */
function ez2_gate_release_evidence( $catalog, $files, $expected_sha ) {
    $names = array(
        'ezb-theme.zip', 'ezb-core.zip', 'RELEASE_METADATA.txt',
        'RELEASE_CONTENTS.json', 'SHA256SUMS', 'ez2-content-candidate.zip',
    );
    if ( ! is_string( $expected_sha )
        || ! preg_match( '/\\A[a-f0-9]{40}\\z/D', $expected_sha )
        || ! is_array( $catalog ) || ! is_array( $files )
        || array_keys( $catalog ) !== array(
            'schema', 'source_sha', 'scope', 'target_site', 'files',
            'one_click_complete', 'elementor_candidate_installable',
            'third_party_plugins_included', 'private_media_included',
            'localwp_installed', 'deployment_authorized',
        ) || $catalog['schema'] !== 1
        || $catalog['source_sha'] !== $expected_sha
        || $catalog['scope'] !== 'engineering-evidence-only'
        || $catalog['target_site'] !== 'ez2-isolated-only'
        || count( $catalog['files'] ) !== count( $names )
        || count( $files ) !== count( $names ) ) {
        return new WP_Error( 'ez2_release_schema', 'Release catalog does not match the isolated source contract.' );
    }
    foreach ( array(
        'one_click_complete', 'elementor_candidate_installable',
        'third_party_plugins_included', 'private_media_included',
        'localwp_installed', 'deployment_authorized',
    ) as $flag ) {
        if ( $catalog[ $flag ] !== false ) {
            return new WP_Error( 'ez2_release_claim', 'Release makes an unauthorised installation claim.' );
        }
    }

    $seen = array();
    foreach ( $catalog['files'] as $index => $record ) {
        if ( ! is_array( $record )
            || array_keys( $record ) !== array( 'name', 'sha256' )
            || $record['name'] !== $names[ $index ]
            || ! is_string( $record['sha256'] )
            || ! preg_match( '/\\A[a-f0-9]{64}\\z/D', $record['sha256'] )
            || isset( $seen[ $record['name'] ] ) ) {
            return new WP_Error( 'ez2_release_member', 'Invalid release component declaration.' );
        }
        $seen[ $record['name'] ] = true;
    }
    if ( array_keys( $files ) !== $names ) {
        return new WP_Error( 'ez2_release_extra', 'Release contents missing, reordered or unexpectedly expanded.' );
    }
    foreach ( $catalog['files'] as $record ) {
        $name = $record['name'];
        $bytes = $files[ $name ];
        if ( ! is_string( $bytes ) || strlen( $bytes ) < 1
            || strlen( $bytes ) > 32 * 1024 * 1024
            || ! hash_equals( $record['sha256'], hash( 'sha256', $bytes ) ) ) {
            return new WP_Error( 'ez2_release_digest', 'Release component bytes failed integrity checks.' );
        }
    }
    return array(
        'status' => 'INTEGRITY_ONLY',
        'source_sha' => $expected_sha,
        'components_verified' => count( $names ),
        'publisher_authenticated' => false,
        'zip_members_safe' => false,
        'source_ci_verified' => false,
        'runtime_install_tested' => false,
        'content_media_installed' => false,
        'one_click_ready' => false,
        'site_modified' => false,
    );
}
