<?php
/**
 * Plugin Name: EZB Core
 * Description: Business-specific content model and functionality for EZ Blinds & Shutters.
 * Version: 0.2.0
 * Requires at least: 6.6
 * Requires PHP: 8.2
 * Text Domain: ezb-core
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Make Page excerpts available to the Owner as the shared source for concise
 * introductory/SEO copy where a Page uses one.
 */
add_action(
	'init',
	function () {
		add_post_type_support( 'page', 'excerpt' );
	},
	20
);

/**
 * Yield SEO/social metadata to a dedicated SEO plugin if one is activated
 * later. This keeps the custom baseline useful now without creating duplicate
 * tags when Rank Math, Yoast or SEOPress takes over.
 */
function ezb_external_seo_plugin_active() {
	return defined( 'RANK_MATH_VERSION' ) ||
		defined( 'WPSEO_VERSION' ) ||
		defined( 'SEOPRESS_VERSION' );
}

/**
 * Emit a lightweight meta description from existing Owner-editable content.
 *
 * Singular Pages and Projects use their excerpt when present. The front page
 * may fall back to the existing site tagline. Empty pages receive no invented
 * generic description.
 */
function ezb_current_meta_description() {
	global $post;

	$description = '';

	if ( $post instanceof WP_Post && in_array( $post->post_type, array( 'page', 'post', 'ezb_project' ), true ) ) {
		$description = trim( wp_strip_all_tags( $post->post_excerpt ) );
	}

	if ( '' === $description && ( is_front_page() || ( $post instanceof WP_Post && 'home' === $post->post_name ) ) ) {
		$description = trim( wp_strip_all_tags( get_bloginfo( 'description' ) ) );
	}

	return $description;
}

function ezb_print_meta_description() {
	if ( is_admin() || ezb_external_seo_plugin_active() ) {
		return;
	}

	$description = ezb_current_meta_description();
	if ( '' === $description ) {
		return;
	}

	printf(
		"<meta name=\"description\" content=\"%s\">\n",
		esc_attr( $description )
	);
}
add_action( 'wp_head', 'ezb_print_meta_description', 2 );

/**
 * Emit conservative structured data using only facts already present in
 * WordPress. Do not invent address, reviews, pricing or local-business claims.
 */
function ezb_print_structured_data() {
	if ( is_admin() || ezb_external_seo_plugin_active() ) {
		return;
	}

	$graph = array();

	if ( is_front_page() ) {
		$graph[] = array(
			'@type' => 'WebSite',
			'@id'   => home_url( '/#website' ),
			'url'   => home_url( '/' ),
			'name'  => get_bloginfo( 'name' ),
		);
	}

	if ( is_singular( 'post' ) ) {
		$post_id = get_queried_object_id();
		if ( $post_id ) {
			$article = array(
				'@type'            => 'BlogPosting',
				'@id'              => get_permalink( $post_id ) . '#article',
				'headline'         => get_the_title( $post_id ),
				'mainEntityOfPage' => get_permalink( $post_id ),
				'datePublished'    => get_the_date( DATE_W3C, $post_id ),
				'dateModified'     => get_the_modified_date( DATE_W3C, $post_id ),
				'publisher'        => array(
					'@type' => 'Organization',
					'name'  => get_bloginfo( 'name' ),
					'url'   => home_url( '/' ),
				),
			);

			$excerpt = trim( wp_strip_all_tags( get_post_field( 'post_excerpt', $post_id ) ) );
			if ( '' !== $excerpt ) {
				$article['description'] = $excerpt;
			}

			$image_id = get_post_thumbnail_id( $post_id );
			if ( $image_id ) {
				$image_url = wp_get_attachment_image_url( $image_id, 'full' );
				if ( $image_url ) {
					$article['image'] = array( $image_url );
				}
			}

			$graph[] = $article;
		}
	}

	if ( ! $graph ) {
		return;
	}

	$payload = array(
		'@context' => 'https://schema.org',
		'@graph'   => $graph,
	);

	// Escape angle brackets so imported or Owner-edited titles cannot close this script element.
	printf(
		'<script type="application/ld+json">%s</script>' . "\n",
		wp_json_encode( $payload, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_HEX_TAG )
	);
}
add_action( 'wp_head', 'ezb_print_structured_data', 20 );

/**
 * Baseline Open Graph / Twitter metadata for current public routes.
 * A dedicated SEO plugin automatically supersedes this output.
 */
function ezb_print_social_metadata() {
	if ( is_admin() || ezb_external_seo_plugin_active() || is_404() ) {
		return;
	}

	$title       = wp_get_document_title();
	$description = ezb_current_meta_description();
	$url         = '';
	$type        = is_singular( 'post' ) ? 'article' : 'website';
	$image       = '';

	if ( is_front_page() ) {
		$url = home_url( '/' );
	} elseif ( is_singular() ) {
		$url = get_permalink();
	} elseif ( is_post_type_archive( 'ezb_project' ) ) {
		$url = get_post_type_archive_link( 'ezb_project' );
	}

	if ( is_singular() ) {
		$image_id = get_post_thumbnail_id();
		if ( $image_id ) {
			$image = (string) wp_get_attachment_image_url( $image_id, 'full' );
		}
	}

	if ( '' === trim( $title ) || ! $url ) {
		return;
	}

	printf( '<meta property="og:title" content="%s">' . "\n", esc_attr( $title ) );
	printf( '<meta property="og:type" content="%s">' . "\n", esc_attr( $type ) );
	printf( '<meta property="og:url" content="%s">' . "\n", esc_url( $url ) );
	printf( '<meta property="og:site_name" content="%s">' . "\n", esc_attr( get_bloginfo( 'name' ) ) );

	if ( '' !== $description ) {
		printf( '<meta property="og:description" content="%s">' . "\n", esc_attr( $description ) );
		printf( '<meta name="twitter:description" content="%s">' . "\n", esc_attr( $description ) );
	}

	if ( '' !== $image ) {
		printf( '<meta property="og:image" content="%s">' . "\n", esc_url( $image ) );
	}

	printf( '<meta name="twitter:card" content="%s">' . "\n", esc_attr( $image ? 'summary_large_image' : 'summary' ) );
	printf( '<meta name="twitter:title" content="%s">' . "\n", esc_attr( $title ) );
}
add_action( 'wp_head', 'ezb_print_social_metadata', 21 );



/**
 * WordPress core emits rel=canonical for singular content but not for the
 * Projects CPT archive. Add the archive self-canonical only for that route.
 */
function ezb_print_project_archive_canonical() {
	if ( ezb_external_seo_plugin_active() || ! is_post_type_archive( 'ezb_project' ) ) {
		return;
	}

	$url = get_post_type_archive_link( 'ezb_project' );
	if ( ! $url ) {
		return;
	}

	printf(
		"<link rel=\"canonical\" href=\"%s\">\n",
		esc_url( $url )
	);
}
add_action( 'wp_head', 'ezb_print_project_archive_canonical', 10 );

add_action(
	'init',
	function () {
		register_post_type(
			'ezb_project',
			array(
				'labels'       => array(
					'name'          => __( 'Projects', 'ezb-core' ),
					'singular_name' => __( 'Project', 'ezb-core' ),
				),
				'public'       => true,
				'show_in_rest' => true,
				'has_archive'  => 'projects',
				'rewrite'      => array( 'slug' => 'projects' ),
				'menu_icon'    => 'dashicons-format-gallery',
				'supports'     => array( 'title', 'editor', 'excerpt', 'thumbnail', 'revisions' ),
			)
		);
	}
);

add_shortcode(
	'ezb_quote_form',
	function () {
		$status = isset( $_GET['quote_status'] ) && is_string( $_GET['quote_status'] )
			? sanitize_key( wp_unslash( $_GET['quote_status'] ) )
			: '';
		ob_start();
		?>
		<div class="ezb-form-wrap">
			<?php if ( 'sent' === $status ) : ?>
				<p class="ezb-form-message ezb-form-message--success" role="status"><?php esc_html_e( 'Thanks — your enquiry has been sent.', 'ezb-core' ); ?></p>
			<?php elseif ( 'invalid' === $status ) : ?>
				<p class="ezb-form-message ezb-form-message--error" role="alert"><?php esc_html_e( 'Please enter your name and a phone number or valid email address. Check any email address you provide.', 'ezb-core' ); ?></p>
			<?php elseif ( 'too_long' === $status ) : ?>
				<p class="ezb-form-message ezb-form-message--error" role="alert"><?php esc_html_e( 'Your enquiry is too long. Please shorten it and try again.', 'ezb-core' ); ?></p>
			<?php elseif ( 'error' === $status ) : ?>
				<p class="ezb-form-message ezb-form-message--error" role="alert"><?php esc_html_e( 'Something went wrong. Please check the form and try again.', 'ezb-core' ); ?></p>
			<?php endif; ?>
			<form class="ezb-quote-form" method="post" action="<?php echo esc_url( admin_url( 'admin-post.php' ) ); ?>">
				<input type="hidden" name="action" value="ezb_quote">
				<?php wp_nonce_field( 'ezb_quote_submit', 'ezb_quote_nonce' ); ?>
				<p class="ezb-hp" aria-hidden="true">
					<label>Website <input type="text" name="website" tabindex="-1" autocomplete="off"></label>
				</p>

				<div class="ezb-form-grid">
					<p><label><?php esc_html_e( 'Name', 'ezb-core' ); ?><br><input type="text" name="name" autocomplete="name" maxlength="120" required></label></p>
					<p><label><?php esc_html_e( 'Suburb / Postcode', 'ezb-core' ); ?><br><input type="text" name="suburb" maxlength="120"></label></p>
					<p><label><?php esc_html_e( 'Phone', 'ezb-core' ); ?><br><input type="tel" name="phone" autocomplete="tel" maxlength="60" aria-describedby="ezb-contact-method-note"></label></p>
					<p><label><?php esc_html_e( 'Email', 'ezb-core' ); ?><br><input type="email" name="email" autocomplete="email" maxlength="254" aria-describedby="ezb-contact-method-note"></label></p>
				</div>
				<p class="ezb-form-note" id="ezb-contact-method-note"><?php esc_html_e( 'Please enter a phone number or email address so we can reply.', 'ezb-core' ); ?></p>

				<p>
					<label><?php esc_html_e( 'Product', 'ezb-core' ); ?><br>
						<select name="product">
							<option value=""><?php esc_html_e( 'Select one', 'ezb-core' ); ?></option>
							<option><?php esc_html_e( 'Roller Blinds', 'ezb-core' ); ?></option>
							<option><?php esc_html_e( 'Retractable Flyscreens', 'ezb-core' ); ?></option>
							<option><?php esc_html_e( 'Plantation Shutters', 'ezb-core' ); ?></option>
							<option><?php esc_html_e( 'Sheer Curtains', 'ezb-core' ); ?></option>
							<option><?php esc_html_e( 'Motorisation', 'ezb-core' ); ?></option>
							<option><?php esc_html_e( 'Other / Not sure', 'ezb-core' ); ?></option>
						</select>
					</label>
				</p>

				<p><label><?php esc_html_e( 'Message', 'ezb-core' ); ?><br><textarea name="message" rows="6" maxlength="4000"></textarea></label></p>
				<p class="ezb-form-note"><?php esc_html_e( 'We can discuss how to share photos after your enquiry.', 'ezb-core' ); ?></p>
				<p><button class="ezb-submit" type="submit"><?php esc_html_e( 'Send enquiry', 'ezb-core' ); ?></button></p>
			</form>
		</div>
		<?php
		return ob_get_clean();
	}
);

function ezb_quote_recipient_email() {
	$setting   = ezb_get_site_setting( 'ezb_quote_recipient_email' );
	$recipient = is_string( $setting ) ? sanitize_email( $setting ) : '';

	// sanitize_email() cleans an address but does not guarantee an @domain.
	// A malformed destination must not silently swallow customer enquiries.
	if ( is_email( $recipient ) ) {
		return $recipient;
	}

	$admin_email = get_option( 'admin_email' );
	$fallback    = is_string( $admin_email ) ? sanitize_email( $admin_email ) : '';

	return is_email( $fallback ) ? $fallback : '';
}

