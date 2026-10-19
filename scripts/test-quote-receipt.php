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
echo 'EZB_QUOTE_RECEIPT_PASS cases=' . $cases . PHP_EOL;
