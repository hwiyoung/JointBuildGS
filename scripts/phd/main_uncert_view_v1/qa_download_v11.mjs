// Real Chromium download completion and on-disk hash, separate from HTTP success.
import {spawn} from 'node:child_process';
import {createReadStream, mkdirSync, readFileSync, statSync, writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
const url=process.env.VIEW_URL||'http://127.0.0.1:8913/';
const label=process.env.QA_LABEL||'preview',release=process.env.RECEIPT_VERSION||'v11',tableDir='/docs/tables_'+(release==='v12'?'v1_2':'v1_1');
const port=9241, dir='/tmp/download-qa';
mkdirSync(dir,{recursive:true});
const browser=spawn('/usr/bin/chromium',['--headless=new','--no-sandbox','--disable-gpu','--disable-dev-shm-usage',`--remote-debugging-port=${port}`,'--user-data-dir=/tmp/download-qa-profile','about:blank'],{stdio:'ignore'});
const pause=ms=>new Promise(r=>setTimeout(r,ms)), pending=new Map(), downloads=new Map();
const result={url,label,started:new Date().toISOString(),downloads:[],scientific_verdict:null};
let ws,id=0;
function cmd(method,params={},sessionId){return new Promise((resolve,reject)=>{
  const key=++id,timer=setTimeout(()=>{pending.delete(key);reject(Error('CDP timeout: '+method))},60000);
  pending.set(key,{resolve:x=>{clearTimeout(timer);resolve(x)},reject:x=>{clearTimeout(timer);reject(x)}});
  ws.send(JSON.stringify({id:key,method,params,sessionId}));
})}
async function hash(path){const h=createHash('sha256');for await(const chunk of createReadStream(path))h.update(chunk);return h.digest('hex')}
try{
  let version;for(let n=0;n<120;n++){try{version=await(await fetch(`http://127.0.0.1:${port}/json/version`)).json();break}catch{await pause(100)}}
  if(!version)throw Error('Browser startup failed');result.browser=version.Browser;
  ws=new WebSocket(version.webSocketDebuggerUrl);await new Promise(r=>ws.onopen=r);
  ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id){const p=pending.get(m.id);if(p){pending.delete(m.id);m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m.result)}}
    else if(m.method==='Browser.downloadWillBegin')downloads.set(m.params.guid,{...m.params});
    else if(m.method==='Browser.downloadProgress'){const d=downloads.get(m.params.guid);if(d)Object.assign(d,m.params)}};
  await cmd('Browser.setDownloadBehavior',{behavior:'allow',downloadPath:dir,eventsEnabled:true});
  const {targetInfos}=await cmd('Target.getTargets');
  const {sessionId}=await cmd('Target.attachToTarget',{targetId:targetInfos.find(t=>t.type==='page').targetId,flatten:true});
  await cmd('Page.enable',{},sessionId);
  await cmd('Page.navigate',{url},sessionId);
  const ev=async expression=>{const x=await cmd('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true},sessionId);if(x.exceptionDetails)throw Error(JSON.stringify(x.exceptionDetails));return x.result?.value};
  for(let n=0;n<300;n++){if(await ev('!!window.UNCERT_APP?.ready && !!window.UNCERT_APP?.judgement'))break;if(n===299)throw Error('Viewer not ready');await pause(100)}
  result.viewer_ready=await ev('({title:document.title,faces:UNCERT_APP.faceRows.length,mvs:UNCERT_APP.judgement.counts.mvs})');
  for(const [selector,receipt] of [['#reportDownload','report_download.json'],['#resultsDownload','results_download.json']]){
    const expected=release==='v12'?JSON.parse(readFileSync(tableDir+'/downloads.json','utf8'))[selector==='#reportDownload'?'report':'full']:JSON.parse(readFileSync(tableDir+'/'+receipt,'utf8'));
    await ev(`document.querySelector(${JSON.stringify(selector)}).click()`);
    let download;for(let n=0;n<2400;n++){
      download=[...downloads.values()].find(d=>d.suggestedFilename===expected.archive);
      if(download?.state==='completed')break;
      if(download?.state==='canceled')throw Error('Download canceled '+expected.archive);
      if(n===2399)throw Error('Download did not complete '+expected.archive);
      await pause(100);
    }
    const path=dir+'/'+expected.archive,actual=await hash(path);
    if(actual!==expected.sha256||statSync(path).size!==expected.bytes)throw Error('Saved file differs '+expected.archive);
    result.downloads.push({...download,sha256:actual,hash_matches:true,saved_bytes:statSync(path).size});
    console.log(JSON.stringify(result.downloads.at(-1)));
  }
  result.finished=new Date().toISOString();result.pass=true;
}catch(e){result.pass=false;result.error=e.stack;console.error(e.stack);process.exitCode=1}
finally{writeFileSync(tableDir+'/download_browser_'+label+'.json',JSON.stringify(result,null,2)+'\n');ws?.close();browser.kill('SIGTERM')}