function ezb_handle_quote_form() {
	if (
		! isset( $_POST['ezb_quote_nonce'] ) ||
		! wp_verify_nonce( sanitize_text_field( wp_unslash( $_POST['ezb_quote_nonce'] ) ), 'ezb_quote_submit' )
	) {
		wp_die(
			esc_html__( 'Invalid request.', 'ezb-core' ),
			esc_html__( 'Invalid request', 'ezb-core' ),
			array( 'response' => 403 )
		);
	}

	// PHP empty( '0' ) is true; even that value must trigger the honeypot.
	if (
		isset( $_POST['website'] ) &&
		( ! is_string( $_POST['website'] ) || '' !== trim( wp_unslash( $_POST['website'] ) ) )
	) {
		wp_safe_redirect( home_url( '/contact/?quote_status=sent' ) );
		exit;
	}

	// Reject array-valued fields rather than silently dropping submitted details.
	// Legitimate HTML form controls submit strings; malformed arrays must not mail.
	foreach ( array( 'name', 'suburb', 'phone', 'email', 'product', 'message' ) as $field ) {
		if ( isset( $_POST[ $field ] ) && ! is_string( $_POST[ $field ] ) ) {
			wp_safe_redirect( home_url( '/contact/?quote_status=invalid' ) );
			exit;
		}
	}

	$name    = isset( $_POST['name'] ) ? sanitize_text_field( wp_unslash( $_POST['name'] ) ) : '';
	$suburb  = isset( $_POST['suburb'] ) ? sanitize_text_field( wp_unslash( $_POST['suburb'] ) ) : '';
	$phone   = isset( $_POST['phone'] ) ? sanitize_text_field( wp_unslash( $_POST['phone'] ) ) : '';
	$email   = isset( $_POST['email'] ) && is_string( $_POST['email'] ) ? sanitize_email( wp_unslash( $_POST['email'] ) ) : '';
	$product = isset( $_POST['product'] ) ? sanitize_text_field( wp_unslash( $_POST['product'] ) ) : '';
	$message = isset( $_POST['message'] ) ? sanitize_textarea_field( wp_unslash( $_POST['message'] ) ) : '';

	// Bound public input before invoking wp_mail; HTML maxlength is not a security boundary.
	if (
		strlen( $name ) > 512 ||
		strlen( $suburb ) > 512 ||
		strlen( $phone ) > 240 ||
		strlen( $email ) > 1024 ||
		strlen( $product ) > 256 ||
		strlen( $message ) > 16000
	) {
		wp_safe_redirect( home_url( '/contact/?quote_status=too_long' ) );
		exit;
	}

	// Reject a supplied invalid email even when a phone number is present.
	// Otherwise an address typo is silently accepted and cannot be replied to.
	if ( '' === $name || ( '' !== $email && ! is_email( $email ) ) || ( '' === $phone && '' === $email ) ) {
		wp_safe_redirect( home_url( '/contact/?quote_status=invalid' ) );
		exit;
	}

	$subject = sprintf( 'EZ website enquiry — %s', $product ? $product : 'General' );
	$body    = "Name: {$name}
Suburb/Postcode: {$suburb}
Phone: {$phone}
Email: {$email}
Product: {$product}

Message:
{$message}
";
	$headers = array();

	if ( is_email( $email ) ) {
		// User-submitted display names are kept in the message body rather than
		// interpreted as an RFC 5322 address/display-name in mail headers.
		$headers[] = 'Reply-To: ' . $email;
	}

	$recipient = ezb_quote_recipient_email();
	$sent      = $recipient ? wp_mail( $recipient, $subject, $body, $headers ) : false;
	wp_safe_redirect( home_url( '/contact/?quote_status=' . ( $sent ? 'sent' : 'error' ) ) );
	exit;
}
add_action( 'admin_post_nopriv_ezb_quote', 'ezb_handle_quote_form' );
add_action( 'admin_post_ezb_quote', 'ezb_handle_quote_form' );


/**
 * Seed browseable prototype pages in development only.
 *
 * This keeps the Codespaces workflow mobile-friendly: after a git pull,
 * the next page request can create any newly-added prototype pages without
 * requiring a container rebuild or manual wp-cli step.
 */
function ezb_seed_prototype_pages() {
	if ( 'development' !== wp_get_environment_type() ) {
		return;
	}


	$pages = array(
		'home'                  => 'Home',
		'products'              => 'Products',
		'roller-blinds'         => 'Roller Blinds',
		'sheer-curtains'        => 'Sheer Curtains',
		'plantation-shutters'   => 'Plantation Shutters',
		'retractable-flyscreens'=> 'Retractable Flyscreens',
		'motorised-blinds'      => 'Motorised Blinds',
		'advice'                => 'Advice',
		'blog'                  => 'Blog',
		'service-areas'         => 'Service Areas',
		'about'                 => 'About',
		'contact'               => 'Contact',
	);

	foreach ( $pages as $slug => $title ) {
		$existing = get_page_by_path( $slug, OBJECT, 'page' );
		if ( $existing ) {
			continue;
		}

		wp_insert_post(
			array(
				'post_type'   => 'page',
				'post_status' => 'publish',
				'post_title'  => $title,
				'post_name'   => $slug,
			)
		);
	}

}
add_action( 'init', 'ezb_seed_prototype_pages', 30 );


/**
 * Seed initial product introductions into editable Page excerpts in development.
 *
 * Only empty excerpts are populated. Once the Owner edits the excerpt in
 * WordPress, that Page record remains authoritative.
 */
function ezb_seed_product_intro_excerpts() {
	if ( 'development' !== wp_get_environment_type() ) {
		return;
	}

	$excerpts = array(
		'roller-blinds' => 'Roller blinds are a practical starting point for many rooms because the design is visually simple and the choice can be matched to privacy, glare and light-control needs.',
		'sheer-curtains' => 'Sheer curtains can soften daylight and give larger windows a more continuous architectural finish. The useful decisions are privacy, layering, stacking and how the curtain should meet the floor.',
		'plantation-shutters' => 'Plantation shutters create a more architectural look than a soft window covering. The important choices are how the panels fit the opening, how they need to move and how the room is used.',
		'retractable-flyscreens' => 'A retractable screen can suit selected doors and larger openings where you want airflow and insect protection while keeping the opening visually light when the screen is not in use.',
		'motorised-blinds' => 'Motorisation is most useful when it solves a practical problem: access, frequent operation, grouped control or a larger opening that is inconvenient to operate manually.',
	);

	foreach ( $excerpts as $slug => $excerpt ) {
		$page = get_page_by_path( $slug, OBJECT, 'page' );
		if ( ! $page || '' !== trim( $page->post_excerpt ) ) {
			continue;
		}

		wp_update_post(
			array(
				'ID'           => $page->ID,
				'post_excerpt' => $excerpt,
			)
		);
	}
}
add_action( 'init', 'ezb_seed_product_intro_excerpts', 32 );

add_shortcode(
	'ezb_page_intro',
	function ( $atts ) {
		$atts = shortcode_atts(
			array( 'slug' => '' ),
			$atts,
			'ezb_page_intro'
		);

		$slug = sanitize_title( $atts['slug'] );
		$page = $slug ? get_page_by_path( $slug, OBJECT, 'page' ) : null;
		if ( ! $page || '' === trim( $page->post_excerpt ) ) {
			return '';
		}

		return '<p class="ezb-lede">' . esc_html( $page->post_excerpt ) . '</p>';
	}
);


/**
 * Seed initial product FAQs into editable Page content in development.
 *
 * This runs only while post_content is empty. Once the Owner edits the Page,
 * WordPress content becomes authoritative and is never overwritten here.
 */
function ezb_seed_product_faq_content() {
	if ( 'development' !== wp_get_environment_type() ) {
		return;
	}

	$faq_sets = array(
		'roller-blinds' => array(
			array( 'q' => 'Should the blind sit inside or outside the window opening?', 'a' => 'It depends on the window, fixing surfaces, light-gap tolerance and the look you want. We check the actual opening before confirming the installation position.' ),
			array( 'q' => 'Can roller blinds be motorised?', 'a' => 'Motorisation can be considered for suitable blinds and openings. Exact compatible systems and minimum sizes will be confirmed against the current product range.' ),
			array( 'q' => 'Can different rooms use different levels of light control?', 'a' => 'Yes. The useful question is what each room needs rather than forcing the same solution everywhere.' ),
		),
		'sheer-curtains' => array(
			array( 'q' => 'Do sheer curtains provide complete night privacy?', 'a' => 'Not usually on their own. The final solution depends on fabric selection, interior lighting and whether a separate privacy layer is included.' ),
			array( 'q' => 'Can sheers be paired with roller blinds?', 'a' => 'Yes, layered window treatments can be considered where you want a softer daytime look plus stronger privacy or blockout control.' ),
			array( 'q' => 'Should curtains touch the floor?', 'a' => 'The final drop is a design and practical decision. Floor level, cleaning, movement and the desired visual finish all matter.' ),
		),
		'plantation-shutters' => array(
			array( 'q' => 'Are shutters suitable for every window?', 'a' => 'No. Window shape, recess depth, hardware and the way the window needs to open can all affect suitability.' ),
			array( 'q' => 'What material should I choose?', 'a' => 'That depends on the room conditions, opening size and the currently available product range. We will publish the active material options only after supplier verification.' ),
			array( 'q' => 'Can shutters work in bathrooms or other humid rooms?', 'a' => 'Potentially, but the material must be appropriate for the environment. The current moisture-suitable range will be confirmed before publication.' ),
		),
		'retractable-flyscreens' => array(
			array( 'q' => 'Can every large opening use a retractable flyscreen?', 'a' => 'No. The opening size, framing, track position and door operation all matter. We confirm suitability after measuring the actual opening.' ),
			array( 'q' => 'Will the screen be visible when it is not in use?', 'a' => 'The purpose of a retractable system is to minimise the visual presence of the screen when retracted, but the exact result depends on the selected system and opening.' ),
			array( 'q' => 'Can I send photos before arranging a measure?', 'a' => 'Yes. Photos of the full opening and surrounding frame can help us understand the job before the site visit.' ),
		),
		'motorised-blinds' => array(
			array( 'q' => 'Can every roller blind be motorised?', 'a' => 'No. Blind dimensions, tube/system compatibility and the current motor range all matter.' ),
			array( 'q' => 'Does motorisation always require fixed wiring?', 'a' => 'No single answer should be assumed. Current battery and powered options will be published after the active supplier range is verified.' ),
			array( 'q' => 'Can multiple blinds be operated together?', 'a' => 'Grouped control may be possible with compatible systems. The final setup depends on the selected product and current control options.' ),
		),
	);

	foreach ( $faq_sets as $slug => $faqs ) {
		$page = get_page_by_path( $slug, OBJECT, 'page' );
		if ( ! $page || '' !== trim( $page->post_content ) ) {
			continue;
		}

		$blocks = '';
		foreach ( $faqs as $faq ) {
			$blocks .= '<!-- wp:details --><details class="wp-block-details"><summary>' . esc_html( $faq['q'] ) . '</summary><!-- wp:paragraph --><p>' . esc_html( $faq['a'] ) . '</p><!-- /wp:paragraph --></details><!-- /wp:details -->';
		}

		wp_update_post(
			array(
				'ID'           => $page->ID,
				'post_content' => $blocks,
			)
		);
	}
}
add_action( 'init', 'ezb_seed_product_faq_content', 33 );


/**
 * Seed a small set of development-only starter articles.
 *
 * These are working copy scaffolds, not production-approved claims. They give
 * the Owner a realistic Blog/content surface now and are never overwritten
 * once edited.
 */
