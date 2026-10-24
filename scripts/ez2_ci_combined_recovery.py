#!/usr/bin/env python3
"""CI-only, two-domain rollback rehearsal using disposable MariaDB clone and scratch files.

Never accepts a site path, never modifies the installed WordPress database, and
never installs to LocalWP. This is a recovery rehearsal, not an EZ2 updater.
"""
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from ez2_ci_file_upgrade import COMPONENTS, snapshot, unpack
from ez2_release_set import run as verify_release

REPO = Path(__file__).resolve().parents[1]
CLONE = 'ez2_ci_combined_disposable'
COMPOSE = ('docker', 'compose', '-f', '.github/release-install/docker-compose.yml')


def gate(release, sha):
    if (os.getenv('GITHUB_ACTIONS') != 'true' or
            os.getenv('EZ2_CI_COMBINED_ROLLBACK') != 'YES_DISPOSABLE_STACK_ONLY'):
        raise ValueError('CI-only explicit combined rollback opt-in required')
    if not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError('Invalid exact SHA')
    if Path(release).resolve(strict=True) != (REPO / '.release').resolve(strict=True):
        raise ValueError('Only repository CI .release directory permitted')
    actual = subprocess.check_output(('git', 'rev-parse', 'HEAD'), cwd=REPO, text=True).strip()
    if actual != sha:
        raise ValueError('CI checkout is not exact requested SHA')
    verify_release('verify', Path(release), sha)


def sql(args, data=None):
    command = (*COMPOSE, 'exec', '-T', 'release-db', 'sh', '-c',
               'export MYSQL_PWD="$MARIADB_ROOT_PASSWORD"; exec mariadb -uroot --batch --skip-column-names "$@"',
               'sh', *args)
    return subprocess.run(command, cwd=REPO, input=data, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, check=True).stdout


def dump(db, data_only=False):
    flags = ('--no-create-info', '--skip-triggers', '--order-by-primary', '--skip-dump-date') if data_only else ()
    command = (*COMPOSE, 'exec', '-T', 'release-db', 'sh', '-c',
               'export MYSQL_PWD="$MARIADB_ROOT_PASSWORD"; exec mariadb-dump -uroot --single-transaction --skip-comments "$@"',
               'sh', *flags, db)
    return subprocess.run(command, cwd=REPO, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, check=True).stdout


def digest(db):
    return hashlib.sha256(dump(db, data_only=True)).hexdigest()


def inject_content_fault(db):
    """Change a synthetic page, option and metadata row in the SQL clone only.

    Not an Elementor importer, LocalWP updater or deployment path.
    """
    if db != CLONE:
        raise ValueError('Content fault may target only the disposable clone')
    marker = '_ez2_ci_transaction_fault'
    if sql(('-e', f"SELECT COUNT(*) FROM `{db}`.wp_postmeta WHERE meta_key='{marker}'")).strip() != b'0':
        raise ValueError('Content fault marker already exists')
    raw_id = sql(('-e', f"SELECT option_value FROM `{db}`.wp_options WHERE option_name='page_on_front'")).strip()
    if not re.fullmatch(rb'[1-9][0-9]*', raw_id):
        raise ValueError('Invalid synthetic front-page identifier')
    post_id = int(raw_id)
    title = sql(('-e', f"SELECT post_title FROM `{db}`.wp_posts WHERE ID={post_id} AND post_type='page'")).strip()
    if title != b'Home':
        raise ValueError('Unexpected synthetic front-page title')
    # Refuse to overwrite existing Elementor-shaped content even in synthetic CI.
    keys = "'_elementor_data','_elementor_edit_mode','_elementor_page_settings'"
    existing = sql(('-e', f"SELECT COUNT(*) FROM `{db}`.wp_postmeta WHERE post_id={post_id} AND meta_key IN ({keys})")).strip()
    if existing != b'0':
        raise ValueError('Synthetic home already has Elementor metadata')
    elementor_data = '[{"id":"ez2-ci-fault","elType":"container","elements":[]}]'
    elementor_settings = '{"ez2_ci_fault":true}'
    sql(('-e',
         f"UPDATE `{db}`.wp_options SET option_value='http://ez2-ci-combined-fault.invalid' WHERE option_name='home';"
         f"UPDATE `{db}`.wp_posts SET post_title='EZ2 synthetic content fault', post_content='EZ2 synthetic body fault' WHERE ID={post_id} AND post_type='page';"
         f"INSERT INTO `{db}`.wp_postmeta (post_id,meta_key,meta_value) VALUES "
         f"({post_id},'{marker}','synthetic candidate metadata'),"
         f"({post_id},'_elementor_data','{elementor_data}'),"
         f"({post_id},'_elementor_edit_mode','builder'),"
         f"({post_id},'_elementor_page_settings','{elementor_settings}');"))
    changed_title = sql(('-e', f"SELECT post_title FROM `{db}`.wp_posts WHERE ID={post_id}")).strip()
    changed_body = sql(('-e', f"SELECT post_content FROM `{db}`.wp_posts WHERE ID={post_id}")).strip()
    marker_count = sql(('-e', f"SELECT COUNT(*) FROM `{db}`.wp_postmeta WHERE post_id={post_id} AND meta_key IN ('{marker}',{keys})")).strip()
    if (changed_title != b'EZ2 synthetic content fault' or
            changed_body != b'EZ2 synthetic body fault' or marker_count != b'4'):
        raise ValueError('Synthetic Elementor-shaped content fault did not apply')
    return post_id


