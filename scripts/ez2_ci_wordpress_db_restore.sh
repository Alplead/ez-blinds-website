#!/usr/bin/env bash
# Rehearse SQL restore of the synthetic release-install WordPress database into
# a SECOND disposable MariaDB database. Never touches LocalWP or production.
set -euo pipefail

if [[ "${GITHUB_ACTIONS:-}" != "true" || "${EZ2_CI_SQL_RESTORE:-}" != "YES_SYNTHETIC_RELEASE_STACK" ]]; then
  echo 'EZ2_CI_SQL_RESTORE_BLOCKED: explicit disposable GitHub CI opt-in required' >&2
  exit 2
fi

cd "$(dirname "${BASH_SOURCE[0]}")/.."
compose=(docker compose -f .github/release-install/docker-compose.yml)
source_db='wordpress'
restore_db='ez2_ci_restore_disposable'

# Password stays inside the disposable container environment; SQL is never logged.
db() {
  "${compose[@]}" exec -T release-db sh -c \
    'export MYSQL_PWD="$MARIADB_ROOT_PASSWORD"; exec mariadb -uroot --batch --skip-column-names "$@"' \
    sh "$@"
}
dump() {
  "${compose[@]}" exec -T release-db sh -c \
    'export MYSQL_PWD="$MARIADB_ROOT_PASSWORD"; exec mariadb-dump -uroot --single-transaction --skip-comments "$@"' \
    sh "$@"
}

"${compose[@]}" exec -T release-db sh -c \
  'test "$MARIADB_DATABASE" = wordpress && test "$MARIADB_USER" = wordpress && test "$MARIADB_ROOT_PASSWORD" = root' \
  || { echo 'EZ2_CI_SQL_RESTORE_BLOCKED: unexpected database fixture' >&2; exit 2; }

existing="$(db -e "SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='${restore_db}'")"
[[ "$existing" == 0 ]] || { echo 'EZ2_CI_SQL_RESTORE_BLOCKED: restore database already exists' >&2; exit 2; }

scratch="$(mktemp -d -t ez2-ci-sql-restore-XXXXXXXX)"
chmod 700 "$scratch"
created=0
cleanup() {
  if [[ "$created" == 1 ]]; then
    db -e "DROP DATABASE \`${restore_db}\`" >/dev/null || true
  fi
  rm -rf -- "$scratch"
}
trap cleanup EXIT

