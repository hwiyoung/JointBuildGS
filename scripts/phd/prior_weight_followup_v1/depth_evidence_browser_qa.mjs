import fs from 'node:fs/promises';
import {spawn} from 'node:child_process';
const pending=new Map(),receipt={checks:[],scientific_verdict:null};let socket,browser,id=0;
const pause=ms=>new Promise(r=>setTimeout(r,ms));
function check(x,name){receipt.checks.push({name,pass:!!x});if(!x)throw Error(name)}
function send(method,params={}){return new Promise((resolve,reject)=>{const n=++id,t=setTimeout(()=>reject(Error(method+' timeout')),15000);pending.set(n,{resolve:v=>{clearTimeout(t);resolve(v)},reject});socket.send(JSON.stringify({id:n,method,params}))})}
async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value}
async function ready(){for(let k=0;k<200;k++){const state=await evaluate('({error:window.__EVIDENCE_ERROR__,ready:window.__EVIDENCE_READY__,image:document.getElementById("figure")?.complete&&document.getElementById("figure")?.naturalWidth>0})');if(state.error)throw Error(state.error);if(state.ready&&state.image)return;await pause(100)}throw Error('image ready timeout')}
try{
 const profile=await fs.mkdtemp('/tmp/depth-evidence-qa-');browser=spawn('/usr/bin/chromium',['--headless=new','--no-sandbox','--disable-gpu','--disable-dev-shm-usage','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank']);
 let port;for(let k=0;k<150;k++){try{port=(await fs.readFile(profile+'/DevToolsActivePort','utf8')).split('\n')[0];break}catch{await pause(100)}}check(port,'browser_started');
 const pages=await(await fetch('http://127.0.0.1:'+port+'/json/list')).json();socket=new WebSocket(pages.find(x=>x.type==='page').webSocketDebuggerUrl);await new Promise(r=>socket.addEventListener('open',r,{once:true}));socket.addEventListener('message',e=>{const m=JSON.parse(e.data);if(m.id&&pending.has(m.id)){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m.result)}});
 await send('Page.enable');await send('Runtime.enable');await send('Emulation.setDeviceMetricsOverride',{width:1600,height:1250,deviceScaleFactor:1,mobile:false});
 await send('Page.navigate',{url:'http://127.0.0.1:7593/app/depth_evidence.html'});await ready();
 for(const region of ['P1','P2','P3']){
  await evaluate(`document.querySelector('[data-region="${region}"]').click()`);await ready();const cases=await evaluate('[...document.getElementById("view").options].map(x=>x.value)');
  for(const c of cases)for(const pool of ['regional_train','all937_context']){
   await evaluate(`document.getElementById('view').value=${JSON.stringify(c)};document.getElementById('pool').value=${JSON.stringify(pool)};document.getElementById('view').dispatchEvent(new Event('change'))`);await ready();
   const state=await evaluate('window.__EVIDENCE_STATE__');check(state.case===c&&state.pool===pool,'image_loaded_'+c+'_'+pool);check(await evaluate('document.querySelectorAll("#metrics tr").length===3'),'three_region_metrics_'+c+'_'+pool);
  }
 }
 await evaluate('document.querySelector("[data-region=P1]").click();document.getElementById("pool").value="regional_train";document.getElementById("pool").dispatchEvent(new Event("change"))');await ready();
 let shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await fs.writeFile('/out/browser_desktop.png',Buffer.from(shot.data,'base64'));
 await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});check(await evaluate('document.documentElement.scrollWidth<=391'),'mobile_no_overflow');
 for(const port of [7593,8910])for(const route of ['/app/weights.html?comparison=prior','/data/mechanism_diagnostic_v1/attempt.2TRgwhGr/report.html','/data/prior_verification_v1/verification.jCU13Dtc/report.html']){const response=await fetch('http://127.0.0.1:'+port+route);check(response.ok,'route_'+port+'_'+route);if(route.startsWith('/app/weights'))check((await response.text()).includes('depth_evidence.html'),'stage2_link_'+port)}
 receipt.status='PASS_STAGE2_BROWSER';
}catch(e){receipt.status='FAIL_STAGE2_BROWSER';receipt.error=String(e);process.exitCode=1}
finally{if(socket)socket.close();if(browser)browser.kill('SIGTERM');await fs.writeFile('/out/browser_qa.json',JSON.stringify(receipt,null,2));console.log(JSON.stringify(receipt))}
