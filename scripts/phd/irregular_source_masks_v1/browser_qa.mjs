// CPU-only, actual Chromium QA. Run in the pinned browser Docker image.
// QA_EVIDENCE_ROOT is an optional read-only mount of the served evidence directory.
// A browser/API roundtrip is reported separately from native-array comparison and
// neither check measures source-decision accuracy or temporal change correctness.
import fs from 'node:fs/promises';
import {spawn} from 'node:child_process';
import {createHash} from 'node:crypto';
import path from 'node:path';

const url=process.env.QA_URL||'http://127.0.0.1:8911/report/';
const output=process.env.QA_OUT||'/out';
const evidenceRoot=process.env.QA_EVIDENCE_ROOT;
const expected=['P1','P2','P3'];
const receipt={schema:'jbgs.irregular_source_masks.browser_qa.v1',status:'RUNNING',scientific_verdict:null,
  url,started_utc:new Date().toISOString(),checks:[],states:[],screenshots:[],resources:[],runtime_errors:[],
  pixel_validation:{status:'PENDING_NO_FINALIZED_CAMERA',browser_api_samples:0,native_array_samples:0,
    native_array_status:evidenceRoot?'PENDING_NO_FINALIZED_CAMERA':'NOT_CHECKED_NO_READ_ONLY_ARRAY_MOUNT',
    interpretation:'Rendering, coordinate routing, and transport checks only; no source accuracy or change-mask validation.'}};
const delay=ms=>new Promise(r=>setTimeout(r,ms));
const hash=x=>createHash('sha256').update(x).digest('hex');
let browser,socket,sequence=0;const pending=new Map();
function check(value,label,details){receipt.checks.push({pass:!!value,label,details});if(!value)throw Error(label)}
function send(method,params={}){return new Promise((resolve,reject)=>{const id=++sequence,timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout '+method))},30000);pending.set(id,{resolve:x=>{clearTimeout(timer);resolve(x)},reject:x=>{clearTimeout(timer);reject(x)}});socket.send(JSON.stringify({id,method,params}))})}
async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result?.value}
async function waitFor(expression,label){for(let n=0;n<200;n++){const r=await evaluate(expression);if(r)return r;await delay(75)}throw Error('Timed out '+label)}
async function settle(){await evaluate('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))')}
async function capture(name){await settle();const r=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});const bytes=Buffer.from(r.data,'base64');await fs.writeFile(path.join(output,name),bytes,{flag:'wx'});receipt.screenshots.push({path:name,sha256:hash(bytes),bytes:bytes.length})}
const visited=new Set();
async function resource(href,label){if(visited.has(href))return;check(new URL(href).origin===new URL(url).origin,'Local artifact origin',{href});const r=await fetch(href,{method:'HEAD'});check(r.status===200,'Artifact HTTP 200',{href,status:r.status});visited.add(href);receipt.resources.push({href,label,status:r.status})}
const media=p=>new URL('../evidence/'+p,url).href;
function canonical(value){if(Array.isArray(value))return value.map(canonical);if(value&&typeof value==='object')return Object.fromEntries(Object.keys(value).sort().map(k=>[k,canonical(value[k])]));return value}
function equal(a,b){return JSON.stringify(canonical(a))===JSON.stringify(canonical(b))}

async function nativePixels(region,camera,points){
  if(!evidenceRoot)return null;
  const script=`import json, sys
import numpy as np
from pathlib import Path
q=json.load(sys.stdin)
p=Path(q['root'])/q['region']/q['view']
m=json.loads((p/'camera.json').read_text())
h,w=m['height'],m['width']
def clean(v):
    if isinstance(v,np.ndarray): return clean(v.tolist())
    if isinstance(v,list): return [clean(x) for x in v]
    if isinstance(v,np.generic): return clean(v.item())
    if isinstance(v,float) and not np.isfinite(v): return None
    return v
out=[]
with np.load(p/'arrays.npz',allow_pickle=False) as a:
    for x,y in q['points']:
        values={}
        for key in a.files:
            v=a[key]
            if v.shape==(h,w): values[key]=clean(v[y,x])
            elif v.ndim==3 and v.shape[-2:]==(h,w): values[key]=clean(v[:,y,x])
            elif v.ndim==3 and v.shape[:2]==(h,w) and v.shape[2]<=32: values[key]=clean(v[y,x])
        out.append(dict(x=x,y=y,values=values))
print(json.dumps(out,allow_nan=False))
`;
  return new Promise((resolve,reject)=>{const p=spawn(process.env.QA_PYTHON||'python',['-c',script],{stdio:['pipe','pipe','pipe']});let out='',err='';p.stdout.on('data',x=>out+=x);p.stderr.on('data',x=>err+=x);p.on('error',reject);p.on('exit',code=>{if(code!==0)reject(Error('Native-array check failed: '+err));else{try{resolve(JSON.parse(out))}catch(e){reject(e)}}});p.stdin.end(JSON.stringify({root:evidenceRoot,region,view:camera.id,points}));});
}