def scratch_upgrade(release, root):
    """Install real release ZIP bytes over synthetic old files; keep backups."""
    live, stage, backup = (root / name for name in ('live', 'stage', 'backup'))
    for folder in (live, stage, backup):
        folder.mkdir()
    for _, category, name, _ in COMPONENTS:
        old = live / category / name
        old.mkdir(parents=True)
        (old / 'owner-original.txt').write_bytes(b'synthetic owner fixture')
    upload = live / 'uploads' / '2026' / 'owner-media.txt'
    upload.parent.mkdir(parents=True)
    upload.write_bytes(b'synthetic upload preserved')
    before = snapshot(live)
    for archive, category, name, entry in COMPONENTS:
        (stage / category).mkdir(exist_ok=True)
        unpack(release / archive, stage / category, name)
        if not (stage / category / name / entry).is_file():
            raise ValueError('Release entrypoint missing')
    moved = []
    try:
        for _, category, name, _ in COMPONENTS:
            old, saved = live / category / name, backup / category / name
            saved.parent.mkdir(exist_ok=True)
            os.replace(old, saved)
            moved.append((old, saved))
            os.replace(stage / category / name, old)
        if snapshot(live) == before:
            raise ValueError('File upgrade did not change synthetic installed files')
        return live, before, moved
    except BaseException:
        restore_files(moved)
        raise


def restore_files(moved):
    # Validate every backup before removing any current files.
    if any(not saved.is_dir() for _, saved in moved):
        raise ValueError('Missing scratch file backup')
    for current, saved in reversed(moved):
        if current.exists():
            shutil.rmtree(current)
        os.replace(saved, current)


def main(release, sha):
    gate(release, sha)
    release = Path(release)
    fixture = sql(('-e', 'SELECT @@hostname'))
    if not fixture.strip():
        raise ValueError('Disposable MariaDB fixture unavailable')
    check = subprocess.run((*COMPOSE, 'exec', '-T', 'release-db', 'sh', '-c',
                            'test "$MARIADB_DATABASE" = wordpress && test "$MARIADB_USER" = wordpress && test "$MARIADB_ROOT_PASSWORD" = root'),
                           cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check.returncode:
        raise ValueError('Not the fixed disposable release DB fixture')
    if sql(('-e', f"SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='{CLONE}'")).strip() != b'0':
        raise ValueError('Scratch clone already exists; refuse to overwrite')
    if sql(('-e', 'SELECT option_value FROM wordpress.wp_options WHERE option_name="home"')).strip() != b'http://localhost:8081':
        raise ValueError('Not the synthetic release WordPress fixture')
    source_digest = digest('wordpress')
    original_sql = dump('wordpress')
    if not original_sql or len(original_sql) > 128 * 1024 * 1024:
        raise ValueError('Synthetic SQL backup empty or too large')
    created = False
    try:
        with tempfile.TemporaryDirectory(prefix='ez2-ci-combined-recovery-') as private:
            root = Path(private)
            sql(('-e', f'CREATE DATABASE \u0060{CLONE}\u0060 CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci'))
            created = True
            sql((CLONE,), data=original_sql)
            if digest(CLONE) != source_digest:
                raise ValueError('Initial clone differs from original WordPress database')
            live, before, moved = scratch_upgrade(release, root)
            try:
                # Both domains now differ at once. Inject a fault after the file
                # replacement AND the SQL mutation, then restore both domains.
                front_id = inject_content_fault(CLONE)
                if digest(CLONE) == source_digest:
                    raise ValueError('SQL fault was not applied to disposable clone')
            finally:
                restore_files(moved)
            sql(('-e', f'DROP DATABASE \u0060{CLONE}\u0060'))
            created = False
            sql(('-e', f'CREATE DATABASE \u0060{CLONE}\u0060 CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci'))
            created = True
            sql((CLONE,), data=original_sql)
            if snapshot(live) != before or digest(CLONE) != source_digest:
                raise ValueError('Combined file and database rollback did not restore both domains')
            restored_title = sql(('-e', f"SELECT post_title FROM `{CLONE}`.wp_posts WHERE ID={front_id}")).strip()
            restored_body = sql(('-e', f"SELECT post_content FROM `{CLONE}`.wp_posts WHERE ID={front_id}")).strip()
            remaining_marker = sql(('-e', f"SELECT COUNT(*) FROM `{CLONE}`.wp_postmeta WHERE post_id={front_id} AND meta_key IN ('_ez2_ci_transaction_fault','_elementor_data','_elementor_edit_mode','_elementor_page_settings')")).strip()
            if (restored_title != b'Home' or remaining_marker != b'0' or
                    restored_body == b'EZ2 synthetic body fault'):
                raise ValueError('Synthetic Elementor-shaped content rows were not restored')
            if digest('wordpress') != source_digest:
                raise ValueError('Installed synthetic WordPress source database changed')
            print('EZ2_CI_COMBINED_ROLLBACK_PASS file_components=2 sql_clone_recovered=true uploads_preserved=true content_rows_recovered=true elementor_meta_recovered=true source_db_untouched=true localwp_touched=false one_click_complete=false')
    finally:
        if created:
            sql(('-e', f'DROP DATABASE IF EXISTS \u0060{CLONE}\u0060'))


if __name__ == '__main__':
    try:
        if len(sys.argv) != 3:
            raise ValueError('Usage: ez2_ci_combined_recovery.py .release EXACT_SHA')
        main(sys.argv[1], sys.argv[2])
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        # Do not echo database SQL, passwords or subprocess stderr.
        print('EZ2_CI_COMBINED_ROLLBACK_FAIL: ' + type(exc).__name__, file=sys.stderr)
        sys.exit(1)
