import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {spawn} from 'node:child_process';
const [url,out='/out']=process.argv.slice(2),target=new URL(url);
if(target.origin!=='http://127.0.0.1:8902'||target.pathname!=='/task/preview22000_v1/P2/gallery_v1/index.html')throw Error('Exact local preview URL required');
const hash=b=>crypto.createHash('sha256').update(b).digest('hex'),pause=ms=>new Promise(r=>setTimeout(r,ms));
const checks=[],pending=new Map(),events=[],logs=[],profile=await fs.mkdtemp('/tmp/preview22000-chrome-');let browser,socket,seq=0;
const receipt={scientific_verdict:null,started_utc:new Date().toISOString(),url,main_completion_inferred:false,geometry_assessed:false,checks};
function check(ok,label,detail={}){checks.push({label,ok,...detail});if(!ok)throw Error(label)}
function send(method,params={}){return new Promise((resolve,reject)=>{const id=++seq,timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout '+method))},25000);pending.set(id,{resolve:v=>{clearTimeout(timer);resolve(v)},reject:e=>{clearTimeout(timer);reject(e)}});socket.send(JSON.stringify({id,method,params}))})}
async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value}
async function ready(index,domain){for(let i=0;i<200;i++){const state=await evaluate('window.previewLoaded||null');if(state&&state.index===index&&state.domain===domain)return state;await pause(100)}throw Error('Gallery did not display expected photo '+index+'/'+domain)}
try{
 browser=spawn('/usr/bin/chromium',['--headless=new','--no-sandbox','--disable-gpu','--disable-dev-shm-usage','--no-first-run','--no-default-browser-check','--remote-debugging-address=127.0.0.1','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank']);
 browser.stderr.on('data',b=>logs.push(b.toString()));let port;
 for(let i=0;i<150;i++){try{port=(await fs.readFile(path.join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0];break}catch{await pause(100)}}if(!port)throw Error('Dedicated browser startup failed');
 const pages=await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();socket=new WebSocket(pages.find(p=>p.type==='page').webSocketDebuggerUrl);
 await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true})});
 socket.addEventListener('message',e=>{const m=JSON.parse(e.data);if(m.id){const p=pending.get(m.id);if(p){pending.delete(m.id);m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m.result)}}else events.push(m)});
 receipt.browser=await send('Browser.getVersion');await send('Page.enable');await send('Runtime.enable');await send('Network.enable');
 await send('Emulation.setDeviceMetricsOverride',{width:1800,height:1120,deviceScaleFactor:1,mobile:false});await send('Page.navigate',{url});await ready(0,'roi');
 const response=await fetch(new URL('manifest.json',target)),bytes=Buffer.from(await response.arrayBuffer());check(response.ok,'manifest_http');const manifest=JSON.parse(bytes);
 check(hash(bytes)===process.env.PREVIEW_MANIFEST_SHA256,'manifest_matches_frozen_file');check(manifest.scientific_verdict===null&&manifest.iteration===22000&&manifest.main_completion_inferred===false&&manifest.geometry_assessed===false&&manifest.total_images===9,'scope_and_membership');
 await fs.writeFile(path.join(out,'served_manifest.json'),bytes,{flag:'wx'});
 const fetched=new Set();
 for(const item of manifest.items){for(const domain of ['roi','full']){
  const records=domain==='roi'?item.roi_images:item.full;
  for(const record of records){if(fetched.has(record.url))continue;const r=await fetch(new URL(record.url,target)),body=Buffer.from(await r.arrayBuffer());check(r.ok&&hash(body)===record.sha256,'actual_image_http_and_sha',{index:item.index,domain,id:record.id});fetched.add(record.url)}
  await evaluate(`document.getElementById('photo').value=${JSON.stringify(String(item.index))};document.getElementById('domain').value=${JSON.stringify(domain)};document.getElementById('photo').dispatchEvent(new Event('change'));`);
  await ready(item.index,domain);const shown=await evaluate(`Array.from(document.querySelectorAll('.viewport img')).map(i=>({src:new URL(i.src).pathname,width:i.naturalWidth,height:i.naturalHeight,complete:i.complete}))`);
  check(shown.length===4&&shown.every((r,i)=>r.complete&&r.src===records[i].url&&r.width===records[i].width&&r.height===records[i].height),'four_actual_images_displayed',{index:item.index,domain});
  if((item.index===0&&['roi','full'].includes(domain))||(item.index===8&&domain==='roi')){const capture=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await fs.writeFile(path.join(out,`${item.index.toString().padStart(5,'0')}_${domain}.png`),Buffer.from(capture.data,'base64'),{flag:'wx'})}
 }}
 await evaluate(`document.getElementById('photo').value='0';document.getElementById('domain').value='roi';document.getElementById('photo').dispatchEvent(new Event('change'));`);await ready(0,'roi');
 const initialWidths=await evaluate(`Array.from(document.querySelectorAll('.viewport img')).map(i=>i.getBoundingClientRect().width)`);
 await evaluate(`document.getElementById('zoom').value='200';document.getElementById('zoom').dispatchEvent(new Event('input'));document.querySelector('.viewport').scrollLeft=90;document.querySelector('.viewport').scrollTop=70;`);await pause(500);
 const zoomed=await evaluate(`({widths:Array.from(document.querySelectorAll('.viewport img')).map(i=>i.getBoundingClientRect().width),scroll:Array.from(document.querySelectorAll('.viewport')).map(v=>[v.scrollLeft,v.scrollTop])})`);
 check(zoomed.widths.length===4&&zoomed.widths.every((w,i)=>Math.abs(w-2*initialWidths[i])<2)&&Math.max(...zoomed.widths)-Math.min(...zoomed.widths)<2&&zoomed.scroll[0][0]>0&&zoomed.scroll[0][1]>0&&zoomed.scroll.every(p=>Math.abs(p[0]-zoomed.scroll[0][0])<2&&Math.abs(p[1]-zoomed.scroll[0][1])<2),'actual_double_zoom_and_nonzero_shared_scroll',zoomed);
 const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await fs.writeFile(path.join(out,'00000_roi_zoom200.png'),Buffer.from(shot.data,'base64'),{flag:'wx'});
 check((await evaluate(`document.getElementById('error').textContent`))==='','no_visible_error');check(events.filter(e=>e.method==='Runtime.exceptionThrown').length===0,'no_uncaught_browser_exception');
 receipt.status='PASS_ACTUAL_RGB_PREVIEW_BROWSER_QA';receipt.images_http_sha_checked=fetched.size;receipt.photo_domain_combinations=18;receipt.screenshots=4;receipt.manifest_sha256=hash(bytes);
}catch(e){receipt.status='FAIL_ACTUAL_RGB_PREVIEW_BROWSER_QA';receipt.error=e.stack;process.exitCode=1}
finally{receipt.finished_utc=new Date().toISOString();await fs.writeFile(path.join(out,'receipt.json'),JSON.stringify(receipt,null,2)+'\n',{flag:'wx'});await fs.writeFile(path.join(out,'chrome.log'),logs.join(''),{flag:'wx'});if(socket)socket.close();if(browser)browser.kill('SIGTERM');console.log(JSON.stringify({status:receipt.status,checks:checks.length,error:receipt.error||null}))}
