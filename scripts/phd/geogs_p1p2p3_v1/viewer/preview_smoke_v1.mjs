// Bounded actual preview display smoke; reuse the dedicated browser image/CDP setup.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {spawn} from 'node:child_process';

const [url, output = '/out'] = process.argv.slice(2);
const target = new URL(url);
if (target.hostname !== '127.0.0.1' || target.port !== '8902' || target.searchParams.get('manifest') !== '/task/evaluation/viewer/manifest_preview_v1.json') throw Error('Exact local preview URL required');
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const hash = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const profile = await fs.mkdtemp('/tmp/geogs-preview-');
const chromeLog = [], events = [], pending = new Map();
let browser, display, socket, sequence = 0;
const receipt = {schema:'GEOGS_PREVIEW_DISPLAY_SMOKE_v1', scientific_verdict:null,
  status:'RUNNING', started_at:new Date().toISOString(), url, image_id:process.env.GEOGS_QA_IMAGE_ID,
  scope:'Three default regional six-panel states, one P1 actual mesh state, one actual render gallery image; no full matrix or scientific validation',
  regions:[], screenshots:[], checks:[]};
function check(pass, name, details) {
  receipt.checks.push({name, pass:!!pass, details});
  if (!pass) throw Error(name);
}
function send(method, params = {}) {
  const id = ++sequence;
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {pending.delete(id); reject(Error('CDP timeout: '+method));}, 30000);
    pending.set(id, {resolve:value=>{clearTimeout(timeout); resolve(value);}, reject:error=>{clearTimeout(timeout); reject(error);}});
    socket.send(JSON.stringify({id, method, params}));
  });
}
async function evaluate(expression) {
  const result = await send('Runtime.evaluate', {expression, returnByValue:true, awaitPromise:true});
  if (result.exceptionDetails) throw Error(JSON.stringify(result.exceptionDetails));
  return result.result?.value;
}
async function ready(region, representation) {
  for (let i=0; i<300; i++) {
    const state = await evaluate('window.__GEOGS_QA || null');
    if (state?.errors?.length) throw Error(JSON.stringify(state.errors));
    if (state?.ready && (!region || state.region===region) && (!representation || state.representation_mode===representation)) {
      await evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))');
      return evaluate('window.__GEOGS_QA');
    }
    await pause(150);
  }
  throw Error('Preview ready timeout: '+region);
}
async function choose(id, value) {
  await evaluate(`(()=>{const el=document.getElementById(${JSON.stringify(id)});if(!el||![...el.options].some(o=>o.value===${JSON.stringify(value)}&&!o.disabled))throw Error('Missing option');el.value=${JSON.stringify(value)};el.dispatchEvent(new Event('change',{bubbles:true}));})()`);
}
async function pixels(state) {
  const rows = await evaluate(`(()=>[...document.querySelectorAll('.panel')].map(panel=>{const canvas=panel.querySelector('canvas'),gl=canvas.getContext('webgl2')||canvas.getContext('webgl'),missing=panel.querySelector('.missing');if(!gl)return {panel:panel.dataset.panel,webgl:false};const data=new Uint8Array(canvas.width*canvas.height*4);gl.readPixels(0,0,canvas.width,canvas.height,gl.RGBA,gl.UNSIGNED_BYTE,data);let different=0;for(let i=4;i<data.length;i+=4)if(data[i]!==data[0]||data[i+1]!==data[1]||data[i+2]!==data[2])different++;return {panel:panel.dataset.panel,webgl:true,width:canvas.width,height:canvas.height,nonbackground_pixels:different,missing_visible:!missing.hidden,missing_text:missing.textContent};}))()`);
  check(rows.length===6, 'six_default_panels', state.region);
  for (const row of rows) {
    const panel = state.panels[row.panel];
    check(row.webgl && (panel.status==='available' ? panel.count>0 && panel.draw_calls>0 && row.nonbackground_pixels>10 : panel.count===0 && row.missing_visible && row.missing_text.length>0),
      'actual_pixels_or_explicit_unavailable', {region:state.region, status:panel.status, candidate:panel.candidate, ...row});
  }
  return rows;
}
async function capture(name) {
  const result = await send('Page.captureScreenshot', {format:'png', captureBeyondViewport:false});
  const bytes = Buffer.from(result.data,'base64');
  await fs.writeFile(path.join(output,name), bytes, {flag:'wx'});
  receipt.screenshots.push({filename:name, bytes:bytes.length, sha256:hash(bytes)});
}
async function stop(child) {
  if (!child || child.exitCode!==null || child.signalCode!==null) return;
  await new Promise(resolve=>{
    const timeout=setTimeout(()=>{child.kill('SIGKILL');},3000);
    child.once('close',()=>{clearTimeout(timeout);resolve();});
    child.kill('SIGTERM');
  });
}
try {
  display=spawn('/usr/bin/Xvfb',['-displayfd','1','-screen','0','1800x1240x24','-nolisten','tcp']);
  display.stderr.on('data',bytes=>chromeLog.push('Xvfb: '+bytes));
  const number=await new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>reject(Error('Xvfb timeout')),10000);
    display.stdout.once('data',bytes=>{clearTimeout(timer);const value=bytes.toString().trim(); /^\d+$/.test(value)?resolve(value):reject(Error('Invalid display'));});
    display.once('error',reject);
  });
  receipt.dedicated_xvfb_display=number;
  for (const suffix of ['config','cache','data']) await fs.mkdir(profile+'/'+suffix);
  const args=['--headless=new','--no-sandbox','--no-first-run','--no-default-browser-check','--enable-automation','--disable-dev-shm-usage','--ozone-platform=headless','--use-gl=angle','--use-angle=gl','--ignore-gpu-blocklist','--disable-vulkan','--remote-debugging-address=127.0.0.1','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'];
  receipt.chrome_args=args;
  receipt.software_webgl='Dedicated Docker Xvfb and software ANGLE GL; no host display or GPU device';
  browser=spawn(process.env.CHROME_BIN||'/usr/bin/chromium',args,{env:{...process.env,DISPLAY:':'+number,LIBGL_ALWAYS_SOFTWARE:'1',XDG_CONFIG_HOME:profile+'/config',XDG_CACHE_HOME:profile+'/cache',XDG_DATA_HOME:profile+'/data'}});
  browser.stderr.on('data',bytes=>chromeLog.push(bytes.toString()));
  let port;
  for (let i=0;i<150;i++) {try {port=(await fs.readFile(path.join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0];break;} catch {await pause(100);}}
  if (!port) throw Error('Dedicated Chrome start timeout');
  const pages=await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  socket=new WebSocket(pages.find(item=>item.type==='page').webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
  socket.addEventListener('message',event=>{const message=JSON.parse(event.data);if(message.id){const item=pending.get(message.id);if(item){pending.delete(message.id);message.error?item.reject(Error(JSON.stringify(message.error))):item.resolve(message.result);}}else events.push(message);});
  receipt.browser=await send('Browser.getVersion');
  await send('Page.enable'); await send('Runtime.enable'); await send('Network.enable');
  await send('Emulation.setDeviceMetricsOverride',{width:1800,height:1240,deviceScaleFactor:1,mobile:false});
  await send('Page.navigate',{url});
  const first=await ready();
  const response=await fetch(first.manifest);
  check(response.ok,'preview_manifest_http_ok',response.status);
  const bytes=Buffer.from(await response.arrayBuffer()), manifest=JSON.parse(bytes.toString());
  await fs.writeFile(path.join(output,'served_manifest_preview_v1.json'),bytes,{flag:'wx'});
  receipt.manifest={url:first.manifest,sha256:hash(bytes),bytes:bytes.length};
  check(JSON.stringify(manifest.regions.map(item=>item.id))===JSON.stringify(['P1','P2','P3']),'three_requested_regions',manifest.regions.map(item=>item.id));
  for (const region of ['P1','P2','P3']) {
    await choose('region-select',region);
    const state=await ready(region);
    const raster=await pixels(state);
    receipt.regions.push({region,state,raster});
    await evaluate('window.scrollTo(0,0)');
    await capture(region+'_default.png');
  }
  await choose('region-select','P1'); await ready('P1');
  await choose('representation-select','mesh');
  const mesh=await ready('P1','mesh');
  await pixels(mesh);
  const native=mesh.panels.vanilla;
  check(native.status==='available'&&native.representation==='mesh'&&native.draw_calls>0&&native.rendered_triangles>0&&native.rendered_triangles===native.mesh_triangle_count,'P1_native_actual_triangles_drawn',native);
  receipt.p1_mesh={region:'P1',resolution:mesh.resolution_mode,surface:mesh.surface_mode,condition:mesh.condition,native};
  let gallery;
  for(let i=0;i<150;i++) {
    gallery=await evaluate(`(()=>{const figure=document.getElementById('render-figure'),img=document.getElementById('render-image');return {hidden:figure.hidden,src:img.src,complete:img.complete,width:img.naturalWidth,height:img.naturalHeight,caption:document.getElementById('render-caption').textContent,selected:document.getElementById('render-select').value,domain:document.getElementById('render-domain-select').value,photo:document.getElementById('render-image-select').value};})()`);
    if(!gallery.hidden&&gallery.complete&&gallery.width>0&&gallery.height>0) break;
    await pause(100);
  }
  check(!gallery.hidden&&gallery.complete&&gallery.width>0&&gallery.height>0&&new URL(gallery.src).origin===target.origin,'one_actual_render_gallery_image_loaded',gallery);
  const expected=manifest.regions.find(item=>item.id==='P1').renders.find(item=>item.id===gallery.selected);
  check(!!expected&&new URL(expected.url||expected.path,first.manifest).href===gallery.src,'gallery_source_matches_preview_manifest',gallery);
  receipt.gallery=gallery;
  const failures=events.filter(event=>event.method==='Runtime.exceptionThrown'||event.method==='Network.loadingFailed'||(event.method==='Network.responseReceived'&&event.params.response.status>=400));
  check(failures.length===0,'no_browser_exception_or_failed_request',failures);
  receipt.status=receipt.regions.some(row=>Object.values(row.state.panels).some(panel=>panel.status!=='available'))?'PASS_PREVIEW_SMOKE_WITH_EXPLICIT_UNAVAILABLE':'PASS_PREVIEW_DISPLAY_SMOKE';
} catch(error) {
  receipt.status='FAIL_PREVIEW_DISPLAY_SMOKE'; receipt.error=String(error);process.exitCode=1;
} finally {
  if(socket) socket.close();
  await stop(browser); await stop(display);
  receipt.completed_at=new Date().toISOString();
  await fs.writeFile(path.join(output,'chrome.log'),chromeLog.join(''),{flag:'wx'});
  await fs.writeFile(path.join(output,'receipt.json'),JSON.stringify(receipt,null,2)+'\n',{flag:'wx'});
  console.log(JSON.stringify({status:receipt.status,screenshots:receipt.screenshots.length,checks:receipt.checks.length,error:receipt.error||null}));
}
