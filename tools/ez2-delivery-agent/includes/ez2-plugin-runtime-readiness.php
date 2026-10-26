<?php
/** Read-only Elementor runtime check; local lock is never installation authority. */
final class EZ2_Plugin_Runtime_Readiness {
    private static function blocked(string $issue): array {
        return ['status'=>'BLOCKED_PLUGIN_RUNTIME','issues'=>[$issue],
            'checked_count'=>0,'matching_count'=>0,'mode'=>'read-only',
            'candidate_lock_attested'=>false,'can_apply'=>false,'site_modified'=>false];
    }
    public static function evaluate($site,$lock,$installed): array {
        if (!is_array($site) || ($site['status']??null)!=='READ_ONLY_PREVIEW_READY'
            || ($site['target_site']??null)!=='ez2-isolated-only'
            || ($site['mode']??null)!=='read-only' || ($site['issues']??null)!==[]
            || ($site['can_apply']??null)!==false || ($site['site_modified']??null)!==false)
            return self::blocked('ISOLATED_SITE_REQUIRED');
        if (!is_array($lock) || array_keys($lock)!==['schema_version','target_site','plugins']
            || ($lock['schema_version']??null)!==1
            || ($lock['target_site']??null)!=='ez2-isolated-only'
            || !is_array($lock['plugins']) || count($lock['plugins'])!==1)
            return self::blocked('CANDIDATE_DEPENDENCY_LOCK_UNAVAILABLE');
        $p=$lock['plugins'][0];
        if (!is_array($p) || array_keys($p)!==['slug','version','entrypoint','source','archive_sha256','activate']
            || ($p['slug']??null)!=='elementor'
            || ($p['entrypoint']??null)!=='elementor/elementor.php'
            || ($p['source']??null)!=='wordpress.org' || ($p['activate']??null)!==true
            || !is_string($p['version']??null)
            || !preg_match('/^[1-9][0-9]{0,2}\.[0-9]{1,3}\.[0-9]{1,3}$/D',$p['version'])
            || !is_string($p['archive_sha256']??null)
            || !preg_match('/^[0-9a-f]{64}$/D',$p['archive_sha256'])
            || $p['archive_sha256']===str_repeat('0',64))
            return self::blocked('INVALID_CANDIDATE_DEPENDENCY_LOCK');
        $actual=is_array($installed)?($installed['elementor/elementor.php']??null):null;
        if (!is_array($actual)) return self::blocked('REQUIRED_PLUGIN_NOT_INSTALLED');
        if (array_keys($actual)!==['version','active','network_active']
            || ($actual['version']??null)!==$p['version']
            || ($actual['active']??null)!==true || ($actual['network_active']??null)!==false)
            return self::blocked('PLUGIN_VERSION_OR_ACTIVATION_MISMATCH');
        return ['status'=>'LOCAL_PLUGIN_MATCH_UNATTESTED','issues'=>[],
            'checked_count'=>1,'matching_count'=>1,'mode'=>'read-only',
            'candidate_lock_attested'=>false,'can_apply'=>false,'site_modified'=>false];
    }
    public static function observe(array $site): array {
        if (($site['status']??null)!=='READ_ONLY_PREVIEW_READY'
            || !function_exists('get_option') || !function_exists('get_plugins')
            || !function_exists('is_plugin_active') || !function_exists('is_plugin_active_for_network'))
            return self::blocked('WORDPRESS_PLUGIN_READ_API_UNAVAILABLE');
        $all=get_plugins(); $key='elementor/elementor.php';
        if (!is_array($all)) return self::blocked('WORDPRESS_PLUGIN_READ_API_UNAVAILABLE');
        $installed=isset($all[$key]) && is_array($all[$key]) ? [
            $key=>['version'=>$all[$key]['Version']??null,
                'active'=>is_plugin_active($key),
                'network_active'=>is_plugin_active_for_network($key)]] : [];
        return self::evaluate($site,get_option('ez2_candidate_dependency_lock',null),$installed);
    }
}
