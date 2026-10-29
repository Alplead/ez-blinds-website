<?php
/** Offline regression for bounded multi-page CI-only WordPress batch writes. */
define('EZ2_CI_BATCH_CONTENT_LIBRARY_ONLY', true);
require_once __DIR__ . '/ez2_ci_batch_content.php';
$GLOBALS['ez2_posts'] = [];
$GLOBALS['ez2_meta'] = [];
function get_post($id) {
    return isset($GLOBALS['ez2_posts'][$id]) ? (object)$GLOBALS['ez2_posts'][$id] : null;
}
function get_post_meta($id, $key, $single = false) {
    $values = $GLOBALS['ez2_meta'][$id][$key] ?? [];
    return $single ? ($values[0] ?? '') : $values;
}
function update_post_meta($id, $key, $value) {
    if (!isset($GLOBALS['ez2_posts'][$id])) return false;
    $GLOBALS['ez2_meta'][$id][$key] = [$value];
    return true;
}
function wp_slash($value) { return $value; }
function check($condition, $message) {
    if (!$condition) throw new RuntimeException('TEST_FAIL:' . $message);
}
function blocked(callable $call, string $expected) {
    try { $call(); }
    catch (RuntimeException $error) {
        check($error->getMessage() === $expected, 'wrong error: ' . $error->getMessage());
        return;
    }
    throw new RuntimeException('TEST_FAIL:unsafe batch accepted');
}
function fixture(int $count): array {
    $GLOBALS['ez2_posts'] = [];
    $GLOBALS['ez2_meta'] = [];
    $token = str_repeat('a', 32);
    $ops = [];
    $before = [];
    for ($i = 1; $i <= $count; ++$i) {
        $GLOBALS['ez2_posts'][$i] = ['post_type'=>'page','post_status'=>'draft',
            'post_title'=>EZ2_CI_Batch_Content::TITLE,'post_content'=>'','post_excerpt'=>''];
        $old = json_encode([['id'=>sprintf('%08x', $i), 'elType'=>'container',
            'settings'=>['version'=>'old'],'elements'=>[]]], JSON_THROW_ON_ERROR);
        $new = json_encode([['id'=>sprintf('%08x', $i), 'elType'=>'container',
            'settings'=>['version'=>'new'],'elements'=>[]]], JSON_THROW_ON_ERROR);
        $GLOBALS['ez2_meta'][$i] = [
            EZ2_CI_Batch_Content::MARK => [$token],
            '_elementor_data' => [$old],
            '_elementor_page_settings' => [['hide_title'=>'no']]
        ];
        $before[$i] = $old;
        $ops[] = ['id'=>$i,'expected'=>hash('sha256', $old),'next'=>$new,
            'settings_expected'=>hash('sha256',serialize(['hide_title'=>'no'])),
            'settings_next'=>['hide_title'=>'yes']];
    }
    return [$token,$ops,$before];
}
$cases = 0;
[$token,$ops,$before] = fixture(3);
foreach (['AFTER_FIRST','AFTER_SECOND','AFTER_LAST'] as $fault) {
    blocked(fn() => EZ2_CI_Batch_Content::apply($ops,$token,$fault), 'INJECTED_CI_BATCH_FAULT');
    foreach ($before as $id=>$value) check(EZ2_CI_Batch_Content::read($id,$token)===$value
        && EZ2_CI_Batch_Content::settings($id,$token)===['hide_title'=>'no'], 'rollback '.$fault);
    ++$cases;
}
check(EZ2_CI_Batch_Content::apply($ops,$token)===3,'three distinct pages updated');
foreach ($ops as $op) check(EZ2_CI_Batch_Content::read($op['id'],$token)===$op['next']
    && EZ2_CI_Batch_Content::settings($op['id'],$token)===$op['settings_next'],'candidate parity');
++$cases;
$same = array_map(fn($op) => ['id'=>$op['id'],
    'expected'=>hash('sha256',$op['next']),'next'=>$op['next'],
    'settings_expected'=>hash('sha256',serialize($op['settings_next'])),
    'settings_next'=>$op['settings_next']], $ops);
check(EZ2_CI_Batch_Content::apply($same,$token)===0,'idempotent');
++$cases;
$restore = array_map(fn($op) => ['id'=>$op['id'],
    'expected'=>hash('sha256',$op['next']),'next'=>$before[$op['id']],
    'settings_expected'=>hash('sha256',serialize($op['settings_next'])),
    'settings_next'=>['hide_title'=>'no']], $ops);
check(EZ2_CI_Batch_Content::apply($restore,$token)===3,'restore all');
++$cases;
$GLOBALS['ez2_posts'][3]['post_content']='Owner edited this page';
blocked(fn() => EZ2_CI_Batch_Content::apply($ops,$token),'UNMANAGED_DRAFT_OR_METADATA');
check(EZ2_CI_Batch_Content::read(1,$token)===$before[1],'owner body conflict preserved other page');
$GLOBALS['ez2_posts'][3]['post_content']='';
++$cases;
$GLOBALS['ez2_meta'][3]['_elementor_data']=['[{"id":"owner"}]'];
blocked(fn() => EZ2_CI_Batch_Content::apply($ops,$token),'OWNER_EDIT_CONFLICT');
check(EZ2_CI_Batch_Content::read(1,$token)===$before[1],'owner data conflict preserved other page');
$GLOBALS['ez2_meta'][3]['_elementor_data']=[$before[3]];
++$cases;
$GLOBALS['ez2_meta'][3]['_elementor_page_settings']=[['hide_title'=>'owner']];
blocked(fn() => EZ2_CI_Batch_Content::apply($ops,$token),'OWNER_EDIT_CONFLICT');
check(EZ2_CI_Batch_Content::settings(3,$token)===['hide_title'=>'owner']
    && EZ2_CI_Batch_Content::read(1,$token)===$before[1], 'owner settings preserved');
$GLOBALS['ez2_meta'][3]['_elementor_page_settings']=[['hide_title'=>'no']];
++$cases;
$duplicate=$ops; $duplicate[1]['id']=1;
blocked(fn() => EZ2_CI_Batch_Content::apply($duplicate,$token),'INVALID_BATCH_ENTRY');
++$cases;
foreach ([1,20] as $size) {
    [$token,$ops,$before]=fixture($size);
    check(EZ2_CI_Batch_Content::apply($ops,$token)===$size,'bounded batch '.$size);
    ++$cases;
}
[$token,$ops]=fixture(21);
blocked(fn() => EZ2_CI_Batch_Content::apply($ops,$token),'INVALID_BATCH');
++$cases;
[$token,$ops]=fixture(1);
blocked(fn() => EZ2_CI_Batch_Content::apply($ops,$token,'AFTER_SECOND'),'INVALID_BATCH');
++$cases;
check($cases===14,'case count');
echo 'EZ2_CI_BATCH_GUARD_PASS cases='.$cases.' max_pages=20 faults=3 owner_edits_blocked=true'."\n";
