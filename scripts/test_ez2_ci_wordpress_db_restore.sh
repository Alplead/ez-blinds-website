#!/usr/bin/env bash
# Offline guard regressions: these must fail before any Docker invocation.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
bash -n ez2_ci_wordpress_db_restore.sh
for mode in unset ci_only optin_only; do
  case "$mode" in
    unset) env -u GITHUB_ACTIONS -u EZ2_CI_SQL_RESTORE bash ez2_ci_wordpress_db_restore.sh > /dev/null 2>&1 && exit 1 ;;
    ci_only) env -u EZ2_CI_SQL_RESTORE GITHUB_ACTIONS=true bash ez2_ci_wordpress_db_restore.sh > /dev/null 2>&1 && exit 1 ;;
    optin_only) env -u GITHUB_ACTIONS EZ2_CI_SQL_RESTORE=YES_SYNTHETIC_RELEASE_STACK bash ez2_ci_wordpress_db_restore.sh > /dev/null 2>&1 && exit 1 ;;
  esac
done
grep -Fq "restore_db='ez2_ci_restore_disposable'" ez2_ci_wordpress_db_restore.sh
grep -Fq "source_db='wordpress'" ez2_ci_wordpress_db_restore.sh
! grep -Eq 'DROP DATABASE.*source_db|DROP DATABASE.*wordpress' ez2_ci_wordpress_db_restore.sh
# Guard against silently reverting to count-only SQL restore comparisons.
grep -Fq 'dump --no-create-info --skip-triggers --order-by-primary --skip-dump-date' ez2_ci_wordpress_db_restore.sh
grep -Fq '[[ "$restored_data_sha" == "$source_data_sha" ]]' ez2_ci_wordpress_db_restore.sh
grep -Fq '[[ "$(data_fingerprint "$source_db")" == "$source_data_sha" ]]' ez2_ci_wordpress_db_restore.sh
# Require an actual disposable data fault, a second import and full recovery checks.
grep -Fq "EZ2_CI_SQL_RESTORE_FAIL: fault injection did not alter clone" ez2_ci_wordpress_db_restore.sh
grep -Fq "EZ2_CI_SQL_RESTORE_FAIL: faulted clone not fully recovered" ez2_ci_wordpress_db_restore.sh
[[ "$(grep -Fc 'gzip -dc "$scratch/wordpress.sql.gz" | db "$restore_db"' ez2_ci_wordpress_db_restore.sh)" == 2 ]]
grep -Fq 'fault_recovered=true synthetic_ci_only=true localwp_touched=false' ez2_ci_wordpress_db_restore.sh
printf '%s\n' 'EZ2_CI_WORDPRESS_DB_RESTORE_GUARD_PASS cases=13'
