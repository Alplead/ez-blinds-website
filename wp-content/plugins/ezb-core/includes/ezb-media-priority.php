<?php
/**
 * Photo-loading policy for EZ2's curated media slots.
 *
 * Only the actual above-the-fold hero should compete for high priority.
 * Product story images on the homepage are below the hero and load lazily.
 * Pure helper to keep performance policy testable without WordPress runtime.
 */
if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

function ezb_media_slot_fetch_attributes( $slot, $is_front_page, $is_matching_product_page ) {
    // Local prototype routes can be rendered while WP still reports the
    // underlying queried page as front_page. A matching product hero wins.
    $hero = true === $is_matching_product_page
        || ( 'home-hero' === $slot && true === $is_front_page );

    return array(
        'loading'       => $hero ? 'eager' : 'lazy',
        'fetchpriority' => $hero ? 'high' : 'auto',
        'decoding'      => 'async',
    );
}
