#!/usr/bin/env python3
"""Crash-recoverable, synthetic-only EZ2 three-component file transaction.

This exercises the missing power-loss recovery state machine. It NEVER accepts
an installed WordPress root or a user-selected deployment directory. Its only
write target is a caller-created disposable fixture carrying a synthetic marker.
No database, media, plugin activation, or LocalWP mutation is performed.
"""
import hashlib
import json
import os
import re
import shutil
import stat
from pathlib import Path

MARKER = '.ez2-synthetic-transaction-only'
MAGIC = 'EZ2_SYNTHETIC_SCRATCH_ONLY_V1\n'
COMPONENTS = ('themes/ezb-theme', 'plugins/ezb-core', 'plugins/elementor')
MAX_FILES = 500
MAX_BYTES = 16 * 1024 * 1024


def _safe_root(root):
    root = Path(root)
    if root.is_symlink() or not root.is_dir() or root.resolve() != root.absolute():
        raise ValueError('Synthetic root must be an existing real directory')
    if any((p / '.git').exists() or (p / '.git').is_symlink()
           or (p / 'wp-config.php').exists() or (p / 'wp-admin').exists()
           for p in (root, *root.parents)):
        raise ValueError('Refusing a Git checkout or WordPress root')
    marker = root / MARKER
    if (marker.is_symlink() or not marker.is_file() or marker.stat().st_nlink != 1
            or marker.read_text(encoding='ascii') != MAGIC):
        raise ValueError('Missing synthetic-only marker')
    for name in ('live', 'stage', 'rollback'):
        p = root / name
        if p.is_symlink() or not p.is_dir() or p.resolve() != p.absolute():
            raise ValueError('Missing or linked scratch component root')
    return root


def _tree(root, component, allow_missing=False):
    directory = root / component
    for parent in (directory.parent, *directory.parent.parents):
        if parent == root.parent:
            break
        if parent.is_symlink():
            raise ValueError('Linked component ancestor')
    if allow_missing and not directory.exists() and not directory.is_symlink():
        return None
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError('Missing or linked component directory')
    seen, total, entries = set(), 0, []
    for base, dirs, files in os.walk(directory, followlinks=False):
        for name in dirs:
            path = Path(base) / name
            if path.is_symlink() or not path.is_dir():
                raise ValueError('Linked or special component directory')
        for name in files:
            path = Path(base) / name
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError('Linked or special component file')
            rel = path.relative_to(directory).as_posix()
            folded = rel.casefold()
            if folded in seen or any(part in ('', '.', '..') for part in rel.split('/')):
                raise ValueError('Ambiguous component path')
            seen.add(folded)
            total += info.st_size
            if len(seen) > MAX_FILES or total > MAX_BYTES:
                raise ValueError('Synthetic fixture exceeds size budget')
            with path.open('rb') as f:
                data = f.read(MAX_BYTES + 1)
            if len(data) != info.st_size:
                raise ValueError('File changed during inspection')
            entries.append((rel, hashlib.sha256(data).hexdigest()))
    if not entries:
        raise ValueError('Empty component fixture')
    return hashlib.sha256(json.dumps(sorted(entries), separators=(',', ':')).encode()).hexdigest()


def _journal_path(root):
    return root / 'ez2-transaction-journal.json'


def _write_journal(root, doc):
    path = _journal_path(root)
    tmp = root / '.ez2-journal-next'
    if tmp.exists() or tmp.is_symlink() or path.is_symlink():
        raise ValueError('Unsafe scratch journal path')
    with tmp.open('x', encoding='ascii') as f:
        json.dump(doc, f, sort_keys=True, separators=(',', ':'))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    # Persist the rename as well as the file body on POSIX.
    if hasattr(os, 'O_DIRECTORY'):
        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(fd)
        finally: os.close(fd)


def _clear_stale_journal_temp(root):
    """Permit recovery after a crash before the atomic journal rename.

    The committed journal remains authoritative; never trust partial next-state
    bytes. Refuse links, special entries and oversized scratch artifacts.
    This only runs under _safe_root's synthetic-only isolation.
    """
    tmp = root / '.ez2-journal-next'
    if not tmp.exists() and not tmp.is_symlink():
        return
    info = tmp.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 8192:
        raise ValueError('Unsafe interrupted scratch journal')
    tmp.unlink()
    if hasattr(os, 'O_DIRECTORY'):
        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _read_journal(root):
    path = _journal_path(root)
    if (path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1
            or path.stat().st_size > 8192):
        raise ValueError('Unsafe or missing journal')
    doc = json.loads(path.read_text(encoding='ascii'))
    if (set(doc) != {'schema', 'status', 'components', 'next_index'}
            or doc['schema'] != 1 or doc['status'] not in ('APPLYING', 'INSTALLED', 'RECOVERED')
            or type(doc['next_index']) is not int
            or not 0 <= doc['next_index'] <= len(COMPONENTS)
            or not isinstance(doc['components'], list) or len(doc['components']) != len(COMPONENTS)):
        raise ValueError('Invalid journal schema')
    for name, row in zip(COMPONENTS, doc['components']):
        if (not isinstance(row, dict) or set(row) != {'name', 'original', 'candidate'}
                or row['name'] != name or
                (row['original'] is not None and not re.fullmatch('[a-f0-9]{64}', row['original']))
                or not isinstance(row['candidate'], str)
                or not re.fullmatch('[a-f0-9]{64}', row['candidate'])):
            raise ValueError('Invalid journal component')
    return doc