function ezb_seed_starter_blog_posts() {
	if ( 'development' !== wp_get_environment_type() ) {
		return;
	}

	$posts = array(
		'roller-blinds-blockout-vs-sunscreen' => array(
			'title'   => 'Blockout or sunscreen roller blinds: where should you start?',
			'excerpt' => 'A practical starting guide to privacy, glare, daylight and room use before choosing roller-blind fabric.',
			'content' => '<p><strong>Working copy for review.</strong> Choosing a roller blind is easier when the first question is not colour, but what the room needs the blind to do.</p><h2>Start with privacy</h2><p>A living room, bedroom and street-facing window can need very different levels of screening. Think about daytime privacy and night privacy separately.</p><h2>Then look at light and glare</h2><p>Filtered daylight can be useful in living areas, while stronger light control may matter in bedrooms or rooms with screens and televisions.</p><h2>Measure the actual opening</h2><p>Handles, trims, recess depth, blind position and acceptable light gaps can all affect the final result. A measure should confirm these details before the product is ordered.</p><p>This article will be expanded with the current EZ fabric range, verified product specifications and real installation examples before publication.</p>',
		),
		'sheer-curtains-privacy-layering' => array(
			'title'   => 'Sheer curtains, privacy and layering: what changes from day to night?',
			'excerpt' => 'How to think about daylight, night privacy, stacking and pairing sheers with a separate privacy layer.',
			'content' => '<p><strong>Working copy for review.</strong> Sheer curtains are mainly about softening a room, filtering daylight and creating a continuous finish across larger glazing.</p><h2>Daylight and privacy are different questions</h2><p>A sheer can change how visible a room feels during the day, but it should not automatically be treated as complete night privacy.</p><h2>Layering can solve two jobs</h2><p>Where stronger privacy or blockout control is needed, a second window treatment can be considered rather than asking one fabric to do everything.</p><h2>Plan the stack and drop</h2><p>Track position, curtain stack, floor clearance and furniture all influence how the finished curtain looks and operates.</p><p>The final version will use current fabric choices and genuine EZ installation photographs after product verification.</p>',
		),
		'plantation-shutters-before-you-choose' => array(
			'title'   => 'Plantation shutters: what should be checked before you choose them?',
			'excerpt' => 'A room-by-room checklist covering opening style, panel movement, moisture exposure and visual fit.',
			'content' => '<p><strong>Working copy for review.</strong> Plantation shutters can make a window feel more architectural, but they are not automatically the best fit for every opening.</p><h2>Check how the window opens</h2><p>Handles, winders, recess depth and the way the original window operates can affect frame and panel design.</p><h2>Think about panel movement</h2><p>Furniture, taps, benches and nearby walls can influence how comfortably shutter panels can open and fold.</p><h2>Match material to the room</h2><p>Bathrooms and other moisture-prone areas need an appropriate material choice. Exact active EZ options will be inserted only after supplier verification.</p><p>The final article will add verified material choices, current warranty wording and real project examples.</p>',
		),
		'retractable-flyscreen-track-threshold-planning' => array(
			'title'   => 'Retractable flyscreen tracks and thresholds: what should you check?',
			'excerpt' => 'A focused guide to lower tracks, floor transitions, handles and everyday passage before a site measure.',
			'content' => '<p><strong>Working copy for review.</strong> A retractable flyscreen has to work with the way people actually move through the opening, not just fit within its width and height.</p><h2>Look closely at the lower track area</h2><p>Floor transitions, existing door tracks and the condition of the threshold can affect where a screen track can sit and how practical the finished opening feels.</p><h2>Check handles and moving panels</h2><p>Door handles, locks and the travel of sliding or folding panels can influence the available fixing position.</p><h2>Think about everyday passage</h2><p>Frequently used openings need a layout that makes sense for normal movement through the doorway. A site measure is used to confirm the details.</p><p>The final version will add verified current system details and genuine EZ installation examples before publication.</p>',
		),
		'motorised-blinds-power-control-planning' => array(
			'title'   => 'Motorised blinds: what should you plan for power and control?',
			'excerpt' => 'Questions to ask about charging or power access, grouped control and day-to-day operation before choosing a motor system.',
			'content' => '<p><strong>Working copy for review.</strong> Once motorisation is being considered, the next question is how the blind will be powered and controlled in normal daily use.</p><h2>Plan access before installation</h2><p>Charging access or another suitable power arrangement should be considered together with the window position and the way the room is used.</p><h2>Decide how many blinds need to work together</h2><p>A single blind and a room full of blinds can create different control needs. Grouped operation may be useful where compatible products are selected.</p><h2>Keep product compatibility separate from the idea</h2><p>Exact motor, control and power options depend on the current blind system and supplier range, so they must be verified before ordering.</p><p>The final version will publish only current EZ-supported motor and control options.</p>',
		),
	);

	foreach ( $posts as $slug => $data ) {
		if ( get_page_by_path( $slug, OBJECT, 'post' ) ) {
			continue;
		}

		wp_insert_post(
			array(
				'post_type'    => 'post',
				'post_status'  => 'publish',
				'post_title'   => $data['title'],
				'post_name'    => $slug,
				'post_excerpt' => $data['excerpt'],
				'post_content' => $data['content'],
			)
		);
	}
}
add_action( 'init', 'ezb_seed_starter_blog_posts', 34 );

/**
 * Migrate the two original starter posts whose search intent overlapped with
 * existing Advice pages. Only untouched development working copies qualify.
 */
function ezb_migrate_overlapping_starter_blog_topics() {
	if ( 'development' !== wp_get_environment_type() ) {
		return;
	}

	$migrations = array(
		'retractable-flyscreens-opening-suitability' => array(
			'expected_title' => 'Is your doorway suitable for a retractable flyscreen?',
			'new_slug'       => 'retractable-flyscreen-track-threshold-planning',
			'new_title'      => 'Retractable flyscreen tracks and thresholds: what should you check?',
			'new_excerpt'    => 'A focused guide to lower tracks, floor transitions, handles and everyday passage before a site measure.',
			'new_content'    => '<p><strong>Working copy for review.</strong> A retractable flyscreen has to work with the way people actually move through the opening, not just fit within its width and height.</p><h2>Look closely at the lower track area</h2><p>Floor transitions, existing door tracks and the condition of the threshold can affect where a screen track can sit and how practical the finished opening feels.</p><h2>Check handles and moving panels</h2><p>Door handles, locks and the travel of sliding or folding panels can influence the available fixing position.</p><h2>Think about everyday passage</h2><p>Frequently used openings need a layout that makes sense for normal movement through the doorway. A site measure is used to confirm the details.</p><p>The final version will add verified current system details and genuine EZ installation examples before publication.</p>',
		),
		'motorised-blinds-when-worth-it' => array(
			'expected_title' => 'When does motorisation make sense for blinds?',
			'new_slug'       => 'motorised-blinds-power-control-planning',
			'new_title'      => 'Motorised blinds: what should you plan for power and control?',
			'new_excerpt'    => 'Questions to ask about charging or power access, grouped control and day-to-day operation before choosing a motor system.',
			'new_content'    => '<p><strong>Working copy for review.</strong> Once motorisation is being considered, the next question is how the blind will be powered and controlled in normal daily use.</p><h2>Plan access before installation</h2><p>Charging access or another suitable power arrangement should be considered together with the window position and the way the room is used.</p><h2>Decide how many blinds need to work together</h2><p>A single blind and a room full of blinds can create different control needs. Grouped operation may be useful where compatible products are selected.</p><h2>Keep product compatibility separate from the idea</h2><p>Exact motor, control and power options depend on the current blind system and supplier range, so they must be verified before ordering.</p><p>The final version will publish only current EZ-supported motor and control options.</p>',
		),
	);

	foreach ( $migrations as $old_slug => $data ) {
		$post = get_page_by_path( $old_slug, OBJECT, 'post' );
		if (
			! $post ||
			$data['expected_title'] !== $post->post_title ||
			false === strpos( $post->post_content, '<strong>Working copy for review.</strong>' )
		) {
			continue;
		}

		wp_update_post(
			array(
				'ID'           => $post->ID,
				'post_name'    => $data['new_slug'],
				'post_title'   => $data['new_title'],
				'post_excerpt' => $data['new_excerpt'],
				'post_content' => $data['new_content'],
			)
		);
	}
}
add_action( 'init', 'ezb_migrate_overlapping_starter_blog_topics', 35 );


/**
 * Connect active product pages to one useful Blog guide without duplicating
 * the full article on the sales page. If the guide does not exist, render
 * nothing so production can fail closed until content is approved.
 */
function ezb_related_guide_map() {
	return array(
		'roller-blinds'          => 'roller-blinds-blockout-vs-sunscreen',
		'sheer-curtains'         => 'sheer-curtains-privacy-layering',
		'plantation-shutters'    => 'plantation-shutters-before-you-choose',
		'retractable-flyscreens' => 'retractable-flyscreen-track-threshold-planning',
		'motorised-blinds'       => 'motorised-blinds-power-control-planning',
	);
}

add_shortcode(
	'ezb_related_guide',
	function ( $atts ) {
		$atts = shortcode_atts(
			array( 'product' => '' ),
			$atts,
			'ezb_related_guide'
		);

		$product = sanitize_title( $atts['product'] );
		$map     = ezb_related_guide_map();

		if ( ! isset( $map[ $product ] ) ) {
			return '';
		}

		$article = get_page_by_path( $map[ $product ], OBJECT, 'post' );
		if ( ! $article || 'publish' !== $article->post_status ) {
			return '';
		}

		$excerpt = trim( wp_strip_all_tags( $article->post_excerpt ) );

		return sprintf(
			'<section class="ezb-section ezb-shell ezb-related-guide"><div class="ezb-related-guide__inner"><p class="ezb-eyebrow">%1$s</p><h2>%2$s</h2>%3$s<p><a class="ezb-related-guide__link" href="%4$s">%5$s</a></p></div></section>',
			esc_html__( 'Related guide', 'ezb-core' ),
			esc_html( get_the_title( $article ) ),
			'' !== $excerpt ? '<p>' . esc_html( $excerpt ) . '</p>' : '',
			esc_url( get_permalink( $article ) ),
			esc_html__( 'Read the guide', 'ezb-core' )
		);
	}
);



/**
 * Keep Blog articles connected to the relevant commercial and evergreen
 * information paths without hard-coding links inside article copy.
 */
function ezb_blog_next_step_map() {
	return array(
		'roller-blinds-blockout-vs-sunscreen' => array(
			'product_url'   => '/roller-blinds/',
			'product_label' => 'Explore Roller Blinds',
		),
		'sheer-curtains-privacy-layering' => array(
			'product_url'   => '/sheer-curtains/',
			'product_label' => 'Explore Sheer Curtains',
		),
		'plantation-shutters-before-you-choose' => array(
			'product_url'   => '/plantation-shutters/',
			'product_label' => 'Explore Plantation Shutters',
		),
		'retractable-flyscreen-track-threshold-planning' => array(
			'product_url'   => '/retractable-flyscreens/',
			'product_label' => 'Explore Retractable Flyscreens',
			'advice_url'    => '/advice/retractable-flyscreen-suitability/',
			'advice_label'  => 'Read the suitability guide',
		),
		'motorised-blinds-power-control-planning' => array(
			'product_url'   => '/motorised-blinds/',
			'product_label' => 'Explore Motorisation',
			'advice_url'    => '/advice/when-motorisation-makes-sense/',
			'advice_label'  => 'When motorisation makes sense',
		),
	);
}

add_shortcode(
	'ezb_blog_next_step',
	function () {
		$post = get_post();
		if ( ! $post || 'post' !== $post->post_type ) {
			return '';
		}

		$map = ezb_blog_next_step_map();
		if ( ! isset( $map[ $post->post_name ] ) ) {
			return '';
		}

		$item  = $map[ $post->post_name ];
		$links = array(
			'<a class="ezb-blog-next-step__link" href="' . esc_url( home_url( $item['product_url'] ) ) . '">' . esc_html( $item['product_label'] ) . '</a>',
		);

		if ( ! empty( $item['advice_url'] ) && ! empty( $item['advice_label'] ) ) {
			$links[] = '<a class="ezb-blog-next-step__link ezb-blog-next-step__link--secondary" href="' . esc_url( home_url( $item['advice_url'] ) ) . '">' . esc_html( $item['advice_label'] ) . '</a>';
		}

		return '<aside class="ezb-blog-next-step"><p class="ezb-eyebrow">' . esc_html__( 'Useful next step', 'ezb-core' ) . '</p><div class="ezb-blog-next-step__links">' . implode( '', $links ) . '</div></aside>';
	}
);


