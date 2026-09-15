import fs from 'node:fs/promises';
import {spawn} from 'node:child_process';
const base=process.argv[2],output='/out',pending=new Map(),receipt={checks:[],scientific_verdict:null};
const pause=ms=>new Promise(r=>setTimeout(r,ms));let socket,browser,id=0;
function check(x,name){receipt.checks.push({name,pass:!!x});if(!x)throw Error(name)}
function send(method,params={}){return new Promise((resolve,reject)=>{const n=++id;const t=setTimeout(()=>reject(Error(method+' timeout')),15000);pending.set(n,{resolve:v=>{clearTimeout(t);resolve(v)},reject});socket.send(JSON.stringify({id:n,method,params}))})}
async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value}
try{
 const profile=await fs.mkdtemp('/tmp/attribution-qa-');browser=spawn('/usr/bin/chromium',['--headless=new','--no-sandbox','--disable-gpu','--disable-dev-shm-usage','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank']);
 let port;for(let k=0;k<150;k++){try{port=(await fs.readFile(profile+'/DevToolsActivePort','utf8')).split('\n')[0];break}catch{await pause(100)}}check(port,'browser_started');
 const pages=await(await fetch('http://127.0.0.1:'+port+'/json/list')).json();socket=new WebSocket(pages.find(x=>x.type==='page').webSocketDebuggerUrl);
 await new Promise(r=>socket.addEventListener('open',r,{once:true}));socket.addEventListener('message',e=>{const m=JSON.parse(e.data);if(m.id&&pending.has(m.id)){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m.result)}});
 await send('Page.enable');await send('Runtime.enable');await send('Emulation.setDeviceMetricsOverride',{width:1500,height:1250,deviceScaleFactor:1,mobile:false});await send('Page.navigate',{url:base});
 for(let k=0;k<150;k++){if(await evaluate('window.__ATTRIBUTION_READY__ === true'))break;await pause(100)}
 check(await evaluate('window.__ATTRIBUTION_READY__ === true'),'canvas_ready');
 check(await evaluate('[...document.images].every(x=>x.complete&&x.naturalWidth>0)'),'all_figures_loaded');
 const before=await evaluate('document.querySelector("canvas").toDataURL()');await evaluate('document.getElementById("state").value="0";document.getElementById("state").dispatchEvent(new Event("change"))');
 check(before!==await evaluate('document.querySelector("canvas").toDataURL()'),'condition_selection_changes_canvas');
 await evaluate('document.getElementById("state").value="3";document.getElementById("state").dispatchEvent(new Event("change"))');
 let shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await fs.writeFile(output+'/browser_desktop.png',Buffer.from(shot.data,'base64'));
 await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
 check(await evaluate('document.documentElement.scrollWidth<=391'),'mobile_no_horizontal_overflow');receipt.status='PASS_BROWSER';receipt.url=base;
}catch(e){receipt.status='FAIL_BROWSER';receipt.error=String(e);process.exitCode=1}
finally{if(socket)socket.close();if(browser)browser.kill('SIGTERM');await fs.writeFile(output+'/browser_qa.json',JSON.stringify(receipt,null,2));console.log(JSON.stringify(receipt))}
