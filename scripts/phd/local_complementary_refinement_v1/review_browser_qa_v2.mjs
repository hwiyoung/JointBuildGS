// Real Chromium UI verification; run in the pinned dedicated browser Docker image.
import fs from 'node:fs/promises';
import crypto from 'node:crypto';
import {spawn} from 'node:child_process';
const [url='http://127.0.0.1:8905',out='/out']=process.argv.slice(2);
if(!['localhost','127.0.0.1'].includes(new URL(url).hostname))throw Error('Local URL required');
const pause=ms=>new Promise(r=>setTimeout(r,ms));
const profile=await fs.mkdtemp('/tmp/lc-review-browser-');
for(const suffix of ['config','cache','data'])await fs.mkdir(profile+'/'+suffix);
const browser=spawn('/usr/bin/chromium',['--headless=new','--no-sandbox','--disable-dev-shm-usage','--disable-gpu','--no-first-run','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{env:{...process.env,XDG_CONFIG_HOME:profile+'/config',XDG_CACHE_HOME:profile+'/cache',XDG_DATA_HOME:profile+'/data'}});
const logs=[],checks=[],shots=[],errors=[];browser.stderr.on('data',x=>logs.push(x.toString()));
let socket,seq=0;const pending=new Map();
function check(ok,name,detail){checks.push({name,pass:!!ok,detail});if(!ok)throw Error(name)}
function send(method,params={}){return new Promise((resolve,reject)=>{const id=++seq;const timer=setTimeout(()=>reject(Error('CDP timeout '+method)),15000);pending.set(id,{resolve:x=>{clearTimeout(timer);resolve(x)},reject});socket.send(JSON.stringify({id,method,params}))})}
async function js(expression){const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value}
async function choose(id,value){await js(`(()=>{const e=document.getElementById(${JSON.stringify(id)});e.value=${JSON.stringify(value)};e.dispatchEvent(new Event('change'))})()`)}
async function imageReady(){for(let i=0;i<100;i++){const r=await js(`(()=>{const e=document.getElementById('figure');return {ready:e.complete&&e.naturalWidth>0,src:e.getAttribute('src'),width:e.naturalWidth,height:e.naturalHeight}})()`);if(r.ready)return r;await pause(50)}throw Error('Image timeout')}
async function capture(name){const r=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});const b=Buffer.from(r.data,'base64');await fs.writeFile(out+'/'+name,b,{flag:'wx'});shots.push({name,sha256:crypto.createHash('sha256').update(b).digest('hex')})}
const receipt={schema:'jbgs.local_review_browser_qa.v2',scientific_verdict:null,url,started_at:new Date().toISOString(),checks,screenshots:shots,errors};
try{
 let port;for(let i=0;i<150;i++){try{port=(await fs.readFile(profile+'/DevToolsActivePort','utf8')).split('\n')[0];break}catch{}await pause(100)}
 if(!port)throw Error('Chromium startup timeout');
 const pages=await(await fetch('http://127.0.0.1:'+port+'/json/list')).json();const page=pages.find(p=>p.type==='page'&&p.url==='about:blank');if(!page)throw Error('Dedicated blank page target missing');socket=new WebSocket(page.webSocketDebuggerUrl);
 await new Promise((r,j)=>{socket.onopen=r;socket.onerror=j});socket.onmessage=e=>{const x=JSON.parse(e.data);if(x.id){const p=pending.get(x.id);if(p){pending.delete(x.id);x.error?p.reject(Error(JSON.stringify(x.error))):p.resolve(x.result)}}else if(x.method==='Runtime.exceptionThrown')errors.push(x.params)};
 await send('Page.enable');await send('Runtime.enable');await send('Emulation.setDeviceMetricsOverride',{width:1500,height:1100,deviceScaleFactor:1,mobile:false});await send('Page.navigate',{url});
 let ready=false;for(let i=0;i<200;i++){ready=await js("document.body?.dataset.ready==='true'");if(ready)break;await pause(100)}check(ready,'actual_packet_loaded');
 const data=await js('data');check(data.scientific_verdict===null&&data.rows.length===data.evaluated_conditions,'count_and_null_verdict',data.evaluated_conditions);receipt.packet=data.packet;
 check((await js('location.pathname')).startsWith('/packets/'+data.packet+'/'),'immutable_packet_navigation');
 for(const row of data.rows){
  await js(`document.querySelector('[data-id="${row.id}"]').click()`);
  check(await js('selected.id')===row.id,'selected_condition',row.id);
  for(const tab of ['roi','full','section','map']){await js(`document.querySelector('[data-tab="${tab}"]').click()`);const img=await imageReady();check(img.src===row.images[tab],'all_four_bound_images',{id:row.id,tab,...img})}
  for(const mesh of ['raw','post']){await choose('mesh',mesh);for(const t of ['0.1','0.2','0.25','0.5','1','2']){await choose('threshold',t);const expected=row.geometry.find(x=>x.candidate===row.condition&&x.mesh_kind===mesh&&Number(x.threshold_m)===Number(t));const text=await js("document.querySelectorAll('#metrics .metric strong')[2].textContent");check(!!expected&&text===Number(expected.f1).toLocaleString('en-US',{minimumFractionDigits:3,maximumFractionDigits:3}),'displayed_F1_matches_bound_numeric_record',{id:row.id,mesh,t,text})}}
 }
 for(const region of ['P1','P2','P3']){await choose('region',region);const ids=await js("[...document.querySelectorAll('#conditions button')].map(x=>x.dataset.id)");check(ids.length===data.rows.filter(x=>x.region===region).length&&ids.every(x=>x.startsWith(region+'/')),'region_filter',region)}
 await choose('region','ALL');await choose('mesh','raw');await choose('threshold','0.5');await js(`document.querySelector('[data-id="${data.rows[0].id}"]').click();document.querySelector('[data-tab="roi"]').click();scrollTo(0,0)`);await imageReady();await capture('desktop.png');
 await js("document.getElementById('figure').scrollIntoView({block:'center'})");await capture('desktop_photo.png');
 await js("document.getElementById('zoom').value='250';document.getElementById('zoom').dispatchEvent(new Event('input'))");check(await js("document.getElementById('figure').style.width")==='250%','image_zoom');
 await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});await js('scrollTo(0,0)');await capture('mobile.png');check(await js('document.documentElement.scrollWidth<=innerWidth'),'mobile_no_page_horizontal_overflow');
 const base=await js('location.href');for(const row of data.rows)for(const x of row.downloads){const r=await fetch(new URL(x.url,base));check(r.ok&&r.headers.get('content-type').includes('text/csv'),'CSV_download_works',x.url)}
 check((await fetch(url+'/packets/'+data.packet+'/%2e%2e%2f%2e%2e%2fcurrent.json')).status===404,'path_escape_rejected');
 check(errors.length===0,'no_browser_runtime_exceptions');receipt.status='PASS_REAL_BROWSER_UI';
}catch(e){receipt.status='FAIL';receipt.error=String(e);process.exitCode=1;if(socket?.readyState===1){try{receipt.failure_page=await js('({href:location.href,body:document.body?.innerText,ready:document.body?.dataset.ready})');await capture('failure.png')}catch{}}}finally{socket?.close();browser.kill('SIGTERM');receipt.finished_at=new Date().toISOString();await fs.writeFile(out+'/receipt.json',JSON.stringify(receipt,null,2)+'\n',{flag:'wx'});await fs.writeFile(out+'/chromium.log',logs.join(''),{flag:'wx'});console.log(JSON.stringify({status:receipt.status,checks:checks.length,packet:receipt.packet,error:receipt.error,scientific_verdict:null}))}
