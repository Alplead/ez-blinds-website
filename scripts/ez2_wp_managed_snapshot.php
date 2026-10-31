<?php
/** Read-only digest inventory of marked Elementor pages on an isolated EZ2 site.
 * Not an installer, installed-release attestation, or Owner-edit override.
 * WP-CLI only; never emits private page/media content.
 */
if (!defined('EZ2_RUNTIME_PROBE_LIBRARY_ONLY')) define('EZ2_RUNTIME_PROBE_LIBRARY_ONLY', true);
require_once __DIR__ . '/ez2_wp_runtime_probe.php';
final class Ez2ManagedSnapshot {
    private static function canonical($v) {
        if (!is_array($v)) return $v;
        if (!array_is_list($v)) ksort($v, SORT_STRING);
        foreach ($v as $k => $x) $v[$k] = self::canonical($x);
        return $v;
    }
    private static function digest($v): string {
        return hash('sha256', json_encode(self::canonical($v),
            JSON_THROW_ON_ERROR | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE));
    }
    public static function evaluate(array $facts, array $rows): array {
        if (Ez2RuntimeProbe::evaluate($facts)['status'] !== 'READY_FOR_MANUAL_ELEMENTOR_FEATURE_TEST')
            throw new RuntimeException('ISOLATED_RUNTIME_GATE_BLOCKED');
        if (count($rows) > 100) throw new RuntimeException('TOO_MANY_MANAGED_PAGES');
        $out = []; $ids = [];
        foreach ($rows as $r) {
            if (!is_array($r) || array_keys($r) !== [
                'id', 'key', 'post_type', 'status', 'title', 'slug', 'body',
                'elementor_data', 'page_settings', 'elementor_version'])
                throw new RuntimeException('INVALID_MANAGED_RECORD_SCHEMA');
            $id = $r['id']; $key = $r['key'];
            if (!is_int($id) || $id < 1 || isset($ids[$id])
                || !is_string($key) || !preg_match('/^ez2-[a-z0-9-]{1,80}$/D', $key)
                || isset($out[$key]))
                throw new RuntimeException('DUPLICATE_OR_INVALID_MANAGED_PAGE');
            if ($r['post_type'] !== 'page'
                || !in_array($r['status'], ['publish','future','draft','pending','private','trash'], true)
                || !is_string($r['title']) || strlen($r['title']) > 1000
                || !is_string($r['slug']) || strlen($r['slug']) > 200
                || !is_string($r['body']) || strlen($r['body']) > 2000000
                || !is_string($r['elementor_data']) || strlen($r['elementor_data']) < 2
                || strlen($r['elementor_data']) > 256000
                || !is_array($r['page_settings'])
                || $r['elementor_version'] !== $facts['expected_elementor_version'])
                throw new RuntimeException('UNSAFE_OR_UNSUPPORTED_MANAGED_PAGE');
            try { $nodes = json_decode($r['elementor_data'], true, 32, JSON_THROW_ON_ERROR); }
            catch (JsonException $e) { throw new RuntimeException('INVALID_ELEMENTOR_JSON'); }
            if (!is_array($nodes) || !array_is_list($nodes) || !$nodes)
                throw new RuntimeException('EMPTY_OR_UNSUPPORTED_ELEMENTOR_PAGE');
            $ids[$id] = true;
            $out[$key] = [
                'key' => $key, 'post_id' => $id, 'post_status' => $r['status'],
                'content_sha256' => self::digest([
                    'title'=>$r['title'], 'slug'=>$r['slug'], 'status'=>$r['status'],
                    'body'=>$r['body'], 'elementor_data'=>$nodes,
                    'page_settings'=>$r['page_settings'],
                    'elementor_version'=>$r['elementor_version']]),
                'elementor_data_sha256' => self::digest($nodes),
            ];
        }
        ksort($out, SORT_STRING);
        return [
            'schema_version'=>1,
            'status'=>$out ? 'MANAGED_CONTENT_DIGESTS_COLLECTED' : 'NO_MANAGED_PAGES',
            'mode'=>'read-only', 'target_site'=>'ez2-isolated-only',
            'runtime_gate_passed'=>true, 'managed_count'=>count($out),
            'entries'=>array_values($out), 'private_content_emitted'=>false,
            'installed_release_attested'=>false, 'localwp_verified'=>false,
            'owner_edit_baseline_trusted'=>false, 'deployment_authorized'=>false,
            'applied'=>false
        ];
    }
    public static function collect(): array {
        if (!defined('WP_CLI') || !WP_CLI || !function_exists('get_posts')
            || !function_exists('get_post_meta') || !function_exists('get_post'))
            throw new RuntimeException('WP_CLI_AND_WORDPRESS_REQUIRED');
        $facts = Ez2RuntimeProbe::collect();
        if (Ez2RuntimeProbe::evaluate($facts)['status'] !== 'READY_FOR_MANUAL_ELEMENTOR_FEATURE_TEST')
            throw new RuntimeException('ISOLATED_RUNTIME_GATE_BLOCKED');
        $ids = get_posts([
            'post_type'=>'any',
            'post_status'=>['publish','future','draft','pending','private','trash'],
            'meta_key'=>'_ez2_managed_key', 'posts_per_page'=>101,
            'fields'=>'ids', 'orderby'=>'ID', 'order'=>'ASC', 'suppress_filters'=>true
        ]);
        if (!is_array($ids) || count($ids) > 100)
            throw new RuntimeException('INVALID_MANAGED_POST_QUERY');
        $rows = [];
        foreach ($ids as $id) {
            $id = (int)$id; $post = get_post($id);
            if (!$post) throw new RuntimeException('MANAGED_POST_DISAPPEARED');
            $meta = [];
            foreach (['_ez2_managed_key','_elementor_data',
                      '_elementor_page_settings','_elementor_version'] as $name) {
                $values = get_post_meta($id, $name, false);
                if (!is_array($values) || count($values) !== 1)
                    throw new RuntimeException('MISSING_OR_DUPLICATE_MANAGED_METADATA');
                $meta[$name] = $values[0];
            }
            $rows[] = [
                'id'=>$id, 'key'=>$meta['_ez2_managed_key'],
                'post_type'=>$post->post_type, 'status'=>$post->post_status,
                'title'=>$post->post_title, 'slug'=>$post->post_name,
                'body'=>$post->post_content, 'elementor_data'=>$meta['_elementor_data'],
                'page_settings'=>$meta['_elementor_page_settings'],
                'elementor_version'=>$meta['_elementor_version']
            ];
        }
        return self::evaluate($facts, $rows);
    }
}
if (!defined('EZ2_MANAGED_SNAPSHOT_LIBRARY_ONLY')) {
    try {
        echo json_encode(Ez2ManagedSnapshot::collect(),
            JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR) . "\n";
    } catch (Throwable $e) {
        fwrite(STDERR, 'EZ2_MANAGED_SNAPSHOT_FAIL: ' . $e->getMessage() . "\n");
        exit(1);
    }
}
