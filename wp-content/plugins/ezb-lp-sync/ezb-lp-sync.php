<?php
/**
 * Plugin Name: EZB LocalWP Sync
 * Description: Private, one-click GitHub-to-LocalWP code update for EZ BNS New Dev only.
 * Version: 0.1.0
 * Requires PHP: 8.2
 * Text Domain: ezb-local-sync
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

const EZB_LP_REPO_API = 'https://api.github.com/repos/Alplead/ez-blinds-website';
const EZB_LP_EXPECTED_HOST = 'ez-bns-new-dev.local';
const EZB_LP_PR = 1;
const EZB_LP_BRANCH = 'feature/vertical-slice-v1';

/**
 * Do not allow this engineering tool to touch the trading website or old VM site.
 * Never use a hostname suffix match here: the host must match EXACTLY.
 */
function ezb_lp_local_guard() {
	$host = strtolower( (string) wp_parse_url( home_url( '/' ), PHP_URL_HOST ) );

	return ! is_multisite()
		&& EZB_LP_EXPECTED_HOST === $host
		&& ! in_array( wp_get_environment_type(), array( 'production', 'staging' ), true )
		&& defined( 'WP_CONTENT_DIR' )
		&& is_dir( WP_CONTENT_DIR . '/themes/ezb-theme' )
		&& is_dir( WP_CONTENT_DIR . '/plugins/ezb-core' );
}

function ezb_lp_api_get( $url ) {
	$response = wp_remote_get(
		$url,
		array(
			'timeout'     => 20,
			'redirection' => 2,
			'headers'     => array(
				'Accept'               => 'application/vnd.github+json',
				'X-GitHub-Api-Version' => '2022-11-28',
				'User-Agent'           => 'EZB-LocalWP-Sync/0.1',
			),
		)
	);
	if ( is_wp_error( $response ) ) {
		return $response;
	}
	if ( 200 !== wp_remote_retrieve_response_code( $response ) ) {
		return new WP_Error( 'ezb_github_http', 'GitHub API request did not succeed (HTTP ' . wp_remote_retrieve_response_code( $response ) . ').' );
	}
	$data = json_decode( wp_remote_retrieve_body( $response ), true );
	return is_array( $data ) ? $data : new WP_Error( 'ezb_github_json', 'GitHub returned an unexpected response.' );
}

/** Check PR identity and the three REQUIRED green workflows on one exact SHA. */
function ezb_lp_verified_head() {
	$pr = ezb_lp_api_get( EZB_LP_REPO_API . '/pulls/' . EZB_LP_PR );
	if ( is_wp_error( $pr ) ) {
		return $pr;
	}
	$sha = (string) ( $pr['head']['sha'] ?? '' );
	$head_repo = (string) ( $pr['head']['repo']['full_name'] ?? '' );
	if (
		! preg_match( '/^[a-f0-9]{40}$/', $sha )
		|| 'Alplead/ez-blinds-website' !== $head_repo
		|| EZB_LP_BRANCH !== ( $pr['head']['ref'] ?? '' )
		|| 'main' !== ( $pr['base']['ref'] ?? '' )
		|| 'open' !== ( $pr['state'] ?? '' )
		|| empty( $pr['draft'] )
		|| ! empty( $pr['merged_at'] )
	) {
		return new WP_Error( 'ezb_pr_identity', 'The protected EZB development PR no longer matches the expected source. Update refused.' );
	}
	$runs = ezb_lp_api_get( EZB_LP_REPO_API . '/actions/runs?head_sha=' . $sha . '&event=pull_request&per_page=100' );
	if ( is_wp_error( $runs ) ) {
		return $runs;
	}
	$required = array( 'Quality' => false, 'Runtime Smoke' => false, 'Release Install Smoke' => false );
	if ( empty( $runs['workflow_runs'] ) || ! is_array( $runs['workflow_runs'] ) ) {
		return new WP_Error( 'ezb_ci_missing', 'GitHub has no verified CI runs for the latest commit.' );
	}
	// A newer failure or queued run for a required workflow must block updates.
	$latest_by_name = array();
	foreach ( $runs['workflow_runs'] as $run ) {
		$name = (string) ( $run['name'] ?? '' );
		if ( ! array_key_exists( $name, $required ) || $sha !== ( $run['head_sha'] ?? '' ) ) {
			continue;
		}
		$id = (int) ( $run['id'] ?? 0 );
		if ( ! isset( $latest_by_name[ $name ] ) || $id > (int) $latest_by_name[ $name ]['id'] ) {
			$latest_by_name[ $name ] = $run;
		}
	}
	foreach ( $required as $name => $_ ) {
		$run = $latest_by_name[ $name ] ?? null;
		if ( ! $run || 'completed' !== ( $run['status'] ?? '' ) || 'success' !== ( $run['conclusion'] ?? '' ) ) {
			return new WP_Error( 'ezb_ci_not_green', $name . ' is missing, failed or still running. No files were changed.' );
		}
	}
	return $sha;
}

