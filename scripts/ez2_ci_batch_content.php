<?php
/**
 * Disposable WordPress batch content upgrade, with real postmeta writes.
 * NEVER run on LocalWP or production. No installation or publication authority.
 */
final class EZ2_CI_Batch_Content {
    const MARK = '_ez2_ci_batch_token';
    const TITLE = 'EZ2 synthetic batch draft - NEVER PUBLISH';

    static function gate(array $f): bool {
        $expected = ['wp_cli'=>true, 'opt_in'=>'YES_DISPOSABLE_RELEASE_ONLY',
            'home'=>'http://localhost:8081', 'siteurl'=>'http://localhost:8081',
            'environment'=>'staging', 'multisite'=>false, 'theme'=>'ezb-theme',
            'core'=>true, 'elementor'=>true, 'elementor_loaded'=>true,
            'elementor_version'=>'4.3.4', 'indexed'=>'0'];
        foreach ($expected as $key=>$value) if (($f[$key]??null)!==$value) return false;
        return is_string($f['sha']??null) && preg_match('/^[a-f0-9]{40}$/D',$f['sha'])
            && is_string($f['digest']??null) && preg_match('/^[a-f0-9]{64}$/D',$f['digest']);
    }

    static function read(int $id, string $token): string {
        $post = get_post($id);
        $mark = get_post_meta($id,self::MARK,false);
        $data = get_post_meta($id,'_elementor_data',false);
        if (!$post || $post->post_type!=='page' || $post->post_status!=='draft'
            || $post->post_title!==self::TITLE || $post->post_content!==''
            || $post->post_excerpt!=='' || count($mark)!==1
            || $mark[0]!==$token || count($data)!==1 || !is_string($data[0]))
            throw new RuntimeException('UNMANAGED_DRAFT_OR_METADATA');
        return $data[0];
    }

    /** Preflight ALL pages, then write; reverse rollback on any failure. */
    static function apply(array $ops, string $token, string $fault=''): int {
        if (!preg_match('/^[a-f0-9]{32}$/D',$token) || count($ops)<1 || count($ops)>20
            || !array_is_list($ops)
            || !in_array($fault,['','AFTER_FIRST','AFTER_SECOND','AFTER_LAST'],true)
            || ($fault==='AFTER_SECOND' && count($ops)<2))
            throw new RuntimeException('INVALID_BATCH');
        $before=[]; $seen=[];
        foreach ($ops as $op) {
            if (!is_array($op) || array_keys($op)!==['id','expected','next'])
                throw new RuntimeException('INVALID_BATCH_SCHEMA');
            ['id'=>$id,'expected'=>$expected,'next'=>$next]=$op;
            if (!is_int($id) || $id<1 || isset($seen[$id])
                || !is_string($expected) || !preg_match('/^[a-f0-9]{64}$/D',$expected)
                || !is_string($next) || strlen($next)<2 || strlen($next)>256000)
                throw new RuntimeException('INVALID_BATCH_ENTRY');
            $nodes=json_decode($next,true,32,JSON_THROW_ON_ERROR);
            if (!is_array($nodes) || !array_is_list($nodes) || !$nodes)
                throw new RuntimeException('INVALID_ELEMENTOR_DATA');
            $seen[$id]=true;
            $before[$id]=self::read($id,$token);
            if (!hash_equals($expected,hash('sha256',$before[$id])))
                throw new RuntimeException('OWNER_EDIT_CONFLICT');
        }
        $written=[];
        try {
            foreach ($ops as $op) {
                $id=$op['id']; $next=$op['next'];
                if (self::read($id,$token)!==$before[$id])
                    throw new RuntimeException('DRAFT_CHANGED_AFTER_PREFLIGHT');
                if ($next===$before[$id]) continue;
                if (!update_post_meta($id,'_elementor_data',wp_slash($next)))
                    throw new RuntimeException('META_WRITE_FAILED');
                $written[]=$id;
                if (self::read($id,$token)!==$next)
                    throw new RuntimeException('POSTINSTALL_CONTENT_MISMATCH');
                if (($fault==='AFTER_FIRST' && count($written)===1)
                    || ($fault==='AFTER_SECOND' && count($written)===2)
                    || ($fault==='AFTER_LAST' && count($written)===count($ops)))
                    throw new RuntimeException('INJECTED_CI_BATCH_FAULT');
            }
        } catch (Throwable $error) {
            foreach (array_reverse($written) as $id) {
                if (!update_post_meta($id,'_elementor_data',wp_slash($before[$id]))
                    || self::read($id,$token)!==$before[$id])
                    throw new RuntimeException('BATCH_ROLLBACK_FAILED',0,$error);
            }
            throw $error;
        }
        return count($written);
    }

