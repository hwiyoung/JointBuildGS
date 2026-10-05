// CPU-only actual Chromium checks of served, source-bound stage reports.
import fs from 'node:fs/promises';
import {spawn} from 'node:child_process';
import {createHash} from 'node:crypto';

const url=process.env.QA_URL||'http://127.0.0.1:8909/report/';
const output=process.env.QA_OUT||'/out';
const expected=(process.env.QA_EXPECT_REGIONS||'P1,P2,P3').split(',');
const receipt={schema:'jbgs.source_selected_2dgs.browser_qa.v1',status:'RUNNING',scientific_verdict:null,url,
  started_utc:new Date().toISOString(),checks:[],states:[],screenshots:[],resources:[],runtime_errors:[]};
const delay=ms=>new Promise(r=>setTimeout(r,ms));
const hash=x=>createHash('sha256').update(x).digest('hex');
let browser,socket,sequence=0;const pending=new Map();
function check(value,label,details){receipt.checks.push({pass:!!value,label,details});if(!value)throw Error(label)}
function send(method,params={}){return new Promise((resolve,reject)=>{const id=++sequence,timer=setTimeout(()=>reject(Error('CDP timeout '+method)),30000);pending.set(id,{resolve:x=>{clearTimeout(timer);resolve(x)},reject:x=>{clearTimeout(timer);reject(x)}});socket.send(JSON.stringify({id,method,params}))})}
async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result?.value}
async function waitFor(expression,label){for(let n=0;n<200;n++){const r=await evaluate(expression);if(r)return r;await delay(75)}throw Error('Timed out '+label)}
async function settle(){await evaluate('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))')}
async function capture(name){await settle();const r=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});const bytes=Buffer.from(r.data,'base64');await fs.writeFile(output+'/'+name,bytes,{flag:'wx'});receipt.screenshots.push({path:name,sha256:hash(bytes),bytes:bytes.length})}
const visited=new Set();
async function resource(href,label){if(visited.has(href))return;check(new URL(href).origin===new URL(url).origin,'Local artifact origin',{href});const r=await fetch(href,{method:'HEAD'});check(r.status===200,'Artifact HTTP 200',{href,status:r.status});visited.add(href);receipt.resources.push({href,label,status:r.status})}
try{
  await fs.mkdir(output,{recursive:true});
  const html=await fetch(url),dataResponse=await fetch(new URL('data.json',url));
  check(html.ok&&dataResponse.ok,'Served HTML and source data available');
  const htmlBytes=Buffer.from(await html.arrayBuffer()),dataBytes=Buffer.from(await dataResponse.arrayBuffer());
  receipt.html_sha256=hash(htmlBytes);receipt.data_sha256=hash(dataBytes);receipt.script_sha256=hash(await fs.readFile(new URL(import.meta.url)));
  const document=JSON.parse(dataBytes);check(JSON.stringify(document.regions.map(r=>r.id))===JSON.stringify(expected),'Exact region membership',document.regions.map(r=>r.id));
  check(document.regions.every(r=>r.stages.length===8),'Eight stages per region');
  const profile=await fs.mkdtemp('/tmp/source-selected-qa-');
  browser=spawn('/usr/bin/chromium',['--headless=new','--no-sandbox','--no-first-run','--disable-dev-shm-usage','--disable-gpu','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank']);
  const logs=[];browser.stderr.on('data',x=>logs.push(x.toString()));let port;
  for(let i=0;i<150;i++){try{port=(await fs.readFile(profile+'/DevToolsActivePort','utf8')).split('\n')[0];break}catch{await delay(100)}}
  if(!port)throw Error('Chromium failed to start: '+logs.join('').slice(-2000));
  const tabs=await(await fetch('http://127.0.0.1:'+port+'/json/list')).json();socket=new WebSocket(tabs.find(x=>x.type==='page').webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject});
  socket.onmessage=e=>{const m=JSON.parse(e.data);if(m.method==='Runtime.exceptionThrown')receipt.runtime_errors.push(m.params);if(pending.has(m.id)){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m.result)}};
  await send('Page.enable');await send('Runtime.enable');receipt.chromium=await send('Browser.getVersion');
  await send('Page.navigate',{url});await waitFor('typeof data!=="undefined"&&data?.regions?.length','loaded stage JSON');
  for(const width of [1440,390]){
    await send('Emulation.setDeviceMetricsOverride',{width,height:width===390?844:1100,deviceScaleFactor:1,mobile:width===390});
    for(let ri=0;ri<document.regions.length;ri++){
      const region=document.regions[ri];await evaluate(`document.querySelectorAll('#region-nav button')[${ri}].click()`);
      for(let si=0;si<8;si++){
        const stage=region.stages[si];await evaluate(`document.querySelectorAll('#stage-nav button')[${si}].click()`);await settle();
        check(await evaluate(`document.querySelector('#stage-panel h2').textContent`)===(si+1)+'단계 · '+stage.title,'Selected stage matches source',{region:region.id,stage:si+1,width});
        for(let ii=0;ii<(stage.images||[]).length;ii++){
          await evaluate(`document.querySelectorAll('#stage-panel img')[${ii}].scrollIntoView({block:'center',behavior:'instant'})`);
          await waitFor(`(()=>{const x=document.querySelectorAll('#stage-panel img')[${ii}];return x?.complete&&x.naturalWidth>0})()`,'actual image load');
        }
        const state=await evaluate(`({viewport:innerWidth,document:document.documentElement.scrollWidth,images:[...document.querySelectorAll('#stage-panel img')].map(x=>({src:x.src,width:x.naturalWidth,right:x.getBoundingClientRect().right})),pending:!!document.querySelector('#stage-panel .empty'),metrics:[...document.querySelectorAll('#stage-panel tbody tr')].map(x=>({label:x.querySelector('th').textContent,value:x.querySelector('td').textContent})),errors:document.querySelector('#error').textContent})`);
        check(state.document<=state.viewport+1&&state.images.every(x=>x.width>0&&x.right<=state.viewport+1),'No horizontal overflow or broken images',{region:region.id,stage:si+1,width,...state});
        check(state.images.length===(stage.images||[]).length&&state.pending===!(stage.images||[]).length,'Pending stages never show fabricated images',{region:region.id,stage:si+1});
        check(JSON.stringify(state.images.map(x=>x.src))===JSON.stringify((stage.images||[]).map(x=>new URL(x.src,url).href)),'Rendered images bind exact declared paths',{region:region.id,stage:si+1});
        const expectedMetrics=await evaluate(`data.regions[${ri}].stages[${si}].metrics.map(x=>({label:x.label,value:value(x.value)+(x.unit?' '+x.unit:'')}))`);
        check(JSON.stringify(state.metrics)===JSON.stringify(expectedMetrics),'Metrics preserve actual nulls and zeros',{region:region.id,stage:si+1,width});
        for(const i of state.images)await resource(i.src,'stage image');
        const links=await evaluate(`[...document.querySelectorAll('#stage-panel a,#region-links a,#top-links a')].map(a=>({href:a.href,label:a.textContent}))`);
        for(const link of links)await resource(link.href,link.label);
        check(!state.errors,'No application error text',state.errors);
        receipt.states.push({region:region.id,stage:si+1,width,image_count:state.images.length,pending:state.pending});
        if(width===390&&[0,3,7].includes(si)){await evaluate(`document.querySelector('#stage-panel').scrollIntoView({block:'start',behavior:'instant'})`);await capture(region.id+'_stage'+(si+1)+'_390.png')}
      }
    }
  }
  // Temporary browser-memory sentinels exercise absence versus a real zero.
  const sentinel=await evaluate(`(()=>{const p=document.createElement('div');metrics(p,[{label:'missing',value:null,unit:'m'},{label:'zero',value:0,unit:'m'}]);return [...p.querySelectorAll('td')].map(x=>x.textContent)})()`);
  check(JSON.stringify(sentinel)===JSON.stringify(['미산출 m','0 m']),'Missing and zero remain distinct',sentinel);
  const statusProbe=await evaluate(`(()=>{const saved={document:data.status,live:statusText};try{data.status='COMPLETE_TECHNICAL_DIAGNOSTIC';statusText='FAILED browser_memory_fixture';renderStatus();const failed=document.querySelector('#run-status').classList.contains('fail')&&document.querySelector('#run-status').textContent.includes('실패');statusText='VALIDATING_FINAL_REPORT';renderStatus();const pending=document.querySelector('#run-status').classList.contains('pending')&&document.querySelector('#run-status').textContent.includes('검증 중');statusText='COMPLETE';renderStatus();const complete=!document.querySelector('#run-status').classList.contains('pending')&&document.querySelector('#run-status').textContent.includes('모든 실행');return {failed,pending,complete}}finally{data.status=saved.document;statusText=saved.live;renderStatus()}})()`);
  check(statusProbe.failed&&statusProbe.pending&&statusProbe.complete,'Live failure and final validation override completed document status',statusProbe);
  check(receipt.runtime_errors.length===0,'No browser runtime exception',receipt.runtime_errors);
  receipt.status='PASS_ACTUAL_BROWSER';
}catch(error){receipt.status='FAIL_BROWSER_QA';receipt.error=String(error);process.exitCode=1;if(socket?.readyState===1){try{await capture('failure.png')}catch{}}}
finally{receipt.finished_utc=new Date().toISOString();await fs.mkdir(output,{recursive:true});await fs.writeFile(output+'/receipt.json',JSON.stringify(receipt,null,2)+'\n',{flag:'wx'});socket?.close();browser?.kill('SIGTERM')}
console.log(JSON.stringify({status:receipt.status,checks:receipt.checks.length,states:receipt.states.length,screenshots:receipt.screenshots.length,error:receipt.error}));
