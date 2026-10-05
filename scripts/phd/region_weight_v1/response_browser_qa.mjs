// CPU Chromium validation of the live region gallery and full-frame assets.
import fs from 'node:fs/promises';
import {spawn} from 'node:child_process';
const out=process.argv[2]||'/out',url='http://127.0.0.1:8910/app/weight_response.html?region=P2&view=source_10';
const pause=ms=>new Promise(r=>setTimeout(r,ms));
const pending=new Map(),events=[],checks=[];let seq=0,browser,socket;
function check(value,name){checks.push({name,pass:!!value});if(!value)throw Error(name);}
function send(method,params={}){const id=++seq;return new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error(method+' timeout')),20000);pending.set(id,{resolve:v=>{clearTimeout(timer);resolve(v)},reject});socket.send(JSON.stringify({id,method,params}));});}
async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value;}
async function settled(){for(let i=0;i<200;i++){if(await evaluate('document.querySelector("#error") && !document.querySelector("#error").hidden'))throw Error(await evaluate('document.querySelector("#error").textContent'));if(await evaluate('window.__WEIGHT_RESPONSE_QA__?.ready'))return;await pause(100);}throw Error('Image not loaded');}
async function change(id,value){await evaluate(`document.getElementById(${JSON.stringify(id)}).value=${JSON.stringify(value)};document.getElementById(${JSON.stringify(id)}).dispatchEvent(new Event('change'));`);await pause(300);await settled();}
const receipt={scientific_verdict:null,url,checks};
try{
 const profile=await fs.mkdtemp('/tmp/region-browser-');
 browser=spawn('/usr/bin/chromium',['--headless=new','--no-sandbox','--disable-gpu','--disable-dev-shm-usage','--no-first-run','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank']);
 const logs=[];browser.stderr.on('data',b=>logs.push(b.toString()));
 let port;for(let i=0;i<200;i++){try{port=(await fs.readFile(profile+'/DevToolsActivePort','utf8')).split('\n')[0];break;}catch{await pause(100);}}
 check(port,'chromium_started');
 const pages=await(await fetch(`http://127.0.0.1:${port}/json/list`)).json();
 socket=new WebSocket(pages.find(p=>p.type==='page').webSocketDebuggerUrl);
 await new Promise(r=>socket.addEventListener('open',r,{once:true}));
 socket.addEventListener('message',e=>{const m=JSON.parse(e.data);if(m.id){const p=pending.get(m.id);if(p){pending.delete(m.id);m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m.result)}}else events.push(m);});
 await send('Page.enable');await send('Runtime.enable');await send('Network.enable');
 await send('Emulation.setDeviceMetricsOverride',{width:1500,height:1300,deviceScaleFactor:1,mobile:false});
 await send('Page.navigate',{url});await settled();
 for(const region of ['P1','P2','P3']){
  await change('region',region);
  check(await evaluate('document.querySelectorAll("#view-select option").length')===(region==='P1'?1:2),region+'_source_count');
  const values=await evaluate('[...document.querySelectorAll("#view-select option")].map(x=>x.value)');
  for(const value of values){
   await change('view-select',value);
   check(await evaluate('window.__WEIGHT_RESPONSE_QA__.ready && window.__WEIGHT_RESPONSE_QA__.sha256.length===64'),region+'_'+value+'_figure_hash_verified');
   check(await evaluate('document.querySelectorAll("#metrics tr").length===3 && document.querySelectorAll("#probes tr").length===2'),region+'_'+value+'_metrics_and_probes');
   const screenshot=await send('Page.captureScreenshot',{format:'png'});await fs.writeFile(out+'/'+region+'_'+value+'.png',Buffer.from(screenshot.data,'base64'),{flag:'wx'});
  }
 }
 check(await evaluate('document.querySelector("#interpretation").textContent.includes("정정") && document.querySelector("#interpretation").textContent.includes("92.3%")'),'p3_mean_interpretation_corrected');
 check((await fetch('http://127.0.0.1:8910/app/weights.html').then(r=>r.text())).includes('./weight_response.html'),'linked_from_existing_viewer');
 await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});await pause(100);
 check(await evaluate('document.documentElement.scrollWidth<=391'),'mobile_no_horizontal_overflow');
 const screenshot=await send('Page.captureScreenshot',{format:'png'});await fs.writeFile(out+'/mobile.png',Buffer.from(screenshot.data,'base64'),{flag:'wx'});
 const errors=events.filter(e=>e.method==='Runtime.exceptionThrown'||e.method==='Network.loadingFailed'||(e.method==='Network.responseReceived'&&e.params.response.status>=400));
 check(errors.length===0,'no_browser_or_network_errors');receipt.status='PASS_WEIGHT_RESPONSE_BROWSER';
 await fs.writeFile(out+'/chrome.log',logs.join(''),{flag:'wx'});
}catch(error){receipt.status='FAIL_WEIGHT_RESPONSE_BROWSER';receipt.error=String(error);process.exitCode=1;}
finally{if(socket)socket.close();if(browser)browser.kill('SIGTERM');await fs.writeFile(out+'/receipt.json',JSON.stringify(receipt,null,2),{flag:'wx'});console.log(JSON.stringify(receipt));}