    static function execute(): void {
        if (!defined('WP_CLI') || !WP_CLI || !function_exists('get_option'))
            throw new RuntimeException('CI_WP_CLI_ONLY');
        if (!function_exists('is_plugin_active'))
            require_once ABSPATH.'wp-admin/includes/plugin.php';
        $facts=['wp_cli'=>true,'opt_in'=>getenv('EZ2_CI_BATCH'),
            'home'=>get_option('home'),'siteurl'=>get_option('siteurl'),
            'environment'=>wp_get_environment_type(),'multisite'=>is_multisite(),
            'theme'=>get_option('stylesheet'),
            'core'=>is_plugin_active('ezb-core/ezb-core.php'),
            'elementor'=>is_plugin_active('elementor/elementor.php'),
            'elementor_loaded'=>did_action('elementor/loaded')>0,
            'elementor_version'=>defined('ELEMENTOR_VERSION')?ELEMENTOR_VERSION:null,
            'indexed'=>(string)get_option('blog_public'),
            'sha'=>getenv('EZ2_CI_RELEASE_SHA'),
            'digest'=>getenv('EZ2_CI_RELEASE_DIGEST')];
        if (!self::gate($facts)) throw new RuntimeException('DISPOSABLE_SITE_GATE');
        $meta='/release/RELEASE_METADATA.txt';
        $path='/release/ez2-runtime-candidate.json';
        foreach ([$meta,$path] as $file)
            if (is_link($file)||!is_file($file)||filesize($file)<1||filesize($file)>256000)
                throw new RuntimeException('RELEASE_INPUT_UNSAFE');
        if (!preg_match('/^commit=([a-f0-9]{40})$/m',file_get_contents($meta),$m)
            || $m[1]!==$facts['sha']
            || !hash_equals($facts['digest'],hash_file('sha256',$path)))
            throw new RuntimeException('EXACT_HEAD_CANDIDATE_MISMATCH');
        $doc=json_decode(file_get_contents($path),true,32,JSON_THROW_ON_ERROR);
        if (!is_array($doc) || ($doc['version']??null)!=='4.3.4'
            || !is_array($doc['content']??null) || !$doc['content'])
            throw new RuntimeException('CANDIDATE_SCHEMA');
        $next=wp_json_encode($doc['content'],JSON_THROW_ON_ERROR);
        $front=(int)get_option('page_on_front');
        $frontPost=get_post($front);
        if (!$frontPost || $frontPost->post_status!=='publish')
            throw new RuntimeException('PUBLISHED_FRONT_PAGE_REQUIRED');
        $token=bin2hex(random_bytes(16)); $ids=[]; $before=[]; $candidates=[];
        try {
            for ($i=1;$i<=3;$i++) {
                $id=wp_insert_post(['post_type'=>'page','post_status'=>'draft',
                    'post_title'=>self::TITLE,'post_content'=>''],true);
                if (is_wp_error($id)||!is_int($id)||$id<1)
                    throw new RuntimeException('SYNTHETIC_DRAFT_INSERT');
                $ids[]=$id;
                $raw=wp_json_encode([['id'=>'ez2ci'.$i,'elType'=>'container',
                    'settings'=>[],'elements'=>[]]],JSON_THROW_ON_ERROR);
                if (!update_post_meta($id,self::MARK,$token)
                    || !update_post_meta($id,'_elementor_edit_mode','builder')
                    || !update_post_meta($id,'_elementor_version','4.3.4')
                    || !update_post_meta($id,'_elementor_data',wp_slash($raw)))
                    throw new RuntimeException('SYNTHETIC_DRAFT_META');
                $before[$id]=self::read($id,$token);
                // Page one uses the exact-head release candidate. Additional
                // drafts use distinct CI-only derivatives to prove a batch
                // can update different pages without publishing either.
                $variant=$doc['content'];
                if ($i>1) $variant[0]['id']=sprintf('e2a1b%03d',$i);
                $candidates[$id]=$i===1 ? $next
                    : wp_json_encode($variant,JSON_THROW_ON_ERROR);
            }
            $plan=[];
            foreach ($ids as $id) $plan[]=['id'=>$id,
                'expected'=>hash('sha256',$before[$id]),'next'=>$candidates[$id]];
            foreach (['AFTER_FIRST','AFTER_SECOND','AFTER_LAST'] as $fault) {
                $failed=false;
                try { self::apply($plan,$token,$fault); }
                catch (RuntimeException $e) {
                    if ($e->getMessage()!=='INJECTED_CI_BATCH_FAULT') throw $e;
                    $failed=true;
                }
                if (!$failed) throw new RuntimeException('FAULT_NOT_INJECTED');
                foreach ($ids as $id)
                    if (self::read($id,$token)!==$before[$id])
                        throw new RuntimeException('FAULT_ROLLBACK_MISMATCH');
            }
            // Owner-edit simulation: second draft changes before preflight.
            $owner=wp_json_encode([['id'=>'owner','elType'=>'container',
                'settings'=>['note'=>'synthetic edit'],'elements'=>[]]],JSON_THROW_ON_ERROR);
            update_post_meta($ids[1],'_elementor_data',wp_slash($owner));
            $conflict=false;
            try { self::apply($plan,$token); }
            catch (RuntimeException $e) {
                if ($e->getMessage()!=='OWNER_EDIT_CONFLICT') throw $e;
                $conflict=true;
            }
            if (!$conflict || self::read($ids[0],$token)!==$before[$ids[0]]
                || self::read($ids[1],$token)!==$owner)
                throw new RuntimeException('OWNER_EDIT_NOT_PRESERVED');
            update_post_meta($ids[1],'_elementor_data',wp_slash($before[$ids[1]]));
            if (self::apply($plan,$token)!==3)
                throw new RuntimeException('BATCH_APPLY_FAILED');
            foreach ($ids as $id)
                if (self::read($id,$token)!==$candidates[$id])
                    throw new RuntimeException('EXACT_CANDIDATE_NOT_INSTALLED');
            $same=[];
            foreach ($ids as $id) $same[]=['id'=>$id,
                'expected'=>hash('sha256',$candidates[$id]),'next'=>$candidates[$id]];
            if (self::apply($same,$token)!==0)
                throw new RuntimeException('BATCH_NOT_IDEMPOTENT');
            $restore=[];
            foreach ($ids as $id) $restore[]=['id'=>$id,
                'expected'=>hash('sha256',$candidates[$id]),'next'=>$before[$id]];
            if (self::apply($restore,$token)!==3)
                throw new RuntimeException('BATCH_RESTORE_FAILED');
            foreach ($ids as $id)
                if (self::read($id,$token)!==$before[$id])
                    throw new RuntimeException('BATCH_RESTORE_MISMATCH');
            if ((int)get_option('page_on_front')!==$front
                || get_post($front)->post_title!==$frontPost->post_title)
                throw new RuntimeException('PUBLISHED_HOME_CHANGED');
        } finally {
            foreach (array_reverse($ids) as $id) {
                self::read($id,$token);
                if (wp_delete_post($id,true)===false || get_post($id))
                    throw new RuntimeException('SYNTHETIC_CLEANUP_FAILED');
            }
        }
        echo "EZ2_CI_BATCH_CONTENT_PASS pages=3 faults=3 owner_conflict_blocked=true idempotent=true restored=true exact_candidate=true distinct_synthetic_pages=true publication=false localwp_touched=false one_click_complete=false\n";
    }
}
if (!defined('EZ2_CI_BATCH_CONTENT_LIBRARY_ONLY')) {
    try { EZ2_CI_Batch_Content::execute(); }
    catch (Throwable $e) {
        fwrite(STDERR,'EZ2_CI_BATCH_CONTENT_FAIL: '.$e->getMessage()."\n");
        exit(1);
    }
}
