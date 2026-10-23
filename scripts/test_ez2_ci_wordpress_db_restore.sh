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
printf '%s\n' 'EZ2_CI_WORDPRESS_DB_RESTORE_GUARD_PASS cases=6'
