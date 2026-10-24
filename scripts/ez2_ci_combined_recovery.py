#!/usr/bin/env python3
"""CI-only, two-domain rollback rehearsal using disposable MariaDB clone and scratch files.

Never accepts a site path, never modifies the installed WordPress database, and
never installs to LocalWP. This is a recovery rehearsal, not an EZ2 updater.
"""
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from ez2_content_candidate_bundle import NAME, SLOTS, verify as verify_candidate
from ez2_elementor_export_check import check as check_elementor, unique, reject_nonfinite
from ez2_release_set import safe_read

from ez2_ci_file_upgrade import COMPONENTS, snapshot, unpack
from ez2_release_set import run as verify_release

REPO = Path(__file__).resolve().parents[1]
CLONE = 'ez2_ci_combined_disposable'
COMPOSE = ('docker', 'compose', '-f', '.github/release-install/docker-compose.yml')
SCRATCH_FAULT_PHASES = ('after_first_backup', 'after_first_install',
                        'after_second_backup', 'after_second_install')


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


def candidate_payload(release, sha):
    """Bind the SQL fault rehearsal to the real exact-head public review ZIP.

    Only the public symbolic Elementor candidate is used. This deliberately
    does not resolve private media or install anything in WordPress.
    """
    archive = safe_read(Path(release), 'ez2-content-candidate.zip')
    verify_candidate(sha, archive)
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        doc = json.loads(zipped.read(NAME), object_pairs_hook=unique,
                         parse_constant=reject_nonfinite)
    summary = check_elementor(doc)
    if doc['version'] != '4.3.4' or set(summary['media_slots']) != SLOTS:
        raise ValueError('Unexpected exact-head Elementor candidate')
    payload = json.dumps(doc['content'], ensure_ascii=False,
                         separators=(',', ':'), allow_nan=False).encode('utf-8')
    if not 0 < len(payload) <= 256000:
        raise ValueError('Unsafe candidate content size')
    return payload


def inject_content_fault(db, elementor_payload=None):
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
    if elementor_payload is not None and (not isinstance(elementor_payload, bytes)
                                          or not 0 < len(elementor_payload) <= 256000):
        raise ValueError('Invalid exact-head Elementor payload')
    elementor_data = (elementor_payload if elementor_payload is not None
                      else b'[{"id":"ez2-ci-fault","elType":"container","elements":[]}]')
    # Hex literals prevent quote/escape handling from altering real candidate JSON.
    encoded_data = '0x' + elementor_data.hex()
    elementor_settings = '{"ez2_ci_fault":true}'
    sql(('-e',
         f"UPDATE `{db}`.wp_options SET option_value='http://ez2-ci-combined-fault.invalid' WHERE option_name='home';"
         f"UPDATE `{db}`.wp_posts SET post_title='EZ2 synthetic content fault', post_content='EZ2 synthetic body fault' WHERE ID={post_id} AND post_type='page';"
         f"INSERT INTO `{db}`.wp_postmeta (post_id,meta_key,meta_value) VALUES "
         f"({post_id},'{marker}','synthetic candidate metadata'),"
         f"({post_id},'_elementor_data',{encoded_data}),"
         f"({post_id},'_elementor_edit_mode','builder'),"
         f"({post_id},'_elementor_page_settings','{elementor_settings}');"))
    changed_title = sql(('-e', f"SELECT post_title FROM `{db}`.wp_posts WHERE ID={post_id}")).strip()
    changed_body = sql(('-e', f"SELECT post_content FROM `{db}`.wp_posts WHERE ID={post_id}")).strip()
    marker_count = sql(('-e', f"SELECT COUNT(*) FROM `{db}`.wp_postmeta WHERE post_id={post_id} AND meta_key IN ('{marker}',{keys})")).strip()
    if (changed_title != b'EZ2 synthetic content fault' or
            changed_body != b'EZ2 synthetic body fault' or marker_count != b'4'):
        raise ValueError('Synthetic Elementor-shaped content fault did not apply')
    if elementor_payload is not None:
        stored = sql(('-e', f"SELECT HEX(meta_value) FROM `{db}`.wp_postmeta "
                             f"WHERE post_id={post_id} AND meta_key='_elementor_data'")).strip()
        if stored.upper() != elementor_payload.hex().upper().encode('ascii'):
            raise ValueError('Exact-head candidate was not stored byte-for-byte')
    return post_id