async function pixelChecks(region,camera){
  const box=camera.roi_bbox||camera.bbox||[0,0,camera.width,camera.height];
  const x=Math.min(camera.width-1,Math.max(0,Math.floor((box[0]+box[2])/2)));
  const y=Math.min(camera.height-1,Math.max(0,Math.floor((box[1]+box[3])/2)));
  const points=[...new Map([[x,y],[0,0],[camera.width-1,camera.height-1]].map(p=>[p.join(','),p])).values()];
  const native=await nativePixels(region,camera,points);
  for(let i=0;i<points.length;i++){
    const [px,py]=points[i],q=new URLSearchParams({region,view:camera.id,x:String(px),y:String(py)});
    const r=await fetch(new URL('/api/pixel?'+q,url));
    check(r.status===200,'Finalized camera exposes exact pixel API',{region,view:camera.id,x:px,y:py,status:r.status});
    const j=await r.json();
    check(j.region===region&&j.view===camera.id&&j.x===px&&j.y===py&&j.values&&Object.keys(j.values).length>0&&j.scientific_verdict===null,'Pixel response retains coordinate identity and evidence-only status',{region,view:camera.id,x:px,y:py,fields:Object.keys(j.values||{})});
    if(native){check(equal(j.values,native[i].values),'API values exactly match mounted native arrays',{region,view:camera.id,x:px,y:py,fields:Object.keys(j.values).length});receipt.pixel_validation.native_array_samples++}
    if(i===0){
      await evaluate('fit()');await settle();
      const point=await evaluate(`(()=>{const b=document.querySelector('#result').getBoundingClientRect();return {x:b.left+b.width/2+(${px}+.5-cx)*scale,y:b.top+b.height/2+(${py}+.5-cy)*scale}})()`);
      await send('Input.dispatchMouseEvent',{type:'mousePressed',x:point.x,y:point.y,button:'left',clickCount:1});
      await send('Input.dispatchMouseEvent',{type:'mouseReleased',x:point.x,y:point.y,button:'left',clickCount:1});
    }else await evaluate(`inspect(${px},${py})`);
    const displayed=await waitFor(`(()=>{try{const p=JSON.parse(document.querySelector('#pixel').textContent);return p.region===${JSON.stringify(region)}&&p.view===${JSON.stringify(camera.id)}&&p.x===${px}&&p.y===${py}?p:false}catch{return false}})()`,'native pixel inspection');
    check(equal(displayed,j),'Browser inspection preserves complete API values including nulls',{region,view:camera.id,x:px,y:py,real_pointer_click:i===0});
    receipt.pixel_validation.browser_api_samples++;
  }
  const outside=await fetch(new URL('/api/pixel?'+new URLSearchParams({region,view:camera.id,x:String(camera.width),y:'0'}),url));
  check(outside.status===400,'Out-of-image pixel is rejected',{region,view:camera.id,status:outside.status});
}

