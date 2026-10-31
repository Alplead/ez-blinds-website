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
function update_post_meta($id, $key, $value, $prev_value = null) {
    if (!isset($GLOBALS['ez2_posts'][$id])) return false;
    // WordPress update_metadata() unslashes the new value, including nested arrays.
    $value = wp_unslash($value);
    if ($key==='_elementor_page_settings' && !empty($GLOBALS['ez2_fail_settings_once'])) {
        $GLOBALS['ez2_fail_settings_once']=false;
        return false;
    }
    // Simulate an Owner editing the first page while the second is written.
    if ($id===2 && $key==='_elementor_page_settings'
        && !empty($GLOBALS['ez2_owner_race_once'])) {
        $mode=$GLOBALS['ez2_owner_race_once'];
        $GLOBALS['ez2_owner_race_once']=false;
        if ($mode==='OWNER_SETTINGS_SUCCESS_SECOND')
            $GLOBALS['ez2_meta'][1]['_elementor_page_settings']=[['hide_title'=>'owner-concurrent']];
        else
            $GLOBALS['ez2_meta'][1]['_elementor_data']=['[{"id":"owner-concurrent"}]'];
        if ($mode==='FAIL_SECOND_SETTINGS') return false;
    }
    // Model a real WordPress postmeta compare-and-swap race just before SQL.
    $race=$GLOBALS['ez2_write_race_once'] ?? null;
    if (is_array($race) && $race['id']===$id && $race['key']===$key
        && $race['on_value']===$value) {
        $GLOBALS['ez2_write_race_once']=null;
        $GLOBALS['ez2_meta'][$id][$key]=[$race['owner_value']];
    }
    if ($prev_value!==null
        && ($GLOBALS['ez2_meta'][$id][$key][0] ?? null)!==$prev_value)
        return false;
    $GLOBALS['ez2_meta'][$id][$key] = [$value];
    return true;
}
function wp_slash($value) {
    return is_array($value) ? array_map('wp_slash', $value)
        : (is_string($value) ? addslashes($value) : $value);
}
function wp_unslash($value) {
    return is_array($value) ? array_map('wp_unslash', $value)
        : (is_string($value) ? stripslashes($value) : $value);
}
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
$GLOBALS['ez2_fail_settings_once']=true;
blocked(fn() => EZ2_CI_Batch_Content::apply($ops,$token),'PAGE_SETTINGS_WRITE_FAILED');
foreach ($before as $id=>$value) check(EZ2_CI_Batch_Content::read($id,$token)===$value
    && EZ2_CI_Batch_Content::settings($id,$token)===['hide_title'=>'no'], 'partial settings write rollback');
++$cases;
// Rollback must not silently overwrite a concurrent Owner edit on page one.
[$raceToken,$raceOps,$raceBefore]=fixture(2);
$GLOBALS['ez2_owner_race_once']='FAIL_SECOND_SETTINGS';
blocked(fn() => EZ2_CI_Batch_Content::apply($raceOps,$raceToken),'BATCH_ROLLBACK_CONFLICT');
check(EZ2_CI_Batch_Content::read(1,$raceToken)==='[{"id":"owner-concurrent"}]'
    && EZ2_CI_Batch_Content::read(2,$raceToken)===$raceBefore[2]
    && EZ2_CI_Batch_Content::settings(2,$raceToken)===['hide_title'=>'no'],
    'Owner concurrent edit preserved; other page rolled back');
++$cases;
// Even when the second write succeeds, postflight must detect earlier drift.
[$raceToken,$raceOps,$raceBefore]=fixture(2);
$GLOBALS['ez2_owner_race_once']='SUCCESS_SECOND_SETTINGS';
blocked(fn() => EZ2_CI_Batch_Content::apply($raceOps,$raceToken),'BATCH_ROLLBACK_CONFLICT');
check(EZ2_CI_Batch_Content::read(1,$raceToken)==='[{"id":"owner-concurrent"}]'
    && EZ2_CI_Batch_Content::read(2,$raceToken)===$raceBefore[2]
    && EZ2_CI_Batch_Content::settings(2,$raceToken)===['hide_title'=>'no'],
    'postflight drift protected Owner edit');
++$cases;
// A page-content edit racing the first write must never be overwritten.
[$raceToken,$raceOps,$raceBefore]=fixture(2);
$GLOBALS['ez2_write_race_once']=['id'=>1,'key'=>'_elementor_data',
    'on_value'=>$raceOps[0]['next'],'owner_value'=>'[{"id":"owner-during-write"}]'];
blocked(fn() => EZ2_CI_Batch_Content::apply($raceOps,$raceToken),'BATCH_ROLLBACK_CONFLICT');
check(EZ2_CI_Batch_Content::read(1,$raceToken)==='[{"id":"owner-during-write"}]'
    && EZ2_CI_Batch_Content::settings(1,$raceToken)===['hide_title'=>'no']
    && EZ2_CI_Batch_Content::read(2,$raceToken)===$raceBefore[2],
    'content CAS preserves Owner edit before forward write');
