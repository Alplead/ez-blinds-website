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

echo "Waiting for database..."
i=0
until wp db check --allow-root >/dev/null 2>&1; do
  i=$((i+1))
  [ "$i" -lt 90 ] || { echo "database did not become ready"; exit 1; }
  sleep 2
done

if ! wp core is-installed --allow-root >/dev/null 2>&1; then
  wp core install --allow-root \
    --url="http://localhost:8081" \
    --title="EZB Release Install Smoke" \
    --admin_user="ezbrelease" \
    --admin_password="release-smoke-only" \
    --admin_email="release@example.invalid" \
    --skip-email
fi

test -s /release/ezb-theme.zip
test -s /release/ezb-core.zip
test -s /release/SHA256SUMS

cd /release
sha256sum -c SHA256SUMS
cd /var/www/html

wp theme install /release/ezb-theme.zip --activate --force --allow-root
wp plugin install /release/ezb-core.zip --activate --force --allow-root

HOME_ID="$(wp post create --allow-root \
  --post_type=page \
  --post_status=publish \
  --post_title='Home' \
  --post_name='home' \
  --post_content='<p>Release install smoke homepage.</p>' \
  --porcelain)"

wp option update show_on_front page --allow-root >/dev/null
wp option update page_on_front "$HOME_ID" --allow-root >/dev/null
wp option update blog_public 0 --allow-root >/dev/null
wp option update permalink_structure '/%postname%/' --allow-root >/dev/null
wp rewrite flush --hard --allow-root >/dev/null

ACTIVE_THEME="$(wp option get stylesheet --allow-root)"
echo "active_theme=$ACTIVE_THEME"
test "$ACTIVE_THEME" = "ezb-theme"

wp plugin is-active ezb-core --allow-root
echo "active_plugin=ezb-core"

ENV_TYPE="$(wp eval 'echo wp_get_environment_type();' --allow-root)"
echo "environment=$ENV_TYPE"
test "$ENV_TYPE" = "staging"

# Staging install must not auto-seed development-only acceptance/project fixtures.
FIXTURE_COUNT="$(wp post list --post_type=ezb_project --name=owner-editability-test --post_status=any --format=count --allow-root)"
echo "owner_editability_fixture_count=$FIXTURE_COUNT"
test "$FIXTURE_COUNT" = "0"

echo "EZB_RELEASE_INSTALL_PASS"
