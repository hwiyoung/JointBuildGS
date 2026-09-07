// Actual saved full-SH RGB comparison checks. No training or geometry extraction.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {spawn} from 'node:child_process';

const [url='http://127.0.0.1:8910/app/rgb_diagnostic.html',output='/out']=process.argv.slice(2);
const target=new URL(url);
if(target.href!=='http://127.0.0.1:8910/app/rgb_diagnostic.html')throw Error('Exact frozen RGB diagnostic URL required');
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const hash=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
const started=Date.now(),deadline=started+300000,pending=new Map(),events=[],chromeLog=[],imageCache=new Map();
let browser,display,socket,sequence=0;
const receipt={schema:'GEOGS_RGB_DIAGNOSTIC_BROWSER_QA_v1',status:'RUNNING',scientific_verdict:null,
  started_at:new Date().toISOString(),url,image_id:process.env.GEOGS_QA_IMAGE_ID,
  scope:'Actual 12 saved train/evaluation RGB cases with six conditions, original pixels, prior filters and synchronized native-size detail; no training, extraction or scientific verdict',
  limits:{wall_seconds:300,host_gpu_devices:false,cpu_browser:true},cases:[],filters:[],details:[],screenshots:[],checks:[]};
function check(pass,name,details){receipt.checks.push({name,pass:!!pass,details});if(!pass)throw Error(name);}
function timeLeft(){if(Date.now()>=deadline)throw Error('Bounded RGB browser QA deadline reached');return deadline-Date.now();}
function send(method,params={}){
  const milliseconds=Math.min(timeLeft(),20000),id=++sequence;
  return new Promise((resolve,reject)=>{const timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout: '+method));},milliseconds);
    pending.set(id,{resolve:value=>{clearTimeout(timer);resolve(value);},reject:error=>{clearTimeout(timer);reject(error);}});socket.send(JSON.stringify({id,method,params}));});
}
async function evaluate(expression){const result=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result?.value;}
async function frames(){await evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))');}
async function ready(caseID,prior){
  const end=Math.min(deadline,Date.now()+60000);
  while(Date.now()<end){const state=await evaluate('window.__GEOGS_RGB_DIAGNOSTIC_QA__ || null');
    if(state?.errors?.length)throw Error(JSON.stringify(state.errors));
    if(state?.ready&&(!caseID||state.case_id===caseID)&&(!prior||state.prior===prior)){await frames();return evaluate('window.__GEOGS_RGB_DIAGNOSTIC_QA__');}
    await pause(60);}
  throw Error('RGB diagnostic did not settle: '+JSON.stringify({caseID,prior}));
}
async function choose(selector,value){await evaluate(`(()=>{const el=document.querySelector(${JSON.stringify(selector)});if(!el||![...el.options].some(o=>o.value===${JSON.stringify(value)}&&!o.disabled))throw Error('Missing selectable option');el.value=${JSON.stringify(value)};el.dispatchEvent(new Event('change',{bubbles:true}));})()`);}
async function click(selector){await evaluate(`(()=>{const el=document.querySelector(${JSON.stringify(selector)});if(!el||el.disabled)throw Error('Missing enabled control');el.click();})()`);}
async function actualBytes(relative){const response=await fetch(new URL(relative,target));check(response.ok,'actual_http_source_available',{relative,status:response.status});return Buffer.from(await response.arrayBuffer());}
async function capture(filename,fullPage=false){const params={format:'png',captureBeyondViewport:fullPage};
  if(fullPage){const metrics=await send('Page.getLayoutMetrics'),size=metrics.cssContentSize||metrics.contentSize;params.clip={x:0,y:0,width:size.width,height:size.height,scale:1};}
  const result=await send('Page.captureScreenshot',params),bytes=Buffer.from(result.data,'base64');check(bytes.length>2000,'actual_png_screenshot',{filename,bytes:bytes.length,full_page:fullPage});await fs.writeFile(path.join(output,filename),bytes,{flag:'wx'});receipt.screenshots.push({filename,full_page:fullPage,bytes:bytes.length,sha256:hash(bytes)});}
