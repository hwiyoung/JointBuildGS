import fs from 'node:fs/promises';
import {spawn} from 'node:child_process';
const out='/out',url='http://127.0.0.1:8913/';
const pause=ms=>new Promise(r=>setTimeout(r,ms));
let browser,display,socket,id=0;const pending=new Map(),events=[];
const receipt={status:'RUNNING',url,scientific_verdict:null,checks:[]};
function check(ok,name,data){receipt.checks.push({name,pass:!!ok,data});if(!ok)throw Error(name);}
function send(method,params={}){const n=++id;return new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('CDP timeout '+method)),15000);pending.set(n,{resolve:x=>{clearTimeout(timer);resolve(x)},reject});socket.send(JSON.stringify({id:n,method,params}));});}
async function ev(expression){const x=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(x.exceptionDetails)throw Error(JSON.stringify(x.exceptionDetails));return x.result.value;}
async function ready(){for(let n=0;n<300;n++){const q=await ev('window.__GEOGS_RGB_QA__||null');if(q?.errors?.length)throw Error(JSON.stringify(q.errors));if(q?.ready&&q?.settled)return q;await pause(100);}throw Error('Viewer did not settle');}
async function screenshot(name){const v=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await fs.writeFile(out+'/'+name,Buffer.from(v.data,'base64'));}
async function reviewReady(region){
 for(let n=0;n<200;n++){
  const data=await ev('(()=>{const r=document.getElementById("region-review"),m=r.querySelector("img[src*=whole_area_judgment]");return {region:r.dataset.region,rows:r.querySelectorAll("tbody tr").length,map:!!m&&m.complete&&m.naturalWidth>0,images:r.querySelectorAll("img").length};})()');
  if(data.region===region&&data.rows>0&&data.map){check(true,region+' automatic map and table',data);return;}
  await pause(100);
 }
 throw Error(region+' inline review did not load');
}
try{
 const profile=await fs.mkdtemp('/tmp/r1-qa-');display=spawn('/usr/bin/Xvfb',['-displayfd','1','-screen','0','1800x1400x24','-nolisten','tcp']);
 const number=await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('Xvfb timeout')),10000);display.stdout.once('data',b=>{clearTimeout(timer);resolve(b.toString().trim())});});
 for(const s of ['config','cache','data'])await fs.mkdir(profile+'/'+s);
 browser=spawn('/usr/bin/chromium',['--headless=new','--no-sandbox','--no-first-run','--no-default-browser-check','--enable-automation','--disable-dev-shm-usage','--ozone-platform=headless','--use-gl=angle','--use-angle=gl','--ignore-gpu-blocklist','--disable-vulkan','--remote-debugging-address=127.0.0.1','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{env:{...process.env,DISPLAY:':'+number,LIBGL_ALWAYS_SOFTWARE:'1',XDG_CONFIG_HOME:profile+'/config',XDG_CACHE_HOME:profile+'/cache',XDG_DATA_HOME:profile+'/data'}});
 let port;for(let n=0;n<150;n++){try{port=(await fs.readFile(profile+'/DevToolsActivePort','utf8')).split('\n')[0];break;}catch{await pause(100)}}
 check(port,'Dedicated CPU browser started');const pages=await(await fetch('http://127.0.0.1:'+port+'/json/list')).json();socket=new WebSocket(pages.find(x=>x.type==='page').webSocketDebuggerUrl);
 await new Promise((r,j)=>{socket.addEventListener('open',r,{once:true});socket.addEventListener('error',j,{once:true})});
 socket.addEventListener('message',e=>{const m=JSON.parse(e.data);if(m.id){const p=pending.get(m.id);if(p){pending.delete(m.id);m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m.result)}}else events.push(m)});
 await send('Page.enable');await send('Runtime.enable');await send('Network.enable');await send('Emulation.setDeviceMetricsOverride',{width:1800,height:1400,deviceScaleFactor:1,mobile:false});await send('Page.navigate',{url});
 let q=await ready();check(Object.keys(q.panels).length===6,'Six comparison panels',q.panels);check(q.panels.prior.status==='available'&&q.panels.mvs.status==='available','Actual prior and MVS loaded',q.panels);
 const manifest=await(await fetch(url+'data/manifest.json')).json();check(manifest.regions.filter(r=>/^R[1-5]$/.test(r.id)).length===5,'All five study regions');
 await fs.writeFile(out+'/served_manifest.json',JSON.stringify(manifest,null,2));
 const buffers=await ev('Promise.all([window.__GEOGS_RGB_QA__.verifyBuffers("prior"),window.__GEOGS_RGB_QA__.verifyBuffers("mvs")])');check(buffers.every(Boolean),'Loaded binary buffer evidence',buffers);
 await screenshot('R1_overview.png');
 await reviewReady('R1');
 await ev('document.getElementById("region-review").scrollIntoView()');await pause(500);await screenshot('R1_inline_review.png');
 await ev('scrollTo(0,0)');
 await ev('window.__GEOGS_RGB_QA__.setRegion("R1_Z08")');q=await ready();check(q.region==='R1_Z08','Z08 focus selection');
 await ev('document.getElementById("preset-top").click()');
 await ev('(()=>{const s=document.querySelector("[data-panel=mvs] select");s.value="judgment";s.dispatchEvent(new Event("change",{bubbles:true}));})()');q=await ready();check(q.panels.mvs.candidate==='judgment','Judgment color selection',q.panels.mvs);
 await screenshot('Z08_judgment.png');
 for(const region of ['R2','R3','R4','R5']){
  await ev('window.__GEOGS_RGB_QA__.setRegion('+JSON.stringify(region)+')');q=await ready();
  check(q.region===region&&Object.keys(q.panels).length===6&&q.panels.prior.drawn&&q.panels.mvs.drawn,region+' six panels and actual input geometry',q.panels);
  await reviewReady(region);
 await screenshot(region+'_overview.png');
 }
 await ev('document.querySelector("[data-panel=mvs] .panel-expand").click()');
 check((await ev('window.__GEOGS_RGB_QA__.focused'))==='mvs','Panel focus works');
 await ev('document.querySelector("[data-panel=mvs] .panel-expand").click()');
 
 await send('Emulation.setDeviceMetricsOverride',{width:390,height:900,deviceScaleFactor:1,mobile:true});await pause(500);
 const size=await ev('({viewport:innerWidth,document:document.documentElement.scrollWidth})');check(size.document<=size.viewport+1,'Mobile width',size);await screenshot('mobile.png');
 const failures=events.filter(x=>x.method==='Runtime.exceptionThrown'||x.method==='Network.loadingFailed'||(x.method==='Network.responseReceived'&&x.params.response.status>=400));check(!failures.length,'No browser or HTTP errors',failures);
 receipt.status='PASS';
}catch(e){receipt.status='FAIL';receipt.error=String(e);process.exitCode=1;}
finally{socket?.close();browser?.kill('SIGTERM');display?.kill('SIGTERM');await fs.writeFile(out+'/receipt.json',JSON.stringify(receipt,null,2));console.log(JSON.stringify({status:receipt.status,error:receipt.error,checks:receipt.checks.length}));}