/**
 * Render the active Page content in development templates that are processed
 * through the prototype router rather than WordPress's normal block-template
 * context builder.
 */
add_shortcode(
	'ezb_current_page_content',
	function () {
		$post = get_post();
		if ( ! $post || 'page' !== $post->post_type ) {
			return '';
		}

		return apply_filters( 'the_content', $post->post_content );
	}
);


/**
 * Owner-maintainable site settings for repeated CTA and public contact details.
 */
function ezb_site_setting_defaults() {
	return array(
		'ezb_cta_heading'      => 'Ready to talk through your windows?',
		'ezb_cta_body'         => 'Send your suburb, the product you are considering and a brief description of your opening. We can then work out the most practical next step.',
		'ezb_cta_button_label' => 'Free Measure & Quote',
		'ezb_public_phone'          => '',
		'ezb_public_email'          => '',
		'ezb_quote_recipient_email' => '',
	);
}

function ezb_get_site_setting( $key ) {
	$defaults = ezb_site_setting_defaults();
	$default  = isset( $defaults[ $key ] ) ? $defaults[ $key ] : '';
	return get_option( $key, $default );
}

add_action(
	'admin_init',
	function () {
		$defaults = ezb_site_setting_defaults();

		register_setting( 'ezb_site_settings', 'ezb_cta_heading', array( 'type' => 'string', 'sanitize_callback' => 'sanitize_text_field', 'default' => $defaults['ezb_cta_heading'] ) );
		register_setting( 'ezb_site_settings', 'ezb_cta_body', array( 'type' => 'string', 'sanitize_callback' => 'sanitize_textarea_field', 'default' => $defaults['ezb_cta_body'] ) );
		register_setting( 'ezb_site_settings', 'ezb_cta_button_label', array( 'type' => 'string', 'sanitize_callback' => 'sanitize_text_field', 'default' => $defaults['ezb_cta_button_label'] ) );
		register_setting( 'ezb_site_settings', 'ezb_public_phone', array( 'type' => 'string', 'sanitize_callback' => 'sanitize_text_field', 'default' => '' ) );
		register_setting( 'ezb_site_settings', 'ezb_public_email', array( 'type' => 'string', 'sanitize_callback' => 'sanitize_email', 'default' => '' ) );
		register_setting( 'ezb_site_settings', 'ezb_quote_recipient_email', array( 'type' => 'string', 'sanitize_callback' => 'sanitize_email', 'default' => '' ) );
	}
);

function ezb_render_site_settings_page() {
	if ( ! current_user_can( 'manage_options' ) ) {
		return;
	}

	$fields = array(
		'ezb_cta_heading'      => __( 'CTA heading', 'ezb-core' ),
		'ezb_cta_body'         => __( 'CTA body', 'ezb-core' ),
		'ezb_cta_button_label' => __( 'CTA button label', 'ezb-core' ),
		'ezb_public_phone'          => __( 'Public phone', 'ezb-core' ),
		'ezb_public_email'          => __( 'Public email', 'ezb-core' ),
		'ezb_quote_recipient_email' => __( 'Enquiry recipient email', 'ezb-core' ),
	);
	?>
	<div class="wrap">
		<h1><?php esc_html_e( 'EZ Site Settings', 'ezb-core' ); ?></h1>
		<p><?php esc_html_e( 'Routine CTA and contact details can be updated here without editing theme code.', 'ezb-core' ); ?></p>
		<form method="post" action="options.php">
			<?php settings_fields( 'ezb_site_settings' ); ?>
			<table class="form-table" role="presentation">
				<?php foreach ( $fields as $key => $label ) : ?>
					<tr>
						<th scope="row"><label for="<?php echo esc_attr( $key ); ?>"><?php echo esc_html( $label ); ?></label></th>
						<td>
							<?php if ( 'ezb_cta_body' === $key ) : ?>
								<textarea class="large-text" rows="4" id="<?php echo esc_attr( $key ); ?>" name="<?php echo esc_attr( $key ); ?>"><?php echo esc_textarea( ezb_get_site_setting( $key ) ); ?></textarea>
							<?php else : ?>
								<input class="regular-text" type="<?php echo in_array( $key, array( 'ezb_public_email', 'ezb_quote_recipient_email' ), true ) ? 'email' : 'text'; ?>" id="<?php echo esc_attr( $key ); ?>" name="<?php echo esc_attr( $key ); ?>" value="<?php echo esc_attr( ezb_get_site_setting( $key ) ); ?>">
							<?php endif; ?>
						</td>
					</tr>
				<?php endforeach; ?>
			</table>
			<?php submit_button(); ?>
		</form>
	</div>
	<?php
}

add_action(
	'admin_menu',
	function () {
		add_options_page(
			__( 'EZ Site Settings', 'ezb-core' ),
			__( 'EZ Site Settings', 'ezb-core' ),
			'manage_options',
			'ezb-site-settings',
			'ezb_render_site_settings_page'
		);
	}
);

add_shortcode(
	'ezb_measure_quote_cta',
	function () {
		$heading = ezb_get_site_setting( 'ezb_cta_heading' );
		$body    = ezb_get_site_setting( 'ezb_cta_body' );
		$label   = ezb_get_site_setting( 'ezb_cta_button_label' );
		$phone   = ezb_get_site_setting( 'ezb_public_phone' );
		$email   = sanitize_email( ezb_get_site_setting( 'ezb_public_email' ) );

		$contact_items = array();

		if ( '' !== trim( $phone ) ) {
			$tel = preg_replace( '/[^0-9+]/', '', $phone );
			if ( '' !== $tel ) {
				$contact_items[] = '<a href="tel:' . esc_attr( $tel ) . '">' . esc_html( $phone ) . '</a>';
			}
		}

		if ( $email ) {
			$contact_items[] = '<a href="mailto:' . esc_attr( $email ) . '">' . esc_html( $email ) . '</a>';
		}

		$contact_markup = $contact_items
			? '<p class="ezb-cta__contact">' . implode( ' <span aria-hidden="true">·</span> ', $contact_items ) . '</p>'
			: '';

		return sprintf(
			'<section class="ezb-section ezb-shell"><div class="ezb-cta">%1$s%2$s%3$s<div class="wp-block-button"><a class="wp-block-button__link wp-element-button" href="%4$s">%5$s</a></div></div></section>',
			'' !== trim( $heading ) ? '<h2>' . esc_html( $heading ) . '</h2>' : '',
			'' !== trim( $body ) ? '<p>' . esc_html( $body ) . '</p>' : '',
			$contact_markup,
			esc_url( home_url( '/contact/' ) ),
			esc_html( $label )
		);
	}
);


/**
 * Seed clearly-labelled prototype Project cards in development only.
 */
function ezb_seed_prototype_projects() {
	if ( 'development' !== wp_get_environment_type() ) {
		return;
	}


	$projects = array(
		'owner-editability-test' => array(
			'title'   => 'Owner Editability Test — Safe to Edit',
			'excerpt' => 'Development-only draft used for the required Owner editability acceptance check.',
			'content' => '<p><strong>Development test only.</strong> During Owner acceptance, edit this sentence or replace the Featured Image, then preview the result. No code should be required.</p>',
			'status'  => 'draft',
		),
		'retractable-flyscreen-large-opening' => array(
			'title'   => 'Retractable Flyscreen — Large Opening',
			'excerpt' => 'Development case-study shell using visually grouped EZ project media. Exact location and project details are intentionally omitted until confirmed.',
			'content' => '<p>This project entry groups genuine EZ installation imagery for development review.</p><h2>The opening</h2><p>A large glazed opening where airflow and visual connection to the outdoor area are important.</p><h2>The solution</h2><p>A retractable flyscreen is visible across the opening in the supplied project imagery. Exact product specifications remain unverified.</p><h2>Evidence status</h2><p>The image grouping is visually supported. Location, customer, date, dimensions and product specification remain unconfirmed.</p>',
		),
		'retractable-flyscreen-indoor-outdoor-opening' => array(
			'title'   => 'Retractable Flyscreen — Indoor / Outdoor Opening',
			'excerpt' => 'Development case-study shell using a visually grouped EZ installation set. Exact location and project details are intentionally omitted until confirmed.',
			'content' => '<p>This development entry groups three genuine EZ installation photographs that show the same indoor-outdoor opening from consistent viewpoints.</p><h2>The opening</h2><p>A living-area opening connecting to a covered outdoor seating area.</p><h2>The solution</h2><p>A retractable flyscreen is visible across the opening in the supplied project imagery. Exact system specification remains unverified.</p><h2>Evidence status</h2><p>Only the visual grouping is treated as verified at this stage. Location, customer, date, dimensions and product specification remain unconfirmed.</p>',
		),
		'prototype-roller-blinds-project' => array(
			'title'   => 'Prototype Project — Roller Blinds',
			'excerpt' => 'Layout placeholder only. This is not a published customer case study.',
			'content' => '<p><strong>Prototype only.</strong> This page demonstrates the future case-study layout for a roller-blind installation. Real location, product details and photography will replace this placeholder after verification.</p>',
		),
		'prototype-sheer-curtains-project' => array(
			'title'   => 'Prototype Project — Sheer Curtains',
			'excerpt' => 'Layout placeholder only. This is not a published customer case study.',
			'content' => '<p><strong>Prototype only.</strong> This page demonstrates the future case-study layout for a sheer-curtain installation. Real project facts and approved media will replace this placeholder.</p>',
		),
		'prototype-retractable-flyscreen-project' => array(
			'title'   => 'Prototype Project — Retractable Flyscreen',
			'excerpt' => 'Layout placeholder only. This is not a published customer case study.',
			'content' => '<p><strong>Prototype only.</strong> This page demonstrates the future case-study layout for a retractable-flyscreen installation. Real project facts and approved media will replace this placeholder.</p>',
		),
	);

	foreach ( $projects as $slug => $project ) {
		if ( get_page_by_path( $slug, OBJECT, 'ezb_project' ) ) {
			continue;
		}

		wp_insert_post(
			array(
				'post_type'    => 'ezb_project',
				'post_status'  => isset( $project['status'] ) ? $project['status'] : 'publish',
				'post_title'   => $project['title'],
				'post_name'    => $slug,
				'post_excerpt' => $project['excerpt'],
				'post_content' => $project['content'],
			)
		);
	}

}
add_action( 'init', 'ezb_seed_prototype_projects', 31 );


/**
 * Seed nested Advice prototype pages in development only.
 */
function ezb_seed_prototype_advice_children() {
	if ( 'development' !== wp_get_environment_type() ) {
		return;
	}


	$parent = get_page_by_path( 'advice', OBJECT, 'page' );
	if ( ! $parent ) {
		return;
	}

	$pages = array(
		'privacy-vs-daylight' => 'Privacy vs daylight: where should you start?',
		'retractable-flyscreen-suitability' => 'What makes an opening suitable for a retractable flyscreen?',
		'when-motorisation-makes-sense' => 'When does motorisation make sense?',
	);

	foreach ( $pages as $slug => $title ) {
		$existing = get_page_by_path( 'advice/' . $slug, OBJECT, 'page' );
		if ( $existing ) {
			continue;
		}

		wp_insert_post(
			array(
				'post_type'   => 'page',
				'post_status' => 'publish',
				'post_title'  => $title,
				'post_name'   => $slug,
				'post_parent' => $parent->ID,
			)
		);
	}

}
add_action( 'init', 'ezb_seed_prototype_advice_children', 32 );


