// Bounded real-browser verification of actual display artifacts. No GPU devices.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {spawn} from 'node:child_process';

const [url = 'http://127.0.0.1:8910/', output = '/out'] = process.argv.slice(2);
const target = new URL(url);
if (target.href !== 'http://127.0.0.1:8910/') throw Error('Exact frozen local viewer URL required');
const roles = ['prior', 'mvs', 'anchor', 'vanilla', 'geogs', 'mvs_geogs', 'gt'];
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const hash = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const started = Date.now(), deadline = started + 180000;
const pending = new Map(), events = [], chromeLog = [];
let browser, display, socket, sequence = 0;
const receipt = {schema:'GEOGS_RGB_BROWSER_QA_v1', status:'RUNNING', scientific_verdict:null,
  started_at:new Date().toISOString(), url, image_id:process.env.GEOGS_QA_IMAGE_ID,
  scope:'Actual RGB artifact integrity and seven-panel UI behavior; no training, surface extraction, scoring, or scientific verdict',
  limits:{wall_seconds:180,host_gpu_devices:false,cpu_browser:true}, regions:[], selections:[], surface_policy_checks:[], points_control_checks:[], cameras:[], screenshots:[], checks:[]};

function check(pass, name, details) {
  receipt.checks.push({name,pass:!!pass,details});
  if (!pass) throw Error(name);
}
function timeLeft() {
  if (Date.now() >= deadline) throw Error('Bounded browser QA deadline reached');
  return deadline - Date.now();
}
function send(method, params={}) {
  const milliseconds=Math.min(timeLeft(),15000),id=++sequence;
  return new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout: '+method));},milliseconds);
    pending.set(id,{resolve:value=>{clearTimeout(timer);resolve(value);},reject:error=>{clearTimeout(timer);reject(error);}});
    socket.send(JSON.stringify({id,method,params}));
  });
}
async function evaluate(expression) {
  const result=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
  if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));
  return result.result?.value;
}
async function frames() {
  await evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))');
}
async function ready(region,role,candidate) {
  const end=Math.min(deadline,Date.now()+35000);
  while(Date.now()<end){
    const state=await evaluate('window.__GEOGS_RGB_QA__ || null');
    if(state?.errors?.length)throw Error(JSON.stringify(state.errors));
    if(state?.ready && (!region || state.region===region) && state.settled===true
        && roles.every(key=>state.panels?.[key] && !state.panels[key].loading)
        && (!role || state.panels[role].candidate===candidate)){
      await frames();return evaluate('window.__GEOGS_RGB_QA__');
    }
    await pause(80);
  }
  throw Error('Viewer did not settle: '+JSON.stringify({region,role,candidate}));
}
async function choose(selector,value) {
  await evaluate(`(()=>{const el=document.querySelector(${JSON.stringify(selector)});if(!el||![...el.options].some(option=>option.value===${JSON.stringify(value)}&&!option.disabled))throw Error('Expected selectable option');el.value=${JSON.stringify(value)};el.dispatchEvent(new Event('change',{bubbles:true}));})()`);
}
async function click(selector) {
  await evaluate(`(()=>{const element=document.querySelector(${JSON.stringify(selector)});if(!element||element.disabled)throw Error('Missing enabled control');element.click();})()`);
}
async function pixels(selectedRoles=roles) {
  return evaluate(`(()=>${JSON.stringify(selectedRoles)}.map(role=>{
    const panel=document.querySelector('[data-panel="'+role+'"]'),canvas=panel?.querySelector('.viewport canvas');
    const missing=panel?.querySelector('.empty-state');
    if(!canvas)return {role,canvas:false};
    const gl=canvas.getContext('webgl2')||canvas.getContext('webgl');if(!gl)return {role,canvas:true,webgl:false};
    const data=new Uint8Array(canvas.width*canvas.height*4);gl.readPixels(0,0,canvas.width,canvas.height,gl.RGBA,gl.UNSIGNED_BYTE,data);
    const colorAt=i=>(data[i]<<16)|(data[i+1]<<8)|data[i+2],background=colorAt(0);
    let nonbackground=0;const unique=new Set(),low=[255,255,255],high=[0,0,0];
    for(let i=0;i<data.length;i+=4){const color=colorAt(i);if(color===background)continue;nonbackground++;if(unique.size<8192)unique.add(color);for(let c=0;c<3;c++){low[c]=Math.min(low[c],data[i+c]);high[c]=Math.max(high[c],data[i+c]);}}
    return {role,canvas:true,webgl:true,width:canvas.width,height:canvas.height,nonbackground_pixels:nonbackground,
      distinct_nonbackground_rgb:unique.size,rgb_min:low,rgb_max:high,missing_visible:!!missing&&!missing.hidden,
      missing_text:missing?.textContent||'',geometry_note:panel.querySelector('.geometry-note')?.textContent||'',
      color_note:panel.querySelector('.source-name')?.textContent||''};
  }))()`);
}
function validatePixels(state,raster) {
  for(const row of raster){
    const panel=state.panels[row.role];
    if(panel.status==='available'){
      check(row.webgl&&panel.drawn&&row.nonbackground_pixels>10&&row.distinct_nonbackground_rgb>3,
        'actual_nonbackground_rgb_pixels',{region:state.region,candidate:panel.candidate,status:panel.status,...row});
      check(row.color_note.length>0,'visible_color_provenance',{region:state.region,role:row.role,text:row.color_note});
      if(/gaussian.*cent/i.test(panel.geometry_kind||''))check(/Gaussian|SH/i.test(row.geometry_note),
        'gaussian_centers_explicitly_labeled',{region:state.region,role:row.role,note:row.geometry_note});
    }else{
      check(['pending','failed'].includes(panel.status)&&!panel.drawn&&row.missing_visible&&row.missing_text.length>5,
        'explicit_unavailable_without_substitution',{region:state.region,candidate:panel.candidate,...row,status:panel.status});
    }
  }
}
async function buffers(state,selectedRoles=roles) {
  const checks=[];
  for(const role of selectedRoles){
    if(state.panels[role].status!=='available')continue;
    const details=await evaluate(`window.__GEOGS_RGB_QA__.verifyBuffers(${JSON.stringify(role)})`);
    const expectedRecords=state.panels[role].representation==='mesh'?3:2;
    const passed=details?.records?.length===expectedRecords && details.records.every(record=>
      record.matches===true && record.bytes>0 && record.sha256===record.expected_sha256)
      && details.color_conversion_matches===true && details.rgb_distinct_sampled>1;
    check(passed,'renderer_bound_buffer_sha256_rgb_verified',
      {region:state.region,role,candidate:state.panels[role].candidate,...details});
    checks.push({role,...details});
  }
  return checks;
}
async function capture(filename) {
  const result=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
  const bytes=Buffer.from(result.data,'base64');
  check(bytes.length>2000,'actual_png_screenshot',{filename,bytes:bytes.length});
  await fs.writeFile(path.join(output,filename),bytes,{flag:'wx'});
  receipt.screenshots.push({filename,bytes:bytes.length,sha256:hash(bytes)});
}
function synchronized(state,action,before,key) {
  const camera=state.cameras.prior;
  check(roles.every(role=>JSON.stringify(state.cameras[role])===JSON.stringify(camera)),
    'seven_cameras_synchronized',{action,cameras:state.cameras});
  if(before&&key)check(JSON.stringify(camera[key])!==JSON.stringify(before[key]),
    'camera_control_changes_state',{action,key,before:before[key],after:camera[key]});
  receipt.cameras.push({action,cameras:state.cameras});
}
async function cameraInteractions() {
  let state=await ready('P1');
  synchronized(state,'default');
  let previous=state.cameras.prior;
  await click('[data-preset="top"]');await frames();state=await ready('P1');
  synchronized(state,'top_preset',previous,'pitch');
  check(state.cameras.prior.pitch>1.5,'top_preset_looks_down',state.cameras.prior);
  previous=state.cameras.prior;
  const rectangle=await evaluate(`(()=>{const r=document.querySelector('[data-panel="prior"] canvas').getBoundingClientRect();return{x:r.x+r.width*.5,y:r.y+r.height*.5};})()`);
  await send('Input.dispatchMouseEvent',{type:'mousePressed',x:rectangle.x,y:rectangle.y,button:'left',clickCount:1});
  await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:rectangle.x+35,y:rectangle.y-20,button:'left',buttons:1});
  await send('Input.dispatchMouseEvent',{type:'mouseReleased',x:rectangle.x+35,y:rectangle.y-20,button:'left',clickCount:1});
  await frames();state=await ready('P1');synchronized(state,'pointer_orbit',previous,'yaw');
  previous=state.cameras.prior;
  await send('Input.dispatchMouseEvent',{type:'mouseWheel',x:rectangle.x,y:rectangle.y,deltaX:0,deltaY:-120});
  await frames();state=await ready('P1');synchronized(state,'wheel_zoom',previous,'zoom');
  await click('#reset-view');await frames();state=await ready('P1');synchronized(state,'reset');
  check(state.cameras.prior.zoom===1,'reset_restores_zoom',state.cameras.prior);
}
async function stop(child) {
  if(!child||child.exitCode!==null||child.signalCode!==null)return;
  await new Promise(resolve=>{const timeout=setTimeout(()=>child.kill('SIGKILL'),2500);
    child.once('close',()=>{clearTimeout(timeout);resolve();});child.kill('SIGTERM');});
}

