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