function ezb_lp_delete_tree( $path ) {
	if ( is_link( $path ) || is_file( $path ) ) {
		return @unlink( $path );
	}
	if ( ! is_dir( $path ) ) {
		return true;
	}
	foreach ( new DirectoryIterator( $path ) as $item ) {
		if ( $item->isDot() ) {
			continue;
		}
		if ( ! ezb_lp_delete_tree( $item->getPathname() ) ) {
			return false;
		}
	}
	return @rmdir( $path );
}

function ezb_lp_copy_tree( $source, $destination ) {
	if ( ! is_dir( $source ) || is_link( $source ) || file_exists( $destination ) || ! wp_mkdir_p( $destination ) ) {
		throw new RuntimeException( 'Cannot create a clean destination directory.' );
	}
	foreach ( new DirectoryIterator( $source ) as $item ) {
		if ( $item->isDot() ) {
			continue;
		}
		if ( $item->isLink() ) {
			throw new RuntimeException( 'A symbolic link in the downloaded source is forbidden.' );
		}
		$target = $destination . '/' . $item->getFilename();
		if ( $item->isDir() ) {
			ezb_lp_copy_tree( $item->getPathname(), $target );
		} elseif ( $item->isFile() && ! copy( $item->getPathname(), $target ) ) {
			throw new RuntimeException( 'Cannot copy a source file.' );
		}
	}
}

/**
 * A rollback-ready swap of ONLY EZ theme + core directories.
 * No DB, uploads, wp-config.php, WordPress core or old site files are changed.
 */
