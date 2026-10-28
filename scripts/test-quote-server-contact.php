<?php
/**
 * Exercise the actual server-side quote contact validator without WordPress,
 * a database, real customer data or any mail delivery.
 */
$source = file_get_contents( __DIR__ . '/../wp-content/plugins/ezb-core/ezb-core.php' );
if ( ! preg_match( '/function ezb_quote_contact_fields_valid\([^)]*\)\s*\{[\s\S]*?\n\}/', $source, $match ) ) {
    throw new RuntimeException( 'Production quote contact validator not found.' );
}
function is_email( $value ) {
    return is_string( $value ) && false !== filter_var( $value, FILTER_VALIDATE_EMAIL ) ? $value : false;
}
eval( $match[0] );

$cases = array(
    array( 'phone only', 'Alice', '0400 123 456', '', '', true ),
    array( 'email only', 'Alice', '', 'alice@example.com', 'alice@example.com', true ),
    array( 'both contact methods', 'Alice', '0400', 'alice@example.com', 'alice@example.com', true ),
    array( 'blank name', '', '0400', '', '', false ),
    array( 'whitespace name', " \t ", '0400', '', '', false ),
    array( 'blank contact', 'Alice', '', '', '', false ),
    array( 'whitespace phone', 'Alice', " \t ", '', '', false ),
    array( 'invalid email only', 'Alice', '', 'bad-email', '', false ),
    array( 'invalid email with phone', 'Alice', '0400', 'bad-email', '', false ),
    array( 'sanitised-away supplied email', 'Alice', '', 'alice@example.com', '', false ),
    array( 'non-string name', array(), '0400', '', '', false ),
    array( 'non-string phone', 'Alice', array(), '', '', false ),
    array( 'non-string supplied email', 'Alice', '', array(), '', false ),
    array( 'non-string cleaned email', 'Alice', '', '', array(), false ),
    array( 'trimmed name and phone', '  Alice  ', ' 0400 ', '', '', true ),
);
foreach ( $cases as $case ) {
    list( $label, $name, $phone, $input, $cleaned, $expected ) = $case;
    if ( ezb_quote_contact_fields_valid( $name, $phone, $input, $cleaned ) !== $expected ) {
        throw new RuntimeException( 'Contact validator regression: ' . $label );
    }
}
$handler = substr( $source, strpos( $source, 'function ezb_handle_quote_form()' ) );
if ( false === strpos( $handler, 'ezb_quote_contact_fields_valid( $name, $phone, $email_input, $email )' )
    || strpos( $handler, 'ezb_quote_contact_fields_valid( $name, $phone, $email_input, $email )' ) > strpos( $handler, 'wp_mail(' ) ) {
    throw new RuntimeException( 'Live handler must validate before mail.' );
}
if ( false === strpos( $handler, "trim( sanitize_text_field( wp_unslash( \$_POST['name'] ) ) )" )
    || false === strpos( $handler, "trim( sanitize_text_field( wp_unslash( \$_POST['phone'] ) ) )" ) ) {
    throw new RuntimeException( 'Server must normalise contact fields before validation.' );
}
echo 'EZB_QUOTE_SERVER_CONTACT_VALIDATION_PASS cases=' . count( $cases ) . PHP_EOL;