async function selectCase(row,prior='both'){
  await choose('#region',row.region);await ready();await choose('#split',row.split);await ready();
  await choose('#case',row.id);await ready(row.id);await choose('#prior',prior);return ready(row.id,prior);
}
async function rasterImages(){return evaluate(`(()=>Array.from(document.querySelectorAll('.cards img'),img=>{
  const canvas=document.createElement('canvas');canvas.width=96;canvas.height=96;const context=canvas.getContext('2d',{willReadFrequently:true});
  if(!img.complete||img.naturalWidth<1)return{condition:img.dataset.condition,loaded:false};
  context.drawImage(img,0,0,96,96);const pixels=context.getImageData(0,0,96,96).data,colors=new Set();let opaque=0;
  for(let i=0;i<pixels.length;i+=4){if(pixels[i+3]===255)opaque++;colors.add((pixels[i]<<16)|(pixels[i+1]<<8)|pixels[i+2]);}
  return{condition:img.dataset.condition,loaded:true,width:img.naturalWidth,height:img.naturalHeight,src:img.currentSrc,distinct_rgb:colors.size,opaque_pixels:opaque,alt:img.alt};
}))()`);}
function descriptorHash(row,condition){return condition?condition.render_sha256:row.photo_sha256;}
async function checkImages(state,row,manifestURL,prior='both'){
  const raster=await rasterImages(),expected=prior==='both'?8:4,conditions=row.conditions.filter(c=>prior==='both'||Number(c.prior)===Number(prior));
  check(state.case_id===row.id&&state.region===row.region&&state.split===row.split&&state.prior===prior&&state.images===expected&&raster.length===expected,
    'controls_and_rendered_case_agree',{case_id:row.id,prior,state,decoded_count:raster.length});
  check(raster.filter(r=>r.condition==='photo').length===(prior==='both'?2:1)&&conditions.every(c=>raster.filter(r=>r.condition===c.id).length===1),
    'original_and_exact_condition_membership',{case_id:row.id,prior,conditions:raster.map(r=>r.condition)});
  for(const image of raster){const condition=image.condition==='photo'?null:conditions.find(c=>c.id===image.condition);const expectedURL=new URL(condition?condition.render_url:row.photo_url,manifestURL).href;
    check(image.loaded&&image.width===row.width&&image.height===row.height&&image.src===expectedURL&&image.distinct_rgb>1&&image.opaque_pixels===96*96,
      'decoded_native_crop_matches_manifest',{case_id:row.id,prior,image,expectedURL});
    let source=imageCache.get(expectedURL);if(!source){const bytes=await actualBytes(expectedURL);source={url:expectedURL,bytes:bytes.length,sha256:hash(bytes)};imageCache.set(expectedURL,source);}
    const expectedHash=descriptorHash(row,condition);check(/^[a-f0-9]{64}$/.test(expectedHash||'')&&expectedHash===source.sha256,'displayed_png_bytes_bound_to_manifest_sha256',{case_id:row.id,condition:image.condition,expected_sha256:expectedHash,...source});
    image.source_bytes=source.bytes;image.source_sha256=source.sha256;image.manifest_sha256=expectedHash;
  }
  return raster;
}
async function detailCheck(row,manifestURL){
  await click('.card-foot button');
  await evaluate('Promise.all([document.querySelector("#detail-photo").decode(),document.querySelector("#detail-render").decode()])');await frames();
  const condition=row.conditions.find(c=>c.mode==='da3'&&Number(c.prior)===.005);
  for(const scale of [1,2]){
    await choose('#zoom',String(scale));await frames();
    const state=await evaluate(`(()=>({open:document.querySelector('#detail').open,zoom:document.querySelector('#zoom').value,images:['detail-photo','detail-render'].map(id=>{const img=document.getElementById(id),r=img.getBoundingClientRect();return{id,width:r.width,height:r.height,natural_width:img.naturalWidth,natural_height:img.naturalHeight,src:img.currentSrc};})}))()`);
    check(state.open&&state.zoom===String(scale)&&state.images.length===2&&state.images.every(img=>img.width===row.width*scale&&img.height===row.height*scale&&img.natural_width===row.width&&img.natural_height===row.height),
      'native_and_twofold_detail_use_exact_pixel_dimensions',{case_id:row.id,scale,state});
    check(state.images[0].src===new URL(row.photo_url,manifestURL).href&&state.images[1].src===new URL(condition.render_url,manifestURL).href,'detail_same_selected_photo_and_condition',{case_id:row.id,scale,state});
    const scroll=await evaluate(`new Promise(resolve=>{const a=document.querySelectorAll('.viewport')[0],b=document.querySelectorAll('.viewport')[1];a.scrollLeft=157;a.scrollTop=173;requestAnimationFrame(()=>requestAnimationFrame(()=>resolve({a:[a.scrollLeft,a.scrollTop],b:[b.scrollLeft,b.scrollTop],max:[a.scrollWidth-a.clientWidth,a.scrollHeight-a.clientHeight]})));})`);
    check(JSON.stringify(scroll.a)===JSON.stringify(scroll.b),'detail_scroll_positions_synchronized',{case_id:row.id,scale,scroll});
    if(scale===2)check(scroll.a.some(value=>value>0),'twofold_detail_scroll_actually_moves',{case_id:row.id,scroll});
    receipt.details.push({case_id:row.id,scale,state,scroll});
    await capture(`${row.id}_detail_${scale*100}percent.png`);
  }
  await click('#close-detail');check(await evaluate('!document.querySelector("#detail").open'),'native_detail_closes',{case_id:row.id});
}
async function stop(child){if(!child||child.exitCode!==null||child.signalCode!==null)return;await new Promise(resolve=>{const timeout=setTimeout(()=>child.kill('SIGKILL'),2500);child.once('close',()=>{clearTimeout(timeout);resolve();});child.kill('SIGTERM');});}