def initialise(root):
    root = _safe_root(root)
    if _journal_path(root).exists() or _journal_path(root).is_symlink():
        raise ValueError('Transaction journal already exists')
    rows = []
    for name in COMPONENTS:
        original = _tree(root / 'live', name, allow_missing=True)
        candidate = _tree(root / 'stage', name)
        if _tree(root / 'rollback', name, allow_missing=True) is not None:
            raise ValueError('Rollback slot is already occupied')
        rows.append({'name': name, 'original': original, 'candidate': candidate})
    doc = {'schema': 1, 'status': 'APPLYING', 'components': rows, 'next_index': 0}
    _write_journal(root, doc)
    return doc


def apply(root, *, interrupt_after=None):
    """Synthetic fixture only. Fault leaves durable journal for explicit recovery."""
    root = _safe_root(root)
    doc = _read_journal(root)
    if doc['status'] != 'APPLYING' or doc['next_index'] != 0:
        raise ValueError('Transaction is not at a clean start')
    if interrupt_after is not None and interrupt_after not in range(1, 7):
        raise ValueError('Invalid synthetic interruption point')
    step = 0
    for index, row in enumerate(doc['components']):
        name = row['name']
        current = root / 'live' / name
        staged = root / 'stage' / name
        saved = root / 'rollback' / name
        if _tree(root / 'live', name, allow_missing=True) != row['original']:
            raise ValueError('Live baseline drifted before swap')
        if _tree(root / 'stage', name) != row['candidate']:
            raise ValueError('Candidate changed before swap')
        saved.parent.mkdir(parents=True, exist_ok=True)
        if row['original'] is not None:
            os.replace(current, saved)
        step += 1
        if interrupt_after == step:
            raise RuntimeError('SYNTHETIC_POWER_LOSS')
        os.replace(staged, current)
        step += 1
        if interrupt_after == step:
            raise RuntimeError('SYNTHETIC_POWER_LOSS')
        if _tree(root / 'live', name) != row['candidate']:
            raise ValueError('Installed synthetic bytes mismatch')
        doc['next_index'] = index + 1
        _write_journal(root, doc)
    doc['status'] = 'INSTALLED'
    _write_journal(root, doc)
    return {'status': 'SYNTHETIC_FILES_INSTALLED_RECOVERY_REQUIRED',
            'components': 3, 'wordpress_touched': False, 'can_apply': False}


def recover(root, *, interrupt_after=None):
    """Restore synthetic components; injected recovery crashes are resumable.

    Faults occur only after a component has reached its original byte state.
    The committed journal remains in its prior state until every component is
    restored. No WordPress root or deployment path is accepted.
    """
    root = _safe_root(root)
    if interrupt_after is not None and (type(interrupt_after) is not int
                                        or interrupt_after not in range(1, len(COMPONENTS) + 1)):
        raise ValueError('Invalid synthetic recovery interruption point')
    doc = _read_journal(root)
    _clear_stale_journal_temp(root)
    if doc['status'] == 'RECOVERED':
        if any(_tree(root / 'live', r['name'], allow_missing=True) != r['original']
               for r in doc['components']):
            raise ValueError('Recovered fixture was modified')
        return {'status': 'SYNTHETIC_RECOVERY_VERIFIED', 'idempotent': True,
                'wordpress_touched': False, 'can_apply': False}
    # Inspect ALL components before destructive recovery. Never overwrite an
    # unknown concurrent edit, even in this synthetic-only rehearsal.
    for row in doc['components']:
        name = row['name']
        live = _tree(root / 'live', name, allow_missing=True)
        saved = _tree(root / 'rollback', name, allow_missing=True)
        if saved is not None:
            if row['original'] is None or saved != row['original'] or live not in (None, row['candidate']):
                raise ValueError('Rollback evidence mismatched or live files drifted')
        elif live not in (row['original'], row['candidate'] if row['original'] is None else row['original']):
            raise ValueError('Unknown live component cannot be safely recovered')
    completed = 0
    for row in reversed(doc['components']):
        name = row['name']
        current = root / 'live' / name
        saved = root / 'rollback' / name
        saved_digest = _tree(root / 'rollback', name, allow_missing=True)
        if saved_digest is not None:
            if current.exists(): shutil.rmtree(current)
            os.replace(saved, current)
        elif row['original'] is None and _tree(root / 'live', name, allow_missing=True) is not None:
            shutil.rmtree(current)
        if _tree(root / 'live', name, allow_missing=True) != row['original']:
            raise ValueError('Original synthetic component not restored')
        completed += 1
        if interrupt_after == completed:
            raise RuntimeError('SYNTHETIC_RECOVERY_POWER_LOSS')
    doc['status'] = 'RECOVERED'
    _write_journal(root, doc)
    return {'status': 'SYNTHETIC_RECOVERY_VERIFIED', 'idempotent': False,
            'wordpress_touched': False, 'can_apply': False}