def scratch_upgrade(release, root, fault_phase=None):
    """Swap exact-release files in disposable scratch, including interruption probes."""
    if fault_phase is not None and fault_phase not in SCRATCH_FAULT_PHASES:
        raise ValueError("Unrecognised scratch file-swap fault phase")
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
        for index, (_, category, name, _) in enumerate(COMPONENTS):
            old, saved = live / category / name, backup / category / name
            saved.parent.mkdir(exist_ok=True)
            os.replace(old, saved)
            moved.append((old, saved))
            ordinal = ("first", "second")[index]
            if fault_phase == "after_" + ordinal + "_backup":
                raise RuntimeError("INJECTED_SCRATCH_FILE_FAULT")
            os.replace(stage / category / name, old)
            if fault_phase == "after_" + ordinal + "_install":
                raise RuntimeError("INJECTED_SCRATCH_FILE_FAULT")
        if snapshot(live) == before:
            raise ValueError('File upgrade did not change synthetic installed files')
        return live, before, moved
    except BaseException:
        restore_files(moved)
        if snapshot(live) != before:
            raise ValueError("Interrupted scratch file-swap failed to restore original bytes")
        raise


def restore_files(moved):
    # Validate every backup before removing any current files.
    if any(not saved.is_dir() for _, saved in moved):
        raise ValueError('Missing scratch file backup')
    for current, saved in reversed(moved):
        if current.exists():
            shutil.rmtree(current)
        os.replace(saved, current)


def exercise_swap_faults(release, root):
    """Rehearse each interruption before the combined SQL fault; never touch WP."""
    root = Path(root)
    root.mkdir()
    for phase in SCRATCH_FAULT_PHASES:
        attempt = root / phase
        attempt.mkdir()
        try:
            scratch_upgrade(release, attempt, fault_phase=phase)
        except RuntimeError as exc:
            if str(exc) != "INJECTED_SCRATCH_FILE_FAULT":
                raise
        else:
            raise ValueError("Scratch fault was not injected: " + phase)
        live = attempt / "live"
        for _, category, name, _ in COMPONENTS:
            if (live / category / name / "owner-original.txt").read_bytes() != b"synthetic owner fixture":
                raise ValueError("Interrupted scratch file-swap lost original component")
        if (live / "uploads" / "2026" / "owner-media.txt").read_bytes() != b"synthetic upload preserved":
            raise ValueError("Interrupted scratch file-swap modified uploads")
        if any((attempt / "backup").rglob("owner-original.txt")):
            raise ValueError("Interrupted scratch file-swap left an un-restored backup")
    return len(SCRATCH_FAULT_PHASES)