/**
 * Render published Advice child pages dynamically.
 *
 * Adding a published child Page beneath Advice is enough to make it appear in
 * the Advice index; no template/code edit is required for each new guide.
 */
add_shortcode(
	'ezb_advice_cards',
	function () {
		$parent = get_page_by_path( 'advice', OBJECT, 'page' );
		if ( ! $parent ) {
			return '';
		}

		$pages = get_children(
			array(
				'post_parent' => $parent->ID,
				'post_type'   => 'page',
				'post_status' => 'publish',
				'numberposts' => -1,
				'orderby'     => 'menu_order title',
				'order'       => 'ASC',
			)
		);

		if ( ! $pages ) {
			return '<div class="ezb-media-placeholder"><p class="ezb-media-placeholder__kicker">ADVICE</p><p>Published advice guides will appear here.</p></div>';
		}

		$known = array(
			'privacy-vs-daylight' => array(
				'priority' => 10,
				'label'    => 'PRIVACY + DAYLIGHT',
				'summary'  => 'A practical guide to balancing privacy, glare and usable daylight.',
			),
			'retractable-flyscreen-suitability' => array(
				'priority' => 20,
				'label'    => 'OPENING SUITABILITY',
				'summary'  => 'A practical guide to opening size, framing, tracks and day-to-day use.',
			),
			'when-motorisation-makes-sense' => array(
				'priority' => 30,
				'label'    => 'MOTORISATION',
				'summary'  => 'A practical guide to access, routine and control options.',
			),
		);

		usort(
			$pages,
			static function ( $a, $b ) use ( $known ) {
				$a_priority = isset( $known[ $a->post_name ]['priority'] ) ? $known[ $a->post_name ]['priority'] : 1000 + (int) $a->menu_order;
				$b_priority = isset( $known[ $b->post_name ]['priority'] ) ? $known[ $b->post_name ]['priority'] : 1000 + (int) $b->menu_order;

				if ( $a_priority === $b_priority ) {
					return strcasecmp( $a->post_title, $b->post_title );
				}

				return $a_priority <=> $b_priority;
			}
		);

		$cards = '';
		foreach ( $pages as $page ) {
			$metadata = isset( $known[ $page->post_name ] ) ? $known[ $page->post_name ] : array();
			$label    = isset( $metadata['label'] ) ? $metadata['label'] : 'ADVICE';

			if ( isset( $metadata['summary'] ) ) {
				$summary = $metadata['summary'];
			} elseif ( '' !== trim( $page->post_excerpt ) ) {
				$summary = $page->post_excerpt;
			} else {
				$summary = wp_trim_words( wp_strip_all_tags( strip_shortcodes( $page->post_content ) ), 22 );
			}

			if ( '' === trim( $summary ) ) {
				$summary = __( 'Practical guidance from EZ Blinds & Shutters.', 'ezb-core' );
			}

			$cards .= '<article class="ezb-card">';
			$cards .= '<div class="ezb-card-media ezb-card-media--advice"><span>' . esc_html( $label ) . '</span></div>';
			$cards .= '<p class="ezb-eyebrow">' . esc_html__( 'Advice guide', 'ezb-core' ) . '</p>';
			$cards .= '<h3><a href="' . esc_url( get_permalink( $page ) ) . '">' . esc_html( $page->post_title ) . '</a></h3>';
			$cards .= '<p>' . esc_html( $summary ) . '</p>';
			$cards .= '</article>';
		}

		return '<div class="ezb-advice-grid ezb-cards">' . $cards . '</div>';
	}
);


/**
 * Verified first-pass legacy redirect registry.
 *
 * This is intentionally incomplete. Only URLs whose destination intent is
 * already supported by the canonical legacy inventory are included here.
 * The final cutover redirect register still requires the launch-stage crawl,
 * sitemap / Search Console evidence and Owner business confirmation.
 */
function ezb_legacy_redirect_registry() {
	return array(
		'/retractable-fly-screen/' => array(
			'status' => 'verified_redirect',
			'target' => '/retractable-flyscreens/',
			'reason' => 'Same product intent; canonical new slug is verified.',
		),
		'/portfolio/' => array(
			'status' => 'verified_redirect',
			'target' => '/projects/',
			'reason' => 'Legacy Projects archive maps to the new Projects archive.',
		),
		'/portfolio/page/2/' => array(
			'status' => 'verified_redirect',
			'target' => '/projects/',
			'reason' => 'Legacy paginated Projects archive maps to the new Projects archive.',
		),
		'/category/roller-blinds/' => array(
			'status' => 'verified_redirect',
			'target' => '/roller-blinds/',
			'reason' => 'Legacy Roller Blinds category intent maps to the product page.',
		),
		'/roman-blinds/' => array(
			'status' => 'gone',
			'target' => '',
			'reason' => 'Owner confirmed Roman Blinds are discontinued and will not be sold.',
		),
		'/panel-guide-blinds/' => array(
			'status' => 'gone',
			'target' => '',
			'reason' => 'Owner confirmed Panel Guide / Panel Glide products are discontinued and will not be sold.',
		),
		'/venetian-blinds/' => array(
			'status' => 'gone',
			'target' => '',
			'reason' => 'Owner confirmed Venetian Blinds are discontinued and will not be sold.',
		),
		'/portfolio/venetian-blinds/' => array(
			'status' => 'gone',
			'target' => '',
			'reason' => 'Owner confirmed the historic Venetian project should be retired.',
		),
		'/2018/02/04/roller-blinds-showcase/' => array(
			'status' => 'verified_redirect',
			'target' => '/roller-blinds/',
			'reason' => 'Historic Roller Blinds showcase maps to the active Roller Blinds product intent.',
		),
		'/2018/02/04/plantation-shutters-showcase/' => array(
			'status' => 'verified_redirect',
			'target' => '/plantation-shutters/',
			'reason' => 'Historic Plantation Shutters showcase maps to the active product intent.',
		),
		'/2018/02/04/roman-blinds-showcase/' => array(
			'status' => 'gone',
			'target' => '',
			'reason' => 'Roman Blinds are discontinued; no truthful replacement product route exists.',
		),
		'/2018/02/04/panel-guide-blinds-showcase/' => array(
			'status' => 'gone',
			'target' => '',
			'reason' => 'Panel Guide / Panel Glide products are discontinued; no truthful replacement route exists.',
		),
		'/2018/02/04/venetian-blinds-showcase/' => array(
			'status' => 'gone',
			'target' => '',
			'reason' => 'Venetian Blinds are discontinued; no truthful replacement product route exists.',
		),
		'/2018/10/06/retractable-fly-screen-showcase/' => array(
			'status' => 'verified_redirect',
			'target' => '/retractable-flyscreens/',
			'reason' => 'Historic retractable-flyscreen showcase maps to the active product intent.',
		),
	);
}

function ezb_legacy_redirect_map() {
	$map = array();

	foreach ( ezb_legacy_redirect_registry() as $source => $entry ) {
		if (
			isset( $entry['status'], $entry['target'] ) &&
			'verified_redirect' === $entry['status'] &&
			'' !== $entry['target']
		) {
			$map[ $source ] = $entry['target'];
		}
	}

	return $map;
}

function ezb_normalise_request_path( $request_uri ) {
	$path = wp_parse_url( $request_uri, PHP_URL_PATH );
	if ( ! is_string( $path ) || '' === $path ) {
		return '';
	}

	if ( '/' === $path ) {
		return '/';
	}

	return trailingslashit( '/' . trim( $path, '/' ) );
}

function ezb_legacy_redirect_target( $request_uri ) {
	$path = ezb_normalise_request_path( $request_uri );
	$map  = ezb_legacy_redirect_map();

	return isset( $map[ $path ] ) ? $map[ $path ] : '';
}

function ezb_legacy_gone_path( $request_uri ) {
	$path     = ezb_normalise_request_path( $request_uri );
	$registry = ezb_legacy_redirect_registry();

	return isset( $registry[ $path ]['status'] ) && 'gone' === $registry[ $path ]['status'];
}

function ezb_apply_retired_legacy_gone() {
	if ( 'development' === wp_get_environment_type() ) {
		return;
	}

	$method = isset( $_SERVER['REQUEST_METHOD'] ) ? strtoupper( sanitize_text_field( wp_unslash( $_SERVER['REQUEST_METHOD'] ) ) ) : 'GET';
	if ( ! in_array( $method, array( 'GET', 'HEAD' ), true ) ) {
		return;
	}

	$request_uri = isset( $_SERVER['REQUEST_URI'] ) ? wp_unslash( $_SERVER['REQUEST_URI'] ) : '';
	if ( ! ezb_legacy_gone_path( $request_uri ) ) {
		return;
	}

	status_header( 410 );
	nocache_headers();

	if ( 'HEAD' === $method ) {
		exit;
	}

	wp_die(
		esc_html__( 'This product or project has been retired and is no longer offered by EZ Blinds & Shutters.', 'ezb-core' ),
		esc_html__( 'Content retired', 'ezb-core' ),
		array( 'response' => 410 )
	);
}
add_action( 'template_redirect', 'ezb_apply_retired_legacy_gone', 0 );

function ezb_apply_verified_legacy_redirects() {
	if ( 'development' === wp_get_environment_type() ) {
		return;
	}

	$method = isset( $_SERVER['REQUEST_METHOD'] ) ? strtoupper( sanitize_text_field( wp_unslash( $_SERVER['REQUEST_METHOD'] ) ) ) : 'GET';
	if ( ! in_array( $method, array( 'GET', 'HEAD' ), true ) ) {
		return;
	}

	$request_uri = isset( $_SERVER['REQUEST_URI'] ) ? wp_unslash( $_SERVER['REQUEST_URI'] ) : '';
	$target      = ezb_legacy_redirect_target( $request_uri );

	if ( '' === $target ) {
		return;
	}

	wp_safe_redirect( home_url( $target ), 301, 'EZB Legacy Redirect' );
	exit;
}
add_action( 'template_redirect', 'ezb_apply_verified_legacy_redirects', 1 );


/**
 * Fail-closed indexing protection for development previews.
 *
 * The bootstrap already sets blog_public=0. These guards remain active even
 * if that database option is changed accidentally, and do nothing outside
 * the development environment.
 */
function ezb_force_dev_robots( $robots ) {
	if ( 'development' !== wp_get_environment_type() ) {
		return $robots;
	}

	unset( $robots['index'], $robots['follow'] );
	$robots['noindex']   = true;
	$robots['nofollow']  = true;
	$robots['noarchive'] = true;

	return $robots;
}
add_filter( 'wp_robots', 'ezb_force_dev_robots', 999 );

function ezb_force_dev_robots_txt( $output, $public ) {
	if ( 'development' !== wp_get_environment_type() ) {
		return $output;
	}

	return "User-agent: *\nDisallow: /\n";
}
add_filter( 'robots_txt', 'ezb_force_dev_robots_txt', 999, 2 );

function ezb_send_dev_x_robots_header() {
	if ( 'development' !== wp_get_environment_type() || is_admin() ) {
		return;
	}

	header( 'X-Robots-Tag: noindex, nofollow, noarchive', true );
}
add_action( 'send_headers', 'ezb_send_dev_x_robots_header', 999 );


/**
 * Resolve the active development URL from the current proxied request.
 *
 * This prevents WordPress canonical redirects from sending Codespaces
 * preview traffic back to the bootstrap URL (localhost:8080).
 */
function ezb_runtime_base_url() {
	if ( 'development' !== wp_get_environment_type() ) {
		return '';
	}

	$host = '';
	if ( ! empty( $_SERVER['HTTP_X_FORWARDED_HOST'] ) ) {
		$host = sanitize_text_field( wp_unslash( $_SERVER['HTTP_X_FORWARDED_HOST'] ) );
	} elseif ( ! empty( $_SERVER['HTTP_HOST'] ) ) {
		$host = sanitize_text_field( wp_unslash( $_SERVER['HTTP_HOST'] ) );
	}

	if ( '' === $host ) {
		return '';
	}

	$scheme = 'http';
	if (
		( ! empty( $_SERVER['HTTP_X_FORWARDED_PROTO'] ) && 'https' === strtolower( sanitize_text_field( wp_unslash( $_SERVER['HTTP_X_FORWARDED_PROTO'] ) ) ) ) ||
		( ! empty( $_SERVER['HTTPS'] ) && 'off' !== strtolower( sanitize_text_field( wp_unslash( $_SERVER['HTTPS'] ) ) ) )
	) {
		$scheme = 'https';
	}

	return $scheme . '://' . $host;
}

