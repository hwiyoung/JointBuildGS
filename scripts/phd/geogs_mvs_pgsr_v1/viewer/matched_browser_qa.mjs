// Actual matched mesh/render QA. Launch only after the matched data is ready.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {spawn} from 'node:child_process';

const [url='http://127.0.0.1:8910/app/matched.html',output='/out']=process.argv.slice(2);
const target=new URL(url);
if(target.href!=='http://127.0.0.1:8910/app/matched.html')throw Error('Exact frozen matched viewer URL required');
const roles=['da3','mvs','mvs_pgsr'],regionIDs=['P1','P2'];
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const hash=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
const started=Date.now(),deadline=started+300000,pending=new Map(),events=[],chromeLog=[];
let browser,display,socket,sequence=0;
const receipt={schema:'GEOGS_MATCHED_BROWSER_QA_v1',status:'RUNNING',scientific_verdict:null,
  started_at:new Date().toISOString(),url,image_id:process.env.GEOGS_QA_IMAGE_ID,
  scope:'Actual three-way raw RGB mesh, synchronized cameras and same-view RGB/depth display; no training, extraction, scoring or scientific verdict',
  limits:{wall_seconds:300,host_gpu_devices:false,cpu_browser:true},regions:[],views:[],cameras:[],screenshots:[],checks:[]};