def verify_applied_transaction(live, before, source_digest, payload, post_id):
    """Assert a *successful* synthetic cross-domain apply before rollback.

    The database is always the fixed disposable clone; no installed WordPress
    site is accepted as an argument. This is not a deploy or commit operation.
    """
    if type(post_id) is not int or post_id < 1:
        raise ValueError('Invalid synthetic page identifier')
    if not isinstance(payload, bytes) or not 0 < len(payload) <= 256000:
        raise ValueError('Invalid exact-head candidate payload')
    live = Path(live)
    for _, category, name, entry in COMPONENTS:
        if not (live / category / name / entry).is_file():
            raise ValueError('Synthetic installed release component missing')
    if (live / 'uploads' / '2026' / 'owner-media.txt').read_bytes() != b'synthetic upload preserved':
        raise ValueError('Synthetic upload changed during successful apply')
    if snapshot(live) == before:
        raise ValueError('Successful synthetic file apply made no change')
    if digest(CLONE) == source_digest or digest('wordpress') != source_digest:
        raise ValueError('Successful apply did not isolate database changes')
    queries = (
        f"SELECT option_value FROM `{CLONE}`.wp_options WHERE option_name='home'",
        f"SELECT post_title FROM `{CLONE}`.wp_posts WHERE ID={post_id}",
        f"SELECT post_content FROM `{CLONE}`.wp_posts WHERE ID={post_id}",
        f"SELECT COUNT(*) FROM `{CLONE}`.wp_postmeta WHERE post_id={post_id} AND meta_key IN ('_ez2_ci_transaction_fault','_elementor_data','_elementor_edit_mode','_elementor_page_settings')",
        f"SELECT HEX(meta_value) FROM `{CLONE}`.wp_postmeta WHERE post_id={post_id} AND meta_key='_elementor_data'",
    )
    observed = [sql(('-e', query)).strip() for query in queries]
    expected = [
        b'http://ez2-ci-combined-fault.invalid',
        b'EZ2 synthetic content fault',
        b'EZ2 synthetic body fault',
        b'4',
        payload.hex().upper().encode('ascii'),
    ]
    if [value.upper() for value in observed] != [value.upper() for value in expected]:
        raise ValueError('Synthetic applied WordPress content did not match exact-head candidate')
    return True


def main(release, sha):
    gate(release, sha)
    release = Path(release)
    payload = candidate_payload(release, sha)
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
            file_faults = exercise_swap_faults(release, root / "file-fault-matrix")
            if digest(CLONE) != source_digest or digest("wordpress") != source_digest:
                raise ValueError("File fault matrix unexpectedly changed WordPress SQL")
            live, before, moved = scratch_upgrade(release, root)
            try:
                # Both domains now differ at once. Inject a fault after the file
                # replacement AND the SQL mutation, then restore both domains.
                front_id = inject_content_fault(CLONE, payload)
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
            # A rollback-only test could pass while never proving the staged
            # theme/core and Elementor candidate worked together. Apply both
            # domains successfully in a SECOND disposable transaction, inspect
            # the exact candidate bytes, then rehearse recovery once more.
            success_root = root / 'successful-apply'
            success_root.mkdir()
            success_live, success_before, success_moved = scratch_upgrade(release, success_root)
            try:
                success_id = inject_content_fault(CLONE, payload)
                verify_applied_transaction(success_live, success_before,
                                           source_digest, payload, success_id)
            finally:
                restore_files(success_moved)
            sql(('-e', f'DROP DATABASE `{CLONE}`'))
            created = False
            sql(('-e', f'CREATE DATABASE `{CLONE}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci'))
            created = True
            sql((CLONE,), data=original_sql)
            if (snapshot(success_live) != success_before or
                    digest(CLONE) != source_digest or digest('wordpress') != source_digest):
                raise ValueError('Successful transaction recovery failed to restore both domains')
            print('EZ2_CI_COMBINED_ROLLBACK_PASS file_components=2 file_fault_scenarios=' + str(file_faults) + ' sql_clone_recovered=true uploads_preserved=true content_rows_recovered=true elementor_meta_recovered=true source_db_untouched=true localwp_touched=false one_click_complete=false exact_head_candidate_rows_recovered=true successful_cross_domain_apply_verified=true second_recovery_verified=true')
    finally:
        if created:
            sql(('-e', f'DROP DATABASE IF EXISTS \u0060{CLONE}\u0060'))


if __name__ == '__main__':
    try:
        if len(sys.argv) != 3:
            raise ValueError('Usage: ez2_ci_combined_recovery.py .release EXACT_SHA')
        main(sys.argv[1], sys.argv[2])
    except (OSError, ValueError, TypeError, KeyError, zipfile.BadZipFile, subprocess.CalledProcessError) as exc:
        # Do not echo database SQL, passwords or subprocess stderr.
        print('EZ2_CI_COMBINED_ROLLBACK_FAIL: ' + type(exc).__name__, file=sys.stderr)
        sys.exit(1)
