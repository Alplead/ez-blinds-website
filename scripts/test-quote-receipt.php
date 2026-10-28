<?php
define( 'EZB_QUOTE_RECEIPT_TEST', true );
function wp_salt( $scheme ) {
    if ( 'auth' !== $scheme ) {
        throw new RuntimeException( 'Unexpected salt scheme' );
    }
    return 'synthetic-test-only-secret';
}
require_once __DIR__ . '/../wp-content/plugins/ezb-core/includes/ezb-quote-receipt.php';

$cases = 0;
function expect_receipt( $actual, $expected, $label ) {
    global $cases;
    ++$cases;
    if ( $actual !== $expected ) {
        throw new RuntimeException( 'Receipt regression: ' . $label );
    }
}
$now = 1790000000;
$receipt = ezb_quote_receipt_issue( $now );
expect_receipt( ezb_quote_receipt_valid( $receipt, $now ), true, 'fresh signed receipt' );
expect_receipt( ezb_quote_receipt_valid( $receipt, $now + 300 ), true, 'expiry boundary' );
expect_receipt( ezb_quote_receipt_valid( $receipt, $now + 301 ), false, 'expired receipt' );
expect_receipt( ezb_quote_receipt_valid( $receipt, $now - 1 ), false, 'future receipt' );
expect_receipt( ezb_quote_receipt_valid( null, $now ), false, 'missing receipt' );
expect_receipt( ezb_quote_receipt_valid( 123, $now ), false, 'non-string receipt' );
expect_receipt( ezb_quote_receipt_valid( '', $now ), false, 'empty receipt' );
expect_receipt( ezb_quote_receipt_valid( 'sent', $now ), false, 'unsigned status' );
expect_receipt( ezb_quote_receipt_valid( substr( $receipt, 0, -1 ) . ( substr( $receipt, -1 ) === 'a' ? 'b' : 'a' ), $now ), false, 'tampered signature' );
expect_receipt( ezb_quote_receipt_valid( (string) ( $now - 1 ) . substr( $receipt, 10 ), $now ), false, 'tampered timestamp' );
expect_receipt( ezb_quote_receipt_valid( strtoupper( $receipt ), $now ), false, 'uppercase signature rejected' );
expect_receipt( ezb_quote_receipt_valid( $receipt . 'junk', $now ), false, 'suffix rejected' );
expect_receipt( ezb_quote_receipt_valid( array( $receipt ), $now ), false, 'array receipt rejected' );
expect_receipt( ezb_quote_receipt_valid( str_repeat( 'x', 100000 ), $now ), false, 'oversized receipt rejected' );
// The original timestamp-only HMAC produced identical receipts for every
// successful enquiry in a single second. Test independent send identities.
$second_receipt = ezb_quote_receipt_issue( $now );
expect_receipt( $second_receipt !== $receipt, true, 'same-second sends have unique receipts' );
expect_receipt( ezb_quote_receipt_valid( $second_receipt, $now ), true, 'second signed receipt is valid' );
expect_receipt( (bool) preg_match( '/\A[0-9]{10}\.[a-f0-9]{32}\.[a-f0-9]{64}\z/D', $receipt ), true, 'receipt has opaque random nonce' );
$nonce_offset = 11;
$changed_nonce = substr( $receipt, 0, $nonce_offset ) . ( $receipt[ $nonce_offset ] === 'a' ? 'b' : 'a' ) . substr( $receipt, $nonce_offset + 1 );
expect_receipt( ezb_quote_receipt_valid( $changed_nonce, $now ), false, 'tampered nonce rejected' );
expect_receipt( ezb_quote_receipt_valid( substr( $receipt, 0, $nonce_offset ) . 'A' . substr( $receipt, $nonce_offset + 1 ), $now ), false, 'noncanonical nonce rejected' );
expect_receipt( ezb_quote_receipt_valid( substr( $receipt, 0, $nonce_offset ) . substr( $receipt, $nonce_offset + 1 ), $now ), false, 'truncated nonce rejected' );
$legacy = $now . '.' . hash_hmac( 'sha256', 'ezb-quote-sent:' . $now, wp_salt( 'auth' ) );
expect_receipt( ezb_quote_receipt_valid( $legacy, $now ), false, 'legacy timestamp-only receipt rejected' );
echo 'EZB_QUOTE_RECEIPT_PASS cases=' . $cases . PHP_EOL;
