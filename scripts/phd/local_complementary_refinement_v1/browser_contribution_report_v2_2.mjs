// Bounded actual-browser QA of an immutable contribution report; Docker only.
import fs from 'node:fs/promises';
import {spawn} from 'node:child_process';
import crypto from 'node:crypto';
const [url,out='/out']=process.argv.slice(2);
if(!url||!['localhost','127.0.0.1'].includes(new URL(url).hostname))throw Error('Local immutable report URL required');
const checks=[],screenshots=[],chromeLog=[],runtimeErrors=[];
const receipt={schema:'jbgs.contribution_report_browser_qa.v2_2',status:'RUNNING',url,started_at:new Date().toISOString(),scientific_verdict:null,
  checks,screenshots,runtime_errors:runtimeErrors,cpu_limit:2,memory_limit_bytes:3*1024**3,uses_training_gpu:false,
  image_id:'sha256:5043f84d76db9d54e64fcf457125aad90ac5423fded88eca6cf487d2b4713a9e',
  scope:'Technical report usability, HTTP source integrity and responsive rendering; no independent scientific verdict.'};
const pause=ms=>new Promise(r=>setTimeout(r,ms)),hash=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
function check(pass,name,details){checks.push({pass:!!pass,name,details});}
const profile=await fs.mkdtemp('/tmp/lc-contribution-');for(const n of ['config','cache','data'])await fs.mkdir(profile+'/'+n);
const browser=spawn('/usr/bin/chromium',['--headless=new','--no-sandbox','--no-first-run','--disable-dev-shm-usage','--disable-gpu','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],
 {env:{...process.env,LIBGL_ALWAYS_SOFTWARE:'1',XDG_CONFIG_HOME:profile+'/config',XDG_CACHE_HOME:profile+'/cache',XDG_DATA_HOME:profile+'/data'}});
browser.stderr.on('data',b=>chromeLog.push(b.toString()));
let ws,seq=0;const pending=new Map();
function send(method,params={}){const id=++seq;return new Promise((resolve,reject)=>{const timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout '+method));},30000);pending.set(id,{resolve:v=>{clearTimeout(timer);resolve(v);},reject:e=>{clearTimeout(timer);reject(e);}});ws.send(JSON.stringify({id,method,params}));});}
async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result?.value;}
async function capture(name){const result=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false}),bytes=Buffer.from(result.data,'base64');await fs.writeFile(out+'/'+name,bytes,{flag:'wx'});screenshots.push({path:name,sha256:hash(bytes),bytes:bytes.length});}
try{
 const r=await fetch(new URL('receipt.json',url)),rb=Buffer.from(await r.arrayBuffer()),report=JSON.parse(rb);
 receipt.report_receipt_sha256=hash(rb);receipt.source_snapshot=report.source_snapshot;receipt.analysis_receipt_sha256=report.analysis_receipt_sha256;
 check(r.ok&&report.status==='PASS_ADDITIVE_CONTRIBUTION_REPORT_BUILT'&&report.evaluated_conditions===13&&report.scientific_verdict===null&&report.current_pointer_modified===false,'Bound immutable 13-condition technical report',report.status);
 let port;for(let i=0;i<150;i++){try{port=(await fs.readFile(profile+'/DevToolsActivePort','utf8')).split('\n')[0];break;}catch{await pause(100);}}
 if(!port)throw Error('Chromium startup failed');const pages=await(await fetch('http://127.0.0.1:'+port+'/json/list')).json();
 const page=pages.find(p=>p.type==='page'&&p.url==='about:blank');if(!page)throw Error('Dedicated page target absent');
 ws=new WebSocket(page.webSocketDebuggerUrl);await new Promise((r,j)=>{ws.onopen=r;ws.onerror=j;});
 ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.method==='Runtime.exceptionThrown')runtimeErrors.push(m.params);if(pending.has(m.id)){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(m.error):p.resolve(m.result);}};
 await send('Page.enable');await send('Runtime.enable');
 let inspectedLinks;
 for(const mode of [{id:'desktop',width:1440,height:1000,mobile:false},{id:'mobile',width:390,height:844,mobile:true}]){
  await send('Emulation.setDeviceMetricsOverride',{width:mode.width,height:mode.height,deviceScaleFactor:1,mobile:mode.mobile});
  await send('Page.navigate',{url});
  for(let i=0;i<200;i++){if(await evaluate('document.readyState==="complete"&&!!document.querySelector("h1")'))break;await pause(100);}
  const state=await evaluate(`(async()=>{for(const i of document.images)i.loading='eager';await Promise.all([...document.images].map(i=>i.complete?Promise.resolve():new Promise(r=>{i.addEventListener('load',r,{once:true});i.addEventListener('error',r,{once:true});})));const table=[...document.querySelectorAll('table')].find(t=>[...t.querySelectorAll('th')].some(h=>h.textContent.trim()==='LC 조건'));return {title:document.title,h1:document.querySelector('h1')?.textContent,text:document.body.innerText.includes('scientific_verdict: null'),conditions:table?[...table.querySelectorAll('tbody tr')].map(r=>[...r.cells].map(c=>c.textContent.trim())):[],images:[...document.images].map(i=>({src:i.src,alt:i.alt,complete:i.complete,naturalWidth:i.naturalWidth,naturalHeight:i.naturalHeight,displayWidth:i.getBoundingClientRect().width})),downloads:[...document.querySelectorAll('a[href^="downloads/"]')].map(a=>({url:a.href,label:a.textContent})),dimensions:{viewport:innerWidth,document:document.documentElement.scrollWidth,body:document.body.scrollWidth},tables:[...document.querySelectorAll('.table')].map(t=>({clientWidth:t.clientWidth,scrollWidth:t.scrollWidth,overflow:getComputedStyle(t).overflowX})),links:[...document.querySelectorAll('a[href]')].map(a=>a.href)}})()`);
  check(state.h1?.includes('현재 LC의 추가 복원 기여는 약하며')&&state.title?.length>0,mode.id+' visible title',state.h1);
  check(state.text,mode.id+' null scientific verdict stated');
  check(state.conditions.length===13&&new Set(state.conditions.map(r=>r[0]+'/'+r[1])).size===13,mode.id+' complete unique 13-condition table',state.conditions);
  check(JSON.stringify(['P1','P2','P3'].map(r=>state.conditions.filter(c=>c[0]===r).length))==='[4,6,3]',mode.id+' P1/P2/P3 condition counts 4/6/3');
  check(state.images.length===7&&state.images.every(i=>i.complete&&i.naturalWidth>0&&i.naturalHeight>0),mode.id+' seven actual images rendered',state.images);
  check(state.dimensions.document<=state.dimensions.viewport+1&&state.dimensions.body<=state.dimensions.viewport+1,mode.id+' no document horizontal overflow',state.dimensions);
  check(state.tables.every(t=>t.scrollWidth<=t.clientWidth+1||['auto','scroll'].includes(t.overflow)),mode.id+' wide tables use internal horizontal scrolling',state.tables);
  check(state.downloads.length>=12,mode.id+' inspectable download links',state.downloads);
  await evaluate('scrollTo(0,0)');await capture(mode.id+'.png');
  if(mode.id==='desktop')inspectedLinks=[...new Set([...state.downloads.map(x=>x.url),...state.images.map(x=>x.src),url])];
 }
 receipt.http_files=[];
 for(const link of inspectedLinks){const r=await fetch(link),b=Buffer.from(await r.arrayBuffer()),relative=new URL(link).pathname.slice(new URL(url).pathname.lastIndexOf('/')+1),expected=report.outputs.find(x=>x.path===relative);const record={url:link,status:r.status,bytes:b.length,sha256:hash(b),expected_sha256:expected?.sha256};receipt.http_files.push(record);check(r.ok&&b.length>0,'HTTP content available',record);check(expected&&expected.sha256===record.sha256,'HTTP bytes match sealed report output',record);}
 check(runtimeErrors.length===0,'No browser runtime errors',runtimeErrors);
 receipt.status=checks.every(c=>c.pass)?'PASS_ACTUAL_REPORT_DESKTOP_MOBILE':'FAIL';
 if(receipt.status==='FAIL')process.exitCode=1;
}catch(error){receipt.status='FAIL';receipt.error=String(error);process.exitCode=1;}
finally{receipt.finished_at=new Date().toISOString();await fs.writeFile(out+'/receipt.json',JSON.stringify(receipt,null,2)+'\n',{flag:'wx'});await fs.writeFile(out+'/chromium.log',chromeLog.join(''),{flag:'wx'});ws?.close();browser.kill('SIGTERM');}
console.log(JSON.stringify({status:receipt.status,checks:checks.length,failed:checks.filter(c=>!c.pass).map(c=>c.name),error:receipt.error,scientific_verdict:null}));