function ezb_lp_install_verified_sha( $sha ) {
	if ( ! ezb_lp_local_guard() ) {
		return new WP_Error( 'ezb_wrong_site', 'Wrong site or site environment. This tool works only on EZ BNS New Dev.' );
	}
	require_once ABSPATH . 'wp-admin/includes/file.php';
	$working = dirname( untrailingslashit( ABSPATH ) ) . '/.ezb-lp-sync-work';
	$backup_root = dirname( untrailingslashit( ABSPATH ) ) . '/ezb-lp-sync-backups';
	if ( ! wp_mkdir_p( $working ) || ! wp_mkdir_p( $backup_root ) ) {
		return new WP_Error( 'ezb_fs', 'Unable to create a private work/backup directory outside the website document root.' );
	}
	$tmp = $working . '/job-' . wp_generate_password( 14, false, false );
	$archive = null;
	$stages = array();
	$installed = array();
	$backups = array();
	$successful = false;
	$backup_dir = $backup_root . '/' . gmdate( 'Ymd-His' ) . '-' . substr( $sha, 0, 12 ) . '-' . wp_generate_password( 6, false, false );

	try {
		if ( ! wp_mkdir_p( $tmp ) || ! wp_mkdir_p( $backup_dir ) ) {
			throw new RuntimeException( 'Cannot initialise a backup/work directory.' );
		}
		$url = 'https://codeload.github.com/Alplead/ez-blinds-website/zip/' . $sha;
		$archive = download_url( $url, 120 );
		if ( is_wp_error( $archive ) ) {
			throw new RuntimeException( 'GitHub source download failed: ' . $archive->get_error_message() );
		}
		if ( ! WP_Filesystem() ) {
			throw new RuntimeException( 'WordPress filesystem is not writable.' );
		}
		$unzip = unzip_file( $archive, $tmp );
		if ( is_wp_error( $unzip ) ) {
			throw new RuntimeException( 'Downloaded source ZIP could not be extracted: ' . $unzip->get_error_message() );
		}
		$matches = glob( $tmp . '/ez-blinds-website-*', GLOB_ONLYDIR );
		if ( ! is_array( $matches ) || 1 !== count( $matches ) ) {
			throw new RuntimeException( 'GitHub source ZIP has an unexpected directory structure.' );
		}
		$root = $matches[0];
		$items = array(
			'theme'  => array(
				'source' => $root . '/wp-content/themes/ezb-theme',
				'target' => WP_CONTENT_DIR . '/themes/ezb-theme',
				'check'  => 'style.css',
			),
			'plugin' => array(
				'source' => $root . '/wp-content/plugins/ezb-core',
				'target' => WP_CONTENT_DIR . '/plugins/ezb-core',
				'check'  => 'ezb-core.php',
			),
		);
		foreach ( $items as $key => $item ) {
			if ( ! is_file( $item['source'] . '/' . $item['check'] ) || ! is_dir( $item['target'] ) ) {
				throw new RuntimeException( 'Expected EZB code files or installed directories were missing.' );
			}
			$stage = dirname( $item['target'] ) . '/.ezb-lp-' . $key . '-pending-' . substr( $sha, 0, 12 );
			if ( file_exists( $stage ) ) {
				throw new RuntimeException( 'A prior unfinished update exists. Refusing to overwrite it.' );
			}
			$stages[ $key ] = $stage;
			ezb_lp_copy_tree( $item['source'], $stage );
		}
		// Copy all source files first, then swap directories; preserve previous
		// installed directories privately in app/ezb-lp-sync-backups.
		foreach ( $items as $key => $item ) {
			$backup = $backup_dir . '/' . basename( $item['target'] );
			if ( ! @rename( $item['target'], $backup ) ) {
				throw new RuntimeException( 'Cannot move the existing ' . $key . ' into the rollback backup.' );
			}
			$backups[ $key ] = $backup;
			if ( ! @rename( $stages[ $key ], $item['target'] ) ) {
				throw new RuntimeException( 'Cannot activate the new ' . $key . ' directory.' );
			}
			$installed[ $key ] = true;
		}
		update_option( 'ezb_lp_sync_sha', $sha, false );
		update_option( 'ezb_lp_sync_last_backup', $backup_dir, false );
		$successful = true;
	} catch ( Throwable $e ) {
		// Restore BOTH installed items on partial failure, including a failed
		// rename after the old directory was moved into the backup.
		foreach ( array_reverse( array( 'theme', 'plugin' ) ) as $key ) {
			$target = ( 'theme' === $key ? WP_CONTENT_DIR . '/themes/ezb-theme' : WP_CONTENT_DIR . '/plugins/ezb-core' );
			if ( isset( $backups[ $key ] ) && is_dir( $backups[ $key ] ) ) {
				if ( is_dir( $target ) ) {
					ezb_lp_delete_tree( $target );
				}
				@rename( $backups[ $key ], $target );
			}
		}
		$error = new WP_Error( 'ezb_sync_failed', 'Update stopped; previous code restored where possible. Reason: ' . $e->getMessage() );
	} finally {
		foreach ( $stages as $stage ) {
			if ( is_dir( $stage ) ) {
				ezb_lp_delete_tree( $stage );
			}
		}
		if ( $archive && is_string( $archive ) && is_file( $archive ) ) {
			@unlink( $archive );
		}
		if ( is_dir( $tmp ) ) {
			ezb_lp_delete_tree( $tmp );
		}
	}
	return $successful ? true : $error;
}

function ezb_lp_initialise_pages() {
	if ( ! ezb_lp_local_guard() ) {
		return new WP_Error( 'ezb_wrong_site', 'Only the dedicated EZ BNS New Dev site may be initialised.' );
	}
	$pages = array(
		'home' => 'Home',
		'products' => 'Products',
		'roller-blinds' => 'Roller Blinds',
		'sheer-curtains' => 'Sheer Curtains',
		'plantation-shutters' => 'Plantation Shutters',
		'retractable-flyscreens' => 'Retractable Flyscreens',
		'motorised-blinds' => 'Motorised Blinds',
		'projects' => 'Projects',
		'advice' => 'Advice',
		'blog' => 'Blog',
		'service-areas' => 'Service Areas',
		'about' => 'About',
		'contact' => 'Contact',
	);
	$created = 0;
	foreach ( $pages as $slug => $title ) {
		if ( get_page_by_path( $slug, OBJECT, 'page' ) ) {
			continue;
		}
		$result = wp_insert_post(
			array(
				'post_type' => 'page', 'post_status' => 'publish',
				'post_title' => $title, 'post_name' => $slug,
				'post_content' => '',
			),
			true
		);
		if ( is_wp_error( $result ) ) {
			return new WP_Error( 'ezb_page_create', 'Unable to create ' . $title . ': ' . $result->get_error_message() );
		}
		$created++;
	}
	$home = get_page_by_path( 'home', OBJECT, 'page' );
	if ( ! $home ) {
		return new WP_Error( 'ezb_home_missing', 'Cannot locate the new Home page.' );
	}
	update_option( 'show_on_front', 'page' );
	update_option( 'page_on_front', (int) $home->ID );
	update_option( 'blog_public', 0 ); // Search engines must not index a local work-in-progress.
	global $wp_rewrite;
	$wp_rewrite->set_permalink_structure( '/%postname%/' );
	$wp_rewrite->flush_rules( false );
	return $created;
}