source_tables="$(db -e "SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA='${source_db}' AND TABLE_TYPE='BASE TABLE'")"
source_posts="$(db -e "SELECT COUNT(*) FROM \`${source_db}\`.wp_posts")"
source_pages="$(db -e "SELECT COUNT(*) FROM \`${source_db}\`.wp_posts WHERE post_type='page'")"
source_options="$(db -e "SELECT COUNT(*) FROM \`${source_db}\`.wp_options")"
source_home="$(db -e "SELECT option_value FROM \`${source_db}\`.wp_options WHERE option_name='home'")"
[[ "$source_tables" =~ ^[0-9]+$ && "$source_tables" -ge 10 \
   && "$source_posts" =~ ^[0-9]+$ && "$source_posts" -ge 1 \
   && "$source_pages" =~ ^[0-9]+$ && "$source_pages" -ge 1 \
   && "$source_options" =~ ^[0-9]+$ && "$source_options" -ge 10 \
   && "$source_home" == 'http://localhost:8081' ]] \
  || { echo 'EZ2_CI_SQL_RESTORE_BLOCKED: not the installed synthetic WordPress fixture' >&2; exit 2; }

# Keep the dump only in an auto-deleted local scratch directory, never an artifact.
# Fingerprint actual row values, not just table/row counts. A count-preserving
# mutation must fail the restore rehearsal. Ordered, data-only SQL is never logged.
# The source is fingerprinted before backup and again after restore.
data_fingerprint() {
  dump --no-create-info --skip-triggers --order-by-primary --skip-dump-date "$1" \
    | sha256sum | cut -d ' ' -f1
}
source_data_sha="$(data_fingerprint "$source_db")"

# Exercise the same four-component private rollback archive format used by
# EZ2 capture, but ONLY with synthetic release-stack data and public release ZIPs.
# This is not a live WordPress capture, LocalWP restore or deployment.
exact_head="$(git rev-parse HEAD)"
[[ "$exact_head" =~ ^[0-9a-f]{40}$ ]] \
  || { echo 'EZ2_CI_SQL_RESTORE_BLOCKED: exact Git HEAD required' >&2; exit 2; }
snapshot="$scratch/synthetic-snapshot"
mkdir -m 700 -p "$snapshot"/{uploads,plugins,theme}
dump "$source_db" > "$snapshot/database.sql"
test -s "$snapshot/database.sql"
printf 'EZ2 disposable synthetic upload fixture\\n' > "$snapshot/uploads/synthetic-ci.txt"
test -s .release/ezb-core.zip && test -s .release/ezb-theme.zip
cp .release/ezb-core.zip "$snapshot/plugins/ezb-core.zip"
cp .release/ezb-theme.zip "$snapshot/theme/ezb-theme.zip"
python3 scripts/ez2_backup_snapshot_pack.py "$snapshot" "$scratch/verified-backup" "$exact_head" > /dev/null
python3 scripts/ez2_backup_archive_guard.py "$scratch/verified-backup" "$exact_head" > /dev/null
python3 scripts/ez2_backup_scratch_replay.py "$scratch/verified-backup" "$exact_head" \
  | grep -Fq '"scratch_deleted": true'
backup_sql="$scratch/verified-backup/database.sql.gz"
gzip -t "$backup_sql"

db -e "CREATE DATABASE \`${restore_db}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci" >/dev/null
created=1
gzip -dc "$backup_sql" | db "$restore_db" >/dev/null

restored_tables="$(db -e "SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA='${restore_db}' AND TABLE_TYPE='BASE TABLE'")"
restored_posts="$(db -e "SELECT COUNT(*) FROM \`${restore_db}\`.wp_posts")"
restored_pages="$(db -e "SELECT COUNT(*) FROM \`${restore_db}\`.wp_posts WHERE post_type='page'")"
restored_options="$(db -e "SELECT COUNT(*) FROM \`${restore_db}\`.wp_options")"
restored_home="$(db -e "SELECT option_value FROM \`${restore_db}\`.wp_options WHERE option_name='home'")"
[[ "$restored_tables" == "$source_tables" && "$restored_posts" == "$source_posts" \
   && "$restored_pages" == "$source_pages" && "$restored_options" == "$source_options" \
   && "$restored_home" == "$source_home" ]] \
  || { echo 'EZ2_CI_SQL_RESTORE_FAIL: restored WordPress data differs' >&2; exit 1; }

restored_data_sha="$(data_fingerprint "$restore_db")"
[[ "$restored_data_sha" == "$source_data_sha" ]] \
  || { echo 'EZ2_CI_SQL_RESTORE_FAIL: restored WordPress row values differ' >&2; exit 1; }
[[ "$(data_fingerprint "$source_db")" == "$source_data_sha" ]] \
  || { echo 'EZ2_CI_SQL_RESTORE_FAIL: source WordPress row values changed' >&2; exit 1; }

[[ "$(db -e "SELECT COUNT(*) FROM \`${source_db}\`.wp_posts")" == "$source_posts" \
   && "$(db -e "SELECT COUNT(*) FROM \`${source_db}\`.wp_options")" == "$source_options" ]] \
  || { echo 'EZ2_CI_SQL_RESTORE_FAIL: source database changed' >&2; exit 1; }

# Inject a count-preserving fault ONLY into the disposable restore database.
# Destroy and rebuild that clone from the SAME verified backup, then compare.
# This is an actual recovery rehearsal, not merely a first-time import.
db -e "UPDATE \`${restore_db}\`.wp_options SET option_value='http://ez2-ci-fault.invalid' WHERE option_name='home'" >/dev/null
[[ "$(db -e "SELECT option_value FROM \`${restore_db}\`.wp_options WHERE option_name='home'")" == 'http://ez2-ci-fault.invalid' \
   && "$(data_fingerprint "$restore_db")" != "$source_data_sha" ]] \
  || { echo 'EZ2_CI_SQL_RESTORE_FAIL: fault injection did not alter clone' >&2; exit 1; }
[[ "$(data_fingerprint "$source_db")" == "$source_data_sha" ]] \
  || { echo 'EZ2_CI_SQL_RESTORE_FAIL: fault injection changed source' >&2; exit 1; }

db -e "DROP DATABASE \`${restore_db}\`" >/dev/null
db -e "CREATE DATABASE \`${restore_db}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci" >/dev/null
gzip -dc "$backup_sql" | db "$restore_db" >/dev/null
[[ "$(db -e "SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA='${restore_db}' AND TABLE_TYPE='BASE TABLE'")" == "$source_tables" \
   && "$(db -e "SELECT COUNT(*) FROM \`${restore_db}\`.wp_posts")" == "$source_posts" \
   && "$(db -e "SELECT COUNT(*) FROM \`${restore_db}\`.wp_posts WHERE post_type='page'")" == "$source_pages" \
   && "$(db -e "SELECT COUNT(*) FROM \`${restore_db}\`.wp_options")" == "$source_options" \
   && "$(db -e "SELECT option_value FROM \`${restore_db}\`.wp_options WHERE option_name='home'")" == "$source_home" \
   && "$(data_fingerprint "$restore_db")" == "$source_data_sha" ]] \
  || { echo 'EZ2_CI_SQL_RESTORE_FAIL: faulted clone not fully recovered' >&2; exit 1; }
[[ "$(data_fingerprint "$source_db")" == "$source_data_sha" ]] \
  || { echo 'EZ2_CI_SQL_RESTORE_FAIL: recovery changed source' >&2; exit 1; }

echo "EZ2_CI_WORDPRESS_DB_RESTORE_PASS tables=${restored_tables} posts=${restored_posts} pages=${restored_pages} fault_recovered=true packaged_backup_verified=true synthetic_ci_only=true localwp_touched=false"
