// Run with node --test tests/consent.test.cjs; no ad requests or external services.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const source=fs.readFileSync('static/js/main.js','utf8');
const helper=source.slice(source.indexOf('const readSiteConsent='),source.indexOf('window.sdsTrack='));
function evaluate(choice){
 const context={document:{cookie:choice===undefined?'':'cookie_consent_v3='+encodeURIComponent(JSON.stringify(choice))},window:{},Date};
 vm.createContext(context);vm.runInContext(helper+'\nthis.choice=readSiteConsent();pushAnalyticsEvent("article_view");',context);return context;
}
const valid={essential:true,analytics:true,ads:false,updatedAt:new Date().toISOString()};
test('consent gates analytics; no retrospective queue for rejected or invalid choices',()=>{
 for(const choice of [undefined,null,{}, {...valid,analytics:false},{...valid,analytics:'true'},{...valid,ads:1},{...valid,essential:false},{...valid,updatedAt:'invalid'},{...valid,updatedAt:'2000-01-01'},{...valid,updatedAt:'2099-01-01'}]){
   const context=evaluate(choice);assert.equal(context.window.dataLayer,undefined);
 }
 assert.equal(evaluate(valid).window.dataLayer.length,1);
});
test('malformed cookie fails closed',()=>{
 const context={document:{cookie:'cookie_consent_v3=%broken'},window:{},Date};vm.createContext(context);vm.runInContext(helper+'\nthis.choice=readSiteConsent();',context);assert.equal(context.choice,null);
});


function cmpHarness(){
 const button={disabled:true,addEventListener(name,callback){this[name]=callback}};
 const status={textContent:''};
 let external,timer;
 const context={window:{},document:{getElementById(id){return id==='googleCmpSettings'?button:status},createElement(){return {addEventListener(name,callback){this[name]=callback}}},head:{appendChild(script){assert.equal(context.window.adsbygoogle.pauseAdRequests,1);external=script}}},setTimeout(callback){timer=callback;return 1},clearTimeout(){}};
 vm.createContext(context);
 vm.runInContext(fs.readFileSync('static/js/google-cmp.js','utf8'),context);
 return {context,button,status,external,timeout:()=>timer()};
}
test('CMP initialises paused before loading the tag and never creates consent or ad inventory',()=>{
 const h=cmpHarness();
 assert.match(h.external.src,/client=ca-pub-7920973591685812$/);
 assert.equal(h.external.crossOrigin,'anonymous');
 assert.equal(h.button.disabled,true);
 const googlefc=h.context.window.googlefc;
 let revoked=0;googlefc.showRevocationMessage=()=>revoked++;
 googlefc.callbackQueue[0].CONSENT_API_READY();
 assert.equal(h.button.disabled,false);
 h.button.click();
 assert.equal(revoked,0);
 googlefc.callbackQueue[1].CONSENT_API_READY();
 assert.equal(revoked,1);
 assert.equal(h.context.window.adsbygoogle.pauseAdRequests,1);
 assert.equal(h.context.window.adsbygoogle.length,0);
});
test('CMP error, missing API or timeout cannot enable ads or fake revocation',()=>{
 for(const failure of ['error','timeout','missing']){
  const h=cmpHarness();
  if(failure==='error')h.external.error();
  if(failure==='timeout')h.timeout();
  if(failure==='missing')h.context.window.googlefc.callbackQueue[0].CONSENT_API_READY();
  assert.equal(h.button.disabled,true);
  assert.match(h.status.textContent,/indisponíveis/);
  assert.equal(h.context.window.adsbygoogle.pauseAdRequests,1);
 }
});
