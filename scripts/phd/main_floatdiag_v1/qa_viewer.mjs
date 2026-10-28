/* Offline file:// interaction and rendering checks, CPU Mesa llvmpipe only. */
import {spawn} from 'node:child_process';
import {mkdirSync,writeFileSync} from 'node:fs';
const stage=process.env.FLOATDIAG_QA_STAGE||'A1';const out='/out/qa/'+stage;mkdirSync(out,{recursive:true});
const xvfb=spawn('/usr/bin/Xvfb',[':99','-screen','0','1440x1800x24','-nolisten','tcp'],{stdio:'ignore'});
await new Promise(r=>setTimeout(r,500));
const browser=spawn('/usr/bin/chromium',['--headless=new','--no-sandbox','--disable-dev-shm-usage',
  '--ozone-platform=x11','--disable-features=Vulkan','--disable-gpu-sandbox','--ignore-gpu-blocklist',
  '--use-gl=angle','--use-angle=gl','--disable-background-networking',
  '--disable-extensions','--no-zygote','--allow-file-access-from-files','--remote-debugging-port=9247',
  '--user-data-dir=/tmp/floatdiag-browser','about:blank'],{stdio:['ignore','ignore','pipe'],env:{...process.env,DISPLAY:':99',LIBGL_ALWAYS_SOFTWARE:'1',GALLIUM_DRIVER:'llvmpipe'}});
let log='',ws,id=0;browser.stderr.on('data',b=>log+=b.toString());
const pending=new Map(),errors=[],requests=[],checks=[];const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function cmd(method,params={}){return new Promise((resolve,reject)=>{const n=++id,t=setTimeout(()=>reject(Error('CDP timeout '+method)),30000);pending.set(n,{resolve:r=>{clearTimeout(t);resolve(r)},reject:e=>{clearTimeout(t);reject(e)}});ws.send(JSON.stringify({id:n,method,params}));});}
async function evaluate(expression){const r=await cmd('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.text);return r.result.value;}
try {
  let pages;for(let i=0;i<100;i++){try{pages=await(await fetch('http://127.0.0.1:9247/json/list')).json();break;}catch{await sleep(100);}}
  if(!pages)throw Error('Chromium did not start');
  ws=new WebSocket(pages.find(p=>p.type==='page').webSocketDebuggerUrl);await new Promise(r=>ws.onopen=r);
  ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id){const p=pending.get(m.id);pending.delete(m.id);if(p)m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m.result);}else if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails);else if(m.method==='Network.requestWillBeSent')requests.push(m.params.request.url);};
  await cmd('Page.enable');await cmd('Runtime.enable');await cmd('Network.enable');
  await cmd('Emulation.setDeviceMetricsOverride',{width:1400,height:1000,deviceScaleFactor:1,mobile:false});
  await cmd('Page.navigate',{url:'file:///docs/보기/index.html'});
  for(let i=0;i<200;i++){if(await evaluate('document.querySelectorAll("canvas[data-rendered=true]").length===7'))break;await sleep(100);}
  const total=await evaluate('document.querySelectorAll("canvas[data-rendered=true]").length');if(total!==7)throw Error('Seven 3D cases required: '+total);
  const interactions=await evaluate(`(()=>{const out=[];for(const host of document.querySelectorAll('[data-viewer]')){const canvas=host.querySelector('canvas'),[result,palette]=host.querySelectorAll('select');canvas.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight'}));const camera=canvas.dataset.camera;for(let i=0;i<3;i++)for(let j=0;j<2;j++){result.selectedIndex=i;palette.selectedIndex=j;result.dispatchEvent(new Event('change'));out.push({case:host.dataset.viewer,result:result.value,palette:palette.value,cameraPreserved:canvas.dataset.camera===camera,faces:Number(canvas.dataset.faces),glError:Number(canvas.dataset.glError),model:canvas.dataset.model});}host.querySelector('button').click();}return out;})()`);
  if(interactions.length!==42||interactions.some(x=>!x.cameraPreserved||x.faces<=0||x.glError!==0))throw Error('GLB or camera interaction failure');
  checks.push(...interactions);
  await evaluate(`Promise.all([...document.images].map(x=>{x.loading='eager';return x.decode().catch(()=>null)}))`);
  const badImages=await evaluate(`[...document.images].filter(x=>!x.complete||x.naturalWidth===0).map(x=>x.src)`);if(badImages.length)throw Error('Missing images '+badImages);
  const broken=await evaluate(`[...document.querySelectorAll('a[href^="#"]')].filter(a=>!document.getElementById(decodeURIComponent(a.hash.slice(1)))).map(a=>a.hash)`);if(broken.length)throw Error('Broken anchors '+broken);
  for(const width of [1400,360]){
    await cmd('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:false});await sleep(300);
    const overflow=await evaluate('document.documentElement.scrollWidth>innerWidth+1');if(overflow)throw Error('Page horizontal overflow '+width);
    await evaluate('scrollTo(0,0)');const shot=await cmd('Page.captureScreenshot',{format:'png'});writeFileSync(out+'/page_'+width+'.png',Buffer.from(shot.data,'base64'));
  }
  await cmd('Emulation.setDeviceMetricsOverride',{width:1400,height:1000,deviceScaleFactor:1,mobile:false});
  for(let i=0;i<7;i++){await evaluate(`document.querySelectorAll('[data-viewer]')[${i}].scrollIntoView()`);await sleep(200);const shot=await cmd('Page.captureScreenshot',{format:'png'});writeFileSync(out+'/case_'+i+'.png',Buffer.from(shot.data,'base64'));}
  await cmd('Emulation.setDeviceMetricsOverride',{width:1000,height:stage==='A2'?1700:780,deviceScaleFactor:1,mobile:false});
  for(let i=0;i<7;i++){
    await evaluate(`(()=>{document.getElementById('blind-review')?.remove();const box=document.createElement('div');box.id='blind-review';box.style='position:fixed;inset:0;z-index:99999;background:white;overflow:hidden';const im=document.createElement('img');im.src=FLOATDIAG_DATA.cases[${i}].plate;im.style='width:1000px;max-width:none;display:block;margin-top:-35px';box.append(im);document.body.append(box);return im.decode();})()`);
    const shot=await cmd('Page.captureScreenshot',{format:'png'});writeFileSync(out+'/blind_'+i+'.png',Buffer.from(shot.data,'base64'));
  }
  await evaluate(`document.getElementById('blind-review').remove()`);
  if(errors.length||requests.some(x=>/^https?:/.test(x)))throw Error('Runtime errors or external request');
  writeFileSync(out+'/receipt.json',JSON.stringify({status:'PASS',checks,imagesVerified:true,anchorsVerified:true,offline:true,errors,requests,scientific_verdict:null},null,2)+'\n');
  console.log('Seven cases / 42 GLBs / stable cameras / images / links / two widths: PASS');
} catch(e){writeFileSync(out+'/failure.json',JSON.stringify({status:'FAIL',error:String(e),checks,errors,requests,scientific_verdict:null},null,2));throw e;}
finally {writeFileSync(out+'/chromium.log',log);if(ws)ws.close();browser.kill('SIGTERM');xvfb.kill('SIGTERM');}