try {
  const profile=await fs.mkdtemp('/tmp/geogs-rgb-qa-');
  display=spawn('/usr/bin/Xvfb',['-displayfd','1','-screen','0','1800x1400x24','-nolisten','tcp']);
  display.stderr.on('data',bytes=>chromeLog.push('Xvfb: '+bytes));
  const number=await new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>reject(Error('Xvfb start timeout')),10000);
    display.stdout.once('data',bytes=>{clearTimeout(timer);const value=bytes.toString().trim();/^\d+$/.test(value)?resolve(value):reject(Error('Invalid Xvfb display'));});
    display.once('error',reject);
  });
  receipt.dedicated_xvfb_display=number;
  for(const suffix of ['config','cache','data'])await fs.mkdir(profile+'/'+suffix);
  const args=['--headless=new','--no-sandbox','--no-first-run','--no-default-browser-check','--enable-automation',
    '--disable-dev-shm-usage','--ozone-platform=headless','--use-gl=angle','--use-angle=gl','--ignore-gpu-blocklist',
    '--disable-vulkan','--remote-debugging-address=127.0.0.1','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'];
  receipt.chrome_args=args;
  receipt.software_webgl='Docker Xvfb + software ANGLE GL; no host display or GPU device mounted';
  browser=spawn(process.env.CHROME_BIN||'/usr/bin/chromium',args,{env:{...process.env,DISPLAY:':'+number,
    LIBGL_ALWAYS_SOFTWARE:'1',XDG_CONFIG_HOME:profile+'/config',XDG_CACHE_HOME:profile+'/cache',XDG_DATA_HOME:profile+'/data'}});
  browser.stderr.on('data',bytes=>chromeLog.push(bytes.toString()));
  let port;
  for(let i=0;i<150;i++){try{port=(await fs.readFile(path.join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0];break;}catch{await pause(100);}}
  if(!port)throw Error('Dedicated Chrome start timeout');
  const pages=await(await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  socket=new WebSocket(pages.find(item=>item.type==='page').webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
  socket.addEventListener('message',event=>{const message=JSON.parse(event.data);if(message.id){const item=pending.get(message.id);if(item){pending.delete(message.id);message.error?item.reject(Error(JSON.stringify(message.error))):item.resolve(message.result);}}else events.push(message);});
  receipt.browser=await send('Browser.getVersion');
  await send('Page.enable');await send('Runtime.enable');await send('Network.enable');
  await send('Emulation.setDeviceMetricsOverride',{width:1800,height:1400,deviceScaleFactor:1,mobile:false});
  await send('Page.navigate',{url});
  await ready();
  check(await evaluate('!!globalThis.crypto?.subtle && typeof window.__GEOGS_RGB_QA__.verifyBuffers==="function"'),
    'browser_sha256_and_bound_buffer_audit_available');
  const response=await fetch(new URL('/data/manifest.json',target));
  check(response.ok,'served_manifest_http_ok',response.status);
  const bytes=Buffer.from(await response.arrayBuffer()),manifest=JSON.parse(bytes.toString());
  await fs.writeFile(path.join(output,'served_manifest.json'),bytes,{flag:'wx'});
  receipt.manifest={sha256:hash(bytes),bytes:bytes.length,built_at:manifest.built_at,run_status:manifest.run_status};
  check(JSON.stringify(manifest.regions.map(row=>row.id))===JSON.stringify(['P1','P2','P3']),
    'requested_three_regions_present',manifest.regions.map(row=>row.id));
  check(manifest.scientific_verdict===null,'scientific_verdict_remains_null');
  check(Array.isArray(manifest.errors)&&manifest.errors.length===0,'no_builder_export_errors',manifest.errors);
  check(await evaluate('document.querySelectorAll(".panel[data-panel]").length')===7,'seven_panels_present');
  check(await evaluate('document.getElementById("representation-select").value')==='auto','default_auto_representation');
  for(const region of ['P1','P2','P3']){
    await choose('#region-select',region);
    let state=await ready(region);
    const raster=await pixels();validatePixels(state,raster);
    for(const role of ['prior','anchor','vanilla','geogs'])check(state.panels[role].status==='available'&&state.panels[role].representation==='mesh',
      'default_native_surface_is_actual_mesh',{region,role,panel:state.panels[role]});
    const integrity=await buffers(state);
    receipt.regions.push({region,state,raster,integrity});
    await evaluate('window.scrollTo(0,0)');await capture(region+'_default_rgb.png');
    if(region==='P1')await cameraInteractions();
    for(const [role,expectedCount] of [['geogs',6],['mvs_geogs',4],['mvs',2]]){
      const selector=`[data-panel="${role}"] .panel-selection select`;
      const options=await evaluate(`Array.from(document.querySelector(${JSON.stringify(selector)}).options,option=>({value:option.value,disabled:option.disabled,text:option.textContent}))`);
      check(options.length===expectedCount&&options.every(row=>!row.disabled),'full_condition_dropdown',{region,role,options});
      for(const option of options){
        await choose(selector,option.value);state=await ready(region,role,option.value);
        const selectedRaster=await pixels([role]);validatePixels(state,selectedRaster);
        const selectedIntegrity=await buffers(state,[role]);
        receipt.selections.push({region,role,option,panel:state.panels[role],raster:selectedRaster,integrity:selectedIntegrity});
      }
    }
    // Exercise the policy while retaining the original auto-mode checks above.
    await choose('#representation-select','points');state=await ready(region);
    const otherRoles=roles.filter(role=>role!=='mvs_geogs');
    for(const role of otherRoles)check(state.panels[role].representation==='points'&&state.panels[role].status==='available',
      'global_points_preserves_other_six_panels',{region,role,panel:state.panels[role]});
    const otherRaster=await pixels(otherRoles);validatePixels(state,otherRaster);
    const otherIntegrity=await buffers(state,otherRoles);
    receipt.points_control_checks.push({region,panels:Object.fromEntries(otherRoles.map(role=>[role,state.panels[role]])),raster:otherRaster,integrity:otherIntegrity});
    const surfaceSelector='[data-panel="mvs_geogs"] .panel-selection select';
    const surfaceOptions=await evaluate(`Array.from(document.querySelector(${JSON.stringify(surfaceSelector)}).options,option=>({value:option.value,disabled:option.disabled}))`);
    check(surfaceOptions.length===4&&surfaceOptions.every(option=>!option.disabled),'four_surface_only_choices_in_global_points',{region,surfaceOptions});
    for(const option of surfaceOptions){
      await choose(surfaceSelector,option.value);state=await ready(region,'mvs_geogs',option.value);
      const panel=state.panels.mvs_geogs;
      check(panel.representation_policy==='surface_only'&&panel.representation==='mesh',
        'surface_only_overrides_global_points',{region,candidate:option.value,panel});
      check(panel.status==='available'?(panel.drawn&&panel.triangles>0):(panel.status==='pending'&&!panel.drawn),
        'surface_only_actual_mesh_or_explicit_pending',{region,candidate:option.value,panel});
      for(const role of otherRoles)check(state.panels[role].representation==='points',
        'other_panels_remain_points_during_surface_selection',{region,candidate:option.value,role,representation:state.panels[role].representation});
      const surfaceRaster=await pixels(['mvs_geogs']);validatePixels(state,surfaceRaster);
      const surfaceIntegrity=await buffers(state,['mvs_geogs']);
      check(panel.status==='pending'?surfaceIntegrity.length===0:surfaceIntegrity.length===1&&surfaceIntegrity[0].records.length===3,
        'surface_only_uses_three_mesh_buffers_or_no_buffers',{region,candidate:option.value,integrity:surfaceIntegrity});
      receipt.surface_policy_checks.push({region,option,panel,raster:surfaceRaster,integrity:surfaceIntegrity});
    }
    await choose('#representation-select','auto');state=await ready(region);
    check(await evaluate('document.getElementById("representation-select").value')==='auto',
      'global_auto_restored_after_surface_policy_checks',{region});
    check(state.panels.mvs_geogs.representation==='mesh','surface_only_retained_after_auto_restore',{region,panel:state.panels.mvs_geogs});
    for(const role of ['prior','anchor','vanilla','geogs'])check(state.panels[role].representation==='mesh'&&state.panels[role].status==='available',
      'other_surface_panels_restore_auto_behavior',{region,role,panel:state.panels[role]});
  }
  check(receipt.selections.filter(row=>row.role!=='mvs').length===30,'all_thirty_regional_geogs_condition_selections');
  check(receipt.selections.filter(row=>row.role==='mvs').length===6,'both_mvs_lineages_selected_in_all_regions');
  check(receipt.surface_policy_checks.length===12&&receipt.points_control_checks.length===3,
    'all_twelve_surface_only_conditions_and_other_six_point_controls_checked');
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
  await frames();await evaluate('window.scrollTo(0,0)');
  const mobile=await evaluate(`(()=>({viewport:innerWidth,document:document.documentElement.scrollWidth,
    panels:Array.from(document.querySelectorAll('.panel'),panel=>{const r=panel.getBoundingClientRect();return{role:panel.dataset.panel,left:r.left,right:r.right,width:r.width};})}))()`);
  check(mobile.document<=mobile.viewport+1&&mobile.panels.length===7&&mobile.panels.every(p=>p.left>=-1&&p.right<=mobile.viewport+1),
    'mobile_no_horizontal_overflow',mobile);
  receipt.mobile=mobile;await capture('mobile_390px.png');
  const failures=events.filter(event=>event.method==='Runtime.exceptionThrown'||event.method==='Network.loadingFailed'
    ||(event.method==='Network.responseReceived'&&event.params.response.status>=400));
  check(failures.length===0,'no_browser_exception_or_failed_network_request',failures);
  check(receipt.screenshots.length>=3,'three_or_more_exported_screenshots');
  receipt.status='PASS_ACTUAL_RGB_BROWSER_QA';
} catch(error) {
  receipt.status='FAIL_ACTUAL_RGB_BROWSER_QA';receipt.error=String(error);process.exitCode=1;
} finally {
  if(socket)socket.close();
  await stop(browser);await stop(display);
  receipt.completed_at=new Date().toISOString();receipt.wall_seconds=(Date.now()-started)/1000;
  await fs.writeFile(path.join(output,'chrome.log'),chromeLog.join(''),{flag:'wx'});
  await fs.writeFile(path.join(output,'receipt.json'),JSON.stringify(receipt,null,2)+'\n',{flag:'wx'});
  console.log(JSON.stringify({status:receipt.status,screenshots:receipt.screenshots.length,checks:receipt.checks.length,
    selections:receipt.selections.length,wall_seconds:receipt.wall_seconds,error:receipt.error||null}));
}
