// Browser acceptance: physical picking, source geometry, unchanged statistics.
import {spawn} from 'node:child_process';
import {mkdirSync,readFileSync,writeFileSync} from 'node:fs';
const base=process.env.VIEW_URL||'http://127.0.0.1:8913/',label=process.env.QA_LABEL||'preview',port=9243;
mkdirSync('/docs/screens_v1_2',{recursive:true});mkdirSync('/docs/tables_v1_2',{recursive:true});
const browser=spawn('/usr/bin/chromium',['--headless=new','--no-sandbox','--disable-gpu','--disable-dev-shm-usage',`--remote-debugging-port=${port}`,'--user-data-dir=/tmp/mvs-geometry-qa','about:blank'],{stdio:'ignore'});
const pause=ms=>new Promise(r=>setTimeout(r,ms)),pending=new Map();let ws,id=0;
const result={base,label,started:new Date().toISOString(),checks:[],screens:[],errors:[],scientific_verdict:null};
function check(name,pass,details){result.checks.push({name,pass,...details});if(!pass)throw Error('Failed: '+name)}
function cmd(method,params={}){return new Promise((resolve,reject)=>{const key=++id,t=setTimeout(()=>{pending.delete(key);reject(Error('Timeout '+method))},180000);pending.set(key,{resolve:x=>{clearTimeout(t);resolve(x)},reject:x=>{clearTimeout(t);reject(x)}});ws.send(JSON.stringify({id:key,method,params}))})}
async function ev(expression){const x=await cmd('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(x.exceptionDetails)throw Error(x.exceptionDetails.exception?.description||JSON.stringify(x.exceptionDetails));return x.result?.value}
async function until(expression){for(let n=0;n<1200;n++){if(await ev(expression))return;await pause(150)}throw Error('Timeout '+expression)}
async function ready(){await until('window.UNCERT_APP?.ready && !UNCERT_APP.judgeBusy && !!UNCERT_APP.judgement');await pause(100)}
async function screenshot(name,selector){if(label!=='preview')return;await ev(`document.querySelector(${JSON.stringify(selector)}).scrollIntoView({block:'center'})`);await pause(150);const clip=await ev(`(()=>{const r=document.querySelector(${JSON.stringify(selector)}).getBoundingClientRect();return {x:r.x+scrollX,y:r.y+scrollY,width:r.width,height:r.height,scale:1}})()`);const x=await cmd('Page.captureScreenshot',{format:'png',captureBeyondViewport:true,clip});writeFileSync('/docs/screens_v1_2/'+name+'.png',Buffer.from(x.data,'base64'));result.screens.push(name)}
try{
  let pages;for(let n=0;n<150;n++){try{pages=await(await fetch(`http://127.0.0.1:${port}/json/list`)).json();break}catch{await pause(100)}}
  ws=new WebSocket(pages.find(p=>p.type==='page').webSocketDebuggerUrl);await new Promise(r=>ws.onopen=r);
  ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id){const p=pending.get(m.id);if(p){pending.delete(m.id);m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m.result)}}else if(m.method==='Runtime.exceptionThrown')result.errors.push(m.params.exceptionDetails.exception?.description||m.params.exceptionDetails.text)};
  await cmd('Page.enable');await cmd('Runtime.enable');await cmd('Emulation.setDeviceMetricsOverride',{width:1720,height:1180,deviceScaleFactor:1,mobile:false});await cmd('Page.navigate',{url:base});await ready();
  check('default_is_actual_mvs_both_maps',await ev("MG.enabled()&&MG.isMvs('left')&&MG.isMvs('right')&&UNCERT_APP.data.clouds.a.n===1200000&&document.title.includes('v1.2')"));
  const ids=await ev('DV.M.cases.map(c=>c.id)');
  const references=JSON.parse(readFileSync('/docs/tables_v1_1/reference_charts.json','utf8')).results;
  for(const caseId of (label!=='preview'?ids.slice(0,1):ids)){
    await ev(`uncertUI.changeCase(${JSON.stringify(caseId)},true)`);await ready();await ev("V11.setPair('mvs')");await ready();
    const geometry=await ev("({left:document.getElementById('geometryLabelleft').textContent,right:document.getElementById('geometryLabelright').textContent,points:uncertUI.maps.left.displayedPoints,mapped:UNCERT_APP.data.clouds.a.stats[UNCERT_APP.data.meta.prior],mapMs:UNCERT_APP.lastMapMs})");
    check(caseId+'/source_geometry',geometry.points>1000&&geometry.left.includes('MVS 실제 점군')&&geometry.right.includes('MVS 실제 점군'),{geometry});
    const key=caseId+'__exclude_0',ref=references[key];
    if(ref){const actual=await ev('UNCERT_APP.judgement');let compared=0;for(let i=0;i<ref.calibration.length;i++)for(const field of ['n','u_median_cm','e_median_cm','e_p25_cm','e_p75_cm']){const a=ref.calibration[i][field],b=actual.calibration[i][field];check(key+'/'+i+'/'+field,a===b||Number.isFinite(a)&&Number.isFinite(b)&&Math.abs(a-b)<1e-6);compared++}check(caseId+'/numeric_reference_checked',compared>0)}else throw Error('Missing frozen numeric reference '+key);
    await screenshot('mvs_maps_'+caseId,'.maps');await screenshot('mvs_3d_'+caseId,'.oblique');
    await ev("V11.setPair('sources')");await ready();check(caseId+'/separate_source_geometry',await ev("MG.isMvs('left')&&!MG.isMvs('right')&&document.getElementById('geometryLabelright').textContent.includes('LoD2 면')"));
    if(caseId==='B173nb_b10__LoD2')await screenshot('mvs_vs_prior','.maps');
    await ev("V11.setPair('mvs');document.getElementById('version').value='b';document.getElementById('version').dispatchEvent(new Event('change'))");await ready();
    check(caseId+'/version_b',await ev("UNCERT_APP.v==='b'&&document.getElementById('geometryLabelleft').textContent.includes('판 나')&&uncertUI.maps.left.displayedPoints>1000"));
    await ev("document.getElementById('version').value='a';document.getElementById('version').dispatchEvent(new Event('change'))");await ready();
    console.log('Verified',caseId);
  }
  await ev("uncertUI.changeCase('B173nb_b10__LoD2',true)");await ready();await ev("V11.setPair('mvs')");await ready();
  await ev("document.getElementById('mapleft').scrollIntoView({block:'center'})");await pause(200);
  const point=await ev(`(()=>{const A=uncertUI,S=A.S,c=A.maps.left.canvas,r=c.getBoundingClientRect(),rs=S.raster;for(let y=20;y<c.height-20;y+=3)for(let x=20;x<c.width-20;x+=3){const p=A.world(x,y,c),xx=Math.floor((p[0]-rs.b.x0)*rs.ppu),yy=Math.floor((rs.b.y1-p[1])*rs.ppu);if(xx<0||yy<0||xx>=rs.w||yy>=rs.h)continue;const i=A.maps.left.pick[yy*rs.w+xx];if(i>=0&&S.match[i])return {x:x+r.x,y:y+r.y,patch:i}}return null})()`);
  check('physical_point_available',!!point);await cmd('Input.dispatchMouseEvent',{type:'mouseMoved',x:point.x,y:point.y});await pause(80);
  check('mvs_hover_is_patch_not_prior_face',await ev("document.getElementById('tooltip').textContent.includes('패치')&&!document.getElementById('tooltip').textContent.includes('LoD2 면')"));
  for(const type of ['mousePressed','mouseReleased'])await cmd('Input.dispatchMouseEvent',{type,button:'left',clickCount:1,x:point.x,y:point.y});
  check('mvs_point_click_opens_own_patch',await ev(`UNCERT_APP.patch===${point.patch}&&UNCERT_APP.faceFocus===null`));
  await ev("document.getElementById('oblique').scrollIntoView({block:'center'})");await pause(150);
  const oblique=await ev("(()=>{const o=UNCERT_APP.mvsOrbitPick,r=document.getElementById('oblique').getBoundingClientRect();for(let y=20;y<o.h-20;y+=2)for(let x=20;x<o.w-20;x+=2)if(o.pick[y*o.w+x]>=0)return {x:x+r.x,y:y+r.y,patch:o.pick[y*o.w+x]}})()");
  for(const type of ['mousePressed','mouseReleased'])await cmd('Input.dispatchMouseEvent',{type,button:'left',clickCount:1,x:oblique.x,y:oblique.y});check('mvs_3d_click',await ev(`UNCERT_APP.patch===${oblique.patch}`));
  await ev("document.getElementById('orbitSide').value='right';document.getElementById('orbitSide').dispatchEvent(new Event('change'));document.getElementById('layerright').value='prior_e';document.getElementById('layerright').dispatchEvent(new Event('change'))");
  check('right_layer_change_refreshes_3d_geometry',await ev("!MG.isMvs('right')&&UNCERT_APP.orbitTriangles.length>0"));
  await ev("V11.setPair('mvs');document.getElementById('orbitSide').value='left';document.getElementById('orbitSide').dispatchEvent(new Event('change'))");await ready();
  const before=await ev('JSON.stringify(UNCERT_APP.judgement.calibration)');
  await ev("document.getElementById('displayGeometry').value='legacy';document.getElementById('displayGeometry').dispatchEvent(new Event('change'))");await ready();
  check('legacy_geometry_available',await ev("!MG.enabled()&&document.getElementById('geometryLabelleft').textContent.includes('LoD2 면')"));
  check('geometry_does_not_change_statistics',before===await ev('JSON.stringify(UNCERT_APP.judgement.calibration)'));
  await ev("document.getElementById('displayGeometry').value='source';document.getElementById('displayGeometry').dispatchEvent(new Event('change'));document.getElementById('shape').value='wall';document.getElementById('shape').dispatchEvent(new Event('input'))");await ready();
  check('wall_filter_changes_stat_population',await ev('UNCERT_APP.match.reduce((a,b)=>a+b,0)>0&&UNCERT_APP.match.reduce((a,b)=>a+b,0)<UNCERT_APP.data.n'));
  await ev("document.getElementById('clearfilters').click()");await ready();
  check('sparse_explanation_and_cm_tooltips',await ev("document.querySelector('#sparsification .chartExplanation').textContent.includes('10을 곱해도')&&document.querySelector('#sparsification circle title').textContent.includes('cm')"));
  await screenshot('chart_explanation','#judgement');
  await cmd('Emulation.setDeviceMetricsOverride',{width:740,height:1100,deviceScaleFactor:1,mobile:false});await pause(150);await screenshot('narrow_mvs','.maps');
  check('no_browser_exceptions',result.errors.length===0);result.pass=true;
}catch(e){result.pass=false;result.fatal=e.stack;console.error(e.stack);process.exitCode=1}
finally{result.finished=new Date().toISOString();writeFileSync('/docs/tables_v1_2/browser_'+label+'.json',JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify({pass:result.pass,checks:result.checks.length,errors:result.errors,fatal:result.fatal}));ws?.close();browser.kill('SIGTERM')}
