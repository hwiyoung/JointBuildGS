// Browser UI QA only; Node built-ins, no project dependencies or user profile.
// Start a separate Chrome with --enable-automation --remote-debugging-port=9228
// --user-data-dir=/tmp/jbgs-p2-ab-v2-qa.<unique> before invoking this driver.
// Usage: node c_browser_qa.mjs URL FRESH_OUTPUT_DIRECTORY /tmp/jbgs-p2-ab-v2-qa.PROFILE [9228] [EXPECTED_ARM_COUNT]
import net from 'node:net';
import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';

const [url,out,profile,port='9228',expectedArmCountArgument]=process.argv.slice(2);
if(!url||!out||!profile)throw Error('Usage: node c_browser_qa.mjs URL FRESH_OUTPUT_DIRECTORY /tmp/jbgs-p2-ab-v2-qa.PROFILE [9228] [EXPECTED_ARM_COUNT]');
const expectedArmCount=expectedArmCountArgument===undefined?null:Number(expectedArmCountArgument);
if(expectedArmCount!==null&&(!Number.isSafeInteger(expectedArmCount)||expectedArmCount<1))throw Error('Expected arm count must be a positive integer');
if(!profile.startsWith('/tmp/jbgs-p2-ab-v2-qa.')||profile.includes('..'))throw Error('A task-specific fresh /tmp Chrome profile is required');
if(!['127.0.0.1','localhost'].includes(new URL(url).hostname))throw Error('QA expects the explicitly authorized local read-only viewer server');
await fs.mkdir(out,{recursive:false});
await fs.writeFile(path.join(out,'source_c_browser_qa.mjs'),await fs.readFile(new URL(import.meta.url)),{flag:'wx'});
await fs.writeFile(path.join(out,'run_configuration.json'),JSON.stringify({url,out,profile,port:Number(port),expected_arm_count:expectedArmCount,scientific_verdict:null},null,2)+'\n',{flag:'wx'});
const pages=await(await fetch(`http://127.0.0.1:${Number(port)}/json/list`)).json();
const target=pages.find(p=>p.type==='page');if(!target)throw Error('No isolated Chrome page');
const ws=new URL(target.webSocketDebuggerUrl),socket=net.createConnection({host:ws.hostname,port:Number(ws.port)});
let stream=Buffer.alloc(0),handshake=false,nextId=1,fragments=[];
const pending=new Map(),events=[];
const connected=new Promise((resolve,reject)=>{
 socket.on('error',reject);
 socket.on('connect',()=>socket.write(`GET ${ws.pathname} HTTP/1.1\r\nHost: ${ws.host}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: ${crypto.randomBytes(16).toString('base64')}\r\nSec-WebSocket-Version: 13\r\n\r\n`));
 socket.on('data',data=>{
  stream=Buffer.concat([stream,data]);
  if(!handshake){const end=stream.indexOf('\r\n\r\n');if(end<0)return;const head=stream.subarray(0,end).toString();if(!head.startsWith('HTTP/1.1 101'))return reject(Error(head));stream=stream.subarray(end+4);handshake=true;resolve();}
  while(stream.length>=2){
   const final=!!(stream[0]&128),opcode=stream[0]&15;let len=stream[1]&127,offset=2;
   if(len===126){if(stream.length<4)return;len=stream.readUInt16BE(2);offset=4;}else if(len===127){if(stream.length<10)return;len=Number(stream.readBigUInt64BE(2));offset=10;}
   if(stream.length<offset+len)return;
   const body=stream.subarray(offset,offset+len);stream=stream.subarray(offset+len);
   if(opcode!==1&&opcode!==0)continue;
   fragments.push(body);if(!final)continue;
   const obj=JSON.parse(Buffer.concat(fragments).toString());fragments=[];
   if(obj.id){const p=pending.get(obj.id);if(p){pending.delete(obj.id);obj.error?p.reject(Error(JSON.stringify(obj.error))):p.resolve(obj.result);}}
   else if(obj.method)events.push(obj);
  }
 });
});
await connected;
function send(method,params={}){
 const id=nextId++,body=Buffer.from(JSON.stringify({id,method,params})),mask=crypto.randomBytes(4);let header;
 if(body.length<126){header=Buffer.from([0x81,0x80|body.length]);}else if(body.length<65536){header=Buffer.alloc(4);header[0]=0x81;header[1]=0x80|126;header.writeUInt16BE(body.length,2);}else{header=Buffer.alloc(10);header[0]=0x81;header[1]=0x80|127;header.writeBigUInt64BE(BigInt(body.length),2);}
 for(let i=0;i<body.length;i++)body[i]^=mask[i%4];
 return new Promise((resolve,reject)=>{pending.set(id,{resolve,reject});socket.write(Buffer.concat([header,mask,body]));setTimeout(()=>{if(pending.has(id)){pending.delete(id);reject(Error('CDP timeout '+method));}},30000).unref();});
}
async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result?.value;}
const pause=ms=>new Promise(r=>setTimeout(r,ms));
const screenshots=[],checks=[];
function check(condition,name,detail){checks.push({name,pass:!!condition,detail});if(!condition)throw Error(name+': '+JSON.stringify(detail));}
async function capture(name){const r=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});const bytes=Buffer.from(r.data,'base64');const file=path.join(out,name+'.png');await fs.writeFile(file,bytes,{flag:'wx'});const entry={path:file,sha256:crypto.createHash('sha256').update(bytes).digest('hex')};screenshots.push(entry);return entry;}
async function state(){return evaluate(`({ready:!!window.P2_GAUSSIAN_VIEWER_READY,state:window.P2_GAUSSIAN_VIEWER_STATE,error:document.getElementById('error')?.textContent,gl:window.__P2_QA_GL?.map(x=>({...x}))})`);}
async function waitState(expected){
 for(let i=0;i<120;i++){const s=await state();if(s.error)throw Error(s.error);if(s.ready&&s.state&&Object.entries(expected).every(([k,v])=>s.state[k]===v)){await pause(100);return s;}await pause(250);}
 throw Error('Viewer state timeout '+JSON.stringify(expected));
}
async function choose(id,value,expected){await evaluate(`(()=>{const e=document.getElementById(${JSON.stringify(id)});e.value=${JSON.stringify(String(value))};e.dispatchEvent(new Event('change',{bubbles:true}));})()`);return waitState(expected);}
async function frames(){
 return evaluate(`(async()=>Promise.all([...document.querySelectorAll('.canvas canvas')].map(async c=>{
  const tmp=document.createElement('canvas');tmp.width=128;tmp.height=96;const ctx=tmp.getContext('2d');ctx.drawImage(c,0,0,128,96);const a=ctx.getImageData(0,0,128,96).data;
  let nonBackground=0;for(let i=0;i<a.length;i+=4)if(Math.abs(a[i]-32)+Math.abs(a[i+1]-42)+Math.abs(a[i+2]-38)>12)nonBackground++;
  const h=await crypto.subtle.digest('SHA-256',a);return {width:c.width,height:c.height,nonBackground,sampledPixelSha256:[...new Uint8Array(h)].map(x=>x.toString(16).padStart(2,'0')).join('')};
 })))()`);
}
function frameChanged(a,b){return a.some((x,i)=>x.sampledPixelSha256!==b[i]?.sampledPixelSha256);}
const instrumentation=`(()=>{
 const original=HTMLCanvasElement.prototype.getContext;window.__P2_QA_GL=[];const seen=new WeakSet();
 HTMLCanvasElement.prototype.getContext=function(kind,...args){const gl=original.call(this,kind,...args);if(!gl||!String(kind).startsWith('webgl')||seen.has(gl))return gl;seen.add(gl);
  const ext=gl.getExtension('WEBGL_debug_renderer_info'),entry={kind,version:gl.getParameter(gl.VERSION),renderer:ext?gl.getParameter(ext.UNMASKED_RENDERER_WEBGL):null,draws:0,triangles:0,points:0,lastMode:null,lastCount:0};window.__P2_QA_GL.push(entry);
  const uniformNames=new WeakMap(),getLocation=gl.getUniformLocation.bind(gl),uploadMatrix=gl.uniformMatrix4fv.bind(gl);
  gl.getUniformLocation=function(program,name){const location=getLocation(program,name);if(location)uniformNames.set(location,name);return location};
  gl.uniformMatrix4fv=function(location,transpose,matrix,...extra){const name=location&&uniformNames.get(location);if(name==='projectionMatrix'||name==='modelViewMatrix')entry[name]=Array.from(matrix);return uploadMatrix(location,transpose,matrix,...extra)};
  for(const key of ['drawArrays','drawElements','drawArraysInstanced','drawElementsInstanced']){const originalDraw=gl[key]?.bind(gl);if(!originalDraw)continue;gl[key]=function(...a){entry.draws++;entry.lastMode=a[0];entry.lastCount=key.includes('Arrays')?a[2]:a[1];if(a[0]===gl.TRIANGLES)entry.triangles++;if(a[0]===gl.POINTS)entry.points++;return originalDraw(...a)};}
  return gl;
 };
})()`;
try{
 const command=await send('Browser.getBrowserCommandLine');
 check(command.arguments.includes('--user-data-dir='+profile),'task_specific_profile_verified',{profile,port:Number(port)});
 const browser=await send('Browser.getVersion');
 await send('Page.enable');await send('Runtime.enable');await send('Log.enable');await send('Network.enable');
 await send('Page.addScriptToEvaluateOnNewDocument',{source:instrumentation});events.length=0;
 await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1150,deviceScaleFactor:1,mobile:false});
 await send('Page.navigate',{url});
 const initial=await waitState({mode:'gaussian'});
 const inspection=await evaluate(`(async()=>{const r=await fetch('inspection.json');if(!r.ok)throw Error('inspection '+r.status);const d=await r.json();return {schema:d.schema,center:d.center,span:d.span,browser_rendering:d.browser_rendering,arms:d.arms}})()`);
 check(inspection.arms.length>0,'actual_arms_present',inspection.arms.length);
 check(new Set(inspection.arms.map(a=>a.id)).size===inspection.arms.length,'unique_arm_ids',inspection.arms.map(a=>a.id));
 if(expectedArmCount!==null)check(inspection.arms.length===expectedArmCount,'exact_expected_arm_count',{expected:expectedArmCount,actual:inspection.arms.length});
 check(initial.gl?.length===2&&initial.gl.every(g=>g.kind==='webgl2'),'two_webgl2_renderers',initial.gl);
 const nativeEvalIds=new Set([542,435,331,555,427,412,333,543,338,394,361]);
 const armChecks=[];
 for(let ai=0;ai<inspection.arms.length;ai++){
  const arm=inspection.arms[ai];
  await choose('arm',ai,{arm:arm.id,mode:'gaussian',section:false});
  const blocks=await evaluate(`(async()=>{const arm=${JSON.stringify(arm)};return Promise.all(['initial','final'].map(async stage=>{
   const response=await fetch(arm[stage].url);if(!response.ok)throw Error('block HTTP '+response.status);const b=await response.json(),n=b.count,result={stage,count:n,role:b.role,thinned:b.thinned,fields:{},positiveScales:true,validQuaternions:true,opacityRange:true,rgbRange:true};
   for(const [key,multiple] of Object.entries({xyz:3,scales:3,quats:4,opacity:1,rgb:3}))result.fields[key]={length:b[key]?.length,expected:n*multiple,finite:Array.isArray(b[key])&&b[key].every(Number.isFinite)};
   result.positiveScales=b.scales.every(x=>x>0);for(let i=0;i<n;i++)if(Math.hypot(...b.quats.slice(i*4,i*4+4))<1e-6)result.validQuaternions=false;
   result.opacityRange=b.opacity.every(x=>x>=0&&x<=1);result.rgbRange=b.rgb.every(x=>x>=0&&x<=1);return result;
  }))})()`);
  for(const b of blocks)check(b.count===arm[b.stage].count&&b.role==='actual_saved_gaussian_parameters'&&b.thinned===false&&Object.values(b.fields).every(f=>f.length===f.expected&&f.finite)&&b.positiveScales&&b.validQuaternions&&b.opacityRange&&b.rgbRange,'actual_parameters_'+arm.id+'_'+b.stage,b);
  const gaussianState=await state(),gaussianFrames=await frames();
  check(gaussianState.state.meshCounts.every((n,i)=>n===blocks[i].count),'actual_mesh_counts_'+arm.id,gaussianState);
  check(gaussianState.gl.every(g=>g.lastMode===4&&g.lastCount>0),'triangle_draw_'+arm.id,gaussianState.gl);
  check(gaussianFrames.every(f=>f.nonBackground>0),'nonempty_gaussian_pixels_'+arm.id,gaussianFrames);
  if(ai===0)await capture('desktop_gaussian_initial_final');
  const centersState=await choose('mode','centers',{arm:arm.id,mode:'centers'}),centersFrames=await frames();
  check(centersState.state.meshCounts.every(n=>n===0)&&centersState.gl.every(g=>g.lastMode===0),'centers_use_points_'+arm.id,centersState);
  check(frameChanged(gaussianFrames,centersFrames),'gaussian_centers_actual_draw_changed_'+arm.id,{gaussianFrames,centersFrames});
  if(ai===0)await capture('desktop_centers');
  const sourceState=await choose('mode','source',{arm:arm.id,mode:'source'});
  check(sourceState.state.meshCounts.every(n=>n===0)&&sourceState.state.counts.every(n=>n===arm.initial.count),'same_initial_support_points_'+arm.id,sourceState);
  await choose('mode','gaussian',{arm:arm.id,mode:'gaussian'});
  const imageChecks=[];
  const actualImageIds=arm.images.map(i=>Number(i.image_id));
  check(actualImageIds.length===nativeEvalIds.size&&new Set(actualImageIds).size===nativeEvalIds.size&&actualImageIds.every(i=>nativeEvalIds.has(i)),
   'complete_unique_frozen_evaluation_triplets_'+arm.id,{expected:[...nativeEvalIds],actual:actualImageIds});
  for(let vi=0;vi<arm.images.length;vi++){
   const image=arm.images[vi];
   check(nativeEvalIds.has(Number(image.image_id)),'frozen_evaluation_role_'+arm.id+'_'+image.image_id,image.camera);
   check(image.camera&&['eval','appearance_eval'].includes(image.camera.role),'camera_role_provenance_'+arm.id+'_'+image.image_id,image.camera);
   check(/^[0-9a-f]{64}$/.test(arm.source_B_views_sha256||image.source_B_views_sha256||''),'source_views_hash_'+arm.id+'_'+image.image_id,{arm:arm.source_B_views_sha256,image:image.source_B_views_sha256});
   const camera=image.camera,validMatrix=(m,n)=>Array.isArray(m)&&m.length===n&&m.every(r=>Array.isArray(r)&&r.length===n&&r.every(Number.isFinite));
   check(validMatrix(camera.K,3)&&(validMatrix(camera.viewmat,4)||(validMatrix(camera.R,3)&&Array.isArray(camera.t)&&camera.t.length===3&&camera.t.every(Number.isFinite))),'finite_camera_matrices_'+arm.id+'_'+image.image_id,camera);
   await evaluate(`(()=>{const e=document.getElementById('view');e.value=${JSON.stringify(String(vi))};e.dispatchEvent(new Event('change',{bubbles:true}));})()`);
   const decoded=await evaluate(`Promise.all([...document.querySelectorAll('#photos img')].map(async i=>{await i.decode();const bytes=await(await fetch(i.src)).arrayBuffer(),digest=await crypto.subtle.digest('SHA-256',bytes);return {src:i.getAttribute('src'),alt:i.alt,width:i.naturalWidth,height:i.naturalHeight,loaded:i.complete&&i.naturalWidth>0,sha256:[...new Uint8Array(digest)].map(x=>x.toString(16).padStart(2,'0')).join('')}}))`);
   check(decoded.length===3&&decoded.every(i=>i.loaded&&i.width===image.camera.width&&i.height===image.camera.height&&i.alt.endsWith(' '+image.image_id)),'same_camera_triplet_'+arm.id+'_'+image.image_id,decoded);
   check(decoded.every((i,k)=>i.src===image[['target','initial','final'][k]]),'triplet_source_paths_'+arm.id+'_'+image.image_id,decoded);
   check(decoded.every((i,k)=>i.sha256===image.image_sha256?.[['target','initial','final'][k]]),'triplet_original_output_bytes_'+arm.id+'_'+image.image_id,decoded);
   imageChecks.push({image_id:image.image_id,camera:image.camera,decoded});
  }
  armChecks.push({id:arm.id,blocks,gaussianState,gaussianFrames,centersFrames,imageChecks});
  console.log(JSON.stringify({arm:ai+1,of:inspection.arms.length,id:arm.id,checkedViews:imageChecks.length}));
 }
 await choose('arm',0,{arm:inspection.arms[0].id,mode:'gaussian'});
 const beforeDrag=await frames(),rect=await evaluate(`(()=>{const r=document.getElementById('initial').getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height}})()`);
 await send('Input.dispatchMouseEvent',{type:'mousePressed',x:rect.x+rect.width/2,y:rect.y+rect.height/2,button:'left',clickCount:1});
 await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:rect.x+rect.width/2+100,y:rect.y+rect.height/2+35,button:'left',buttons:1});
 await send('Input.dispatchMouseEvent',{type:'mouseReleased',x:rect.x+rect.width/2+100,y:rect.y+rect.height/2+35,button:'left',clickCount:1});
 const afterDrag=await frames();check(frameChanged(beforeDrag,afterDrag),'drag_changes_rendered_pixels',{beforeDrag,afterDrag});await capture('desktop_dragged');
 await evaluate(`document.getElementById('section').click()`);const sectionState=await waitState({section:true}),sectionFrames=await frames();
 check(sectionState.state.meshCounts.every((n,i)=>n>=0&&n<=sectionState.state.counts[i])&&sectionState.state.meshCounts.some((n,i)=>n<sectionState.state.counts[i]),'section_selects_subset',sectionState);await capture('desktop_section');
 await evaluate(`document.getElementById('oblique').click()`);await waitState({section:false});
 await evaluate(`document.getElementById('top').click()`);await pause(150);await capture('desktop_top');
 await evaluate(`document.getElementById('oblique').click()`);await waitState({section:false});
 await evaluate(`document.getElementById('photos').scrollIntoView({block:'center'})`);await capture('native_view_triplet');await evaluate('window.scrollTo(0,0)');
 await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});await pause(150);
 const mobile=await evaluate(`({viewport:[innerWidth,innerHeight],scrollWidth:document.documentElement.scrollWidth,clientWidth:document.documentElement.clientWidth,overflow:document.documentElement.scrollWidth>document.documentElement.clientWidth,canvasBoxes:[...document.querySelectorAll('.canvas canvas')].map(c=>{const r=c.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height}})})`);
 check(!mobile.overflow&&mobile.canvasBoxes.every(r=>r.width>0&&r.x>=0&&r.x+r.width<=mobile.clientWidth+1),'mobile_390_layout',mobile);
 const mobileFraming=await evaluate(`(async()=>{
  const arm=${JSON.stringify(inspection.arms[0])},center=${JSON.stringify(inspection.center)};
  const multiply=(m,p)=>[0,1,2,3].map(r=>m[r]*p[0]+m[r+4]*p[1]+m[r+8]*p[2]+m[r+12]*p[3]);
  return Promise.all(['initial','final'].map(async(stage,panel)=>{
   const b=await(await fetch(arm[stage].url)).json(),gl=window.__P2_QA_GL[panel],mv=gl.modelViewMatrix,projection=gl.projectionMatrix;
   if(![mv,projection].every(m=>Array.isArray(m)&&m.length===16&&m.every(Number.isFinite)))throw Error('Actual WebGL camera matrices unavailable');
   let outsideCenters=0;const ndcMin=[Infinity,Infinity],ndcMax=[-Infinity,-Infinity];
   for(let i=0;i<b.count;i++){
    const position=[...b.xyz.slice(3*i,3*i+3).map((v,k)=>v-center[k]),1],clip=multiply(projection,multiply(mv,position)),ndc=[clip[0]/clip[3],clip[1]/clip[3]];
    if(!ndc.every(Number.isFinite))throw Error('Nonfinite projected center');
    if(ndc.some(v=>Math.abs(v)>1+1e-6))outsideCenters++;
    for(let k=0;k<2;k++){ndcMin[k]=Math.min(ndcMin[k],ndc[k]);ndcMax[k]=Math.max(ndcMax[k],ndc[k]);}
   }
   return {stage,count:b.count,outsideCenters,ndcMin,ndcMax,modelViewMatrix:mv,projectionMatrix:projection};
  }));
 })()`);
 check(mobileFraming.every(p=>p.outsideCenters===0),'mobile_actual_camera_contains_all_centers',mobileFraming);await capture('mobile_390');
 const errors=events.filter(e=>e.method==='Runtime.exceptionThrown'||(e.method==='Runtime.consoleAPICalled'&&e.params.type==='error')||(e.method==='Log.entryAdded'&&e.params.entry.level==='error'&&e.params.entry.source!=='network'));
 const networkFailures=events.filter(e=>e.method==='Network.loadingFailed'||(e.method==='Network.responseReceived'&&e.params.response.status>=400));
 check(errors.length===0,'no_javascript_or_browser_errors',errors);check(networkFailures.length===0,'no_failed_network_requests',networkFailures);
 const result={task_id:'PHD-P2-AB-V2-GAUSSIAN-BROWSER-QA',status:'PASS_BROWSER_PARAMETER_INSPECTION_AND_INTERACTION_ONLY',scientific_verdict:null,url,browser,profile,port:Number(port),source_sha256:crypto.createHash('sha256').update(await fs.readFile(new URL(import.meta.url))).digest('hex'),initial,inspection,armChecks,sectionState,sectionFrames,mobile,mobileFraming,checks,screenshots,errors,networkFailures,
  limits:['Does not claim equality of the browser kernel compositor to gsplat.','Point visibility alone is never a Gaussian rendering PASS.','Native camera linkage follows the exporter receipt; independent geometry accuracy remains outside browser QA.','UI QA does not establish source currentness, detail recovery, scientific performance, or confirmatory inference.']};
 await fs.writeFile(path.join(out,'browser_qa.json'),JSON.stringify(result,null,2)+'\n',{flag:'wx'});
 console.log(JSON.stringify({status:result.status,armCount:armChecks.length,checkCount:checks.length,screenshots},null,2));
}catch(e){await fs.writeFile(path.join(out,'FAILED.json'),JSON.stringify({error:String(e),checks,events,scientific_verdict:null},null,2)+'\n',{flag:'wx'});throw e;}finally{socket.end();}