function check(pass,name,details){receipt.checks.push({name,pass:!!pass,details});if(!pass)throw Error(name);}
function timeLeft(){if(Date.now()>=deadline)throw Error('Bounded matched browser QA deadline reached');return deadline-Date.now();}
function send(method,params={}){
  const milliseconds=Math.min(timeLeft(),20000),id=++sequence;
  return new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout: '+method));},milliseconds);
    pending.set(id,{resolve:value=>{clearTimeout(timer);resolve(value);},reject:error=>{clearTimeout(timer);reject(error);}});
    socket.send(JSON.stringify({id,method,params}));
  });
}
async function evaluate(expression){
  const result=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
  if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result?.value;
}
async function frames(){await evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))');}
async function ready(region,view){
  const end=Math.min(deadline,Date.now()+60000);
  while(Date.now()<end){
    const state=await evaluate('window.__GEOGS_MATCHED_QA__ || null');
    if(state?.errors?.length)throw Error(JSON.stringify(state.errors));
    if(state?.ready&&state.settled&&(!region||state.region===region)&&(!view||state.selected_view===view)){
      await frames();return evaluate('window.__GEOGS_MATCHED_QA__');
    }
    await pause(80);
  }
  throw Error('Matched page did not settle: '+JSON.stringify({region,view}));
}
async function click(selector){await evaluate(`(()=>{const el=document.querySelector(${JSON.stringify(selector)});if(!el||el.disabled)throw Error('Missing enabled control');el.click();})()`);}
async function choose(selector,value){await evaluate(`(()=>{const el=document.querySelector(${JSON.stringify(selector)});if(!el||![...el.options].some(o=>o.value===${JSON.stringify(value)}&&!o.disabled))throw Error('Missing selectable option');el.value=${JSON.stringify(value)};el.dispatchEvent(new Event('change',{bubbles:true}));})()`);}
async function actualBytes(relative){
  const response=await fetch(new URL(relative,target));check(response.ok,'actual_http_source_available',{relative,status:response.status});
  return Buffer.from(await response.arrayBuffer());
}
async function capture(filename){
  const result=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
  const bytes=Buffer.from(result.data,'base64');check(bytes.length>2000,'actual_png_screenshot',{filename,bytes:bytes.length});
  await fs.writeFile(path.join(output,filename),bytes,{flag:'wx'});receipt.screenshots.push({filename,bytes:bytes.length,sha256:hash(bytes)});
}
function synchronized(state,action){
  const first=state.cameras.da3;
  check(first&&roles.every(role=>JSON.stringify(state.cameras[role])===JSON.stringify(first)),
    'three_cameras_exactly_synchronized',{region:state.region,action,cameras:state.cameras});
  receipt.cameras.push({region:state.region,action,cameras:state.cameras});
}
async function geometryPixels(){
  return evaluate(`(()=>${JSON.stringify(roles)}.map(role=>{
    const panel=document.querySelector('[data-panel="'+role+'"]'),canvas=panel?.querySelector('canvas'),empty=panel?.querySelector('.empty');
    if(!canvas)return{role,canvas:false};
    const gl=canvas.getContext('webgl2')||canvas.getContext('webgl');if(!gl)return{role,canvas:true,webgl:false};
    const rgba=new Uint8Array(canvas.width*canvas.height*4);gl.readPixels(0,0,canvas.width,canvas.height,gl.RGBA,gl.UNSIGNED_BYTE,rgba);
    const key=i=>(rgba[i]<<16)|(rgba[i+1]<<8)|rgba[i+2],background=key(0),colors=new Set();let nonbackground=0;
    for(let i=0;i<rgba.length;i+=4){const value=key(i);if(value!==background){nonbackground++;if(colors.size<8192)colors.add(value);}}
    return{role,canvas:true,webgl:true,width:canvas.width,height:canvas.height,nonbackground_pixels:nonbackground,
      distinct_nonbackground_rgb:colors.size,missing_visible:!!empty&&!empty.hidden};
  }))()`);
}
function checkGeometry(state,raster){
  for(const role of roles){
    const panel=state.panels?.[role],row=raster.find(r=>r.role===role);
    check(panel?.status==='available'&&panel.representation==='mesh'&&panel.count>0&&panel.triangle_count>0&&panel.drawn,
      'three_actual_nonempty_default_meshes',{region:state.region,role,panel});
    check(panel.integrity==='SHA256_AND_BYTES_VERIFIED'&&panel.buffers?.length===3&&panel.buffers.every(b=>b.bytes>0&&b.sha256===b.expected_sha256&&/^[a-f0-9]{64}$/.test(b.sha256)),
      'browser_bound_mesh_sha256',{region:state.region,role,buffers:panel.buffers});
    check(row?.webgl&&!row.missing_visible&&row.nonbackground_pixels>10&&row.distinct_nonbackground_rgb>3,
      'actual_mesh_canvas_nonbackground_rgb',{region:state.region,...row});
  }
}
async function imagePixels(){
  return evaluate(`(()=>Array.from(document.querySelectorAll('.image-slot'),slot=>{
    const image=slot.querySelector('img'),panel=slot.closest('[data-render]'),key=panel?panel.dataset.render+'.'+(slot.classList.contains('rgb')?'rgb':'depth'):'original';
    if(!image||!image.complete||image.naturalWidth<1)return{key,loaded:false,text:slot.textContent};
    const canvas=document.createElement('canvas');canvas.width=192;canvas.height=139;const context=canvas.getContext('2d',{willReadFrequently:true});
    context.drawImage(image,0,0,canvas.width,canvas.height);const pixels=context.getImageData(0,0,canvas.width,canvas.height).data,colors=new Set();
    let opaque=0;for(let i=0;i<pixels.length;i+=4){if(pixels[i+3])opaque++;if(colors.size<8192)colors.add((pixels[i]<<16)|(pixels[i+1]<<8)|pixels[i+2]);}
    return{key,loaded:true,width:image.naturalWidth,height:image.naturalHeight,distinct_sampled_rgb:colors.size,opaque_sampled_pixels:opaque,alt:image.alt};
  }))()`);
}
function imageDescriptor(view,key){if(key==='original')return view.original;const [role,kind]=key.split('.');return view.conditions?.[role]?.[kind];}
async function checkImages(state,view){
  const raster=await imagePixels(),keys=['original',...roles.flatMap(role=>[role+'.rgb',role+'.depth'])];
  check(raster.length===7&&keys.every(key=>raster.some(r=>r.key===key)),'seven_actual_images_per_camera',{region:state.region,view:view.id,raster});
  const dimensions=[];
  for(const key of keys){
    const row=raster.find(r=>r.key===key),runtime=state.images?.[key],descriptor=imageDescriptor(view,key);
    check(row.loaded&&row.width>1&&row.height>1&&row.distinct_sampled_rgb>1&&row.opaque_sampled_pixels>100,
      'actual_nonblank_decoded_image',{region:state.region,view:view.id,...row});
    check(runtime?.status==='available'&&runtime.view===view.id&&descriptor?.sha256===runtime.sha256
      &&/^[a-f0-9]{64}$/.test(runtime.sha256)&&descriptor.bytes===runtime.bytes,
      'decoded_image_bytes_sha256_match_bound_source',{region:state.region,view:view.id,key,runtime,descriptor});
    dimensions.push([row.width,row.height]);
  }
  check(dimensions.every(size=>JSON.stringify(size)===JSON.stringify(dimensions[0])),
    'same_crop_dimensions_original_and_six_renders',{region:state.region,view:view.id,dimensions});
  check(Array.isArray(view.depth_range_m)&&view.depth_range_m.length===2&&view.depth_range_m.every(Number.isFinite)&&view.depth_range_m[0]<view.depth_range_m[1],
    'shared_depth_display_range_declared',{region:state.region,view:view.id,range:view.depth_range_m});
  check(await evaluate('document.getElementById("depth-scale").textContent.includes("세 조건 공통 depth 표시 범위")'),
    'shared_depth_range_visible',{region:state.region,view:view.id});
  receipt.views.push({region:state.region,view_id:view.id,image_name:view.image_name,depth_range_m:view.depth_range_m,roi_bbox:view.roi_bbox,raster,loaded_images:state.images});
}
async function optionalCenters(region){
  const available=['all','alpha01'].filter(mode=>region.conditions.every(c=>c.centers?.[mode]));
  receipt.center_diagnostics=receipt.center_diagnostics || [];
  for(const mode of ['all','alpha01'])if(!region.conditions.some(c=>c.centers?.[mode]))check(
    await evaluate(`document.querySelector('#representation option[value="${mode}"]').disabled`),
    'absent_center_diagnostic_disabled',{region:region.id,mode});
  for(const mode of available){
    await choose('#representation',mode);const state=await ready(region.id);
    for(const role of roles){const panel=state.panels[role];check(panel.status==='available'&&panel.representation===mode&&panel.point_size_px===2,
      'optional_centers_same_fixed_point_size',{region:region.id,mode,role,panel});
      check(mode!=='alpha01'||panel.alpha_threshold===.1,'optional_opacity_threshold_explicit',{region:region.id,mode,role,threshold:panel.alpha_threshold});}
    check(await evaluate('document.getElementById("representation-note").textContent.includes("진단용")'),'centers_display_only_label_visible',{region:region.id,mode});
    synchronized(state,'centers_'+mode);receipt.center_diagnostics.push({region:region.id,mode,panels:state.panels});
  }
  if(available.length){await choose('#representation','mesh');await ready(region.id);}
}
async function stop(child){
  if(!child||child.exitCode!==null||child.signalCode!==null)return;
  await new Promise(resolve=>{const timeout=setTimeout(()=>child.kill('SIGKILL'),2500);child.once('close',()=>{clearTimeout(timeout);resolve();});child.kill('SIGTERM');});
}

