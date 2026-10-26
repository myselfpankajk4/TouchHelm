const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm'),fs=require('node:fs');
const source=fs.readFileSync('web/browser-link.js','utf8');
function fixture({publicLink=true,hash='',ok=true,ready=true,reject=false}={}){
 const calls=[],nodes=[];let stripped=false;
 const document={querySelector:()=>publicLink?{}:null,documentElement:{classList:{add(){},remove(){}}},body:{append(n){nodes.push(n);}},createElement:()=>({append(...n){this.children=n;},setAttribute(){},remove(){this.removed=true;}})};
 const context={window:{},document,location:{hash,pathname:'/',search:''},history:{replaceState(){stripped=true;}},URLSearchParams,AbortSignal,
 fetch:async(url,options)=>{calls.push({url,options,stripped});if(reject)throw Error('offline');return {ok,json:async()=>({ready})};}};
 vm.runInNewContext(source,context);return {context,calls,nodes,get stripped(){return stripped;}};
}
test('LAN pages do not create a public pairing gate',()=>{const f=fixture({publicLink:false});assert.equal(f.context.window.TouchHelmBrowserLink,undefined);assert.equal(f.calls.length,0);});
test('legacy ticket-only fragments are removed and rejected before any network request',async()=>{const f=fixture({hash:'#browser-link='+'t'.repeat(43)});assert.equal(await f.context.window.TouchHelmBrowserLink.ready,false);assert.equal(f.stripped,true);assert.equal(f.calls.length,0);});
test('refresh cannot reuse a legacy HTTP cookie to establish control',async()=>{const f=fixture();assert.equal(await f.context.window.TouchHelmBrowserLink.ready,false);assert.equal(f.calls.length,0);assert.equal(f.context.window.TouchHelmBrowserLink.local,true);});
test('missing or malformed QR identity stays blocked with recovery and no relay fallback',async()=>{for(const options of [{hash:'#browser-link=bad'},{hash:'#browser-link='+'t'.repeat(43)+'&fingerprint=bad'},{hash:'#other=123'},{}]){const f=fixture(options);assert.equal(await f.context.window.TouchHelmBrowserLink.ready,false);assert.equal(f.context.window.TouchHelmBrowserLink.allowed,false);assert.equal(f.context.window.TouchHelmBrowserLink.settled,true);assert.equal(f.calls.length,0);assert.match(f.nodes[0].children[0].textContent,/fresh QR/);assert.match(f.nodes[0].children[1].textContent,/no internet control fallback/);}});
