<?php
/** Standalone photo priority regression. No WP installation or private media. */
define( 'ABSPATH', '/ez2-fixture/' );
require dirname( __DIR__ ) . '/wp-content/plugins/ezb-core/includes/ezb-media-priority.php';

$checks = 0;
function ezb_assert_attr( $slot, $front, $product, $loading, $priority ) {
    global $checks;
    $attrs = ezb_media_slot_fetch_attributes( $slot, $front, $product );
    if ( $attrs !== array(
        'loading' => $loading, 'fetchpriority' => $priority, 'decoding' => 'async'
    ) ) {
        throw new RuntimeException( 'Wrong image policy for ' . $slot . '; front=' . (int)$front . '; product=' . (int)$product );
    }
    $checks++;
}
ezb_assert_attr( 'home-hero', true, false, 'eager', 'high' );
ezb_assert_attr( 'home-hero', false, false, 'lazy', 'auto' );
ezb_assert_attr( 'roller-hero', true, false, 'lazy', 'auto' );
ezb_assert_attr( 'rfs-hero', true, false, 'lazy', 'auto' );
ezb_assert_attr( 'shutters-hero', true, false, 'lazy', 'auto' );
ezb_assert_attr( 'sheer-hero', true, false, 'lazy', 'auto' );
ezb_assert_attr( 'roller-hero', false, true, 'eager', 'high' );
ezb_assert_attr( 'roller-hero', true, true, 'eager', 'high' );
ezb_assert_attr( 'rfs-hero', false, true, 'eager', 'high' );
ezb_assert_attr( 'shutters-hero', false, true, 'eager', 'high' );
ezb_assert_attr( 'sheer-hero', false, true, 'eager', 'high' );
ezb_assert_attr( 'roller-hero', false, false, 'lazy', 'auto' );
ezb_assert_attr( 'shutters-hero', false, false, 'lazy', 'auto' );
ezb_assert_attr( 'home-hero', false, true, 'eager', 'high' );
ezb_assert_attr( 'unknown', false, false, 'lazy', 'auto' );
ezb_assert_attr( 'unknown', true, false, 'lazy', 'auto' );
echo 'EZ2_MEDIA_LOADING_PRIORITY_PASS cases=' . $checks . "\n";