try{
  const profile=await fs.mkdtemp('/tmp/geogs-matched-qa-');
  display=spawn('/usr/bin/Xvfb',['-displayfd','1','-screen','0','1800x1400x24','-nolisten','tcp']);display.stderr.on('data',bytes=>chromeLog.push('Xvfb: '+bytes));
  const number=await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('Xvfb start timeout')),10000);display.stdout.once('data',bytes=>{clearTimeout(timer);const value=bytes.toString().trim();/^\d+$/.test(value)?resolve(value):reject(Error('Invalid Xvfb display'));});display.once('error',reject);});
  receipt.dedicated_xvfb_display=number;
  for(const suffix of ['config','cache','data'])await fs.mkdir(profile+'/'+suffix);
  const args=['--headless=new','--no-sandbox','--no-first-run','--no-default-browser-check','--enable-automation','--disable-dev-shm-usage',
    '--ozone-platform=headless','--use-gl=angle','--use-angle=gl','--ignore-gpu-blocklist','--disable-vulkan','--remote-debugging-address=127.0.0.1',
    '--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'];
  receipt.chrome_args=args;receipt.software_webgl='Docker Xvfb + software ANGLE GL; no host display or GPU device mounted';
  browser=spawn(process.env.CHROME_BIN||'/usr/bin/chromium',args,{env:{...process.env,DISPLAY:':'+number,LIBGL_ALWAYS_SOFTWARE:'1',XDG_CONFIG_HOME:profile+'/config',XDG_CACHE_HOME:profile+'/cache',XDG_DATA_HOME:profile+'/data'}});
  browser.stderr.on('data',bytes=>chromeLog.push(bytes.toString()));
  let port;for(let i=0;i<150;i++){try{port=(await fs.readFile(path.join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0];break;}catch{await pause(100);}}
  if(!port)throw Error('Dedicated Chrome start timeout');
  const pages=await(await fetch(`http://127.0.0.1:${port}/json/list`)).json();socket=new WebSocket(pages.find(item=>item.type==='page').webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
  socket.addEventListener('message',event=>{const message=JSON.parse(event.data);if(message.id){const item=pending.get(message.id);if(item){pending.delete(message.id);message.error?item.reject(Error(JSON.stringify(message.error))):item.resolve(message.result);}}else events.push(message);});
  receipt.browser=await send('Browser.getVersion');receipt.node_version=process.version;
  await send('Page.enable');await send('Runtime.enable');await send('Network.enable');
  await send('Emulation.setDeviceMetricsOverride',{width:1800,height:1400,deviceScaleFactor:1,mobile:false});
  await send('Page.navigate',{url});await ready();
  check(await evaluate('!!globalThis.crypto?.subtle'),'browser_sha256_available');
  check(await evaluate('document.querySelectorAll(".geometry-panel[data-panel]").length')===3,'three_geometry_columns_present');
  check(await evaluate('document.getElementById("representation").value')==='mesh','raw_mesh_default_without_substitution');
  check(await evaluate('document.querySelector("header a").getAttribute("href")')==='/', 'existing_viewer_return_link_targets_root');
  receipt.app_sources=[];
  for(const name of ['matched.html','matched.js','matched.css']){
    const actual=await actualBytes('/app/'+name),expected=await fs.readFile(path.join(output,'app_'+name));
    check(hash(actual)===hash(expected),'served_app_matches_execution_snapshot',{name,actual_sha256:hash(actual),snapshot_sha256:hash(expected)});
    receipt.app_sources.push({name,bytes:actual.length,sha256:hash(actual)});
  }
  const bytes=await actualBytes('/data/matched/manifest.json'),manifest=JSON.parse(bytes.toString());
  await fs.writeFile(path.join(output,'served_manifest.json'),bytes,{flag:'wx'});
  receipt.manifest={bytes:bytes.length,sha256:hash(bytes),generated_at:manifest.generated_at,surface_contract:manifest.surface_contract};
  check(manifest.schema==='geogs_matched_comparison_v1'&&manifest.scientific_verdict===null,'matched_schema_and_null_scientific_verdict');
  check(JSON.stringify(manifest.regions.map(r=>r.id))===JSON.stringify(regionIDs),'requested_p1_p2_present');
  check(manifest.surface_contract?.surface==='raw'&&manifest.surface_contract?.mesh_resolution===512,'same_raw_tsdf512_surface_contract',manifest.surface_contract);
  for(const region of manifest.regions){
    await click('[data-region="'+region.id+'"]');let state=await ready(region.id);
    const raster=await geometryPixels();checkGeometry(state,raster);synchronized(state,'default');receipt.regions.push({region:region.id,state,raster});
    for(const viewName of ['top','oblique','side']){
      await click('[data-preset="'+viewName+'"]');await frames();state=await ready(region.id);synchronized(state,viewName);
      if(viewName==='top')check(state.cameras.da3.pitch>1.5,'top_preset_looks_down',{region:region.id,camera:state.cameras.da3});
      if(viewName==='side')check(Math.abs(state.cameras.da3.pitch)<.1,'side_preset_looks_horizontally',{region:region.id,camera:state.cameras.da3});
      await evaluate('window.scrollTo(0,0)');await frames();await capture(region.id+'_'+viewName+'_raw_rgb_mesh.png');
    }
    const views=region.views || [];
    check(views.length===2&&new Set(views.map(v=>v.id)).size===2,'two_frozen_camera_views_per_region',{region:region.id,views:views.map(v=>({id:v.id,image_name:v.image_name}))});
    for(let index=0;index<views.length;index++){
      const view=views[index];await choose('#photo-view',view.id);state=await ready(region.id,view.id);await checkImages(state,view);
      await evaluate('document.querySelector(".renders").scrollIntoView({block:"start"})');await frames();await capture(region.id+'_view'+(index+1)+'_actual_rgb_depth.png');
    }
    await optionalCenters(region);
  }
  await click('[data-region="P1"]');await ready('P1');await click('[data-preset="oblique"]');await frames();
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
  await frames();await evaluate('window.scrollTo(0,0)');await frames();
  const mobile=await evaluate(`(()=>({viewport:innerWidth,document:document.documentElement.scrollWidth,
    grids:Array.from(document.querySelectorAll('.three-columns'),grid=>{const r=grid.getBoundingClientRect();return{left:r.left,right:r.right,width:r.width,clientWidth:grid.clientWidth,scrollWidth:grid.scrollWidth,overflow:getComputedStyle(grid).overflowX};}),
    canvas_count:document.querySelectorAll('.viewport canvas').length}))()`);
  check(mobile.viewport===390&&mobile.document<=391&&mobile.canvas_count===3&&mobile.grids.length===2&&mobile.grids.every(g=>g.left>=-1&&g.right<=391&&g.overflow==='auto'),
    'mobile390_page_fits_with_explicit_horizontal_comparison_grids',mobile);
  const state=await ready('P1');synchronized(state,'mobile390');receipt.mobile=mobile;await capture('mobile_390px.png');
  const failures=events.filter(e=>e.method==='Runtime.exceptionThrown'||e.method==='Network.loadingFailed'||(e.method==='Network.responseReceived'&&e.params.response.status>=400));
  check(failures.length===0,'no_browser_exception_or_failed_network_request',failures);
  check(receipt.regions.length===2&&receipt.views.length===4&&receipt.screenshots.length===11,'all_requested_regions_views_and_screenshots_recorded');
  receipt.status='PASS_MATCHED_BROWSER_QA';
}catch(error){receipt.status='FAIL_MATCHED_BROWSER_QA';receipt.error=String(error);process.exitCode=1;}
finally{
  if(socket)socket.close();await stop(browser);await stop(display);
  receipt.completed_at=new Date().toISOString();receipt.wall_seconds=(Date.now()-started)/1000;
  await fs.writeFile(path.join(output,'chrome.log'),chromeLog.join(''),{flag:'wx'});
  await fs.writeFile(path.join(output,'receipt.json'),JSON.stringify(receipt,null,2)+'\n',{flag:'wx'});
  console.log(JSON.stringify({status:receipt.status,regions:receipt.regions.length,views:receipt.views.length,
    screenshots:receipt.screenshots.length,checks:receipt.checks.length,wall_seconds:receipt.wall_seconds,error:receipt.error || null}));
}
