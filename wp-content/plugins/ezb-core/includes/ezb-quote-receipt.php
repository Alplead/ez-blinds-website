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
    // Give each successful send a distinct, non-identifying receipt.
    $nonce = bin2hex( random_bytes( 16 ) );
    return $issued . '.' . $nonce . '.' . hash_hmac( 'sha256', 'ezb-quote-sent:' . $issued . ':' . $nonce, wp_salt( 'auth' ) );
}

function ezb_quote_receipt_valid( $token, $now = null ) {
    if ( ! is_string( $token ) || 108 !== strlen( $token ) || ! preg_match( '/\A([0-9]{10})\.([a-f0-9]{32})\.([a-f0-9]{64})\z/D', $token, $matches ) ) {
        return false;
    }
    $issued = (int) $matches[1];
    $current = null === $now ? time() : (int) $now;
    if ( $issued > $current || $current - $issued > 300 ) {
        return false;
    }
    $expected = hash_hmac( 'sha256', 'ezb-quote-sent:' . $matches[1] . ':' . $matches[2], wp_salt( 'auth' ) );
    return hash_equals( $expected, $matches[3] );
}