++$cases;
// A settings edit racing the second metadata write must restore our data,
// while preserving the Owner's settings change on the same page.
[$raceToken,$raceOps,$raceBefore]=fixture(2);
$GLOBALS['ez2_write_race_once']=['id'=>1,'key'=>'_elementor_page_settings',
    'on_value'=>['hide_title'=>'yes'],'owner_value'=>['hide_title'=>'owner-race']];
blocked(fn() => EZ2_CI_Batch_Content::apply($raceOps,$raceToken),'BATCH_ROLLBACK_CONFLICT');
check(EZ2_CI_Batch_Content::read(1,$raceToken)===$raceBefore[1]
    && EZ2_CI_Batch_Content::settings(1,$raceToken)===['hide_title'=>'owner-race']
    && EZ2_CI_Batch_Content::read(2,$raceToken)===$raceBefore[2],
    'settings CAS preserves Owner edit and restores our data');
++$cases;
// Even during rollback, a fresh Owner edit must defeat the stale CAS.
[$raceToken,$raceOps,$raceBefore]=fixture(2);
$GLOBALS['ez2_write_race_once']=['id'=>1,'key'=>'_elementor_data',
    'on_value'=>$raceBefore[1],'owner_value'=>'[{"id":"owner-during-rollback"}]'];
blocked(fn() => EZ2_CI_Batch_Content::apply($raceOps,$raceToken,'AFTER_SECOND'),
    'BATCH_ROLLBACK_CONFLICT');
check(EZ2_CI_Batch_Content::read(1,$raceToken)==='[{"id":"owner-during-rollback"}]'
    && EZ2_CI_Batch_Content::settings(1,$raceToken)===['hide_title'=>'no']
    && EZ2_CI_Batch_Content::read(2,$raceToken)===$raceBefore[2]
    && EZ2_CI_Batch_Content::settings(2,$raceToken)===['hide_title'=>'no'],
    'rollback CAS preserves Owner data and restores other fields');
++$cases;
// Owner changes only settings on an earlier page during a later write.
// Restore the earlier page's transaction-owned data independently.
[$raceToken,$raceOps,$raceBefore]=fixture(2);
$GLOBALS['ez2_owner_race_once']='OWNER_SETTINGS_SUCCESS_SECOND';
blocked(fn() => EZ2_CI_Batch_Content::apply($raceOps,$raceToken),'BATCH_ROLLBACK_CONFLICT');
check(EZ2_CI_Batch_Content::read(1,$raceToken)===$raceBefore[1]
    && EZ2_CI_Batch_Content::settings(1,$raceToken)===['hide_title'=>'owner-concurrent']
    && EZ2_CI_Batch_Content::read(2,$raceToken)===$raceBefore[2]
    && EZ2_CI_Batch_Content::settings(2,$raceToken)===['hide_title'=>'no'],
    'independent rollback preserves Owner settings without stranding our data');
++$cases;
// A no-op final page must not skip the last-phase rollback test.
[$raceToken,$raceOps,$raceBefore]=fixture(2);
$raceOps[1]['next']=$raceBefore[2];
$raceOps[1]['settings_next']=['hide_title'=>'no'];
blocked(fn() => EZ2_CI_Batch_Content::apply($raceOps,$raceToken,'AFTER_LAST'),
    'INJECTED_CI_BATCH_FAULT');
check(EZ2_CI_Batch_Content::read(1,$raceToken)===$raceBefore[1]
    && EZ2_CI_Batch_Content::read(2,$raceToken)===$raceBefore[2],
    'last-phase fault restores changed page when final page is unchanged');
++$cases;
[$token,$ops,$before]=fixture(3);
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
// WordPress recursively unslashes postmeta writes: nested settings must
// retain quotes and backslashes through apply, injected rollback, and restore.
[$token,$ops,$before]=fixture(1);
$specialBefore=['hide_title'=>'no','custom'=>['caption'=>'Owner "quote" \\ path']];
$specialNext=['hide_title'=>'yes','custom'=>['caption'=>'New "quote" \\ path']];
$GLOBALS['ez2_meta'][1]['_elementor_page_settings']=[$specialBefore];
$ops[0]['settings_expected']=hash('sha256',serialize($specialBefore));
$ops[0]['settings_next']=$specialNext;
blocked(fn() => EZ2_CI_Batch_Content::apply($ops,$token,'AFTER_FIRST'),
    'INJECTED_CI_BATCH_FAULT');
check(EZ2_CI_Batch_Content::settings(1,$token)===$specialBefore,
    'escaped settings preserved after injected rollback');
check(EZ2_CI_Batch_Content::apply($ops,$token)===1
    && EZ2_CI_Batch_Content::settings(1,$token)===$specialNext,
    'escaped settings preserved after apply');
$escapedRestore=[['id'=>1,'expected'=>hash('sha256',$ops[0]['next']),
    'next'=>$before[1],
    'settings_expected'=>hash('sha256',serialize($specialNext)),
    'settings_next'=>$specialBefore]];
check(EZ2_CI_Batch_Content::apply($escapedRestore,$token)===1
    && EZ2_CI_Batch_Content::settings(1,$token)===$specialBefore,
    'escaped settings preserved after restore');
++$cases;
check($cases===23,'case count');
echo 'EZ2_CI_BATCH_GUARD_PASS cases='.$cases.' max_pages=20 faults=3 owner_edits_blocked=true escaped_settings=true'."\n";
