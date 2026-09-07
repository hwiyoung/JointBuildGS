// Read-only browser inspection: original geometry and application remain unchanged.
import fs from 'node:fs/promises';
import {spawn} from 'node:child_process';
import crypto from 'node:crypto';
const [configPath,out]=process.argv.slice(2), config=JSON.parse(await fs.readFile(configPath,'utf8'));
const pause=ms=>new Promise(r=>setTimeout(r,ms)), hash=b=>crypto.createHash('sha256').update(b).digest('hex');
const profile=await fs.mkdtemp('/tmp/p2-focus-'), pending=new Map();
let browser,display,socket,seq=0;
const receipt={schema:'P2_VIEW_FOCUS_AUDIT_v1',scientific_verdict:null,status:'RUNNING',config,image_id:process.env.GEOGS_QA_IMAGE_ID,states:[],screenshots:[],errors:[]};
function send(method,params={}) {const id=++seq;return new Promise((resolve,reject)=>{const t=setTimeout(()=>{pending.delete(id);reject(Error(method+' timeout'));},30000);pending.set(id,{resolve:x=>{clearTimeout(t);resolve(x);},reject:x=>{clearTimeout(t);reject(x);}});socket.send(JSON.stringify({id,method,params}));});}
async function evaluate(expression) {const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result?.value;}
async function ready(representation) {for(let i=0;i<400;i++){const q=await evaluate('window.__GEOGS_QA || null');if(q?.errors?.length)throw Error(JSON.stringify(q.errors));if(q?.ready&&(!representation||(q.region==='P2'&&q.representation_mode===representation))){await pause(200);return q;}await pause(150);}throw Error('Application ready timeout');}
async function choose(id,value){await evaluate(`(()=>{const e=document.getElementById(${JSON.stringify(id)});e.value=${JSON.stringify(value)};e.dispatchEvent(new Event('change',{bubbles:true}));})()`);}
async function frame(){await evaluate('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))');}
async function capture(name){await frame();const state=await evaluate('window.__GEOGS_QA');const boxes=await evaluate(`(()=>{const ps=['vanilla','changed','reference'].map(k=>document.querySelector('[data-panel="'+k+'"]'));const r=ps.map(p=>p.getBoundingClientRect());return {x:r[0].left,y:r[0].top,width:r[2].right-r[0].left,height:Math.max(...r.map(x=>x.height)),scale:1};})()`);// Full viewport includes the unchanged panel labels and notes.
const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});const bytes=Buffer.from(shot.data,'base64');await fs.writeFile(out+'/'+name+'.png',bytes,{flag:'wx'});receipt.states.push({name,state});receipt.screenshots.push({name:name+'.png',sha256:hash(bytes),bytes:bytes.length,clip:boxes});}
async function drag(dx,dy,modifiers=0){const p=await evaluate(`(()=>{const r=document.querySelector('[data-panel="vanilla"] canvas').getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2};})()`);await send('Input.dispatchMouseEvent',{type:'mousePressed',...p,button:'left',buttons:1,clickCount:1,modifiers});await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:p.x+dx,y:p.y+dy,button:'left',buttons:1,modifiers});await send('Input.dispatchMouseEvent',{type:'mouseReleased',x:p.x+dx,y:p.y+dy,button:'left',buttons:0,modifiers});await frame();}
try {
  display=spawn('/usr/bin/Xvfb',['-displayfd','1','-screen','0','1800x1240x24','-nolisten','tcp']);
  const number=await new Promise((resolve,reject)=>{const t=setTimeout(()=>reject(Error('Xvfb timeout')),10000);display.stdout.once('data',b=>{clearTimeout(t);resolve(b.toString().trim());});display.once('error',reject);});
  for(const p of ['config','cache','data'])await fs.mkdir(profile+'/'+p);
  browser=spawn('/usr/bin/chromium',['--headless=new','--no-sandbox','--no-first-run','--disable-dev-shm-usage','--ozone-platform=headless','--use-gl=angle','--use-angle=gl','--ignore-gpu-blocklist','--disable-vulkan','--remote-debugging-address=127.0.0.1','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{env:{...process.env,DISPLAY:':'+number,LIBGL_ALWAYS_SOFTWARE:'1',XDG_CONFIG_HOME:profile+'/config',XDG_CACHE_HOME:profile+'/cache',XDG_DATA_HOME:profile+'/data'}});
  browser.stderr.on('data',()=>{});
  let port;for(let i=0;i<150;i++){try{port=(await fs.readFile(profile+'/DevToolsActivePort','utf8')).split('\n')[0];break;}catch{await pause(100);}}
  if(!port)throw Error('Chromium start timeout');
  const pages=await(await fetch('http://127.0.0.1:'+port+'/json/list')).json();socket=new WebSocket(pages.find(p=>p.type==='page').webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
  socket.addEventListener('message',e=>{const m=JSON.parse(e.data),p=pending.get(m.id);if(p){pending.delete(m.id);m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m.result);}});
  receipt.browser=await send('Browser.getVersion');await send('Page.enable');await send('Runtime.enable');await send('Emulation.setDeviceMetricsOverride',{width:1800,height:1240,deviceScaleFactor:1,mobile:false});
  const manifestURL=new URL(config.url).searchParams.get('manifest');const manifest=Buffer.from(await(await fetch(new URL(manifestURL,config.url))).arrayBuffer());
  if(hash(manifest)!==config.manifest_sha256)throw Error('Manifest changed');receipt.manifest_sha256=hash(manifest);
  await send('Page.navigate',{url:config.url});await ready();await choose('region-select','P2');await ready('points');await choose('condition-select',config.condition);await ready('points');
  await evaluate(`document.querySelector('[data-panel="vanilla"]').scrollIntoView({block:'start'})`);await pause(200);
  await capture('P2_whole_points');await choose('representation-select','mesh');await ready('mesh');await capture('P2_whole_mesh');
  // Real pointer events rotate to look along X, then pan to the recorded section vicinity.
  await drag(-.8/.007,-.65/.007);const q=await evaluate('window.__GEOGS_QA'),mpp=q.cameras.vanilla.meters_per_pixel;
  await drag(9/mpp,3.5325/mpp,8);
  const p=await evaluate(`(()=>{const r=document.querySelector('[data-panel="vanilla"] canvas').getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2};})()`);
  await send('Input.dispatchMouseEvent',{type:'mouseWheel',...p,deltaX:0,deltaY:-Math.log(config.zoom)/.001});await pause(200);
  await capture('P2_focus_along_x_mesh');await choose('representation-select','points');await ready('points');await capture('P2_focus_along_x_points');
  const last=receipt.states.at(-1).state;receipt.focus_camera=last.cameras.vanilla;
  if(Math.abs(last.cameras.vanilla.target[1]-100)>.1||Math.abs(last.cameras.vanilla.target[2]+30)>.1)throw Error('Unexpected focus target');
  for(const {state} of receipt.states){const a=state.panels.vanilla,b=state.panels.changed;if(a.candidate===b.candidate||a.status!=='available'||b.status!=='available')throw Error('Invalid comparison binding');if(JSON.stringify(state.cameras.vanilla)!==JSON.stringify(state.cameras.changed))throw Error('Unmatched cameras');}
  receipt.status='PASS_DISPLAY_INSPECTION';receipt.scope='Camera and representation changes only. Full geometry remains visible; this is not a clipped X=134 section. No new quality metrics or training.';
}catch(e){receipt.status='FAIL';receipt.errors.push(String(e.stack||e));process.exitCode=1;}
finally{socket?.close();for(const p of [browser,display]){if(p&&p.exitCode===null){p.kill('SIGTERM');await Promise.race([new Promise(r=>p.once('exit',r)),pause(1500)]);if(p.exitCode===null)p.kill('SIGKILL');}}await fs.writeFile(out+'/receipt.json',JSON.stringify(receipt,null,2)+'\n',{flag:'wx'});console.log(JSON.stringify({status:receipt.status,screenshots:receipt.screenshots,errors:receipt.errors}));}
