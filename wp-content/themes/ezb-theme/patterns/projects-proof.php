<?php
/**
 * Title: Project proof
 * Slug: ezb-theme/projects-proof
 * Categories: featured
 */
?>
<!-- wp:group {"align":"full","className":"ezb-section ezb-shell","layout":{"type":"constrained"}} -->
<div class="wp-block-group alignfull ezb-section ezb-shell">
	<!-- wp:group {"align":"wide","className":"ezb-proof","layout":{"type":"constrained"}} -->
	<div class="wp-block-group alignwide ezb-proof">
		<!-- wp:heading -->
		<h2 class="wp-block-heading">Real EZ projects</h2>
		<!-- /wp:heading -->
		<!-- wp:paragraph -->
		<p>We will use verified EZ installation photography and short case studies here—real homes, real openings and the reasoning behind the chosen solution.</p>
		<!-- /wp:paragraph -->
		<!-- wp:query {"query":{"perPage":3,"postType":"ezb_project","order":"desc","orderBy":"date"}} -->
		<div class="wp-block-query">
			<!-- wp:post-template -->
			<!-- wp:post-featured-image {"isLink":true} /-->
			<!-- wp:post-title {"isLink":true,"level":3} /-->
			<!-- wp:post-excerpt /-->
			<!-- /wp:post-template -->
		</div>
		<!-- /wp:query -->
	</div>
	<!-- /wp:group -->
</div>
<!-- /wp:group -->