try{
  const profile=await fs.mkdtemp('/tmp/geogs-rgb-diagnostic-qa-');
  display=spawn('/usr/bin/Xvfb',['-displayfd','1','-screen','0','1800x1400x24','-nolisten','tcp']);display.stderr.on('data',bytes=>chromeLog.push('Xvfb: '+bytes));
  const number=await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('Xvfb start timeout')),10000);display.stdout.once('data',bytes=>{clearTimeout(timer);const value=bytes.toString().trim();/^\d+$/.test(value)?resolve(value):reject(Error('Invalid Xvfb display'));});display.once('error',reject);});
  receipt.dedicated_xvfb_display=number;for(const suffix of ['config','cache','data'])await fs.mkdir(profile+'/'+suffix);
  const args=['--headless=new','--no-sandbox','--no-first-run','--no-default-browser-check','--enable-automation','--disable-dev-shm-usage','--ozone-platform=headless','--use-gl=angle','--use-angle=gl','--ignore-gpu-blocklist','--disable-vulkan','--remote-debugging-address=127.0.0.1','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'];
  receipt.chrome_args=args;
  browser=spawn(process.env.CHROME_BIN||'/usr/bin/chromium',args,{env:{...process.env,DISPLAY:':'+number,LIBGL_ALWAYS_SOFTWARE:'1',XDG_CONFIG_HOME:profile+'/config',XDG_CACHE_HOME:profile+'/cache',XDG_DATA_HOME:profile+'/data'}});browser.stderr.on('data',bytes=>chromeLog.push(bytes.toString()));
  let port;for(let i=0;i<150;i++){try{port=(await fs.readFile(path.join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0];break;}catch{await pause(100);}}
  if(!port)throw Error('Dedicated Chrome start timeout');
  const pages=await(await fetch(`http://127.0.0.1:${port}/json/list`)).json();socket=new WebSocket(pages.find(item=>item.type==='page').webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
  socket.addEventListener('message',event=>{const message=JSON.parse(event.data);if(message.id){const item=pending.get(message.id);if(item){pending.delete(message.id);message.error?item.reject(Error(JSON.stringify(message.error))):item.resolve(message.result);}}else events.push(message);});
  receipt.browser=await send('Browser.getVersion');receipt.node_version=process.version;
  await send('Page.enable');await send('Runtime.enable');await send('Network.enable');await send('Emulation.setDeviceMetricsOverride',{width:1800,height:1400,deviceScaleFactor:1,mobile:false});
  await send('Page.navigate',{url});await ready();
  check(await evaluate('document.querySelector("header a").getAttribute("href")')==='/','return_link_targets_existing_3d_viewer');
  check(await evaluate(`document.querySelector('aside').textContent.includes('평가뷰는 MVS와 독립인 검증 자료가 아닙니다.')`),'mvs_evaluation_independence_limit_visible');
  receipt.app_sources=[];for(const name of ['rgb_diagnostic.html','rgb_diagnostic.js','rgb_diagnostic.css']){const actual=await actualBytes('/app/'+name),expected=await fs.readFile(path.join(output,'app_'+name));check(hash(actual)===hash(expected),'served_app_matches_execution_snapshot',{name,actual_sha256:hash(actual),snapshot_sha256:hash(expected)});receipt.app_sources.push({name,bytes:actual.length,sha256:hash(actual)});}
  const pointerBytes=await actualBytes('/data/rgb_diagnostic_v1/latest.json'),pointer=JSON.parse(pointerBytes.toString());
  await fs.writeFile(path.join(output,'served_latest.json'),pointerBytes,{flag:'wx'});
  const manifestURL=new URL(pointer.manifest_url,target),manifestBytes=await actualBytes(manifestURL.href),manifest=JSON.parse(manifestBytes.toString());
  await fs.writeFile(path.join(output,'served_manifest.json'),manifestBytes,{flag:'wx'});receipt.manifest={url:manifestURL.href,sha256:hash(manifestBytes),bytes:manifestBytes.length};
  check(manifest.status==='PASS'&&manifest.scientific_verdict===null&&manifest.cases.length===12&&new Set(manifest.cases.map(r=>r.id)).size===12,'completed_twelve_case_null_verdict_manifest');
  for(const region of ['P1','P2','P3'])for(const split of ['train','evaluation'])check(manifest.cases.filter(r=>r.region===region&&r.split===split).length===2,'two_input_selected_cases_per_region_and_split',{region,split});
  for(const row of manifest.cases){check(row.conditions.length===6&&['da3','mvs','mvs_pgsr'].every(mode=>[.005,.0005].every(prior=>row.conditions.filter(c=>c.mode===mode&&Number(c.prior)===prior).length===1)),'six_exact_saved_conditions_per_case',{case_id:row.id});const state=await selectCase(row),raster=await checkImages(state,row,manifestURL);receipt.cases.push({case_id:row.id,region:row.region,split:row.split,state,raster});
    if(row.region==='P2'&&manifest.cases.find(r=>r.region==='P2'&&r.split===row.split).id===row.id){await evaluate('window.scrollTo(0,0)');await frames();await capture(row.id+'_both_priors.png',true);}
  }
  const detailRow=manifest.cases.find(r=>r.region==='P2'&&r.split==='train');await selectCase(detailRow);
  for(const prior of ['0.005','0.0005']){await choose('#prior',prior);const state=await ready(detailRow.id,prior),raster=await checkImages(state,detailRow,manifestURL,prior);receipt.filters.push({case_id:detailRow.id,prior,raster});}
  await choose('#prior','both');await ready(detailRow.id,'both');await detailCheck(detailRow,manifestURL);
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});await frames();await evaluate('window.scrollTo(0,0)');await frames();
  const mobile=await evaluate(`(()=>({viewport:innerWidth,document:document.documentElement.scrollWidth,controls:Array.from(document.querySelectorAll('.controls select'),el=>{const r=el.getBoundingClientRect();return{left:r.left,right:r.right,width:r.width};}),cards:Array.from(document.querySelectorAll('.cards'),el=>{const r=el.getBoundingClientRect();return{left:r.left,right:r.right,width:r.width};})}))()`);
  check(mobile.viewport===390&&mobile.document<=391&&mobile.controls.length===4&&mobile.controls.every(r=>r.left>=-1&&r.right<=391)&&mobile.cards.length===2&&mobile.cards.every(r=>r.left>=-1&&r.right<=391),'mobile390_no_page_or_control_overflow',mobile);receipt.mobile=mobile;await capture('mobile_390px.png');
  for(const source of receipt.app_sources){const bytes=await actualBytes('/app/'+source.name);check(hash(bytes)===source.sha256,'app_source_unchanged_through_all_checks',{name:source.name,sha256:hash(bytes)});}
  check(hash(await actualBytes('/data/rgb_diagnostic_v1/latest.json'))===hash(pointerBytes),'diagnostic_pointer_unchanged_through_all_checks');
  const failures=events.filter(e=>e.method==='Runtime.exceptionThrown'||e.method==='Network.loadingFailed'||(e.method==='Network.responseReceived'&&e.params.response.status>=400));check(failures.length===0,'no_browser_exception_or_failed_network_request',failures);
  check(receipt.cases.length===12&&receipt.filters.length===2&&receipt.details.length===2&&receipt.screenshots.length===5,'all_cases_filters_detail_scales_and_screenshots_recorded');receipt.source_images=[...imageCache.values()];receipt.status='PASS_RGB_DIAGNOSTIC_BROWSER_QA';
}catch(error){receipt.status='FAIL_RGB_DIAGNOSTIC_BROWSER_QA';receipt.error=String(error);process.exitCode=1;}
finally{if(socket)socket.close();await stop(browser);await stop(display);receipt.completed_at=new Date().toISOString();receipt.wall_seconds=(Date.now()-started)/1000;
  await fs.writeFile(path.join(output,'chrome.log'),chromeLog.join(''),{flag:'wx'});await fs.writeFile(path.join(output,'receipt.json'),JSON.stringify(receipt,null,2)+'\n',{flag:'wx'});
  console.log(JSON.stringify({status:receipt.status,cases:receipt.cases.length,filters:receipt.filters.length,details:receipt.details.length,screenshots:receipt.screenshots.length,checks:receipt.checks.length,wall_seconds:receipt.wall_seconds,error:receipt.error||null}));}
