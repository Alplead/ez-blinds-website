<?php
/** Synthetic local file fixtures only; no WordPress, customer media or writes to LP. */
require_once __DIR__ . '/../tools/ez2-delivery-agent/includes/ez2-private-media-readiness.php';
$cases = 0;
$check = static function (bool $ok, string $why) use (&$cases): void {
    if (!$ok) throw new RuntimeException('Private media readiness: ' . $why);
    ++$cases;
};
$tmp = sys_get_temp_dir() . '/ez2-private-media-' . bin2hex(random_bytes(8));
$root = $tmp . '/uploads';
mkdir($root . '/2026/10', 0700, true);
$pixel = base64_decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/qX8AAAAASUVORK5CYII=', true);
$file = $root . '/2026/10/hero.png';
file_put_contents($file, $pixel);
$host = 'ez2-review.local';
$url = 'http://' . $host . '/wp-content/uploads/2026/10/hero.png';
$site = ['status' => 'READ_ONLY_PREVIEW_READY', 'target_site' => 'ez2-isolated-only',
    'mode' => 'read-only', 'can_apply' => false, 'site_modified' => false];
$map = ['schema_version' => 2, 'target_site' => 'ez2-isolated-only',
    'host' => $host, 'slots' => ['home-hero-one' => ['id' => 17, 'url' => $url, 'mime' => 'image/png', 'sha256' => hash('sha256', $pixel)]]];
$meta = ['post_type' => 'attachment', 'status' => 'inherit', 'mime' => 'image/png',
    'url' => $url, 'file' => $file];
$lookup = static fn(int $id) => $id === 17 ? $meta : null;
$run = static fn($s = null, $m = null, $h = null, $r = null, $fn = null) =>
    EZ2_Private_Media_Readiness::evaluate($s ?? $site, $m ?? $map, $h ?? $host, $r ?? $root, $fn ?? $lookup);
