const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm'),fs=require('node:fs');
const source=fs.readFileSync('web/browser-link.js','utf8');
function fixture({publicLink=true,hash='',ok=true,ready=true,reject=false}={}){
 const calls=[],nodes=[];let stripped=false;
 const document={querySelector:()=>publicLink?{}:null,documentElement:{classList:{add(){},remove(){}}},body:{append(n){nodes.push(n);}},createElement:()=>({append(...n){this.children=n;},setAttribute(){},remove(){this.removed=true;}})};
 const context={window:{},document,location:{hash,pathname:'/',search:''},history:{replaceState(){stripped=true;}},URLSearchParams,AbortSignal,
 fetch:async(url,options)=>{calls.push({url,options,stripped});if(reject)throw Error('offline');return {ok,json:async()=>({ready})};}};
 vm.runInNewContext(source,context);return {context,calls,nodes};
}
test('LAN pages do not create a public pairing gate',()=>{const f=fixture({publicLink:false});assert.equal(f.context.window.TouchHelmBrowserLink,undefined);assert.equal(f.calls.length,0);});
test('one-use fragment is removed before its credentialed POST and never stored',async()=>{const f=fixture({hash:'#browser-link='+'t'.repeat(43)});assert.equal(await f.context.window.TouchHelmBrowserLink.ready,true);assert.equal(f.calls.length,1);assert.equal(f.calls[0].stripped,true);assert.equal(f.calls[0].url,'/api/browser-link/pair');assert.equal(f.calls[0].options.credentials,'same-origin');assert.equal(JSON.parse(f.calls[0].options.body).token,'t'.repeat(43));assert.equal(f.nodes[0].removed,true);});
test('refresh checks its secure cookie instead of replaying a QR secret',async()=>{const f=fixture();assert.equal(await f.context.window.TouchHelmBrowserLink.ready,true);assert.equal(f.calls[0].url,'/api/browser-link/status');assert.equal(f.calls[0].options.body,undefined);});
test('invalid, consumed and unreachable links stay blocked with recovery text',async()=>{for(const options of [{hash:'#browser-link=bad'},{ok:false},{ready:false},{reject:true}]){const f=fixture(options);assert.equal(await f.context.window.TouchHelmBrowserLink.ready,false);assert.equal(f.context.window.TouchHelmBrowserLink.allowed,false);assert.equal(f.context.window.TouchHelmBrowserLink.settled,true);assert.match(f.nodes[0].children[0].textContent,/fresh QR/);assert.match(f.nodes[0].children[1].textContent,/New QR code/);}});