add_action( 'admin_menu', function () {
	add_management_page( 'EZB LocalWP Sync', 'EZB Local Sync', 'manage_options', 'ezb-local-sync', 'ezb_lp_sync_admin' );
} );

function ezb_lp_sync_admin() {
	if ( ! current_user_can( 'manage_options' ) ) {
		wp_die( esc_html__( 'You do not have permission.' ) );
	}
	$allowed = ezb_lp_local_guard();
	$notice = '';
	$ok = false;
	if ( 'POST' === $_SERVER['REQUEST_METHOD'] && isset( $_POST['ezb_lp_action'] ) ) {
		check_admin_referer( 'ezb_lp_sync_action', 'ezb_lp_nonce' );
		if ( ! $allowed ) {
			$notice = 'Safety guard: this is not the dedicated EZ BNS New Dev site. No changes made.';
		} elseif ( 'setup' === $_POST['ezb_lp_action'] ) {
			$result = ezb_lp_initialise_pages();
			$ok = ! is_wp_error( $result );
			$notice = $ok ? 'EZB new-site pages are initialised; ' . $result . ' missing pages created. Old content was preserved.' : $result->get_error_message();
		} elseif ( 'check' === $_POST['ezb_lp_action'] || 'update' === $_POST['ezb_lp_action'] ) {
			$sha = ezb_lp_verified_head();
			if ( is_wp_error( $sha ) ) {
				$notice = $sha->get_error_message();
			} elseif ( 'check' === $_POST['ezb_lp_action'] ) {
				$ok = true;
				$notice = 'GitHub three-workflow PASS. Latest approved commit: ' . $sha . '. Installed: ' . (string) get_option( 'ezb_lp_sync_sha', 'Not tracked yet' ) . '.';
			} elseif ( $sha === get_option( 'ezb_lp_sync_sha' ) ) {
				$ok = true;
				$notice = 'Already current. No files changed: ' . $sha;
			} else {
				$result = ezb_lp_install_verified_sha( $sha );
				$ok = ! is_wp_error( $result );
				$notice = $ok ? 'EZB theme and core updated to ' . $sha . '. Previous files backed up outside app/public. Refresh the site.' : $result->get_error_message();
			}
		}
	}
	?>
	<div class="wrap">
		<h1>EZ BNS — LocalWP Update Centre</h1>
		<p><strong>Only for:</strong> <?php echo esc_html( EZB_LP_EXPECTED_HOST ); ?></p>
		<?php if ( $notice ) : ?>
			<div class="<?php echo $ok ? 'notice notice-success' : 'notice notice-error'; ?>"><p><?php echo esc_html( $notice ); ?></p></div>
		<?php endif; ?>
		<?php if ( ! $allowed ) : ?>
			<div class="notice notice-error"><p>Safety lock: the website hostname/environment or installed EZB directories do not match. No updates are permitted.</p></div>
		<?php else : ?>
			<p>Source: <code>Alplead/ez-blinds-website</code> / Draft PR #1 / <code>feature/vertical-slice-v1</code>.</p>
			<p>The exact GitHub commit must pass <strong>Quality, Runtime Smoke and Release Install Smoke</strong> before updating. Changes affect only EZB Theme and EZB Core; never content, uploads, credentials or database.</p>
			<p>Last installed via this tool: <code><?php echo esc_html( (string) get_option( 'ezb_lp_sync_sha', 'Not tracked yet' ) ); ?></code></p>
			<?php foreach ( array( 'setup' => '1. Initialise Home and product pages (once)', 'check' => '2. Check GitHub tests and latest version', 'update' => '3. Backup and install latest TEST-PASS version' ) as $action => $label ) : ?>
				<form method="post" style="margin: 1em 0;">
					<?php wp_nonce_field( 'ezb_lp_sync_action', 'ezb_lp_nonce' ); ?>
					<input type="hidden" name="ezb_lp_action" value="<?php echo esc_attr( $action ); ?>">
					<?php submit_button( esc_html( $label ), $action === 'update' ? 'primary' : 'secondary', 'submit', false ); ?>
				</form>
			<?php endforeach; ?>
			<p><strong>Important:</strong> This is a manually triggered sync, not an automatic push into your home VM. Do not click update while editing theme files. WordPress content and the 25 photos require separate import/checks.</p>
			<p><a href="<?php echo esc_url( home_url( '/' ) ); ?>">Open new-site Home</a> | <a href="<?php echo esc_url( home_url( '/products/' ) ); ?>">Open Products</a></p>
		<?php endif; ?>
	</div>
	<?php
}
