// CPU Chromium: all nine final models, same-camera masks, and existing pages.
import fs from 'node:fs/promises';
import path from 'node:path';
import {spawn} from 'node:child_process';
const output=process.argv[2] || '/out';
const url='http://127.0.0.1:8910/app/weights.html?comparison=prior';
const roles=['alpha_4','prior_0005_alpha4'];
const started=Date.now(),deadline=started+240000,pending=new Map(),events=[],logs=[];
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
  for(const id of ['P1','P1_context','P2','P2_context','P3','P3_context']){
    await evaluate('window.__GEOGS_MATCHED_QA__.setRegion('+JSON.stringify(id)+')');let state=await ready();await frames();
    check(Object.keys(state.panels).length===2,'two_prior_panels',{id});
    check(state.panels.alpha_4.drawn&&state.panels.alpha_4.integrity==='SHA256_AND_BYTES_VERIFIED','existing_final_mesh_verified',{id});
    const next=state.panels.prior_0005_alpha4;
    if(process.env.JBGS_REQUIRE_COMPLETE==='1')check(next.status==='available','final_output_required',{id});
    check(['pending','available'].includes(next.status),'new_arm_explicit_state',{id,status:next.status});
    if(next.status==='pending')check(!next.drawn,'no_substitute_for_pending',{id});
    else check(next.drawn&&next.integrity==='SHA256_AND_BYTES_VERIFIED','new_final_mesh_verified',{id});
    const views=await evaluate('[...document.querySelectorAll("#photo-view option")].map(x=>x.value)');
    for(const view of views){await evaluate('window.__GEOGS_MATCHED_QA__.setView('+JSON.stringify(view)+')');state=await ready();
      check(state.images.original.status==='available'&&state.images['alpha_4.rgb'].status==='available','same_camera_existing_render',{id,view});
      if(next.status==='available')check(['rgb','depth'].every(kind=>state.images['prior_0005_alpha4.'+kind].status==='available'),'new_final_rgb_and_depth',{id,view});
      check(state.weight.region===id,'same_mask_region',{id,view});
    }
    if(!id.includes('_'))await capture(id+'.png');
  }
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});await frames();
  check(await evaluate('document.documentElement.scrollWidth<=391'),'mobile_no_overflow');await capture('mobile.png');
  await send('Emulation.setDeviceMetricsOverride',{width:1500,height:1200,deviceScaleFactor:1,mobile:false});
  await send('Page.navigate',{url:'http://127.0.0.1:8910/app/weights.html'});await sleep(1000);await ready();
  check(await evaluate('Object.keys(window.__GEOGS_MATCHED_QA__.panels).length===3'),'original_three_arm_view_preserved');
  const errors=events.filter(e=>e.method==='Runtime.exceptionThrown'||e.method==='Network.loadingFailed'||(e.method==='Network.responseReceived'&&e.params.response.status>=400));
  check(errors.length===0,'no_browser_network_errors',{errors});receipt.status='PASS_PRIOR_WEIGHT_BROWSER';
}catch(error){receipt.status='FAIL_PRIOR_WEIGHT_BROWSER';receipt.error=String(error);process.exitCode=1;}
finally{if(socket)socket.close();await stop(browser);await stop(display);receipt.wall_seconds=(Date.now()-started)/1000;
 await fs.writeFile(path.join(output,'receipt.json'),JSON.stringify(receipt,null,2),{flag:'wx'});
 await fs.writeFile(path.join(output,'chrome.log'),logs.join(''),{flag:'wx'});
 console.log(JSON.stringify({status:receipt.status,checks:receipt.checks.length,error:receipt.error||null}));}
