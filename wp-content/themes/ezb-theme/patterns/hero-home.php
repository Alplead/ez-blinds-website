<?php
/**
 * Title: Home hero
 * Slug: ezb-theme/hero-home
 * Categories: featured
 */
?>
<!-- wp:group {"align":"full","className":"ezb-hero ezb-shell","layout":{"type":"constrained"}} -->
<div class="wp-block-group alignfull ezb-hero ezb-shell">
	<!-- wp:columns {"align":"wide","className":"ezb-hero-grid","verticalAlignment":"center"} -->
	<div class="wp-block-columns alignwide are-vertically-aligned-center ezb-hero-grid">
		<!-- wp:column {"verticalAlignment":"center","width":"54%"} -->
		<div class="wp-block-column is-vertically-aligned-center" style="flex-basis:54%">
			<!-- wp:paragraph {"className":"ezb-eyebrow"} -->
			<p class="ezb-eyebrow">Melbourne • Measure • Supply • Install</p>
			<!-- /wp:paragraph -->
			<!-- wp:heading {"level":1} -->
			<h1 class="wp-block-heading">Window furnishings, measured and installed for Melbourne homes</h1>
			<!-- /wp:heading -->
			<!-- wp:paragraph {"className":"ezb-lede"} -->
			<p class="ezb-lede">Real project photography, practical product advice and a straightforward measure-and-quote process.</p>
			<!-- /wp:paragraph -->
			<!-- wp:buttons -->
			<div class="wp-block-buttons">
				<!-- wp:button -->
				<div class="wp-block-button"><a class="wp-block-button__link wp-element-button" href="/contact/">Free Measure &amp; Quote</a></div>
				<!-- /wp:button -->
				<!-- wp:button {"className":"is-style-outline"} -->
				<div class="wp-block-button is-style-outline"><a class="wp-block-button__link wp-element-button" href="/projects/">View Projects</a></div>
				<!-- /wp:button -->
			</div>
			<!-- /wp:buttons -->
		</div>
		<!-- /wp:column -->

		<!-- wp:column {"verticalAlignment":"center","width":"46%"} -->
		<div class="wp-block-column is-vertically-aligned-center" style="flex-basis:46%">
			<!-- wp:shortcode -->[ezb_media_slot slot="home-hero"]<!-- /wp:shortcode -->
		</div>
		<!-- /wp:column -->
	</div>
	<!-- /wp:columns -->
</div>
<!-- /wp:group -->