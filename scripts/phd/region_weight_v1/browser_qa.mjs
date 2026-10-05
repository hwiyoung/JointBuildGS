// CPU Chromium check of the live incremental viewer, including pending arms.
import fs from 'node:fs/promises';
import path from 'node:path';
import {spawn} from 'node:child_process';
const output=process.argv[2] || '/out';
const url='http://127.0.0.1:8910/app/p2p3_weights.html';
const roles=['alpha_0','alpha_1','alpha_4'];
const started=Date.now(),deadline=started+180000,pending=new Map(),events=[],logs=[];
const receipt={status:'RUNNING',scientific_verdict:null,url,checks:[],states:[],screenshots:[]};
let browser,display,socket,sequence=0;
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
function check(value,name,details){receipt.checks.push({name,pass:!!value,details});if(!value)throw Error(name);}
function send(method,params={}){
  const id=++sequence;
  return new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout: '+method));},20000);
    pending.set(id,{resolve:v=>{clearTimeout(timer);resolve(v);},reject:e=>{clearTimeout(timer);reject(e);}});
    socket.send(JSON.stringify({id,method,params}));
  });
}
async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result?.value;}
async function ready(){while(Date.now()<deadline){const q=await evaluate('window.__GEOGS_MATCHED_QA__ || null');if(q?.errors.length)throw Error(JSON.stringify(q.errors));if(q?.settled)return q;await sleep(100);}throw Error('Browser deadline');}
async function frames(){await evaluate('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))');}
async function capture(name){const r=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await fs.writeFile(path.join(output,name),Buffer.from(r.data,'base64'),{flag:'wx'});receipt.screenshots.push(name);}
async function stop(child){if(!child||child.exitCode!==null)return;await new Promise(r=>{const timer=setTimeout(()=>child.kill('SIGKILL'),2000);child.once('close',()=>{clearTimeout(timer);r();});child.kill('SIGTERM');});}
try{
  const profile=await fs.mkdtemp('/tmp/p2p3-incremental-qa-');
  display=spawn('/usr/bin/Xvfb',['-displayfd','1','-screen','0','1800x1400x24','-nolisten','tcp']);
  const number=await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('Xvfb timeout')),10000);display.stdout.once('data',b=>{clearTimeout(timer);resolve(b.toString().trim());});display.once('error',reject);});
  for(const part of ['config','cache','data'])await fs.mkdir(profile+'/'+part);
  browser=spawn('/usr/bin/chromium',['--headless=new','--no-sandbox','--no-first-run','--no-default-browser-check','--disable-dev-shm-usage','--ozone-platform=headless','--use-gl=angle','--use-angle=gl','--ignore-gpu-blocklist','--disable-vulkan','--remote-debugging-address=127.0.0.1','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],
    {env:{...process.env,DISPLAY:':'+number,LIBGL_ALWAYS_SOFTWARE:'1',XDG_CONFIG_HOME:profile+'/config',XDG_CACHE_HOME:profile+'/cache',XDG_DATA_HOME:profile+'/data'}});
  browser.stderr.on('data',b=>logs.push(b.toString()));
  let port;
  while(Date.now()<deadline){try{port=(await fs.readFile(profile+'/DevToolsActivePort','utf8')).split('\n')[0];break;}catch{await sleep(100);}}
  if(!port)throw Error('Chrome timeout');
  const pages=await(await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  socket=new WebSocket(pages.find(p=>p.type==='page').webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
  socket.addEventListener('message',e=>{const m=JSON.parse(e.data);if(m.id){const item=pending.get(m.id);if(item){pending.delete(m.id);m.error?item.reject(Error(JSON.stringify(m.error))):item.resolve(m.result);}}else events.push(m);});
  receipt.browser=await send('Browser.getVersion');receipt.cpu_only=true;
  await send('Page.enable');await send('Runtime.enable');await send('Network.enable');
  await send('Emulation.setDeviceMetricsOverride',{width:1800,height:1300,deviceScaleFactor:1,mobile:false});
  await send('Page.navigate',{url});await ready();
  const manifest=await(await fetch('http://127.0.0.1:8910/data/p2p3_weights_v1/manifest.json')).json();
  check(manifest.schema==='region_weight_comparison_v1'&&manifest.scientific_verdict===null,'correct_incremental_manifest');
  for(const region of manifest.regions){
    await evaluate(`window.__GEOGS_MATCHED_QA__.setRegion(${JSON.stringify(region.id)})`);
    let state=await ready();await frames();state=await ready();
    for(const condition of region.conditions){
      const panel=state.panels[condition.id];
      check(panel.status===condition.status,'panel_matches_own_condition',{id:condition.id,expected:condition.status,actual:panel.status});
      if(condition.status==='available')check(panel.drawn&&panel.triangle_count>0&&panel.integrity==='SHA256_AND_BYTES_VERIFIED','actual_final_mesh_rendered_with_hash_verification',{id:condition.id,panel});
      else check(!panel.drawn,'unfinished_arm_has_no_substitute',{id:condition.id});
    }
    for(const preset of ['top','oblique','side']){
      await evaluate(`window.__GEOGS_MATCHED_QA__.setPreset(${JSON.stringify(preset)})`);await frames();state=await ready();
      check(roles.every(r=>JSON.stringify(state.cameras[r])===JSON.stringify(state.cameras.alpha_0)),'three_cameras_synchronized',{region:region.id,preset});
    }
    for(const view of region.views){
      await evaluate(`window.__GEOGS_MATCHED_QA__.setView(${JSON.stringify(view.id)})`);state=await ready();
      check(state.images.original.status==='available','correct_original_photo_loads',{region:region.id,view:view.id});
      for(const role of roles)for(const type of ['rgb','depth'])check(state.images[role+'.'+type].status===(view.conditions[role].status==='available'?'available':'pending'),'individual_render_available_or_explicit_pending',{region:region.id,view:view.id,role,type});
    }
    receipt.states.push(state);
  }
  await evaluate('window.__GEOGS_MATCHED_QA__.setRegion("P2")');await ready();
  await evaluate('window.__GEOGS_MATCHED_QA__.setPreset("oblique")');await frames();
  await capture('incremental_viewer_desktop.png');
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});await frames();
  check(await evaluate('document.documentElement.scrollWidth<=391'),'mobile_page_fits');await capture('incremental_viewer_mobile.png');
  // Default matched page continues to use its original roles and schema.
  await send('Page.navigate',{url:'http://127.0.0.1:8910/app/matched.html'});await ready();
  const previous=await evaluate('window.__GEOGS_MATCHED_QA__');
  check(['da3','mvs','mvs_pgsr'].every(r=>previous.panels[r]?.status==='available'),'existing_matched_page_preserved');
  const errors=events.filter(e=>e.method==='Runtime.exceptionThrown'||e.method==='Network.loadingFailed'||(e.method==='Network.responseReceived'&&e.params.response.status>=400));
  check(errors.length===0,'no_browser_or_network_errors',errors);
  receipt.status='PASS_INCREMENTAL_VIEWER_BROWSER';
}catch(error){receipt.status='FAIL_INCREMENTAL_VIEWER_BROWSER';receipt.error=String(error);process.exitCode=1;}
finally{
  if(socket)socket.close();await stop(browser);await stop(display);
  receipt.wall_seconds=(Date.now()-started)/1000;
  await fs.writeFile(path.join(output,'receipt.json'),JSON.stringify(receipt,null,2)+'\n',{flag:'wx'});
  await fs.writeFile(path.join(output,'chrome.log'),logs.join(''),{flag:'wx'});
  console.log(JSON.stringify({status:receipt.status,checks:receipt.checks.length,wall_seconds:receipt.wall_seconds,error:receipt.error || null}));
}
