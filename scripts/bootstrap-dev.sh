#!/usr/bin/env bash
set -euo pipefail

COMPOSE="docker compose -f .devcontainer/docker-compose.yml"
WPCLI_TMP="/tmp/wp-cli.phar"

$COMPOSE up -d db wordpress

echo "Waiting for database/WordPress container..."
for i in {1..60}; do
  if $COMPOSE exec -T wordpress php -r 'exit(@fsockopen("db",3306) ? 0 : 1);' >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

curl -fsSL https://raw.githubusercontent.com/wp-cli/builds/gh-pages/phar/wp-cli.phar -o "$WPCLI_TMP"
$COMPOSE cp "$WPCLI_TMP" wordpress:/tmp/wp-cli.phar

WP="$COMPOSE exec -T wordpress php /tmp/wp-cli.phar --allow-root"

if ! $WP core is-installed >/dev/null 2>&1; then
  $WP core install     --url="http://localhost:8080"     --title="EZ Blinds & Shutters Development"     --admin_user="ezbdev"     --admin_password="dev-only-change-me"     --admin_email="dev@example.invalid"     --skip-email
fi

$WP theme activate ezb-theme
$WP plugin activate ezb-core

create_page() {
  local title="$1"
  local slug="$2"
  if ! $WP post list --post_type=page --name="$slug" --field=ID | grep -q .; then
    $WP post create --post_type=page --post_status=publish --post_title="$title" --post_name="$slug" >/dev/null
  fi
}

create_page "Home" "home"
create_page "Retractable Flyscreens" "retractable-flyscreens"
create_page "Contact" "contact"

HOME_ID="$($WP post list --post_type=page --name=home --field=ID | head -1)"
$WP option update show_on_front page
$WP option update page_on_front "$HOME_ID"
$WP rewrite structure '/%postname%/' --hard
$WP rewrite flush --hard

echo "Development WordPress is ready at http://localhost:8080"
