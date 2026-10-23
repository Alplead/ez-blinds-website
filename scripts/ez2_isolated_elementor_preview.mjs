/** Synthetic Elementor draft browser proof. No production, LocalWP or customer media. */
import { chromium } from 'playwright';
import fs from 'node:fs/promises';
import path from 'node:path';
export const HOST='ez2-review.local';
export const VIEWPORTS=[
 {name:'desktop',width:1440,height:900,motion:'no-preference'},
 {name:'mobile',width:390,height:844,motion:'no-preference'},
 {name:'reduced-mobile',width:320,height:700,motion:'reduce'}
];
export function validateScope(e){
 if(e.EZ2_ISOLATED_ELEMENTOR_PREVIEW!=='YES_DISPOSABLE_AUTHENTICATED_ONLY' ||
 !/^[a-f0-9]{40}$/.test(e.EZ2_SOURCE_SHA||'') ||
 !/^[1-9][0-9]{0,9}$/.test(e.EZ2_CI_DRAFT_ID||'') ||
 !e.EZ2_CI_AUTH_COOKIE_JSON ||
 !e.EZ2_PREVIEW_OUTPUT || !path.isAbsolute(e.EZ2_PREVIEW_OUTPUT) ||
 path.resolve(e.EZ2_PREVIEW_OUTPUT)==='/' || e.EZ2_PREVIEW_OUTPUT.includes('..'))
 throw Error('DISPOSABLE_AUTHENTICATED_PREVIEW_GATE');
 parseAuth(e);
}
export function parseAuth(e){
 let auth;
 try{auth=JSON.parse(e.EZ2_CI_AUTH_COOKIE_JSON);}catch{throw Error('INVALID_SYNTHETIC_AUTH_COOKIE');}
 if(!auth||Object.keys(auth).sort().join(',')!=='name,value'||
 !/^wordpress_logged_in_[a-z0-9]{8,64}$/.test(auth.name||'')||
 typeof auth.value!=='string'||auth.value.length<20||auth.value.length>2048||
 /[^\\x21-\\x7e]/.test(auth.value))throw Error('INVALID_SYNTHETIC_AUTH_COOKIE');
 return auth;
}
export function reviewEvidence(e){
 const errors=[];
 if(e.status!==200||e.host!==HOST||!e.loggedIn)errors.push('authenticated isolated preview');
 if(!e.elementorDocument||!e.heroContainer||!e.heading||!e.quoteButton)errors.push('Elementor draft DOM');
 if(e.galleryCount!==4||e.uniqueMedia!==4||!e.localGalleryUrls)errors.push('synthetic media');
 if(e.slideDuration!==5000||e.transitionDuration!==1200||e.transition!=='fade'||
 e.kenBurns!=='yes'||e.zoomDirection!=='in')errors.push('Elementor motion settings');
 if(e.horizontalOverflow||e.styleSheets<1)errors.push('responsive layout');
 if(e.reducedMotion!==e.expectedReducedMotion)errors.push('motion emulation');
 if(e.pageErrors.length||e.failedLocalRequests.length||e.failedLocalResponses.length)
 errors.push('browser errors');
 return errors;
}
export async function run(e=process.env){
 validateScope(e);
 const auth=parseAuth(e);
 const browser=await chromium.launch({headless:true}),evidence=[];
 try{
  await fs.mkdir(e.EZ2_PREVIEW_OUTPUT,{recursive:true});
  for(const vp of VIEWPORTS){
   const context=await browser.newContext({viewport:{width:vp.width,height:vp.height},
    reducedMotion:vp.motion,serviceWorkers:'block'});
   try{
    await context.addCookies([{name:auth.name,value:auth.value,url:'http://'+HOST+'/',httpOnly:true,sameSite:'Lax'}]);
    const blockedExternalRequests=[];
    await context.route('**/*',async route=>{
     const req=route.request(),u=new URL(req.url());
     if(u.protocol!=='http:'||u.hostname!==HOST||u.port||u.username||u.password){
      blockedExternalRequests.push(u.origin+u.pathname);return route.abort('blockedbyclient');
     }
     try{
      const response=await route.fetch({url:'http://127.0.0.1:8080'+u.pathname+u.search,
       headers:{...req.headers(),host:HOST},maxRedirects:0});
      return route.fulfill({response});
     }catch{return route.abort('failed');}
    });
    const page=await context.newPage(),pageErrors=[],failedLocalRequests=[],failedLocalResponses=[];
    page.on('pageerror',err=>pageErrors.push(err.message));
    page.on('requestfailed',req=>{const u=new URL(req.url());if(u.hostname===HOST)failedLocalRequests.push(u.pathname);});
    page.on('response',res=>{const u=new URL(res.url());if(u.hostname===HOST&&res.status()>=400)failedLocalResponses.push({path:u.pathname,status:res.status()});});
    const response=await page.goto('http://'+HOST+'/?page_id='+e.EZ2_CI_DRAFT_ID+'&preview=true',
     {waitUntil:'networkidle',timeout:45000});
    const loggedIn=await page.locator('#wpadminbar').count()>0;
    const observed=await page.evaluate(id=>{
     const hero=document.querySelector('.elementor-element-e2a10001');
     let settings={};try{settings=JSON.parse(hero?.getAttribute('data-settings')||'{}');}catch{}
     const gallery=settings.background_slideshow_gallery||[];
     return {host:location.hostname,
      elementorDocument:Boolean(document.querySelector('.elementor[data-elementor-id="'+id+'"]')),
      heroContainer:Boolean(hero&&hero.getAttribute('data-element_type')==='container'),
      heading:[...document.querySelectorAll('.elementor-heading-title')].some(x=>x.textContent.trim()==='Blinds & Shutters'),
      quoteButton:[...document.querySelectorAll('.elementor-button-text')].some(x=>x.textContent.trim()==='Request a Quote'),
      galleryCount:Array.isArray(gallery)?gallery.length:0,
      uniqueMedia:Array.isArray(gallery)?new Set(gallery.map(x=>x.id)).size:0,
      localGalleryUrls:Array.isArray(gallery)&&gallery.every(x=>Number.isInteger(x.id)&&x.id>0&&
       typeof x.url==='string'&&x.url.startsWith('http://ez2-review.local/wp-content/uploads/')&&x.url.endsWith('.png')),
      slideDuration:settings.background_slideshow_slide_duration,
      transitionDuration:settings.background_slideshow_transition_duration,
      transition:settings.background_slideshow_slide_transition,
      kenBurns:settings.background_slideshow_ken_burns,
      zoomDirection:settings.background_slideshow_ken_burns_zoom_direction,
      horizontalOverflow:document.documentElement.scrollWidth>document.documentElement.clientWidth+1,
      styleSheets:document.styleSheets.length,
      reducedMotion:matchMedia('(prefers-reduced-motion: reduce)').matches
     };
    },e.EZ2_CI_DRAFT_ID);
    const item={viewport:vp.name,status:response?.status()||0,loggedIn,...observed,
     expectedReducedMotion:vp.motion==='reduce',pageErrors,failedLocalRequests,
     failedLocalResponses,blockedExternalRequests,syntheticMediaOnly:true,
     localwpVerified:false,realMediaVerified:false,animationPlaybackVerified:false,
     deploymentAuthorized:false};
    item.failures=reviewEvidence(item);evidence.push(item);
    await page.screenshot({path:path.join(e.EZ2_PREVIEW_OUTPUT,'elementor-preview-'+vp.name+'.png'),fullPage:true});
   }finally{await context.close();}
  }
 }finally{
  await browser.close();
  await fs.mkdir(e.EZ2_PREVIEW_OUTPUT,{recursive:true});
  await fs.writeFile(path.join(e.EZ2_PREVIEW_OUTPUT,'elementor-preview-evidence.json'),
   JSON.stringify({sourceSha:e.EZ2_SOURCE_SHA,scope:'disposable-authenticated-elementor-draft',
    evidence,localwpVerified:false,realMediaVerified:false,animationPlaybackVerified:false,
    deploymentAuthorized:false},null,2)+'\n');
 }
 const failures=evidence.flatMap(x=>x.failures.map(f=>x.viewport+': '+f));
 if(failures.length||evidence.length!==VIEWPORTS.length)throw Error('EZ2_ELEMENTOR_DRAFT_PREVIEW_FAIL '+failures.join('; '));
 console.log('EZ2_ELEMENTOR_DRAFT_PREVIEW_PASS viewports=3 synthetic_only=true localwp=false');
}
if(process.argv[1]?.endsWith('/ez2_isolated_elementor_preview.mjs'))
 run().catch(e=>{console.error(e.message);process.exitCode=1;});