function ezb_filter_runtime_home_url( $value ) {
	$runtime = ezb_runtime_base_url();
	return $runtime ? $runtime : $value;
}
add_filter( 'pre_option_home', 'ezb_filter_runtime_home_url' );
add_filter( 'pre_option_siteurl', 'ezb_filter_runtime_home_url' );

/**
 * Rewrite leaked localhost asset origins to the active development preview.
 *
 * WordPress can derive theme asset URLs from constants initialised before the
 * runtime home/siteurl filters above. Only local development origins are
 * rewritten; normal staging/production asset URLs are left untouched.
 */
function ezb_rewrite_dev_loader_src( $src ) {
	if ( 'development' !== wp_get_environment_type() || ! is_string( $src ) || '' === $src ) {
		return $src;
	}

	$host = wp_parse_url( $src, PHP_URL_HOST );
	if ( ! in_array( $host, array( 'localhost', '127.0.0.1' ), true ) ) {
		return $src;
	}

	$runtime = ezb_runtime_base_url();
	if ( '' === $runtime ) {
		return $src;
	}

	$path     = wp_parse_url( $src, PHP_URL_PATH );
	$query    = wp_parse_url( $src, PHP_URL_QUERY );
	$fragment = wp_parse_url( $src, PHP_URL_FRAGMENT );
	$rewritten = untrailingslashit( $runtime ) . ( is_string( $path ) ? $path : '' );

	if ( is_string( $query ) && '' !== $query ) {
		$rewritten .= '?' . $query;
	}

	if ( is_string( $fragment ) && '' !== $fragment ) {
		$rewritten .= '#' . $fragment;
	}

	return $rewritten;
}
add_filter( 'style_loader_src', 'ezb_rewrite_dev_loader_src', 999 );
add_filter( 'script_loader_src', 'ezb_rewrite_dev_loader_src', 999 );


/**
 * Codespaces preview hardening.
 *
 * In development, WordPress may retain localhost from bootstrap as its
 * canonical origin. Disable canonical redirects and let the browser rewrite
 * any leaked localhost URLs to the active preview origin.
 */
function ezb_disable_dev_canonical_redirect( $redirect_url, $requested_url ) {
	if ( 'development' === wp_get_environment_type() ) {
		return false;
	}

	return $redirect_url;
}
add_filter( 'redirect_canonical', 'ezb_disable_dev_canonical_redirect', 10, 2 );

function ezb_print_dev_url_bridge() {
	if ( 'development' !== wp_get_environment_type() ) {
		return;
	}

	$path_map = array(
		'/products/'                                   => 'products',
		'/roller-blinds/'                              => 'roller-blinds',
		'/sheer-curtains/'                             => 'sheer-curtains',
		'/plantation-shutters/'                        => 'plantation-shutters',
		'/retractable-flyscreens/'                     => 'retractable-flyscreens',
		'/motorised-blinds/'                           => 'motorised-blinds',
		'/projects/'                                   => 'projects',
		'/advice/'                                     => 'advice',
		'/blog/'                                       => 'blog',
		'/advice/privacy-vs-daylight/'                 => 'privacy-vs-daylight',
		'/advice/retractable-flyscreen-suitability/'   => 'retractable-flyscreen-suitability',
		'/advice/when-motorisation-makes-sense/'       => 'when-motorisation-makes-sense',
		'/service-areas/'                              => 'service-areas',
		'/about/'                                      => 'about',
		'/contact/'                                    => 'contact',
	);
	?>
	<script id="ezb-codespaces-url-bridge">
	(function () {
		var pathMap = <?php echo wp_json_encode( $path_map ); ?>;

		function prototypeUrlFor(pathname) {
			if (!pathname) return null;
			var clean = pathname.replace(/\/+$/, '/') || '/';
			var key = pathMap[clean];
			return key ? (window.location.origin + '/?ezb_page=' + encodeURIComponent(key)) : null;
		}

		function rewriteUrl(value) {
			if (!value) return value;

			try {
				var url = new URL(value, window.location.href);
				var prototypeUrl = prototypeUrlFor(url.pathname);
				if (prototypeUrl) {
					return prototypeUrl + url.search.replace(/^\?/, '&') + url.hash;
				}

				if (url.hostname === 'localhost' || url.hostname === '127.0.0.1') {
					return window.location.origin + url.pathname + url.search + url.hash;
				}
			} catch (e) {}

			return value;
		}

		function reconcile(root) {
			(root || document).querySelectorAll('a[href]').forEach(function (el) {
				var next = rewriteUrl(el.getAttribute('href'));
				if (next) el.setAttribute('href', next);
			});

			(root || document).querySelectorAll('form[action]').forEach(function (el) {
				var next = rewriteUrl(el.getAttribute('action'));
				if (next) el.setAttribute('action', next);
			});
		}

		if (document.readyState === 'loading') {
			document.addEventListener('DOMContentLoaded', function () {
				reconcile(document);
			});
		} else {
			reconcile(document);
		}

		new MutationObserver(function (mutations) {
			mutations.forEach(function (mutation) {
				mutation.addedNodes.forEach(function (node) {
					if (node.nodeType === 1) reconcile(node);
				});
			});
		}).observe(document.documentElement, { childList: true, subtree: true });
	})();
	</script>
	<?php
}
add_action( 'wp_footer', 'ezb_print_dev_url_bridge', 100 );


/**
 * Development-only prototype router.
 *
 * Existing Codespaces can retain localhost as their bootstrap origin.
 * During whole-site prototyping we bypass pretty-permalink canonicalisation
 * completely and render known prototype templates from a query-string route.
 */
function ezb_get_dev_prototype_routes() {
	return array(
		'products'                         => 'page-products.html',
		'roller-blinds'                    => 'page-roller-blinds.html',
		'sheer-curtains'                   => 'page-sheer-curtains.html',
		'plantation-shutters'              => 'page-plantation-shutters.html',
		'retractable-flyscreens'           => 'page-retractable-flyscreens.html',
		'motorised-blinds'                 => 'page-motorised-blinds.html',
		'projects'                         => 'archive-ezb_project.html',
		'advice'                           => 'page-advice.html',
		'blog'                             => 'page-blog.html',
		'privacy-vs-daylight'              => 'page-privacy-vs-daylight.html',
		'retractable-flyscreen-suitability'=> 'page-retractable-flyscreen-suitability.html',
		'when-motorisation-makes-sense'    => 'page-when-motorisation-makes-sense.html',
		'service-areas'                    => 'page-service-areas.html',
		'about'                            => 'page-about.html',
		'contact'                          => 'page-contact.html',
	);
}

function ezb_rewrite_dev_prototype_html( $html ) {
	if ( 'development' !== wp_get_environment_type() || '' === $html ) {
		return $html;
	}

	$path_map = array(
		'/products/'                                   => 'products',
		'/roller-blinds/'                              => 'roller-blinds',
		'/sheer-curtains/'                             => 'sheer-curtains',
		'/plantation-shutters/'                        => 'plantation-shutters',
		'/retractable-flyscreens/'                     => 'retractable-flyscreens',
		'/motorised-blinds/'                           => 'motorised-blinds',
		'/projects/'                                   => 'projects',
		'/advice/'                                     => 'advice',
		'/blog/'                                       => 'blog',
		'/advice/privacy-vs-daylight/'                 => 'privacy-vs-daylight',
		'/advice/retractable-flyscreen-suitability/'   => 'retractable-flyscreen-suitability',
		'/advice/when-motorisation-makes-sense/'       => 'when-motorisation-makes-sense',
		'/service-areas/'                              => 'service-areas',
		'/about/'                                      => 'about',
		'/contact/'                                    => 'contact',
	);

	$callback = static function ( $matches ) use ( $path_map ) {
		$attribute = $matches[1];
		$quote     = $matches[2];
		$value     = html_entity_decode( $matches[3], ENT_QUOTES, 'UTF-8' );

		$parsed = wp_parse_url( $value );
		$path   = isset( $parsed['path'] ) ? trailingslashit( $parsed['path'] ) : '';

		if ( isset( $path_map[ $path ] ) ) {
			$query = '?ezb_page=' . rawurlencode( $path_map[ $path ] );
			return $attribute . '=' . $quote . esc_attr( $query ) . $quote;
		}

		if ( preg_match( '#^/projects/([^/]+)/$#', $path, $project_match ) ) {
			$query = '?ezb_page=project&ezb_project=' . rawurlencode( $project_match[1] );
			return $attribute . '=' . $quote . esc_attr( $query ) . $quote;
		}

		if ( isset( $parsed['host'] ) && in_array( strtolower( $parsed['host'] ), array( 'localhost', '127.0.0.1' ), true ) ) {
			$relative = isset( $parsed['path'] ) ? $parsed['path'] : '/';
			if ( ! empty( $parsed['query'] ) ) {
				$relative .= '?' . $parsed['query'];
			}
			if ( ! empty( $parsed['fragment'] ) ) {
				$relative .= '#' . $parsed['fragment'];
			}
			return $attribute . '=' . $quote . esc_attr( $relative ) . $quote;
		}

		return $matches[0];
	};

	return preg_replace_callback(
		'/\b(href|action)=(["\'])(.*?)\2/i',
		$callback,
		$html
	);
}

/**
 * Reject malformed routing query parameters before WP_Query parses requests.
 *
 * ezb_project is a registered public post-type query variable on ALL hosts,
 * including staging and production; arrays can cause a TypeError in core.
 * ezb_page is a development-only prototype transport parameter.
 */
function ezb_reject_malformed_route_query() {
	$is_dev     = 'development' === wp_get_environment_type();
	$parameters = array( 'ezb_project' );
	if ( $is_dev ) {
		$parameters[] = 'ezb_page';
	}

	foreach ( $parameters as $parameter ) {
		if ( isset( $_GET[ $parameter ] ) && ! is_string( $_GET[ $parameter ] ) ) {
			wp_die(
				esc_html__( $is_dev ? 'Invalid development route request.' : 'Invalid route request.', 'ezb-core' ),
				esc_html__( 'Invalid request', 'ezb-core' ),
				array( 'response' => 400 )
			);
		}
	}
}
add_action( 'init', 'ezb_reject_malformed_route_query', 0 );

