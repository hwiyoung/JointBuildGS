// Browser-only UI QA through Chrome DevTools, using Node built-ins exclusively.
// Project numerical tools continue to run in Docker. Never uses a user profile.
import net from 'node:net';
import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';

const url=process.argv[2];const out=process.argv[3];
if(!url||!out)throw Error('usage: node sample_browser_qa.mjs URL FRESH_OUTPUT_DIRECTORY');
await fs.mkdir(out,{recursive:false});
const pages=await(await fetch('http://127.0.0.1:9227/json/list')).json();
const target=pages.find(p=>p.type==='page');if(!target)throw Error('No isolated Chrome page');
const ws=new URL(target.webSocketDebuggerUrl),socket=net.createConnection({host:ws.hostname,port:Number(ws.port)});
let stream=Buffer.alloc(0),handshake=false,nextId=1;const pending=new Map(),events=[];
const connected=new Promise((resolve,reject)=>{
 socket.on('error',reject);
 socket.on('connect',()=>socket.write(`GET ${ws.pathname} HTTP/1.1\r\nHost: ${ws.host}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: ${crypto.randomBytes(16).toString('base64')}\r\nSec-WebSocket-Version: 13\r\n\r\n`));
 socket.on('data',data=>{
  stream=Buffer.concat([stream,data]);
  if(!handshake){const end=stream.indexOf('\r\n\r\n');if(end<0)return;const head=stream.subarray(0,end).toString();if(!head.startsWith('HTTP/1.1 101'))return reject(Error(head));stream=stream.subarray(end+4);handshake=true;resolve();}
  while(stream.length>=2){const opcode=stream[0]&15;let len=stream[1]&127,offset=2;if(len===126){if(stream.length<4)return;len=stream.readUInt16BE(2);offset=4;}else if(len===127){if(stream.length<10)return;len=Number(stream.readBigUInt64BE(2));offset=10;}if(stream.length<offset+len)return;const body=stream.subarray(offset,offset+len);stream=stream.subarray(offset+len);if(opcode!==1)continue;const obj=JSON.parse(body.toString());if(obj.id){const p=pending.get(obj.id);if(p){pending.delete(obj.id);obj.error?p.reject(Error(JSON.stringify(obj.error))):p.resolve(obj.result);}}else if(obj.method)events.push(obj);}
 });
});
await connected;
function send(method,params={}){const id=nextId++,body=Buffer.from(JSON.stringify({id,method,params})),mask=crypto.randomBytes(4);let header;if(body.length<126){header=Buffer.from([0x81,0x80|body.length]);}else if(body.length<65536){header=Buffer.alloc(4);header[0]=0x81;header[1]=0x80|126;header.writeUInt16BE(body.length,2);}else{header=Buffer.alloc(10);header[0]=0x81;header[1]=0x80|127;header.writeBigUInt64BE(BigInt(body.length),2);}for(let i=0;i<body.length;i++)body[i]^=mask[i%4];return new Promise((resolve,reject)=>{pending.set(id,{resolve,reject});socket.write(Buffer.concat([header,mask,body]));setTimeout(()=>{if(pending.has(id)){pending.delete(id);reject(Error('CDP timeout '+method));}},15000).unref();});}
async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result?.value;}
const pause=ms=>new Promise(r=>setTimeout(r,ms));
async function capture(name,clip){const r=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false,...(clip?{clip}: {})});const image=Buffer.from(r.data,'base64');await fs.writeFile(path.join(out,name+'.png'),image,{flag:'wx'});return crypto.createHash('sha256').update(image).digest('hex');}
async function choose(id,value){await evaluate(`(()=>{const e=document.getElementById(${JSON.stringify(id)});e.value=${JSON.stringify(String(value))};e.dispatchEvent(new Event('change',{bubbles:true}));return e.value;})()`);await pause(100);}
try{
 await send('Page.enable');await send('Runtime.enable');await send('Log.enable');await send('Log.clear');await send('Runtime.discardConsoleEntries');await send('Network.enable');events.length=0;
 await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1100,deviceScaleFactor:1,mobile:false});
 await send('Page.navigate',{url});
 let ready=false;for(let i=0;i<60;i++){await pause(250);ready=await evaluate('Boolean(window.P2_INSPECTOR_READY)');if(ready)break;}
 const initial=await evaluate(`(()=>({ready:Boolean(window.P2_INSPECTOR_READY),status:document.getElementById('status')?.textContent,error:document.getElementById('error')?.textContent,unitOptions:document.getElementById('unit')?.options.length,arms:[...(document.getElementById('arm')?.options||[])].map(x=>({key:x.value,label:x.textContent})),canvases:[...document.querySelectorAll('canvas')].map(c=>({width:c.width,height:c.height,webgl2:!!c.getContext('webgl2'),glVersion:c.getContext('webgl2')?.getParameter(c.getContext('webgl2').VERSION)})),viewport:[innerWidth,innerHeight],overflow:document.documentElement.scrollWidth>innerWidth}))()`);
 const desktopBefore=await capture('desktop_before');
 if(!ready)throw Error('P2_INSPECTOR_READY false '+JSON.stringify(initial));
 const rect=await evaluate(`(()=>{const r=document.querySelector('#left').getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height};})()`);
 await send('Input.dispatchMouseEvent',{type:'mousePressed',x:rect.x+rect.width/2,y:rect.y+rect.height/2,button:'left',clickCount:1});
 await send('Input.dispatchMouseEvent',{type:'mouseMoved',x:rect.x+rect.width/2+100,y:rect.y+rect.height/2+35,button:'left',buttons:1});
 await send('Input.dispatchMouseEvent',{type:'mouseReleased',x:rect.x+rect.width/2+100,y:rect.y+rect.height/2+35,button:'left',clickCount:1});
 const desktopDragged=await capture('desktop_dragged');
 await evaluate(`document.getElementById('oblique').click()`);
 await choose('unit',0);const unitZero=await evaluate(`document.getElementById('decision').textContent`);await capture('unit0_oblique');
 await evaluate(`document.getElementById('top').click()`);await capture('unit0_top');
 await choose('unit',542);await evaluate(`document.getElementById('oblique').click()`);await capture('unit542_oblique');
 await evaluate(`document.getElementById('uas').click();document.getElementById('ref-right').click();document.getElementById('section').click()`);await capture('unit542_section_with_reference');
 const sectionState=await evaluate(`({decision:document.getElementById('decision').textContent,error:document.getElementById('error').textContent})`);
 await choose('unit','all');await evaluate(`document.getElementById('oblique').click()`);
 const armChecks=[],specialChecks=[];
 for(const arm of initial.arms){
  await choose('arm',arm.key);
  const state=await evaluate(`({error:document.getElementById('error').textContent,title:document.querySelectorAll('.views h2')[1].textContent,images:document.querySelectorAll('#images img').length})`);
  const loadedImages=await evaluate(`Promise.all([...document.querySelectorAll('#images img')].map(async i=>{try{await i.decode()}catch{}return {src:i.getAttribute('src'),loaded:i.complete&&i.naturalWidth>0}}))`);
  armChecks.push({key:arm.key,...state,loadedImages});
  if(arm.key.includes('SHARED-SHIFT')){await capture('all_abstain_with_reference');await evaluate(`document.getElementById('ref-right').click()`);await capture('all_abstain_without_reference');await evaluate(`document.getElementById('ref-right').click()`);specialChecks.push({key:arm.key,status:await evaluate(`document.getElementById('metrics').textContent`)});}
  if(arm.key.includes('DN-')){
   const ids=await evaluate(`[...document.getElementById('image-view').options].map(o=>o.value)`),checked=[];
   for(const id of ids){await choose('image-view',id);checked.push({imageId:id,images:await evaluate(`Promise.all([...document.querySelectorAll('#images img')].map(async i=>{try{await i.decode()}catch{}return {src:i.getAttribute('src'),loaded:i.complete&&i.naturalWidth>0,width:i.naturalWidth,height:i.naturalHeight}}))`)});}
   await capture('dn_desktop');await evaluate(`document.getElementById('images').scrollIntoView({block:'center'})`);await capture('dn_images');await evaluate('window.scrollTo(0,0)');specialChecks.push({key:arm.key,checkedViews:checked});
  }
 }
 const firstB=initial.arms.find(a=>!a.key.startsWith('A/'));let bImages=null;
 if(firstB){await choose('arm',firstB.key);bImages=await evaluate(`Promise.all([...document.querySelectorAll('#images img')].map(async i=>{try{await i.decode()}catch{}return {src:i.getAttribute('src'),width:i.naturalWidth,height:i.naturalHeight,loaded:i.complete&&i.naturalWidth>0}}))`);await capture('first_b_arm_desktop');}
 await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});await pause(100);await capture('mobile_390');
 const mobile=await evaluate(`({viewport:[innerWidth,innerHeight],scrollWidth:document.documentElement.scrollWidth,clientWidth:document.documentElement.clientWidth,overflow:document.documentElement.scrollWidth>document.documentElement.clientWidth,canvasBoxes:[...document.querySelectorAll('canvas')].map(c=>{const r=c.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height}})})`);
 const errors=events.filter(e=>e.method==='Runtime.exceptionThrown'||(e.method==='Runtime.consoleAPICalled'&&e.params.type==='error')||(e.method==='Log.entryAdded'&&e.params.entry.level==='error'));
 const networkFailures=events.filter(e=>e.method==='Network.loadingFailed'||(e.method==='Network.responseReceived'&&e.params.response.status>=400));
 const result={url,initial,drag_changed_screenshot:desktopBefore!==desktopDragged,unit0_decision:unitZero,unit542_section:sectionState,armChecks,specialChecks,bImages,mobile,errors,networkFailures,screenshots:await fs.readdir(out),browser:'Host Chrome in fresh isolated /tmp profile with explicit SwiftShader; no user-profile access',scientific_verdict:null};
 await fs.writeFile(path.join(out,'browser_qa.json'),JSON.stringify(result,null,2)+'\n',{flag:'wx'});console.log(JSON.stringify(result,null,2));
}catch(e){await fs.writeFile(path.join(out,'FAILED.json'),JSON.stringify({error:String(e),events,scientific_verdict:null},null,2)+'\n',{flag:'wx'});throw e;}finally{socket.end();}
