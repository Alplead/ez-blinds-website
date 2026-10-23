import assert from 'node:assert/strict';
import {HOST,VIEWPORTS,validateScope,reviewEvidence} from './ez2_isolated_elementor_preview.mjs';
let cases=0;
const env={EZ2_ISOLATED_ELEMENTOR_PREVIEW:'YES_DISPOSABLE_AUTHENTICATED_ONLY',
 EZ2_SOURCE_SHA:'a'.repeat(40),EZ2_CI_DRAFT_ID:'42',EZ2_CI_ADMIN_USER:'ezbdev',
 EZ2_CI_ADMIN_PASSWORD:'dev-only-change-me',EZ2_PREVIEW_OUTPUT:'/tmp/ez2-ci-draft'};
assert.doesNotThrow(()=>validateScope(env));cases++;
for(const change of [{EZ2_ISOLATED_ELEMENTOR_PREVIEW:'YES'},{EZ2_SOURCE_SHA:'main'},
 {EZ2_CI_DRAFT_ID:'0'},{EZ2_CI_DRAFT_ID:'42;rm'},{EZ2_CI_ADMIN_USER:'admin'},
 {EZ2_CI_ADMIN_PASSWORD:'real-secret'},{EZ2_PREVIEW_OUTPUT:'/'},
 {EZ2_PREVIEW_OUTPUT:'../public'},{EZ2_PREVIEW_OUTPUT:'/tmp/../public'}]){
 assert.throws(()=>validateScope({...env,...change}));cases++;
}
assert.deepEqual(VIEWPORTS.map(v=>[v.width,v.height]),[[1440,900],[390,844],[320,700]]);cases++;
const good={status:200,host:HOST,loggedIn:true,elementorDocument:true,
 heroContainer:true,heading:true,quoteButton:true,galleryCount:4,uniqueMedia:4,
 localGalleryUrls:true,slideDuration:5000,transitionDuration:1200,
 transition:'fade',kenBurns:'yes',zoomDirection:'in',
 horizontalOverflow:false,styleSheets:4,reducedMotion:true,expectedReducedMotion:true,
 pageErrors:[],failedLocalRequests:[],failedLocalResponses:[]};
assert.deepEqual(reviewEvidence(good),[]);cases++;
for(const change of [{status:302},{host:'other.local'},{loggedIn:false},
 {elementorDocument:false},{heroContainer:false},{heading:false},{quoteButton:false},
 {galleryCount:3},{uniqueMedia:3},{localGalleryUrls:false},{slideDuration:1000},
 {transitionDuration:0},{transition:'slide'},{kenBurns:'no'},{zoomDirection:'out'},
 {horizontalOverflow:true},{styleSheets:0},{reducedMotion:false},
 {pageErrors:['failure']},{failedLocalRequests:['/missing.js']},
 {failedLocalResponses:[{path:'/missing.png',status:404}]}]){
 assert.ok(reviewEvidence({...good,...change}).length);cases++;
}
assert.equal(cases,33);
console.log('EZ2_ELEMENTOR_DRAFT_PREVIEW_GUARD_PASS cases='+cases);