function ezb_render_dev_prototype_route() {
	if ( 'development' !== wp_get_environment_type() || empty( $_GET['ezb_page'] ) || ! is_string( $_GET['ezb_page'] ) ) {
		return;
	}

	$key              = sanitize_key( wp_unslash( $_GET['ezb_page'] ) );
	$routes           = ezb_get_dev_prototype_routes();
	$post_context_set = false;

	if ( 'project' === $key ) {
		$slug = isset( $_GET['ezb_project'] ) && is_string( $_GET['ezb_project'] )
			? sanitize_title( wp_unslash( $_GET['ezb_project'] ) )
			: '';
		$post = $slug ? get_page_by_path( $slug, OBJECT, 'ezb_project' ) : null;

		if ( ! $post ) {
			status_header( 404 );
			return;
		}

		$GLOBALS['post'] = $post;
		setup_postdata( $post );
		$post_context_set = true;
		$template         = get_stylesheet_directory() . '/templates/single-ezb_project.html';
	} else {
		if ( ! isset( $routes[ $key ] ) ) {
			status_header( 404 );
			return;
		}

		$page_paths = array(
			'privacy-vs-daylight'               => 'advice/privacy-vs-daylight',
			'retractable-flyscreen-suitability' => 'advice/retractable-flyscreen-suitability',
			'when-motorisation-makes-sense'     => 'advice/when-motorisation-makes-sense',
		);
		$page_path  = isset( $page_paths[ $key ] ) ? $page_paths[ $key ] : $key;
		$page       = get_page_by_path( $page_path, OBJECT, 'page' );

		if ( $page ) {
			$GLOBALS['post'] = $page;
			setup_postdata( $page );
			$post_context_set = true;
		}

		$template = get_stylesheet_directory() . '/templates/' . $routes[ $key ];
	}
	if ( ! is_readable( $template ) ) {
		status_header( 500 );
		wp_die( esc_html__( 'Prototype template is unavailable.', 'ezb-core' ) );
	}

	status_header( 200 );
	nocache_headers();
	header( 'Content-Type: text/html; charset=' . get_bloginfo( 'charset' ) );

	$markup   = file_get_contents( $template );
	$rendered = do_blocks( $markup );
	$rendered = do_shortcode( $rendered );
	$rendered = ezb_rewrite_dev_prototype_html( $rendered );

	ob_start();
	wp_head();
	$head_assets = ob_get_clean();

	ob_start();
	wp_footer();
	$footer_assets = ob_get_clean();

	echo '<!doctype html><html ' . get_language_attributes() . '><head>'; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped
	echo '<meta charset="' . esc_attr( get_bloginfo( 'charset' ) ) . '">';
	echo '<meta name="viewport" content="width=device-width, initial-scale=1">';
	echo $head_assets; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped
	echo '</head><body class="' . esc_attr( implode( ' ', get_body_class() ) ) . '">';
	echo $rendered; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped
	echo $footer_assets; // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped
	echo '</body></html>';

	if ( $post_context_set ) {
		wp_reset_postdata();
	}

	exit;
}
add_action( 'template_redirect', 'ezb_render_dev_prototype_route', 0 );


/**
 * Development media-slot candidates.
 *
 * Slots map to genuine EZ source filenames identified during the Drive media
 * inventory. They are development candidates only until Owner/publication
 * approval. When an attachment with the matching basename exists, the slot
 * renders the image; otherwise it renders a visible prototype placeholder.
 */
function ezb_media_slot_candidates() {
	return array(
		'home-hero' => array(
			'page_slug' => 'home',
			'filename'  => 'PXL_20231017_045427584~2.jpg',
			'label'    => 'Homepage hero — real EZ project media',
			'alt'      => 'EZ Blinds & Shutters installation in a bright double-height living area',
		),
		'roller-hero' => array(
			'page_slug' => 'roller-blinds',
			'filename'  => 'IMAG3884~2.jpg',
			'label'    => 'Roller Blinds — real EZ project media',
			'alt'      => 'Roller blinds installed across apartment glazing',
		),
		'shutters-hero' => array(
			'page_slug' => 'plantation-shutters',
			'filename'  => 'IMG_4689.jpg',
			'label'    => 'Plantation Shutters — real EZ project media',
			'alt'      => 'Plantation shutters installed in a bright living room',
		),
		'rfs-hero' => array(
			'page_slug' => 'retractable-flyscreens',
			'filename'  => 'EZ blinds and shutters Retractable Flyscreen S 01.jpg',
			'label'    => 'Retractable Flyscreens — real EZ project media',
			'alt'      => 'Retractable flyscreen installed across a large glazed opening',
		),
		'sheer-hero' => array(
			'page_slug' => 'sheer-curtains',
			'filename'  => 'PXL_20231017_045427584~2.jpg',
			'label'     => 'Sheer Curtains — real EZ installation media',
			'alt'       => 'Full-height sheer curtains in a bright double-height living area',
		),
	);
}

function ezb_featured_image_for_page_slug( $slug ) {
	$page = get_page_by_path( sanitize_title( $slug ), OBJECT, 'page' );
	if ( ! $page ) {
		return 0;
	}

	$thumbnail_id = get_post_thumbnail_id( $page->ID );
	return $thumbnail_id ? (int) $thumbnail_id : 0;
}

function ezb_find_attachment_by_basename( $basename ) {
	global $wpdb;
	static $found_in_request = array();

	$basename = wp_basename( $basename );
	if ( isset( $found_in_request[ $basename ] ) ) {
		return $found_in_request[ $basename ];
	}
	$stem       = pathinfo( $basename, PATHINFO_FILENAME );
	$extension  = strtolower( pathinfo( $basename, PATHINFO_EXTENSION ) );
	$candidates = array( $basename );

	if ( '' !== $stem ) {
		// Use the optimized WebP before an original JPG/PNG if both exist.
		// Exact MP4 filenames must keep their original search priority.
		if ( in_array( $extension, array( 'jpg', 'jpeg', 'png' ), true ) ) {
			array_unshift( $candidates, $stem . '.webp' );
		} else {
			$candidates[] = $stem . '.webp';
		}
		$candidates[] = $stem . '.jpg';
		$candidates[] = $stem . '.jpeg';
		$candidates[] = $stem . '.png';
	}

	$normalised_candidates = array();
	foreach ( $candidates as $candidate ) {
		$normalised_candidates[] = $candidate;
		$normalised_candidates[] = sanitize_file_name( $candidate );
	}

	foreach ( array_unique( $normalised_candidates ) as $candidate ) {
		$like = '%' . $wpdb->esc_like( '/' . $candidate );
		$id   = $wpdb->get_var(
			$wpdb->prepare(
				"SELECT post_id FROM {$wpdb->postmeta}
				WHERE meta_key = '_wp_attached_file'
				AND meta_value LIKE %s
				ORDER BY post_id DESC
				LIMIT 1",
				$like
			)
		);

		if ( $id ) {
			// Product heroes and gallery cards can request the same asset.
			// Avoid repeating the expensive suffix-LIKE lookup on this request.
			$found_in_request[ $basename ] = (int) $id;
			return $found_in_request[ $basename ];
		}
	}

	// Keep misses uncached so a new import remains discoverable in this request.
	return 0;
}

/**
 * Development-only genuine EZ motion slot.
 *
 * The current source video contains identifiable people and has not yet passed
 * publication/privacy approval. It may be previewed in development after the
 * web derivative is imported, but it must not render in production yet.
 */
function ezb_retractable_video_candidate() {
	return array(
		'filename' => 'EZ_Retractable_Flyscreen_WEB_V1_720x1280_muted.mp4',
		'poster'   => 'EZ_Retractable_Flyscreen_WEB_V1_poster.jpg',
	);
}

add_shortcode(
	'ezb_retractable_video',
	function () {
		if ( 'development' !== wp_get_environment_type() ) {
			return '';
		}

		$candidate = ezb_retractable_video_candidate();
		$video_id  = ezb_find_attachment_by_basename( $candidate['filename'] );

		if ( ! $video_id || 'video/mp4' !== get_post_mime_type( $video_id ) ) {
			return '';
		}

		$video_url = wp_get_attachment_url( $video_id );
		if ( ! $video_url ) {
			return '';
		}

		$poster_id  = ezb_find_attachment_by_basename( $candidate['poster'] );
		$poster_url = $poster_id ? wp_get_attachment_url( $poster_id ) : '';

		return sprintf(
			'<section class="ezb-section ezb-shell ezb-video-feature"><div class="ezb-video-feature__inner"><div class="ezb-video-feature__copy"><p class="ezb-eyebrow">%1$s</p><h2>%2$s</h2><p>%3$s</p></div><div class="ezb-video-feature__frame"><video data-ezb-autoplay-video muted loop playsinline controls preload="metadata"%4$s><source src="%5$s" type="video/mp4"></video></div></div></section>',
			esc_html__( 'Real EZ installation motion', 'ezb-core' ),
			esc_html__( 'See a retractable flyscreen in motion', 'ezb-core' ),
			esc_html__( 'Development preview only. Publication and privacy approval are still required before launch.', 'ezb-core' ),
			$poster_url ? ' poster="' . esc_url( $poster_url ) . '"' : '',
			esc_url( $video_url )
		);
	}
);

/**
 * Development Project media groupings grounded in the Media Asset Registry.
 *
 * Grouping is visual/provisional only. It does not authorise publication of
 * customer, suburb, date, dimensions or product-specification claims.
 */
function ezb_project_media_groups() {
	return array(
		'retractable-flyscreen-large-opening' => array(
			'label'  => 'Retractable Flyscreen — verified visual grouping candidate',
			'images' => array(
				array(
					'filename' => 'EZ blinds and shutters Retractable Flyscreen S 01.jpg',
					'alt'      => 'Retractable flyscreen across a large indoor-outdoor opening beside a dining area',
				),
				array(
					'filename' => 'EZ blinds and shutters Retractable Flyscreen S 02.jpg',
					'alt'      => 'Second interior view of the same retractable flyscreen opening',
				),
				array(
					'filename' => 'EZ blinds and shutters Retractable Flyscreen S 03.jpg',
					'alt'      => 'Closer view of the same retractable flyscreen mesh and opening',
				),
			),
		),
		'retractable-flyscreen-indoor-outdoor-opening' => array(
			'label'  => 'Retractable Flyscreen — indoor / outdoor visual grouping candidate',
			'images' => array(
				array(
					'filename' => 'IMAG3550.jpg',
					'alt'      => 'Retractable flyscreen viewed from a living area toward an outdoor seating area',
				),
				array(
					'filename' => 'IMAG3554.jpg',
					'alt'      => 'Another view of the same retractable flyscreen indoor-outdoor opening',
				),
				array(
					'filename' => 'IMAG3558.jpg',
					'alt'      => 'Outdoor-side view of the same retractable flyscreen opening',
				),
			),
		),
	);
}

/**
 * Product-level real-installation galleries.
 *
 * These images may come from different homes. They are product examples only
 * and must not be presented as one Project or used to infer customer/location facts.
 */
function ezb_product_media_galleries() {
	return array(
		'roller-blinds' => array(
			'label'  => 'Roller Blinds real installation examples',
			'images' => array(
				array( 'filename' => 'EZ blinds and shutters Roller blinds 01.jpg', 'alt' => 'Light-coloured roller blinds beside a bright dining area' ),
				array( 'filename' => 'EZ blinds and shutters Roller blinds 02.jpg', 'alt' => 'Roller blinds installed across apartment living and kitchen glazing' ),
				array( 'filename' => 'EZ blinds and shutters Roller blinds 03.jpg', 'alt' => 'Roller blinds fitted across a living-room window and door opening' ),
				array( 'filename' => 'EZ blinds and shutters Roller blinds 06.jpg', 'alt' => 'Roller blinds installed across bedroom windows' ),
				array( 'filename' => 'EZ blinds and shutters Roller blinds 07.jpg', 'alt' => 'Roller blind fitted above a glazed door in a bright living area' ),
				array( 'filename' => 'EZ blinds and shutters Roller blinds 08.jpg', 'alt' => 'Roller blinds installed across a wide sliding-door opening' ),
			),
		),
		'plantation-shutters' => array(
			'label'  => 'Plantation Shutters real installation examples',
			'images' => array(
				array( 'filename' => 'EZ blinds and shutters Plantation shutters 01.jpg', 'alt' => 'Plantation shutters fitted across a bright living-room window' ),
				array( 'filename' => 'EZ blinds and shutters Plantation shutters  11.jpg', 'alt' => 'Plantation shutters fitted to multiple windows in a furnished room' ),
				array( 'filename' => 'EZ blinds and shutters Plantation shutters  14.jpg', 'alt' => 'Plantation shutters fitted to bedroom window and door openings' ),
				array( 'filename' => 'EZ blinds and shutters Plantation shutters  18.jpg', 'alt' => 'Plantation shutters fitted across bay-style living-room windows' ),
			),
		),
		'retractable-flyscreens' => array(
			'label'  => 'Retractable Flyscreens real installation examples',
			'images' => array(
				array( 'filename' => 'EZ blinds and shutters Retractable Flyscreen S 01.jpg', 'alt' => 'Retractable flyscreen across a large indoor-outdoor opening' ),
				array( 'filename' => 'EZ blinds and shutters Retractable Flyscreen S 04.jpg', 'alt' => 'Retractable flyscreen installed at a balcony opening behind curtains' ),
				array( 'filename' => 'IMAG3550.jpg', 'alt' => 'Retractable flyscreen viewed from a living area toward outdoor seating' ),
				array( 'filename' => 'IMAG3554.jpg', 'alt' => 'Close view of retractable flyscreen mesh across a glazed opening' ),
				array( 'filename' => 'IMAG3558.jpg', 'alt' => 'Outdoor-side view of a retractable flyscreen opening' ),
				array( 'filename' => 'IMAG4409.jpg', 'alt' => 'Retractable flyscreen across a wide deck opening' ),
				array( 'filename' => 'IMAG4430.jpg', 'alt' => 'Retractable flyscreen fitted to a timber-framed outdoor opening' ),
				array( 'filename' => 'IMAG4641 (2).jpg', 'alt' => 'Retractable flyscreen across a bright sliding-door opening' ),
				array( 'filename' => 'IMAG6334.jpg', 'alt' => 'Retractable flyscreen spanning a wide covered outdoor opening' ),
				array( 'filename' => 'IMAG6475.jpg', 'alt' => 'Retractable flyscreen fitted to a brick-walled deck opening' ),
			),
		),
	);
}

