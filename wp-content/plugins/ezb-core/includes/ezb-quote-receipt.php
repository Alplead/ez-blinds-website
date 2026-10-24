<?php
/**
 * A public query string cannot prove that an enquiry was actually mailed.
 * Issue a short-lived, tamper-evident receipt only after wp_mail succeeds.
 * No customer details or secret keys are embedded in the receipt.
 */
if ( ! defined( 'ABSPATH' ) && ! defined( 'EZB_QUOTE_RECEIPT_TEST' ) ) {
    exit;
}

function ezb_quote_receipt_issue( $now = null ) {
    $issued = (string) ( null === $now ? time() : $now );
    return $issued . '.' . hash_hmac( 'sha256', 'ezb-quote-sent:' . $issued, wp_salt( 'auth' ) );
}

function ezb_quote_receipt_valid( $token, $now = null ) {
    if ( ! is_string( $token ) || 75 !== strlen( $token ) || ! preg_match( '/\A([0-9]{10})\.([a-f0-9]{64})\z/D', $token, $matches ) ) {
        return false;
    }
    $issued = (int) $matches[1];
    $current = null === $now ? time() : (int) $now;
    if ( $issued > $current || $current - $issued > 300 ) {
        return false;
    }
    $expected = hash_hmac( 'sha256', 'ezb-quote-sent:' . $matches[1], wp_salt( 'auth' ) );
    return hash_equals( $expected, $matches[2] );
}