try {
    $good = $run();
    $check($good['status'] === 'PRIVATE_MEDIA_REFERENCES_VERIFIED_READ_ONLY'
        && $good['slot_count'] === 1 && $good['verified_count'] === 1
        && $good['unresolved_count'] === 0 && $good['byte_integrity_verified'] === true,
        'verified synthetic image with pinned bytes');
    $check(!$good['private_content_emitted'] && !$good['can_apply']
        && !$good['media_publication_authorized'] && !$good['site_modified'], 'no apply');
    $check(!str_contains(json_encode($good), $url) && !str_contains(json_encode($good), $file)
        && !str_contains(json_encode($good), '17'), 'no private identifiers');
    $check(!str_contains(json_encode($good), $map['slots']['home-hero-one']['sha256']),
        'no private image digest in report');
    foreach (['status' => 'BLOCKED', 'target_site' => 'ez-bns-new-dev.local',
              'mode' => 'write', 'can_apply' => true, 'site_modified' => true] as $key => $value) {
        $bad = $site; $bad[$key] = $value;
        $check($run($bad)['issues'] === ['ISOLATED_SITE_REQUIRED'], 'unsafe site');
    }
    foreach (['ezbns.com.au', 't2-ez-blinds-shutters.local', 'ez-bns-new-dev.local',
              'ez2-review.local.evil.invalid'] as $badHost)
        $check($run(null, null, $badHost)['issues'] === ['ISOLATED_SITE_REQUIRED'], 'unsafe host');
    $check($run(null, null, null, $tmp)['issues'] === ['UNSAFE_UPLOAD_ROOT'], 'wrong upload root');
    $check($run(null, [])['issues'] === ['PRIVATE_MEDIA_MAP_UNAVAILABLE_OR_INVALID'], 'no private map');
    $check($run(null, null, null, null, static fn($id) => null)['issues']
        === ['ATTACHMENT_MISSING_OR_MISMATCHED'], 'missing attachment');
    $check($run(null, null, null, null, static function ($id) { throw new RuntimeException('private'); })['issues']
        === ['ATTACHMENT_LOOKUP_FAILED'], 'lookup redaction');
    foreach (['schema_version' => 1, 'target_site' => 'other', 'host' => 'ezbns.com.au',
              'slots' => []] as $key => $value) {
        $bad = $map; $bad[$key] = $value;
        $check($run(null, $bad)['status'] === 'BLOCKED_PRIVATE_MEDIA_READINESS', 'invalid map');
    }
    foreach (['../secret', 'Home_Hero', ''] as $key) {
        $bad = $map; $bad['slots'] = [$key => $map['slots']['home-hero-one']];
        $check($run(null, $bad)['issues'] === ['INVALID_PRIVATE_MEDIA_SLOT'], 'bad slot key');
    }
    $missingDigest = $map;
    unset($missingDigest['slots']['home-hero-one']['sha256']);
    $check($run(null, $missingDigest)['issues'] === ['INVALID_PRIVATE_MEDIA_SLOT'],
        'missing pinned image digest');
    foreach (['bad', str_repeat('f', 63), strtoupper(hash('sha256', $pixel)), 42] as $digest) {
        $bad = $map; $bad['slots']['home-hero-one']['sha256'] = $digest;
        $check($run(null, $bad)['issues'] === ['INVALID_PRIVATE_MEDIA_SLOT'],
            'malformed pinned image digest');
    }
    $bad = $map; $bad['slots']['home-hero-one']['sha256'] = str_repeat('f', 64);
    $check($run(null, $bad)['issues'] === ['PRIVATE_MEDIA_BYTES_MISMATCH'],
        'valid format but incorrect digest');
    $check($run(null, $bad)['byte_integrity_verified'] === false,
        'failed image integrity never reported verified');
    foreach (['id' => 0, 'url' => 'https://evil.invalid/p.png', 'mime' => 'image/svg+xml'] as $key => $value) {
        $bad = $map; $bad['slots']['home-hero-one'][$key] = $value;
        $check($run(null, $bad)['issues'] === ['INVALID_PRIVATE_MEDIA_SLOT'], 'bad slot value');
    }
    foreach (['http://ez2-review.local:8080/wp-content/uploads/2026/10/hero.png',
              'http://ez2-review.local/wp-content/uploads/2026/10/../hero.png',
              'http://ez2-review.local/wp-content/uploads/2026/10/hero.png?x=1',
              'http://ez2-review.local/wp-content/uploads/2026/10/%68ero.png',
              'http://ez2-review.local/wp-content/uploads/2026/10/hero.jpg'] as $unsafe) {
        $bad = $map; $bad['slots']['home-hero-one']['url'] = $unsafe;
        $check($run(null, $bad)['issues'] === ['INVALID_PRIVATE_MEDIA_SLOT'], 'unsafe URL');
    }
    foreach (['post_type' => 'page', 'status' => 'publish', 'mime' => 'image/jpeg',
              'url' => 'http://ez2-review.local/wp-content/uploads/2026/10/other.png',
              'file' => $tmp . '/missing.png'] as $key => $value) {
        $bad = $meta; $bad[$key] = $value;
        $check($run(null, null, null, null, static fn($id) => $bad)['issues']
            === ['ATTACHMENT_MISSING_OR_MISMATCHED'], 'bad attachment');
    }
    $other = $root . '/2026/10/other.png'; file_put_contents($other, $pixel);
    $check($run(null, null, null, null, static fn($id) => array_replace($meta, ['file' => $other]))['issues']
        === ['MEDIA_URL_FILE_MISMATCH'], 'URL-to-file mismatch');
    $link = $root . '/2026/10/linked.png';
    if (symlink($file, $link)) {
        $check($run(null, null, null, null, static fn($id) => array_replace($meta, ['file' => $link]))['issues']
            === ['ATTACHMENT_MISSING_OR_MISMATCHED'], 'symlink');
        unlink($link);
    }
    $hard = $root . '/2026/10/hard.png';
    if (link($file, $hard)) {
        $check($run()['issues'] === ['UNSAFE_PRIVATE_MEDIA_FILE'], 'hardlink');
        unlink($hard);
    }
    file_put_contents($file, 'not an image but more than thirty-two bytes of synthetic data');
    $check($run()['issues'] === ['INVALID_PRIVATE_MEDIA_IMAGE'], 'corrupt bytes');
    file_put_contents($file, $pixel);
    file_put_contents($file, $pixel . 'synthetic-trailing-bytes');
    $check($run()['issues'] === ['PRIVATE_MEDIA_BYTES_MISMATCH'],
        'valid image header but modified private image bytes');
    file_put_contents($file, $pixel);
    $duplicate = $map;
    $duplicate['slots']['second-slot'] = ['id' => 18, 'url' => $url, 'mime' => 'image/png', 'sha256' => hash('sha256', $pixel)];
    $check($run(null, $duplicate)['issues'] === ['CONFLICTING_PRIVATE_MEDIA_MAPPING'], 'duplicate URL');
    $duplicate['slots']['second-slot'] = ['id' => 17, 'url' => str_replace('hero.png', 'other.png', $url), 'mime' => 'image/png', 'sha256' => hash('sha256', $pixel)];
    $check($run(null, $duplicate)['issues'] === ['CONFLICTING_PRIVATE_MEDIA_MAPPING'], 'duplicate ID');
} finally {
    foreach ([$file, $root . '/2026/10/other.png'] as $path) if (is_file($path)) unlink($path);
    rmdir($root . '/2026/10'); rmdir($root . '/2026'); rmdir($root); rmdir($tmp);
}
echo "EZ2_PRIVATE_MEDIA_READINESS_PASS cases={$cases} read_only=true localwp_touched=false can_apply=false\n";