add_shortcode(
	'ezb_project_cards',
	function () {
		$projects = get_posts(
			array(
				'post_type'      => 'ezb_project',
				'post_status'    => 'publish',
				'posts_per_page' => -1,
				'orderby'        => 'date',
				'order'          => 'DESC',
			)
		);

		if ( ! $projects ) {
			return '<div class="ezb-media-placeholder"><p class="ezb-media-placeholder__kicker">PROJECTS</p><p>Published projects will appear here.</p></div>';
		}

		$display_titles = array(
			'retractable-flyscreen-large-opening'          => 'Retractable Flyscreen',
			'retractable-flyscreen-indoor-outdoor-opening' => 'Indoor / Outdoor Flyscreen',
			'prototype-roller-blinds-project'               => 'Roller Blinds',
			'prototype-sheer-curtains-project'              => 'Sheer Curtains',
		);
		$priority = array(
			'retractable-flyscreen-large-opening'          => 10,
			'retractable-flyscreen-indoor-outdoor-opening' => 20,
			'prototype-roller-blinds-project'               => 900,
			'prototype-sheer-curtains-project'              => 910,
		);

		$projects = array_values(
			array_filter(
				$projects,
				static function ( $project ) {
					return 'prototype-retractable-flyscreen-project' !== $project->post_name;
				}
			)
		);

		usort(
			$projects,
			static function ( $a, $b ) use ( $priority ) {
				$a_priority = isset( $priority[ $a->post_name ] ) ? $priority[ $a->post_name ] : 100;
				$b_priority = isset( $priority[ $b->post_name ] ) ? $priority[ $b->post_name ] : 100;

				if ( $a_priority === $b_priority ) {
					return strcasecmp( $a->post_title, $b->post_title );
				}

				return $a_priority <=> $b_priority;
			}
		);

		$groups = ezb_project_media_groups();
		$cards  = '';

		foreach ( $projects as $project ) {
			$slug             = $project->post_name;
			$display_title    = isset( $display_titles[ $slug ] ) ? $display_titles[ $slug ] : $project->post_title;
			$is_prototype     = 0 === strpos( $slug, 'prototype-' );
			$eyebrow          = $is_prototype ? __( 'Prototype project', 'ezb-core' ) : __( 'Project', 'ezb-core' );
			$summary          = trim( $project->post_excerpt );
			$attachment_id    = get_post_thumbnail_id( $project->ID );

			if ( '' === $summary ) {
				$summary = wp_trim_words( wp_strip_all_tags( strip_shortcodes( $project->post_content ) ), 22 );
			}

			if ( ! $attachment_id && isset( $groups[ $slug ]['images'][0]['filename'] ) ) {
				$attachment_id = ezb_find_attachment_by_basename( $groups[ $slug ]['images'][0]['filename'] );
			}

			if ( $attachment_id ) {
				$media = wp_get_attachment_image(
					$attachment_id,
					'large',
					false,
					array(
						'class'   => 'ezb-project-index-grid__image',
						'loading' => 'lazy',
					)
				);
			} else {
				$media = '<div class="ezb-card-media ezb-card-media--project"><span>' .
					esc_html( $is_prototype ? 'PROJECT PLACEHOLDER' : 'REAL EZ PROJECT MEDIA' ) .
					'</span></div>';
			}

			$cards .= '<article class="ezb-card">';
			$cards .= $media;
			$cards .= '<p class="ezb-eyebrow">' . esc_html( $eyebrow ) . '</p>';
			$cards .= '<h2><a href="' . esc_url( get_permalink( $project ) ) . '">' . esc_html( $display_title ) . '</a></h2>';
			$cards .= '<p>' . esc_html( $summary ) . '</p>';
			$cards .= '</article>';
		}

		return '<div class="ezb-project-index-grid ezb-cards">' . $cards . '</div>';
	}
);


add_shortcode(
	'ezb_project_gallery',
	function () {
		$post = get_post();
		if ( ! $post || 'ezb_project' !== $post->post_type ) {
			return '';
		}

		$groups             = ezb_project_media_groups();
		$featured_image_id = get_post_thumbnail_id( $post->ID );

		if ( ! isset( $groups[ $post->post_name ] ) ) {
			if ( $featured_image_id ) {
				return sprintf(
					'<section class="ezb-project-gallery-block" aria-label="%1$s"><div class="ezb-project-gallery ezb-project-gallery--1"><figure class="ezb-project-gallery__item">%2$s</figure></div></section>',
					esc_attr__( 'Project installation media', 'ezb-core' ),
					wp_get_attachment_image(
						$featured_image_id,
						'large',
						false,
						array(
							'class'   => 'ezb-project-gallery__image',
							'loading' => 'lazy',
						)
					)
				);
			}

			return '<div class="ezb-media-placeholder"><p class="ezb-media-placeholder__kicker">REAL EZ PROJECT MEDIA</p><p>Add a Featured Image or approved project media from the WordPress editor.</p></div>';
		}

		$group = $groups[ $post->post_name ];
		$items = '';

		foreach ( $group['images'] as $image ) {
			$attachment_id = ezb_find_attachment_by_basename( $image['filename'] );

			if ( $attachment_id ) {
				$items .= '<figure class="ezb-project-gallery__item">';
				$items .= wp_get_attachment_image(
					$attachment_id,
					'large',
					false,
					array(
						'class'   => 'ezb-project-gallery__image',
						'alt'     => $image['alt'],
						'loading' => 'lazy',
					)
				);
				$items .= '</figure>';
				continue;
			}

			$items .= '<div class="ezb-project-gallery__placeholder">';
			$items .= '<p class="ezb-media-placeholder__kicker">REAL EZ PROJECT MEDIA</p>';
			$items .= '<p>Approved web derivative pending WordPress Media Library import.</p>';
			$items .= '</div>';
		}

		$status = '';
		if ( 'development' === wp_get_environment_type() ) {
			$status = sprintf(
				'<p class="ezb-project-gallery__status">%s</p>',
				esc_html( $group['label'] . '. Visual grouping only; project facts remain unverified.' )
			);
		}

		$gallery_class = 'ezb-project-gallery ezb-project-gallery--' . count( $group['images'] );

		return sprintf(
			'<section class="ezb-project-gallery-block" aria-label="%1$s"><div class="%2$s">%3$s</div>%4$s</section>',
			esc_attr__( 'Project installation media', 'ezb-core' ),
			esc_attr( $gallery_class ),
			$items,
			$status
		);
	}
);

function ezb_product_gallery_fit_mode( $width, $height ) {
	$width  = (int) $width;
	$height = (int) $height;

	if ( $width <= 0 || $height <= 0 ) {
		return 'cover';
	}

	$ratio = $width / $height;

	return ( $ratio < 0.9 || $ratio > 2.0 ) ? 'contain' : 'cover';
}

function ezb_product_gallery_fit_class( $attachment_id ) {
	$metadata = wp_get_attachment_metadata( $attachment_id );
	$width    = isset( $metadata['width'] ) ? (int) $metadata['width'] : 0;
	$height   = isset( $metadata['height'] ) ? (int) $metadata['height'] : 0;

	return 'contain' === ezb_product_gallery_fit_mode( $width, $height )
		? ' ezb-product-gallery__image--contain'
		: '';
}


add_shortcode(
	'ezb_product_gallery',
	function ( $atts ) {
		$atts = shortcode_atts(
			array(
				'product' => '',
			),
			$atts,
			'ezb_product_gallery'
		);

		$product   = sanitize_title( $atts['product'] );
		$galleries = ezb_product_media_galleries();

		if ( ! isset( $galleries[ $product ] ) ) {
			return '';
		}

		$group = $galleries[ $product ];
		$items = '';
		$count = 0;

		foreach ( $group['images'] as $image ) {
			$attachment_id = ezb_find_attachment_by_basename( $image['filename'] );
			if ( ! $attachment_id ) {
				continue;
			}

			$items .= '<figure class="ezb-project-gallery__item">';
			$items .= wp_get_attachment_image(
				$attachment_id,
				'large',
				false,
				array(
					'class'   => 'ezb-product-gallery__image ezb-project-gallery__image' . ezb_product_gallery_fit_class( $attachment_id ),
					'alt'     => $image['alt'],
					'loading' => 'lazy',
				)
			);
			$items .= '</figure>';
			$count++;
		}

		if ( '' === $items ) {
			return '';
		}

		return sprintf(
			'<section class="ezb-section ezb-shell ezb-product-gallery-block" aria-label="%1$s"><div class="wp-block-group alignwide"><p class="ezb-eyebrow">%2$s</p><h2>%3$s</h2><div class="ezb-project-gallery ezb-project-gallery--%4$d">%5$s</div></div></section>',
			esc_attr( $group['label'] ),
			esc_html__( 'Real EZ installations', 'ezb-core' ),
			esc_html__( 'See the finish in real homes', 'ezb-core' ),
			$count,
			$items
		);
	}
);

add_shortcode(
	'ezb_media_slot',
	function ( $atts ) {
		$atts = shortcode_atts(
			array(
				'slot' => '',
			),
			$atts,
			'ezb_media_slot'
		);

		$slot       = sanitize_key( $atts['slot'] );
		$candidates = ezb_media_slot_candidates();

		if ( ! isset( $candidates[ $slot ] ) ) {
			return '';
		}

		$candidate         = $candidates[ $slot ];
		$featured_image_id = ! empty( $candidate['page_slug'] )
			? ezb_featured_image_for_page_slug( $candidate['page_slug'] )
			: 0;
		$attachment_id     = $featured_image_id;

		if ( ! $attachment_id ) {
			$attachment_id = ezb_find_attachment_by_basename( $candidate['filename'] );
		}

		if ( $attachment_id ) {
			// The fallback candidate alt must never describe a different
			// photograph when an Owner changes the page's Featured Image.
			$alt = $candidate['alt'];
			if ( $featured_image_id ) {
				$owner_alt = get_post_meta( $featured_image_id, '_wp_attachment_image_alt', true );
				$alt       = is_string( $owner_alt ) && '' !== trim( $owner_alt )
					? $owner_alt
					: __( 'Window furnishings photograph', 'ezb-core' );
			}
			return wp_get_attachment_image(
				$attachment_id,
				'large',
				false,
				array(
					'class'         => 'ezb-media-slot__image',
					'alt'           => $alt,
					'loading'       => 'eager',
					'fetchpriority' => 'high',
					'decoding'      => 'async',
				)
			);
		}

		return sprintf(
			'<div class="ezb-media-slot ezb-media-placeholder"><p class="ezb-media-placeholder__kicker">%1$s</p><p>%2$s</p></div>',
			esc_html__( 'REAL EZ PROJECT MEDIA', 'ezb-core' ),
			esc_html( $candidate['label'] )
		);
	}
);
