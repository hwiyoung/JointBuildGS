// Actual Chromium verification of the served MVS-conditioned inspection artifact.
// Run in the existing browser Docker image. No dependencies, server, or GPU use.
import fs from 'node:fs/promises';
import {spawn} from 'node:child_process';
import {createHash} from 'node:crypto';

const target = process.env.QA_URL || process.argv[2];
const out = process.env.QA_OUT || '/out';
if (!target) throw Error('QA_URL is required and must name the exact served review HTML.');
const url = new URL(target);
if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) throw Error('QA_URL must be an HTTP(S) artifact URL without credentials.');
const checks = [], states = [], screenshots = [], errors = [], consoleErrors = [], failedRequests = [], badResponses = [], chromiumLog = [];
const receipt = {
  schema:'jbgs.mvs_evidence.browser_qa.v1', status:'RUNNING', url:target,
  started_at:new Date().toISOString(), scientific_verdict:null,
  scope:'Actual served artifact: P1/P2/P3 camera and layer switches, pointer/keyboard selection, raw patch images, links, desktop and narrow layout. Technical UI evidence only.',
  training_gpu_used:false, node_version:process.version,
  checks, states, screenshots, runtime_errors:errors, console_errors:consoleErrors,
  failed_requests:failedRequests, bad_responses:badResponses,
  image_loading_verification:'Scroll every selected case image into view before waiting for its native lazy load.',
};
const pause = ms => new Promise(resolve => setTimeout(resolve,ms));
const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');
let browser, socket, sequence = 0;
const pending = new Map();
function check(pass,name,details) {
  checks.push({pass:Boolean(pass),name,details});
  if (!pass) throw Error(name);
}
function send(method,params={}) {
  const id = ++sequence;
  return new Promise((resolve,reject) => {
    const timer = setTimeout(() => {pending.delete(id);reject(Error('CDP timeout: '+method));},30000);
    pending.set(id,{resolve:result=>{clearTimeout(timer);resolve(result);},reject:error=>{clearTimeout(timer);reject(error);}});
    socket.send(JSON.stringify({id,method,params}));
  });
}
async function evaluate(expression) {
  const response = await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
  if (response.exceptionDetails) throw Error(JSON.stringify(response.exceptionDetails));
  return response.result?.value;
}
async function waitFor(expression,label) {
  for (let i=0;i<200;i++) {const value=await evaluate(expression);if(value)return value;await pause(75);}
  throw Error('Timed out: '+label);
}
async function choose(id,value) {
  await evaluate(`(()=>{const e=document.getElementById(${JSON.stringify(id)});if(!e||![...e.options].some(o=>o.value===${JSON.stringify(String(value))}))throw Error('Missing selector option');e.value=${JSON.stringify(String(value))};e.dispatchEvent(new Event('change',{bubbles:true}));})()`);
}
async function ready(region,camera,layer) {
  const state = await waitFor(`(()=>{const q=id=>document.getElementById(id),s=q('load-status');if(!s)return false;if(s.classList.contains('error'))throw Error(s.textContent);return q('region').value===${JSON.stringify(String(region))}&&q('camera').value===${JSON.stringify(String(camera))}&&q('layer').value===${JSON.stringify(String(layer))}&&s.textContent.includes('좌표 일치')?{region:q('region').value,camera:q('camera').value,layer:q('layer').value,status:s.textContent}:false;})()`,'camera/layer ready');
  await evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))');
  return state;
}
async function capture(name,selector) {
  if(selector) await evaluate(`document.querySelector(${JSON.stringify(selector)}).scrollIntoView({block:'start',behavior:'instant'})`);
  else await evaluate('window.scrollTo(0,0)');
  await evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))');
  const result = await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
  const bytes = Buffer.from(result.data,'base64');
  await fs.writeFile(out+'/'+name,bytes,{flag:'wx'});
  screenshots.push({path:name,bytes:bytes.length,sha256:sha256(bytes)});
}
async function noOverflow(mode) {
  const layout = await evaluate('({viewport:innerWidth,document:document.documentElement.scrollWidth,canvas:[...document.querySelectorAll("canvas")].map(c=>({width:c.clientWidth,height:c.clientHeight})),caseScroll:document.getElementById("case-list").scrollWidth})');
  check(layout.document<=layout.viewport+1&&layout.canvas.every(c=>c.width>100&&c.height>100),'No horizontal page overflow: '+mode,layout);
}
async function inspectPoint(region,camera) {
  const point = await evaluate(`(()=>{const c=window.MVS_EVIDENCE.regions[${region}].cameras[${camera}],ps=c.points.filter(p=>Number.isFinite(p.u)&&Number.isFinite(p.v));if(!ps.length)return null;const p=ps.reduce((a,b)=>(a.u-c.width/2)**2+(a.v-c.height/2)**2<(b.u-c.width/2)**2+(b.v-c.height/2)**2?a:b);const rr=[...document.querySelectorAll('canvas')].map(x=>x.getBoundingClientRect()),s=Math.min(...rr.map(r=>Math.min(r.width/c.width,r.height/c.height))),r=rr[0];return {u:p.u,v:p.v,x:r.left+r.width/2+(p.u-c.width/2)*s,y:r.top+r.height/2+(p.v-c.height/2)*s,count:ps.length,hasRight:ps.some(q=>q.u>p.u+.1),hasNull:Object.values(p).some(v=>v===null),profile:p.profile_neighbor_count};})()`);
  check(Boolean(point),'Camera has inspectable grid samples',{region,camera});
  await send('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,x:point.x,y:point.y});
  await send('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,x:point.x,y:point.y});
  const ui = await evaluate(`({heading:document.getElementById('point-heading').textContent,text:document.getElementById('point-fields').textContent,expectedU:Number(${point.u}).toLocaleString('ko-KR',{maximumFractionDigits:3}),expectedV:Number(${point.v}).toLocaleString('ko-KR',{maximumFractionDigits:3})})`);
  check(ui.heading.includes('u '+ui.expectedU)&&ui.heading.includes('v '+ui.expectedV),'Actual pointer selects expected image-coordinate sample',{region,camera,point,heading:ui.heading});
  check(ui.text.includes('프로파일 이웃 영상 수')&&ui.text.includes('저비용 구간 수')&&ui.text.includes('불확실성이 0이라는 뜻이 아닙니다'),'Profile fields and zero-width interpretation displayed',{region,camera});
  if(point.hasNull)check(ui.text.includes('미확인 (null)'),'Null remains explicitly unknown',{region,camera});
  await send('Input.dispatchKeyEvent',{type:'keyDown',key:'ArrowRight',code:'ArrowRight',windowsVirtualKeyCode:39});
  await send('Input.dispatchKeyEvent',{type:'keyUp',key:'ArrowRight',code:'ArrowRight',windowsVirtualKeyCode:39});
  if(point.hasRight)check(await evaluate("document.getElementById('point-heading').textContent")!==ui.heading,'Keyboard selects neighboring sample',{region,camera});
  await evaluate("document.getElementById('zoom-in').click()");
  await waitFor("document.getElementById('zoom-text').textContent==='130%'",'zoom updates');
  check(true,'Zoom control updates visible image scale',{region,camera});
  await evaluate("document.getElementById('fit').click()");
  await waitFor("document.getElementById('zoom-text').textContent==='100%'",'fit resets zoom');
}
async function inspectCases(region,camera) {
  const expected = await evaluate(`window.MVS_EVIDENCE.regions[${region}].cameras[${camera}].cases.map(c=>({id:c.id,figure:c.figure,profile:c.profile,patches:c.patches}))`);
  check(expected.length>0,'Camera has reviewable cases',{region,camera});
  let patchesSeen=0;
  for(let index=0;index<expected.length;index++) {
    await evaluate(`document.querySelectorAll('.case-button')[${index}].click()`);
    // Case figures use native loading=lazy. Exercise normal scrolling before
    // waiting; an offscreen figure is not a failed or missing resource.
    const figureCount=await evaluate("document.querySelectorAll('#case-detail img').length");
    for(let imageIndex=0;imageIndex<figureCount;imageIndex++) {
      await evaluate(`document.querySelectorAll('#case-detail img')[${imageIndex}].scrollIntoView({block:'center',behavior:'instant'})`);
      await waitFor(`(()=>{const i=document.querySelectorAll('#case-detail img')[${imageIndex}];return i&&i.complete&&i.naturalWidth>0})()`,`visible case image ${region}/${camera}/${index}/${imageIndex}`);
    }
    const loaded = await waitFor(`(()=>{const xs=[...document.querySelectorAll('#case-detail img')];return xs.length&&xs.every(i=>i.complete&&i.naturalWidth>0)?xs.map(i=>({src:i.src,width:i.naturalWidth,height:i.naturalHeight,pixelated:getComputedStyle(i).imageRendering})):false})()`,'case images');
    const wanted = [expected[index].figure,expected[index].profile,expected[index].patches].filter(Boolean).map(path=>new URL(path,target).href);
    check(JSON.stringify(loaded.map(i=>i.src))===JSON.stringify(wanted),'Case figure URLs bind exact case metadata',{region,camera,index,loaded});
    if(expected[index].patches) {
      const patch = await evaluate("(()=>{const f=document.querySelector('.raw-patches'),i=f?.querySelector('img');return f&&i?{caption:f.textContent,pixelated:getComputedStyle(i).imageRendering,span:getComputedStyle(f).gridColumn}:null})()");
      check(patch?.pixelated==='pixelated'&&patch.caption.includes('7 × 7')&&patch.caption.includes('가시성 gate를 적용하지 않았습니다'),'Actual patch PNG uses nearest pixels with raw-support caption',{region,camera,index,patch});
      patchesSeen++;
    }
  }
  return patchesSeen;
}
async function inspectLinks() {
  const links = await evaluate("[...document.querySelectorAll('#raw-links a,#photo-link,#map-link')].filter(a=>!a.hidden).map(a=>({href:a.href,download:a.hasAttribute('download'),label:a.textContent}))");
  check(links.filter(link=>link.download).length===2,'Summary and sample JSON download links exist');
  const json = await evaluate("Promise.all([...document.querySelectorAll('#raw-links a[download]')].map(async a=>({label:a.textContent,value:await(await fetch(a.href)).json()})))");
  check(json.length===2&&Array.isArray(json[1].value),'Downloadable sample JSON can actually be read',{samples:json[1]?.value.length});
  for(const link of links.filter(link=>!link.download)) {
    check(new URL(link.href).origin===url.origin,'Evidence link stays on artifact origin',link);
    const response=await fetch(link.href,{method:'HEAD'});
    check(response.ok,'Evidence link responds successfully',{...link,status:response.status});
  }
}

try {
  await fs.mkdir(out,{recursive:true});
  const response = await fetch(target),bytes=Buffer.from(await response.arrayBuffer());
  check(response.ok,'Exact served review HTML loads',{status:response.status});
  receipt.html_sha256=sha256(bytes);
  receipt.qa_script_sha256=sha256(await fs.readFile(new URL(import.meta.url)));
  const profile=await fs.mkdtemp('/tmp/mvs-evidence-qa-');
  for(const folder of ['config','cache','data'])await fs.mkdir(profile+'/'+folder);
  browser=spawn(process.env.QA_CHROMIUM || '/usr/bin/chromium',['--headless=new','--no-sandbox','--no-first-run','--disable-dev-shm-usage','--disable-gpu','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{env:{...process.env,XDG_CONFIG_HOME:profile+'/config',XDG_CACHE_HOME:profile+'/cache',XDG_DATA_HOME:profile+'/data'}});
  browser.stderr.on('data',chunk=>chromiumLog.push(chunk.toString()));
  let browserError;browser.on('error',error=>{browserError=error;});
  let port;
  for(let i=0;i<150;i++){if(browserError)throw browserError;try{port=(await fs.readFile(profile+'/DevToolsActivePort','utf8')).split('\n')[0];break;}catch{await pause(100);}}
  if(!port)throw Error('Chromium startup timeout');
  const pages=await(await fetch('http://127.0.0.1:'+port+'/json/list')).json();
  const page=pages.find(item=>item.type==='page'&&item.url==='about:blank');
  if(!page)throw Error('Dedicated blank browser page missing');
  socket=new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
  socket.onmessage=event=>{
    const message=JSON.parse(event.data);
    if(message.method==='Runtime.exceptionThrown')errors.push(message.params);
    if(message.method==='Runtime.consoleAPICalled'&&message.params.type==='error')consoleErrors.push(message.params);
    if(message.method==='Network.loadingFailed'&&!message.params.canceled)failedRequests.push(message.params);
    if(message.method==='Network.responseReceived'&&message.params.response.status>=400&&!message.params.response.url.endsWith('/favicon.ico'))badResponses.push(message.params.response);
    if(pending.has(message.id)){const call=pending.get(message.id);pending.delete(message.id);message.error?call.reject(Error(JSON.stringify(message.error))):call.resolve(message.result);}
  };
  await send('Page.enable');await send('Runtime.enable');await send('Network.enable');
  receipt.browser_version=await send('Browser.getVersion');
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1100,deviceScaleFactor:1,mobile:false});
  await send('Page.navigate',{url:target});
  const regions=await waitFor("window.MVS_EVIDENCE?.regions?.length?window.MVS_EVIDENCE.regions.map(r=>({id:r.id,cameras:r.cameras.map(c=>({id:c.id,layers:c.layers.length}))})):false",'data manifest');
  check(['P1','P2','P3'].every(id=>regions.some(region=>region.id===id)),'All P1/P2/P3 regions available',regions);
  check(await evaluate("document.querySelector('.notice').textContent.includes('독립적인 정답이 아닙니다')"),'MVS-conditioned scope visible');
  let patchCount=0;
  for(let region=0;region<regions.length;region++) {
    await choose('region',region);
    for(let camera=0;camera<regions[region].cameras.length;camera++) {
      await choose('camera',camera);await ready(region,camera,0);
      await evaluate('window.scrollTo(0,0)');
      await inspectPoint(region,camera);
      for(let layer=0;layer<regions[region].cameras[camera].layers;layer++) {
        await choose('layer',layer);const state=await ready(region,camera,layer);
        const exact=await evaluate(`(()=>{const l=window.MVS_EVIDENCE.regions[${region}].cameras[${camera}].layers[${layer}];return {expected:new URL(l.path,location.href).href,actual:document.getElementById('map-link').href,label:document.getElementById('map-title').textContent,expectedLabel:l.label||l.id}})()`);
        check(exact.actual===exact.expected&&exact.label===exact.expectedLabel,'Selected layer displays exact metadata and image URL',{region,camera,layer,exact});
        states.push({region:regions[region].id,camera:regions[region].cameras[camera].id,...state});
      }
      await inspectLinks();patchCount+=await inspectCases(region,camera);
      await noOverflow('desktop');
      if(camera===0){await capture(`desktop_${regions[region].id}_overview.png`);await capture(`desktop_${regions[region].id}_patches.png`,'.raw-patches');}
    }
  }
  check(patchCount>0,'Actual-neighbor patch PNGs loaded',{patchCount});receipt.patch_case_count=patchCount;
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
  for(let region=0;region<regions.length;region++) {
    await choose('region',region);await ready(region,0,0);
    await evaluate('window.scrollTo(0,0)');
    await inspectCases(region,0);await noOverflow('narrow '+regions[region].id);
    await capture(`narrow_${regions[region].id}_overview.png`);
    await capture(`narrow_${regions[region].id}_patches.png`,'.raw-patches');
  }
  check(errors.length===0&&consoleErrors.length===0&&failedRequests.length===0&&badResponses.length===0,'No browser runtime or artifact resource errors',{errors,consoleErrors,failedRequests,badResponses});
  receipt.status='PASS_ACTUAL_BROWSER';
} catch(error) {
  receipt.status='FAIL';receipt.error=String(error);process.exitCode=1;
  if(socket?.readyState===1){try{receipt.failure_page=await evaluate('({url:location.href,body:document.body?.innerText})');await capture('failure.png');}catch{}}
} finally {
  receipt.finished_at=new Date().toISOString();receipt.check_count=checks.length;receipt.state_count=states.length;
  await fs.mkdir(out,{recursive:true});
  await fs.writeFile(out+'/receipt.json',JSON.stringify(receipt,null,2)+'\n',{flag:'wx'});
  await fs.writeFile(out+'/chromium.log',chromiumLog.join(''),{flag:'wx'});
  socket?.close();browser?.kill('SIGTERM');
}
console.log(JSON.stringify({status:receipt.status,checks:checks.length,states:states.length,patch_case_count:receipt.patch_case_count,error:receipt.error,scientific_verdict:null}));