try{
  await fs.mkdir(output,{recursive:true});
  const html=await fetch(url),dataResponse=await fetch(new URL('../evidence/data.json',url));
  check(html.ok,'Served report HTML available',{status:html.status});
  const htmlBytes=Buffer.from(await html.arrayBuffer());receipt.html_sha256=hash(htmlBytes);receipt.script_sha256=hash(await fs.readFile(new URL(import.meta.url)));
  let source=null;
  if(dataResponse.ok){const bytes=Buffer.from(await dataResponse.arrayBuffer());receipt.data_sha256=hash(bytes);source=JSON.parse(bytes);check(equal(source.regions.map(r=>r.id),expected),'Exact P1/P2/P3 source membership',source.regions.map(r=>r.id))}
  else check(dataResponse.status===404,'Absent evidence is an explicit pending state',{status:dataResponse.status});
  const profile=await fs.mkdtemp('/tmp/irregular-mask-qa-');
  browser=spawn('/usr/bin/chromium',['--headless=new','--no-sandbox','--no-first-run','--disable-dev-shm-usage','--disable-gpu','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank']);
  const logs=[];browser.stderr.on('data',x=>logs.push(x.toString()));let port;
  for(let i=0;i<150;i++){try{port=(await fs.readFile(profile+'/DevToolsActivePort','utf8')).split('\n')[0];break}catch{await delay(100)}}
  if(!port)throw Error('Chromium failed to start: '+logs.join('').slice(-2000));
  const tabs=await(await fetch('http://127.0.0.1:'+port+'/json/list')).json();socket=new WebSocket(tabs.find(x=>x.type==='page').webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject});
  socket.onmessage=e=>{const m=JSON.parse(e.data);if(m.method==='Runtime.exceptionThrown')receipt.runtime_errors.push(m.params);if(pending.has(m.id)){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m.result)}};
  await send('Page.enable');await send('Runtime.enable');receipt.chromium=await send('Browser.getVersion');
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1200,deviceScaleFactor:1,mobile:false});
  await send('Page.navigate',{url});
  await waitFor('document.querySelectorAll("#regions button").length===3','P1/P2/P3 selector including pending regions');
  // Freeze only browser auto-refresh so one immutable source snapshot is audited.
  // The served inputs and running extraction remain untouched.
  await evaluate('(()=>{const last=setInterval(()=>{},2147483647);for(let i=1;i<=last;i++)clearInterval(i)})()');
  await evaluate('refresh()');
  const live=await evaluate('data');if(live)source=live;
  receipt.browser_data_sha256=hash(Buffer.from(await evaluate('dataSignature||JSON.stringify(data)')));
  for(const r of source?.regions||[])check((r.cameras||[]).length<=3&&new Set((r.cameras||[]).map(c=>c.id)).size===(r.cameras||[]).length,'Available cameras are unique and within the three-view contract',{region:r.id,views:(r.cameras||[]).map(c=>c.id)});
  receipt.available_cameras=source?.regions?.reduce((n,r)=>n+(r.cameras?.length||0),0)||0;
  receipt.completed_cameras=source?.regions?.reduce((n,r)=>n+(r.cameras||[]).filter(c=>c.status?.startsWith('COMPLETE')).length,0)||0;
  for(const width of [1440,1920]){
    await send('Emulation.setDeviceMetricsOverride',{width,height:1200,deviceScaleFactor:1,mobile:false});
    for(let ri=0;ri<expected.length;ri++){
      const region=expected[ri],cameras=source?.regions?.find(r=>r.id===region)?.cameras||[];
      await evaluate(`document.querySelectorAll('#regions button')[${ri}].click()`);
      await waitFor(`regionId===${JSON.stringify(region)}&&document.querySelector('#regions button.active')?.textContent.startsWith(${JSON.stringify(region)})`,'selected region');
      check(await evaluate(`document.querySelector('#camera').options.length`)===cameras.length,'Camera selector matches available views',{region,width,count:cameras.length});
      if(!cameras.length){
        await settle();await delay(150);
        const state=await evaluate(`({cam:cam===null,rgb:rgb===null,layer:layerImage===null,options:document.querySelector('#layer').options.length,counts:document.querySelector('#counts').children.length,pixel:document.querySelector('#pixel').textContent,viewport:innerWidth,scroll:document.documentElement.scrollWidth,error:document.querySelector('#error').textContent})`);
        check(state.cam&&state.rgb&&state.layer&&state.options===0&&state.counts===0&&state.scroll<=state.viewport+1&&!state.error,'Pending region has stable empty state, no stale image or counts',{region,width,...state});
        receipt.states.push({region,width,pending:true});
        if(width===1440)await capture(region+'_pending_1440.png');
        continue;
      }
      for(const camera of cameras){
        await evaluate(`document.querySelector('#camera').value=${JSON.stringify(camera.id)};document.querySelector('#camera').dispatchEvent(new Event('change'))`);
        await waitFor(`cam?.id===${JSON.stringify(camera.id)}&&rgb?.complete&&rgb.naturalWidth>0`,'actual native RGB');
        const expectedRgb=media(camera.rgb||camera.photo||((camera.folder||region+'/'+camera.id)+'/rgb.jpg'));
        const rgbState=await evaluate(`({src:rgb.src,width:rgb.naturalWidth,height:rgb.naturalHeight})`);
        check(rgbState.src===expectedRgb&&rgbState.width===camera.width&&rgbState.height===camera.height,'RGB path and intrinsic dimensions match native camera',{region,view:camera.id,width,...rgbState,expected:[camera.width,camera.height]});
        await resource(expectedRgb,'native RGB');
        const layers=camera.layers||[];
        check(await evaluate(`document.querySelector('#layer').options.length`)===layers.length,'All declared source layers selectable',{region,view:camera.id,layers:layers.length});
        for(const layer of layers){
          await evaluate(`document.querySelector('#layer').value=${JSON.stringify(layer.id)};document.querySelector('#layer').dispatchEvent(new Event('change'))`);
          await waitFor(`layerImage?.complete&&layerImage.src===${JSON.stringify(media(layer.path))}`,'actual native layer');
          const state=await evaluate(`({src:layerImage.src,width:layerImage.naturalWidth,height:layerImage.naturalHeight,title:document.querySelector('#result-title').textContent,viewport:innerWidth,scroll:document.documentElement.scrollWidth,canvas:[...document.querySelectorAll('canvas')].map(c=>({width:c.width,height:c.height,right:c.getBoundingClientRect().right})),error:document.querySelector('#error').textContent})`);
          check(state.width===camera.width&&state.height===camera.height&&state.title===layer.label,'Layer retains native dimensions and declared identity',{region,view:camera.id,layer:layer.id,...state});
          check(state.scroll<=state.viewport+1&&state.canvas.every(c=>c.width>0&&c.height>0&&c.right<=state.viewport+1),'Desktop has no horizontal overflow or empty canvas',{region,view:camera.id,layer:layer.id,width});
          check(!state.error,'No application loading error',{region,view:camera.id,layer:layer.id,error:state.error});
          await resource(state.src,'native layer');receipt.states.push({region,view:camera.id,layer:layer.id,width,pending:false,camera_status:camera.status});
        }
        await evaluate(`document.querySelector('#roi').click()`);check(await evaluate('Number.isFinite(scale)&&scale>0&&Number.isFinite(cx)&&Number.isFinite(cy)'),'ROI fit uses finite image coordinates',{region,view:camera.id,width});
        await evaluate(`document.querySelector('#fit').click()`);
        if(width===1440){
          // In-progress arrays can be atomically republished during inspection.
          // Compare exact numerical values only after camera completion seals them.
          if(camera.status?.startsWith('COMPLETE'))await pixelChecks(region,camera);
          for(const link of await evaluate(`[...document.querySelectorAll('#files a')].map(a=>a.href)`))await resource(link,'native evidence');
          if(camera===cameras[0]){
            const decisionLayer=layers.find(l=>l.id==='decision')||layers[0];
            if(decisionLayer){await evaluate(`document.querySelector('#layer').value=${JSON.stringify(decisionLayer.id)};document.querySelector('#layer').dispatchEvent(new Event('change'))`);await waitFor(`layerImage?.complete&&layerImage.src===${JSON.stringify(media(decisionLayer.path))}`,'decision layer screenshot')}
            await evaluate(`document.querySelector('#roi').click();window.scrollTo(0,document.querySelector('.panels').offsetTop-120)`);
            await capture(region+(camera.status?.startsWith('COMPLETE')?'_available':'_partial')+'_1440.png');
            await evaluate('window.scrollTo(0,0)');
          }
        }
      }
    }
  }
  check(receipt.runtime_errors.length===0,'No browser runtime exception',receipt.runtime_errors);
  if(receipt.pixel_validation.browser_api_samples)receipt.pixel_validation.status='PASS_BROWSER_API_ROUNDTRIP';
  if(receipt.pixel_validation.native_array_samples)receipt.pixel_validation.native_array_status='PASS_SAMPLED_NATIVE_ARRAY_EQUALITY';
  receipt.status=receipt.completed_cameras===9?'PASS_ACTUAL_BROWSER':receipt.available_cameras?'PASS_ACTUAL_BROWSER_PARTIAL_DATA':'PASS_ACTUAL_BROWSER_PENDING_DATA';
  receipt.interpretation='Browser behavior is verified only for the recorded available views. Pending data, unsampled numerical values, region accuracy, and scientific validity remain unverified.';
}catch(error){receipt.status='FAIL_BROWSER_QA';receipt.error=String(error);process.exitCode=1;if(socket?.readyState===1){try{await capture('failure.png')}catch{}}}
finally{receipt.finished_utc=new Date().toISOString();await fs.mkdir(output,{recursive:true});await fs.writeFile(path.join(output,'receipt.json'),JSON.stringify(receipt,null,2)+'\n',{flag:'wx'});socket?.close();browser?.kill('SIGTERM')}
console.log(JSON.stringify({status:receipt.status,checks:receipt.checks.length,states:receipt.states.length,screenshots:receipt.screenshots.length,pixel_validation:receipt.pixel_validation,error:receipt.error}));
