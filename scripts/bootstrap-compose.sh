#!/bin/sh
set -eu

cd /var/www/html

echo "Waiting for wp-config.php..."
i=0
until [ -f wp-config.php ]; do
  i=$((i+1))
  [ "$i" -lt 90 ] || { echo "wp-config.php was not created"; exit 1; }
  sleep 2
done

repair_upload_permissions() {
  mkdir -p wp-content/uploads
  current_subdir="$(date +%Y/%m)"
  mkdir -p "wp-content/uploads/$current_subdir"
  chown -R 33:33 wp-content/uploads
  find wp-content/uploads -type d -exec chmod 775 {} +
  find wp-content/uploads -type f -exec chmod 664 {} +
}

repair_upload_permissions

echo "Waiting for database..."
i=0
until wp db check --allow-root >/dev/null 2>&1; do
  i=$((i+1))
  [ "$i" -lt 90 ] || { echo "database did not become ready"; exit 1; }
  sleep 2
done

if ! wp core is-installed --allow-root >/dev/null 2>&1; then
  wp core install --allow-root     --url="http://localhost:8080"     --title="EZ Blinds & Shutters"     --admin_user="ezbdev"     --admin_password="dev-only-change-me"     --admin_email="dev@example.invalid"     --skip-email
fi

CURRENT_CORE_VERSION="$(wp core version --allow-root)"
if [ "$CURRENT_CORE_VERSION" != "7.1.3" ]; then
  wp core update --version=7.1.3 --force --allow-root
fi

wp theme activate ezb-theme --allow-root
wp plugin activate ezb-core --allow-root

ensure_page() {
  title="$1"
  slug="$2"
  if ! wp post list --allow-root --post_type=page --name="$slug" --field=ID | grep -q .; then
    wp post create --allow-root       --post_type=page       --post_status=publish       --post_title="$title"       --post_name="$slug" >/dev/null
  fi
}

ensure_page "Home" "home"
ensure_page "Retractable Flyscreens" "retractable-flyscreens"
ensure_page "Contact" "contact"
ensure_page "Roller Blinds" "roller-blinds"
ensure_page "Plantation Shutters" "plantation-shutters"
ensure_page "About" "about"

HOME_ID="$(wp post list --allow-root --post_type=page --name=home --field=ID | head -1)"
wp option update blogname 'EZ Blinds & Shutters' --allow-root >/dev/null
wp option update blogdescription 'Melbourne window furnishings' --allow-root >/dev/null
wp option update blog_public 0 --allow-root >/dev/null
wp option update timezone_string 'Australia/Melbourne' --allow-root >/dev/null
wp option update show_on_front page --allow-root >/dev/null
wp option update page_on_front "$HOME_ID" --allow-root >/dev/null
if ! wp post list --allow-root --post_type=ezb_project --name=retractable-flyscreen-large-opening --field=ID | grep -q .; then
  wp post create --allow-root \
    --post_type=ezb_project \
    --post_status=publish \
    --post_title="Retractable Flyscreen — Large Opening" \
    --post_name="retractable-flyscreen-large-opening" \
    --post_excerpt="Development case-study shell using verified EZ project media. Exact location and project details are intentionally omitted until confirmed." \
    --post_content="<p>This project entry is the first reusable case-study shell for the new EZ website.</p><h2>The opening</h2><p>A large glazed opening where airflow and visual connection to the outdoor area are important.</p><h2>The solution</h2><p>A retractable flyscreen configuration selected to screen the opening while keeping the system visually light. Exact product specifications will be added only after current supplier details are verified.</p><h2>Why this case study matters</h2><p>The final version will pair this structure with genuine EZ installation photography from the approved media library.</p>" >/dev/null
fi

wp rewrite structure '/%postname%/' --allow-root >/dev/null
wp rewrite flush --hard --allow-root >/dev/null
repair_upload_permissions

echo "EZB_BOOTSTRAP_OK"
