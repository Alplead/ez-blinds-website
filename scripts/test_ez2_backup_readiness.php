<?php
/** Offline pure guard tests; no WordPress installation, backups or credentials. */
require_once __DIR__ . '/../tools/ez2-delivery-agent/includes/ez2-backup-readiness.php';
$good = [
    'site_status' => 'READ_ONLY_PREVIEW_READY',
    'source_sha' => str_repeat('a', 40),
    'root' => '/srv/ez2/public', 'content' => '/srv/ez2/public/wp-content',
    'uploads' => '/srv/ez2/public/wp-content/uploads',
    'plugins' => '/srv/ez2/public/wp-content/plugins',
    'themes' => '/srv/ez2/public/wp-content/themes',
    'backup' => '/srv/ez2-private-backup', 'backup_exists' => true,
    'backup_is_link' => false, 'backup_writable' => true,
    'db_connected' => true, 'free_bytes' => 1024 * 1024 * 1024,
    'backup_under_git_checkout' => false,
];
$cases = 0;
$check = static function(array $data, ?string $issue) use (&$cases): void {
    $r = EZ2_Backup_Readiness::evaluate($data);
    $expected = $issue === null ? 'BACKUP_LOCATION_CANDIDATE_ONLY' : 'BLOCKED_BACKUP_PREPARATION';
    if ($r['status'] !== $expected || ($issue !== null && !in_array($issue, $r['issues'], true))
        || $r['backup_created'] !== false || $r['backup_verified'] !== false
        || $r['restore_rehearsed'] !== false || $r['can_apply'] !== false
        || $r['site_modified'] !== false || $r['one_click_complete'] !== false) {
        throw new RuntimeException('Unsafe backup preflight accepted: ' . json_encode($data));
    }
    $cases++;
};
$check($good, null);
foreach ([
    ['site_status', 'BLOCKED', 'SITE_NOT_ISOLATED'],
    ['source_sha', str_repeat('a', 39), 'EXACT_SHA_REQUIRED'],
    ['root', 'relative/site', 'UNSAFE_PATH_ROOT'],
    ['root', '/srv/ez2/../public', 'UNSAFE_PATH_ROOT'],
    ['root', "/srv/ez2/\npublic", 'UNSAFE_PATH_ROOT'],
    ['content', '/srv/other', 'COMPONENT_OUTSIDE_ROOT'],
    ['uploads', '/srv/private', 'COMPONENT_OUTSIDE_CONTENT'],
    ['plugins', '/srv/other/plugins', 'COMPONENT_OUTSIDE_CONTENT'],
    ['themes', '/srv/other/themes', 'COMPONENT_OUTSIDE_CONTENT'],
    ['backup', '/srv/ez2/public/backups', 'BACKUP_OVERLAPS_WORDPRESS_ROOT'],
    ['backup', '/srv/ez2', 'BACKUP_OVERLAPS_WORDPRESS_ROOT'],
    ['backup', '/srv/ez2/public', 'BACKUP_OVERLAPS_WORDPRESS_ROOT'],
    ['backup', '/srv/ez2/publication-backup', null],
    ['backup_exists', false, 'BACKUP_DESTINATION_UNSAFE'],
    ['backup_is_link', true, 'BACKUP_DESTINATION_UNSAFE'],
    ['backup_writable', false, 'BACKUP_DESTINATION_UNSAFE'],
    ['backup_under_git_checkout', true, 'BACKUP_INSIDE_GIT_CHECKOUT'],
    ['backup_under_git_checkout', null, 'BACKUP_INSIDE_GIT_CHECKOUT'],
    ['db_connected', false, 'DATABASE_NOT_READY'],
    ['free_bytes', 100, 'BACKUP_FREE_SPACE_INSUFFICIENT'],
    ['free_bytes', NAN, 'BACKUP_FREE_SPACE_INSUFFICIENT'],
    ['free_bytes', null, 'BACKUP_FREE_SPACE_INSUFFICIENT'],
    ['backup', '/srv/ez2//private', 'UNSAFE_PATH_BACKUP'],
] as [$key, $value, $issue]) {
    $input = $good;
    $input[$key] = $value;
    $check($input, $issue);
}
$win = $good;
$win['root'] = 'C:\\Local Sites\\EZ2\\app\\public';
$win['content'] = 'C:\\Local Sites\\EZ2\\app\\public\\wp-content';
$win['uploads'] = 'C:\\Local Sites\\EZ2\\app\\public\\wp-content\\uploads';
$win['plugins'] = 'C:\\Local Sites\\EZ2\\app\\public\\wp-content\\plugins';
$win['themes'] = 'C:\\Local Sites\\EZ2\\app\\public\\wp-content\\themes';
$win['backup'] = 'D:\\Private EZ2 Backups';
$check($win, null);
$win['backup'] = 'C:\\Local Sites\\EZ2\\app\\public\\backups';
$check($win, 'BACKUP_OVERLAPS_WORDPRESS_ROOT');
// Win32 aliases must never bypass backup/root isolation.
foreach ([
    'D:\\Private EZ2 Backups\\CON',
    'D:\\Private EZ2 Backups\\con.txt',
    'D:\\Private EZ2 Backups\\LPT1',
    'D:\\Private EZ2 Backups\\NUL',
    'D:\\Private EZ2 Backups\\folder.',
    'D:\\Private EZ2 Backups\\folder ',
    'D:\\Private EZ2 Backups\\folder:stream',
    'D:\\Private EZ2 Backups\\PROGRA~1',
    'D:\\Private EZ2 Backups\\folder?name',
] as $unsafeBackup) {
    $candidate = $win;
    $candidate['backup'] = $unsafeBackup;
    $check($candidate, 'UNSAFE_PATH_BACKUP');
}
// Exercise actual ancestor traversal, including Git linked worktree marker files.
$temp = sys_get_temp_dir() . '/ez2-backup-git-' . bin2hex(random_bytes(8));
if (!mkdir($temp, 0700) || !mkdir($temp . '/repo', 0700)
    || !mkdir($temp . '/repo/backups', 0700)
    || !mkdir($temp . '/outside', 0700)) throw new RuntimeException('Fixture setup failed');
try {
    if (EZ2_Backup_Readiness::gitCheckoutAncestor($temp . '/outside')) {
        throw new RuntimeException('Clean private directory incorrectly flagged');
    }
    $cases++;
    mkdir($temp . '/repo/.git', 0700);
    if (!EZ2_Backup_Readiness::gitCheckoutAncestor($temp . '/repo/backups')) {
        throw new RuntimeException('Git checkout ancestor not detected');
    }
    $cases++;
    rmdir($temp . '/repo/.git');
    file_put_contents($temp . '/repo/.git', 'gitdir: /synthetic/worktrees/ez2');
    if (!EZ2_Backup_Readiness::gitCheckoutAncestor($temp . '/repo/backups')) {
        throw new RuntimeException('Linked worktree ancestor not detected');
    }
    $cases++;
    if (!EZ2_Backup_Readiness::gitCheckoutAncestor($temp . '/missing')) {
        throw new RuntimeException('Nonexistent backup directory accepted');
    }
    $cases++;
} finally {
    if (is_file($temp . '/repo/.git')) unlink($temp . '/repo/.git');
    rmdir($temp . '/repo/backups');
    rmdir($temp . '/repo');
    rmdir($temp . '/outside');
    rmdir($temp);
}
echo "EZ2_BACKUP_READINESS_GUARD_PASS cases={$cases} backup_created=false apply_disabled=true\n";
