const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('static/js/clarity.js','utf8');
const valid={essential:true,analytics:true,ads:false,updatedAt:new Date().toISOString()};
function harness(initial,project='zdbchcjjtg'){
 let cookie=initial===undefined?'':'cookie_consent_v3='+encodeURIComponent(JSON.stringify(initial));
 const scripts=[],listeners={},deletions=[],masked=[];
 const element={setAttribute:(...args)=>masked.push(args)};
 const document={currentScript:{dataset:{projectId:project},nonce:'test-nonce'},
   documentElement:{},querySelectorAll:()=>[element],createElement:()=>({}),head:{appendChild:s=>scripts.push(s)}};
 Object.defineProperty(document,'cookie',{get:()=>cookie,set:value=>deletions.push(value)});
 const window={addEventListener:(type,fn)=>listeners[type]=fn};
 const context={window,document,location:{hostname:'www.sussurrosdosaber.com'},Date};
 vm.createContext(context);vm.runInContext(source,context);
 return {window,context,scripts,deletions,masked,setChoice:value=>{cookie='cookie_consent_v3='+encodeURIComponent(JSON.stringify(value))},change:()=>listeners.cookieconsentchange?.({detail:valid})};
}
test('no vendor request before consent; invalid and expired choices fail closed',()=>{
 for(const value of [undefined,{},null,{...valid,analytics:false},{...valid,analytics:'true'},
   {...valid,ads:1},{...valid,essential:false},{...valid,updatedAt:'2000-01-01'},
   {...valid,updatedAt:'invalid'},{...valid,updatedAt:'2099-01-01'}]){
   const h=harness(value);assert.equal(h.scripts.length,0);assert.equal(h.window.clarity,undefined);
   h.change();assert.equal(h.scripts.length,0); // forged event does not grant consent
 }
});
test('valid stored consent loads the supplied project once with masking and denied ads',()=>{
 const h=harness(valid);
 assert.equal(h.scripts.length,1);assert.equal(h.scripts[0].src,'https://www.clarity.ms/tag/zdbchcjjtg?ref=bwt');
 assert.equal(h.scripts[0].nonce,'test-nonce');assert.equal(h.scripts[0].async,true);
 assert.deepEqual(h.masked,[['data-clarity-mask','true']]);
 const call=h.window.clarity.q[0];assert.equal(call[0],'consentv2');
 assert.equal(call[1].analytics_Storage,'granted');assert.equal(call[1].ad_Storage,'denied');
 h.change();vm.runInContext(source,h.context);assert.equal(h.scripts.length,1);
});
test('accepting later loads; withdrawal signals denial and clears domain cookies',()=>{
 const h=harness();h.setChoice(valid);h.change();assert.equal(h.scripts.length,1);
 h.setChoice({...valid,analytics:false});h.change();
 const call=h.window.clarity.q.at(-1);assert.equal(call[1].analytics_Storage,'denied');assert.equal(call[1].ad_Storage,'denied');
 assert(h.deletions.some(s=>s.startsWith('_clck=;')&&s.includes('Domain=.sussurrosdosaber.com')));
 assert(h.deletions.some(s=>s.startsWith('_clsk=;')));assert.equal(h.scripts.length,1);
});
test('invalid project identifiers cannot produce external script URLs',()=>{
 for(const id of ['',undefined,'bad/id','https://evil.example','<script>'])assert.equal(harness(valid,id??'bad/id').scripts.length,0);
});
