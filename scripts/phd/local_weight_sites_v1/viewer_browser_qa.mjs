// Actual exported case data in a dedicated CPU Chromium container.
import fs from 'node:fs/promises';
import {spawn} from 'node:child_process';
import crypto from 'node:crypto';

const [url, out='/out', mode='full'] = process.argv.slice(2);
if(!url||new URL(url).hostname!=='127.0.0.1')throw Error('Local viewer URL required');
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
let browser,display,socket,sequence=0;
const pending=new Map(),events=[],chromeLog=[];
const receipt={status:'RUNNING',url,scientific_verdict:null,checks:[],screenshots:[],software_rendering:true};
function check(pass,name,data){receipt.checks.push({name,pass:!!pass,data});if(!pass)throw Error(name);}
function send(method,params={}){const id=++sequence;return new Promise((resolve,reject)=>{const timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout '+method));},30000);pending.set(id,{resolve:value=>{clearTimeout(timer);resolve(value);},reject:error=>{clearTimeout(timer);reject(error);}});socket.send(JSON.stringify({id,method,params}));});}
async function ev(expression){const response=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(response.exceptionDetails)throw Error(JSON.stringify(response.exceptionDetails));return response.result.value;}
async function ready(cid){for(let i=0;i<600;i++){const state=await ev('(()=>{const q=window.__LOCAL_WEIGHT_QA__;return q?{...q,settled:q.settled}:null;})()');if(state?.errors?.length)throw Error(JSON.stringify(state.errors));if(state?.ready&&state?.settled&&(!cid||state.caseID===cid))return state;await pause(100);}throw Error('Viewer timeout '+cid);}
async function choose(id,value){await ev(`(()=>{const el=document.getElementById(${JSON.stringify(id)});el.value=${JSON.stringify(value)};el.dispatchEvent(new Event('change',{bubbles:true}));})()`);await pause(150);}
async function click(id){await ev(`document.getElementById(${JSON.stringify(id)}).click()`);await pause(100);}
async function screenshot(name,anchor){if(anchor)await ev(`document.getElementById(${JSON.stringify(anchor)}).scrollIntoView({behavior:'instant'})`);await pause(200);const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});const bytes=Buffer.from(shot.data,'base64');await fs.writeFile(out+'/'+name,bytes,{flag:'wx'});receipt.screenshots.push({name,sha256:crypto.createHash('sha256').update(bytes).digest('hex')});}
async function selectCase(cid){await ev(`document.querySelector('#case-list [data-case="${cid}"]').click()`);return ready(cid);}
async function imagesReady(){await ev("document.getElementById('photos-section').scrollIntoView({behavior:'instant'})");await ev("Promise.all([...document.querySelectorAll('#photos image')].map(svg=>new Promise((resolve,reject)=>{const image=new Image();image.onload=()=>resolve(image.naturalWidth);image.onerror=()=>reject(Error('Source photo failed'));image.src=svg.getAttribute('href');})))");}
async function raster(){return ev(`(()=>{return [...document.querySelectorAll('.view canvas')].map(canvas=>{const gl=canvas.getContext('webgl2')||canvas.getContext('webgl');if(!gl)return {ok:false};const bytes=new Uint8Array(canvas.width*canvas.height*4);gl.readPixels(0,0,canvas.width,canvas.height,gl.RGBA,gl.UNSIGNED_BYTE,bytes);let different=0;for(let i=4;i<bytes.length;i+=4)if(bytes[i]!==bytes[0]||bytes[i+1]!==bytes[1]||bytes[i+2]!==bytes[2])different++;return {ok:different>20,different};});})()`);}
try{
  const profile=await fs.mkdtemp('/tmp/local-weight-qa-');
  display=spawn('/usr/bin/Xvfb',['-displayfd','1','-screen','0','1700x1200x24','-nolisten','tcp']);
  const displayNumber=await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('Xvfb timeout')),10000);display.stdout.once('data',bytes=>{clearTimeout(timer);resolve(bytes.toString().trim());});});
  for(const suffix of ['config','cache','data'])await fs.mkdir(profile+'/'+suffix);
  const args=['--headless=new','--no-sandbox','--no-first-run','--no-default-browser-check','--enable-automation','--disable-dev-shm-usage','--ozone-platform=headless','--use-gl=angle','--use-angle=gl','--ignore-gpu-blocklist','--disable-vulkan','--remote-debugging-address=127.0.0.1','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'];
  browser=spawn('/usr/bin/chromium',args,{env:{...process.env,DISPLAY:':'+displayNumber,LIBGL_ALWAYS_SOFTWARE:'1',XDG_CONFIG_HOME:profile+'/config',XDG_CACHE_HOME:profile+'/cache',XDG_DATA_HOME:profile+'/data'}});
  browser.stderr.on('data',bytes=>chromeLog.push(bytes.toString()));
  let port;for(let i=0;i<150;i++){try{port=(await fs.readFile(profile+'/DevToolsActivePort','utf8')).split('\n')[0];break;}catch{await pause(100);}}
  check(port,'dedicated CPU browser started');
  const pages=await(await fetch('http://127.0.0.1:'+port+'/json/list')).json();
  socket=new WebSocket(pages.find(page=>page.type==='page').webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
  socket.addEventListener('message',event=>{const message=JSON.parse(event.data);if(message.id){const callback=pending.get(message.id);if(callback){pending.delete(message.id);message.error?callback.reject(Error(JSON.stringify(message.error))):callback.resolve(message.result);}}else events.push(message);});
  await send('Page.enable');await send('Runtime.enable');await send('Network.enable');
  await send('Emulation.setDeviceMetricsOverride',{width:1680,height:1120,deviceScaleFactor:1,mobile:false});
  if(mode==='entry'){
    const destination=new URL(url);
    for(const old of ['local_weight_sites_20260920_v2','local_weight_sites_20260921_v3']){
      const entry=new URL('/data/'+old+'/index.html?case=W019#photos-section',url);
      await send('Page.navigate',{url:entry.href});await ready('W019');await imagesReady();
      const actual=await ev('({pathname:location.pathname,query:location.search,hash:location.hash,photo:window.__LOCAL_WEIGHT_QA__.photo})');
      check(actual.pathname===destination.pathname&&actual.query==='?case=W019'&&actual.hash==='#photos-section',old+' preserves case and section through relative redirect',actual);
      check(actual.photo.points===10,old+' reaches visible point-overlay viewer');
    }
    await screenshot('old_entry_to_current.png','photos-section');
    for(const old of ['local_weight_sites_20260920_v2','local_weight_sites_20260921_v3']){
      await send('Page.navigate',{url:new URL('/data/'+old+'/index.archived.html?case=C10',url).href});
      await ready('C10');check((await ev('location.pathname')).endsWith('/index.archived.html'),old+' historical viewer remains usable');
    }
    const errors=events.filter(event=>event.method==='Runtime.exceptionThrown'||event.method==='Network.loadingFailed'&&!event.params.canceled||event.method==='Network.responseReceived'&&event.params.response.status>=400);
    check(errors.length===0,'entry and archive pages have no runtime or HTTP errors',errors);
    receipt.status='PASS';
  }else{
  await send('Page.navigate',{url});
  let state=await ready('C10');
  const catalog=await(await fetch(new URL('catalog.json',url))).json();
  check(catalog.cases.length===20&&catalog.priority_count===6,'all historical cases retained with revised six priorities');
  check(catalog.cases.find(c=>c.id==='W019').group==='held'&&!catalog.cases.find(c=>c.id==='W019').priority,'W019 retained as correspondence diagnostic');
  check(state.caseID==='C10','default case is R1 Z07');
  await screenshot('C10_overview.png');
  for(const entry of catalog.cases){
    if(entry.id!=='C10')state=await selectCase(entry.id);
    const spec=await(await fetch(new URL(entry.file,url))).json();
    if(spec.mvs_audit){
      check((await ev('window.__LOCAL_WEIGHT_QA__.mvsAudit.status'))===spec.mvs_audit.status,entry.id+' MVS review status matches audited source');
      check(await ev("document.querySelectorAll('#mvs-audit-table tr').length===20"),entry.id+' all 20 MVS reviews remain listed');
    }
    check(state.slice===(spec.metric_basis==='MVS'?'all':'0.5'),entry.id+' geometry-appropriate initial view');
    check(state.panels.length===4&&state.panels.every(panel=>panel.drawn&&(panel.role==='input'||panel.triangles>0)&&panel.scored===spec.cohorts.all.n),entry.id+' exact native mesh and scored cohort',state.panels);
    check(new Set(state.panels.map(panel=>JSON.stringify(panel.camera))).size===1&&new Set(state.panels.map(panel=>panel.meters_per_pixel)).size===1,entry.id+' camera and scale synchronization');
    const shown=await ev("[...document.querySelectorAll('#metric-cards strong')].map(node=>node.textContent)");
    check(JSON.stringify(shown)===JSON.stringify(['prior','mvs','da3'].map(role=>spec.cohorts.all.metrics[role].median_m.toFixed(3))),entry.id+' metrics match exact selected data',shown);
    check((await ev("document.getElementById('metric-definition').textContent")).includes(spec.metric_basis==='MVS'?'독립 정확도 아님':'UAS 참조'),entry.id+' evaluation metric role explicit');
    await imagesReady();
    check(await ev("(()=>{const photos=document.getElementById('photos');return photos.hidden?!document.querySelector('#photos image')&&!document.getElementById('photo-empty').hidden:document.querySelectorAll('#photos image').length===2;})()"),entry.id+' full and crop source images or explicit absence');
    if(spec.photo_views.length){
      const actual=await ev("[...document.querySelectorAll('#photo-detail .photo-dot')].map(g=>({id:Number(g.dataset.point),x:Number(g.querySelector('circle').getAttribute('cx')),y:Number(g.querySelector('circle').getAttribute('cy'))}))");
      const expected=spec.photo_views[0].points.filter(p=>p.in_frame);
      check(actual.length===expected.length&&actual.every((p,i)=>p.id===expected[i].id&&Math.abs(p.x-expected[i].xy[0])<1e-6&&Math.abs(p.y-expected[i].xy[1])<1e-6),entry.id+' exact original-pixel point overlay', {displayed:actual.length});
      check(spec.photo_views.every(v=>v.points.length===spec.cohorts.all.n&&new Set(v.points.map(p=>p.id)).size===spec.cohorts.all.n),entry.id+' stable point identity across views');
    }
    check(spec.validation.length===4&&spec.validation.every(item=>item.max_distance_replay_error_m<.001),entry.id+' cropped geometry distance identity');
    if(['C10','W019','W138','C03','C04','C05'].includes(entry.id)){
      await screenshot(entry.id+'_surfaces.png','surfaces');
      const rasterized=await raster();check(rasterized.every(item=>item.ok),entry.id+' WebGL rasterized',rasterized);
    }
    if(entry.id==='C05'){await screenshot('C05_mvs_audit.png','mvs-audit-card');await screenshot('C05_photos.png','photos-section');}
    if(entry.id==='W019'){
      await screenshot('W019_photos.png','photos-section');
      const point=spec.photo_views[0].points.find(p=>p.in_frame&&p.mvs_supported).id;
      await ev(`document.querySelector('#photo-detail [data-point="${point}"]').dispatchEvent(new MouseEvent('click',{bubbles:true}))`);
      check((await ev('window.__LOCAL_WEIGHT_QA__.photo.selected'))===point,'actual projection point click selects same ID');
      await choose('photo-view','1');
      check((await ev('window.__LOCAL_WEIGHT_QA__.photo.selected'))===point,'selected point preserved across camera change');
      await screenshot('W019_point_second_view.png','photos-section');
      await click('photo-points');check(await ev("document.querySelectorAll('#photos .photo-dot').length===0"),'overlay off leaves unmodified photos');await click('photo-points');
    }
  }
  state=await selectCase('C10');
  await choose('cohort','upper');state=await ready('C10');
  check(state.panels.every(panel=>panel.scored===80)&&(await ev("document.getElementById('cohort-note').textContent")).includes('80점 중 80점'),'Z07 upper cohort changes both data and displayed points');
  check((await ev("document.querySelectorAll('#metric-cards strong')[1].textContent"))==='1.606','Z07 upper residual remains 1.606m');
  await screenshot('C10_upper80.png','numbers');
  check((await ev('window.__LOCAL_WEIGHT_QA__.photo.points'))===80,'Z07 photo projections follow upper cohort');
  await imagesReady();await screenshot('C10_upper80_photos.png','photos-section');
  await choose('slice','all');await click('oblique');state=await ready('C10');
  check(state.slice==='all'&&new Set(state.panels.map(panel=>JSON.stringify(panel.camera))).size===1,'uncut oblique synchronized');
  await screenshot('C10_oblique.png','surfaces');
  await choose('section-axis','v');state=await ready('C10');check(state.axis==='v','orthogonal native section control');
  await choose('fourth','local_prior0');state=await ready('C10');check(state.panels.at(-1).role==='local_prior0','historical local-prior0 model switch');
  await click('wireframe');await click('connectors');await click('xray');await click('show-mvs');
  await choose('fourth','da3');await choose('section-axis','u');await choose('cohort','all');await click('reset');
  await choose('filter-role','priority');check(await ev("document.querySelectorAll('#case-list [data-case]').length===6"),'priority filter includes C10 and five DA3 cases');
  await choose('filter-role','excluded');check(await ev("document.querySelectorAll('#case-list [data-case]').length===2"),'excluded evidence remains inspectable');
  await choose('filter-role','all');await choose('filter-region','R2');check(await ev("[...document.querySelectorAll('#case-list .name')].every(el=>el.textContent.includes('R2'))"),'region filter');
  await choose('filter-region','all');await click('map-region');
  const mapTarget=await ev("(()=>{const p=window.__LOCAL_WEIGHT_QA__.map.markers.find(x=>x.id==='W019'),r=document.getElementById('map').getBoundingClientRect();return {x:r.left+p.x,y:r.top+p.y};})()");
  await send('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...mapTarget});
  await send('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...mapTarget});
  state=await ready('W019');check(state.caseID==='W019','actual map click selects W019');
  await click('photo-open');check(await ev("document.getElementById('photo-dialog').open"),'photo enlargement opens');await click('photo-close');
  await ev("document.querySelector('#case-list [data-case=\"C03\"]').click();document.querySelector('#case-list [data-case=\"C10\"]').click()");
  state=await ready('C10');check(state.caseID==='C10','rapid navigation retains latest case');
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:900,deviceScaleFactor:1,mobile:true});
  await ev("scrollTo({top:0,behavior:'instant'})");await pause(400);state=await ready('C10');
  const width=await ev('({viewport:innerWidth,page:document.documentElement.scrollWidth})');check(width.page<=width.viewport+1,'mobile no horizontal page overflow',width);await screenshot('mobile.png');
  await screenshot('mobile_surfaces.png','surfaces');
  await imagesReady();await screenshot('mobile_photos.png','photos-section');
  check(await ev('document.documentElement.scrollWidth<=innerWidth+1'),'mobile photos do not overflow');
  const errors=events.filter(event=>event.method==='Runtime.exceptionThrown'||event.method==='Network.loadingFailed'&&!event.params.canceled||event.method==='Network.responseReceived'&&event.params.response.status>=400);
  check(errors.length===0,'no runtime or HTTP errors',errors);
  receipt.status='PASS';
  }
}catch(error){receipt.status='FAIL';receipt.error=String(error);process.exitCode=1;try{receipt.state=await ev('window.__LOCAL_WEIGHT_QA__||null');await screenshot('failure.png');}catch{}receipt.events=events.filter(event=>event.method==='Runtime.exceptionThrown'||event.method==='Network.loadingFailed'||event.method==='Network.responseReceived'&&event.params.response.status>=400);}
finally{socket?.close();browser?.kill('SIGTERM');display?.kill('SIGTERM');await fs.writeFile(out+'/chrome.log',chromeLog.join(''));await fs.writeFile(out+'/receipt.json',JSON.stringify(receipt,null,2)+'\n');console.log(JSON.stringify({status:receipt.status,error:receipt.error,checks:receipt.checks.length,screenshots:receipt.screenshots.length}));}
