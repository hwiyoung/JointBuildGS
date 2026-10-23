// Extend the same QA harness with real pointer events and byte-level packet checks.
import {readFileSync,writeFileSync} from 'node:fs';
const base=readFileSync('/src/qa_browser.mjs','utf8');
const insert=`
await evaluate("uncertTest.changeCase('B173nb_b10__LoD2',true)");await until('UNCERT_APP.ready');
const rect=await evaluate("(()=>{const r=document.getElementById('mapleft').getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height}})()");
const mx=rect.x+rect.w/2,my=rect.y+rect.h/2;const camera=await evaluate('({...UNCERT_APP.camera})');
await cmd('Input.dispatchMouseEvent',{type:'mouseWheel',x:mx,y:my,deltaX:0,deltaY:-350});await pause(200);
results.checks.push({test:'real_wheel_zoom',before:camera,after:await evaluate('({...UNCERT_APP.camera})')});
await cmd('Input.dispatchMouseEvent',{type:'mousePressed',x:mx,y:my,button:'left',clickCount:1});await cmd('Input.dispatchMouseEvent',{type:'mouseMoved',x:mx+40,y:my+25,button:'left',buttons:1});await cmd('Input.dispatchMouseEvent',{type:'mouseReleased',x:mx+40,y:my+25,button:'left',clickCount:1});await pause(200);
results.checks.push({test:'real_pan_synchronized',camera:await evaluate('({...UNCERT_APP.camera})')});
await evaluate("document.querySelector('[data-mode=lasso]').click()");
await cmd('Input.dispatchMouseEvent',{type:'mousePressed',x:mx-90,y:my-80,button:'left',clickCount:1});for(const [x,y]of [[mx+90,my-80],[mx+90,my+80],[mx-90,my+80],[mx-90,my-80]])await cmd('Input.dispatchMouseEvent',{type:'mouseMoved',x,y,button:'left',buttons:1});await cmd('Input.dispatchMouseEvent',{type:'mouseReleased',x:mx-90,y:my-80,button:'left',clickCount:1});await pause(200);
results.checks.push({test:'real_lasso',n:await evaluate('UNCERT_APP.selectionSummary.n'),vertices:await evaluate('UNCERT_APP.selectionShape.length')});
await evaluate("document.querySelector('[data-mode=pan]').click();uncertTest.fit()");
const target=await evaluate("(()=>{const s=UNCERT_APP,i=s.data.samples.find(i=>s.z.in_eval[i]&&s.z.roof_like[i]),r=document.getElementById('mapleft').getBoundingClientRect();return {x:r.x+r.width/2+(s.z.centre[3*i]-s.camera.x)*s.camera.scale,y:r.y+r.height/2-(s.z.centre[3*i+1]-s.camera.y)*s.camera.scale}})()");
await cmd('Input.dispatchMouseEvent',{type:'mouseMoved',...target});await pause(100);results.checks.push({test:'hover',text:await evaluate('document.getElementById("tooltip").innerText')});
await cmd('Input.dispatchMouseEvent',{type:'mousePressed',...target,button:'left',clickCount:1});await cmd('Input.dispatchMouseEvent',{type:'mouseReleased',...target,button:'left',clickCount:1});await pause(400);results.checks.push({test:'real_patch_click',patch:await evaluate('UNCERT_APP.patch')});
await evaluate("document.getElementById('enableRange').checked=true;document.getElementById('filterlow').value='5';document.getElementById('filterhigh').value='10';uncertTest.refresh(false)");results.checks.push({test:'range_filter',n:await evaluate('UNCERT_APP.selectionSummary.n')});
await evaluate("uncertTest.setQuestion(3)");await evaluate("UNCERT_APP.exclude=true;document.getElementById('excludeCorr').checked=true;uncertTest.refresh(true)");await until('!UNCERT_APP.questionBusy');results.checks.push({test:'exclude_corrections',result:await evaluate('UNCERT_APP.questionResult')});
await evaluate("UNCERT_APP.v='b';document.getElementById('version').value='b';UNCERT_APP.r='3.0';document.getElementById('radius').value='3.0';uncertTest.setQuestion(2)");await until('!UNCERT_APP.questionBusy');results.checks.push({test:'q2_version_b_radius3',result:await evaluate('UNCERT_APP.questionResult')});
const integrity=await evaluate("(async()=>{const c=await DV.load('B173nb_b10__LoD2');const wanted=['centre','mvs_a_u','u_prior','z_a','w_b','errW_b'];let out=[];for(const r of ['1.0','1.5','3.0'])for(const k of wanted){const a=c.rings[r][k],h=await crypto.subtle.digest('SHA-256',a.buffer.slice(a.byteOffset,a.byteOffset+a.byteLength));out.push({r,k,sha256:Array.from(new Uint8Array(h),b=>b.toString(16).padStart(2,'0')).join('')})}return out})()");results.checks.push({test:'decoded_float_byte_hashes',integrity});
`;
const code=base.replace("if(mode==='smoke'){",insert+"if(mode==='smoke'){");writeFileSync('/tmp/qa_extended.mjs',code);await import('/tmp/qa_extended.mjs');
