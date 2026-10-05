import fs from 'node:fs/promises';
import {spawn} from 'node:child_process';
import crypto from 'node:crypto';
const [url='http://127.0.0.1:8906',out='/out']=process.argv.slice(2),checks=[],screenshots=[],errors=[];
const pause=ms=>new Promise(r=>setTimeout(r,ms));
const profile=await fs.mkdtemp('/tmp/lc3d-');
for(const name of ['config','cache','data'])await fs.mkdir(profile+'/'+name);
const xvfb=spawn('/usr/bin/Xvfb',['-displayfd','1','-screen','0','1800x1240x24','-nolisten','tcp']);
const display=await new Promise((r,j)=>{xvfb.stdout.once('data',b=>r(b.toString().trim()));xvfb.once('error',j);});
const browser=spawn('/usr/bin/chromium',['--headless=new','--no-sandbox','--disable-dev-shm-usage','--ozone-platform=headless','--use-gl=angle','--use-angle=gl','--ignore-gpu-blocklist','--disable-vulkan','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{env:{...process.env,DISPLAY:':'+display,LIBGL_ALWAYS_SOFTWARE:'1',XDG_CONFIG_HOME:profile+'/config',XDG_CACHE_HOME:profile+'/cache',XDG_DATA_HOME:profile+'/data'}});
browser.stderr.on('data',b=>errors.push(b.toString()));
let ws,seq=0;const pending=new Map();
function check(ok,name,detail){checks.push({pass:!!ok,name,detail});if(!ok)throw Error(name);}
function send(method,params={}){const id=++seq;return new Promise((r,j)=>{const timer=setTimeout(()=>{pending.delete(id);j(Error(method+' timeout'));},30000);pending.set(id,{r:x=>{clearTimeout(timer);r(x);},j:x=>{clearTimeout(timer);j(x);}});ws.send(JSON.stringify({id,method,params}));});}
async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result?.value;}
async function choose(id,value){await evaluate(`(()=>{const e=document.getElementById(${JSON.stringify(id)});e.value=${JSON.stringify(value)};e.dispatchEvent(new Event('change',{bubbles:true}));})()`);}
async function ready(region,condition,surface,representation='mesh'){
 for(let i=0;i<600;i++){const q=await evaluate('window.__GEOGS_QA');if(q?.errors?.length)throw Error(JSON.stringify(q.errors));if(q?.ready&&(!region||q.region===region)&&(!condition||q.condition===condition)&&(!surface||q.surface_mode===surface)&&q.representation_mode===representation)return q;await pause(100);}throw Error('Actual geometry load timeout');
}
async function capture(name){const r=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await fs.writeFile(out+'/'+name,Buffer.from(r.data,'base64'),{flag:'wx'});screenshots.push(name);}
const receipt={schema:'jbgs.lc_3d_browser_qa.v2',status:'RUNNING',url,started_at:new Date().toISOString(),scientific_verdict:null,checks,screenshots,software_webgl:true,uses_training_gpu:false};
try{
 let port;for(let i=0;i<100;i++){try{port=(await fs.readFile(profile+'/DevToolsActivePort','utf8')).split('\n')[0];break;}catch{await pause(100);}}
 check(!!port,'Chromium CDP ready');const pages=await(await fetch('http://127.0.0.1:'+port+'/json/list')).json();
 ws=new WebSocket(pages.find(x=>x.type==='page').webSocketDebuggerUrl);await new Promise((r,j)=>{ws.onopen=r;ws.onerror=j;});
 ws.onmessage=e=>{const m=JSON.parse(e.data);if(pending.has(m.id)){const p=pending.get(m.id);pending.delete(m.id);m.error?p.j(m.error):p.r(m.result);}};
 await send('Page.enable');await send('Runtime.enable');await send('Emulation.setDeviceMetricsOverride',{width:1680,height:1180,deviceScaleFactor:1,mobile:false});await send('Page.navigate',{url});await ready();
 const manifestResponse=await fetch(url+'/manifest.json'),manifestBytes=Buffer.from(await manifestResponse.arrayBuffer()),m=JSON.parse(manifestBytes);
 receipt.evaluated_conditions=m.evaluated_conditions;receipt.source_review_packet=m.source_review_packet;receipt.source_review_receipt_sha256=m.source_review_receipt_sha256;
 receipt.manifest_url=manifestResponse.url;receipt.manifest_sha256=crypto.createHash('sha256').update(manifestBytes).digest('hex');
 const exportReceipt=await(await fetch(new URL('receipt.json',manifestResponse.url))).arrayBuffer();receipt.export_receipt_sha256=crypto.createHash('sha256').update(Buffer.from(exportReceipt)).digest('hex');
 for(const region of m.regions){
  await choose('region-select',region.id);await ready(region.id);
  for(const condition of region.conditions){
   await choose('condition-select',condition.id);
   for(const surface of ['raw','post']){
    await choose('surface-select',surface);const q=await ready(region.id,condition.id,surface);
    check(q.panels.vanilla.candidate===condition.parent_candidate_id.replace(/raw$/,surface),'Matched G follows LC coefficient and protection',{region:region.id,condition:condition.id,surface,actual:q.panels.vanilla.candidate});
    check(q.panels.changed.candidate===condition.candidate_id.replace(/raw$/,surface),'LC actual selected candidate',{region:region.id,condition:condition.id,surface});
    for(const [key,p] of Object.entries(q.panels)){
     if(p.status==='reconstruction_failure'){check(p.rendered_triangles===0&&p.rendered_points===0,'Empty reconstruction remains explicit failure',{region:region.id,condition:condition.id,surface,key});continue;}
     check(p.status==='available'&&p.draw_calls>0,'Actual available source draws',{region:region.id,condition:condition.id,surface,key,status:p.status});
     check(p.representation==='mesh'?p.rendered_triangles===p.mesh_triangle_count&&p.rendered_triangles>0:p.rendered_points===p.display_sample_count&&p.rendered_points>0,'Exact declared triangles or point source drawn',{region:region.id,condition:condition.id,surface,key,triangles:p.rendered_triangles,points:p.rendered_points});
    }
    const cameras=Object.values(q.cameras);check(cameras.length===6&&cameras.every(c=>JSON.stringify(c.position)===JSON.stringify(cameras[0].position)&&JSON.stringify(c.target)===JSON.stringify(cameras[0].target)),'Six cameras synchronized',{region:region.id,condition:condition.id,surface});
   }
  }
  if(region.id==='P1'||region.id==='P3'){await choose('surface-select','raw');await ready(region.id,undefined,'raw');await capture(region.id+'_matched_mesh.png');}
 }
 await choose('representation-select','points');let q=await ready('P3',undefined,'raw','points');check(Object.values(q.panels).every(p=>p.rendered_points>0),'Points representation renders all sources');
 await choose('color-select','distance');q=await ready('P3',undefined,'raw','points');check(q.mode==='distance','Reference distance display changes color');
 await choose('prior-select','points');q=await ready('P3',undefined,'raw','points');check(q.panels.prior.candidate==='als_points','Original ALS points available');
 const images=await evaluate('Promise.all([...document.querySelectorAll("figure:not([hidden]) img")].map(i=>i.complete?Promise.resolve({src:i.src,w:i.naturalWidth}):new Promise(r=>{i.onload=()=>r({src:i.src,w:i.naturalWidth});i.onerror=()=>r({src:i.src,w:0});})))');check(images.length===2&&images.every(i=>i.w>0),'Linked real section and photograph rendered',images);
 const raster=await evaluate(`(()=>[...document.querySelectorAll('.panel')].map(p=>{const c=p.querySelector('canvas'),gl=c.getContext('webgl2')||c.getContext('webgl'),a=new Uint8Array(c.width*c.height*4);gl.readPixels(0,0,c.width,c.height,gl.RGBA,gl.UNSIGNED_BYTE,a);let n=0;for(let i=4;i<a.length;i+=4)if(a[i]!==a[0]||a[i+1]!==a[1]||a[i+2]!==a[2])n++;return {panel:p.dataset.panel,nonbackground:n};}))()`);check(raster.every(x=>x.nonbackground>10),'Actual nonbackground WebGL pixels',raster);
 receipt.status='PASS_ACTUAL_3D_MATCHED_CONDITIONS_RAW_POST';
}catch(error){receipt.status='FAIL';receipt.error=String(error);process.exitCode=1;}
finally{receipt.finished_at=new Date().toISOString();await fs.writeFile(out+'/receipt.json',JSON.stringify(receipt,null,2)+'\n',{flag:'wx'});await fs.writeFile(out+'/chromium.log',errors.join(''),{flag:'wx'});ws?.close();browser.kill('SIGTERM');xvfb.kill('SIGTERM');}
console.log(JSON.stringify({status:receipt.status,evaluated_conditions:receipt.evaluated_conditions,checks:checks.length,error:receipt.error,scientific_verdict:null}));
