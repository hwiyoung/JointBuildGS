// Actual Chromium verification of sealed input-only photometric walkthroughs.
// Run only in the pinned Docker browser image; no training GPU access.
import fs from 'node:fs/promises';
import {spawn} from 'node:child_process';
import crypto from 'node:crypto';

const [url,out='/out',site='/site']=process.argv.slice(2);
if(!url||!['localhost','127.0.0.1'].includes(new URL(url).hostname)||!new URL(url).pathname.startsWith('/packets/packet_'))throw Error('Explicit immutable localhost packet URL required');
const imageId='sha256:5043f84d76db9d54e64fcf457125aad90ac5423fded88eca6cf487d2b4713a9e';
const checks=[],screenshots=[],runtimeErrors=[],consoleErrors=[],networkFailures=[],chromeLog=[],httpFiles=[],states=[];
const receipt={schema:'jbgs.photometric_walkthrough.browser_qa.v3.2',status:'RUNNING',url,started_at:new Date().toISOString(),scientific_verdict:null,
  image_id:imageId,cpu_limit:2,memory_limit_bytes:3*1024**3,training_gpu_used:false,checks,screenshots,runtime_errors:runtimeErrors,console_errors:consoleErrors,network_failures:networkFailures,http_files:httpFiles,states,
  scope:'Every actual case, source pair, neighbor and six UI stages; displayed numbers and asset bytes versus sealed case JSON; desktop/mobile/dialog usability. This is technical publication QA, not independent photometric or scientific validation.'};
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
const pause=ms=>new Promise(r=>setTimeout(r,ms));
const finite=x=>typeof x==='number'&&Number.isFinite(x);
const formatted=(x,n=4)=>finite(x)?x.toFixed(n):'미측정';
function median(values){const a=values.filter(finite).sort((a,b)=>a-b);if(!a.length)return null;const half=Math.floor(a.length/2);return a.length%2?a[half]:(a[half-1]+a[half])/2;}
function check(pass,name,details){checks.push({pass:!!pass,name,details});if(!pass)throw Error(name);}
const same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
const sourceName=k=>({prior:'Prior · 기존 ALS',da3:'DA3 · 영상 depth',mvs:'MVS · 영상 depth'})[k];
const statusLabel=s=>({DEFINED_DESCRIPTIVE_ONLY:'점수 계산됨 · 신뢰 판정 전',PARTIAL_OR_UNDEFINED_SEE_SOURCE_STATUS:'일부 또는 전체 점수 미정의',UNDEFINED_INSUFFICIENT_COMMON_PIXELS:'공통 표본 부족',UNDEFINED_FLAT_PATCH:'밝기 변화 부족'})[s]||'자료 미지원';
const relativeAsset=p=>p?'assets/diagnostic/'+String(p).replace(/^\.?\//,''):null;
function initialNeighbor(item,pair){const k=pair.slice(6),paired=item.neighbors.findIndex(n=>Number(n.comparisons[pair].common_count)>=2);if(paired>=0)return paired;return Math.max(0,item.neighbors.findIndex(n=>Number(n.sources?.prior?.projectable_sample_count)>0||Number(n.sources?.[k]?.projectable_sample_count)>0));}
const artifactURLs=new Map();
let browser,socket,seq=0,currentBefore,published;
const pending=new Map();
function send(method,params={}){const id=++seq;return new Promise((resolve,reject)=>{const timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout '+method));},30000);pending.set(id,{resolve:r=>{clearTimeout(timer);resolve(r);},reject:e=>{clearTimeout(timer);reject(e);}});socket.send(JSON.stringify({id,method,params}));});}
async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result?.value;}
async function choose(id,value){await evaluate(`(()=>{const e=document.getElementById(${JSON.stringify(id)});if(!e||![...e.options].some(o=>o.value===${JSON.stringify(String(value))}))throw Error('Missing QA option');e.value=${JSON.stringify(String(value))};e.dispatchEvent(new Event('change',{bubbles:true}));})()`);}
async function ready(expected){for(let i=0;i<200;i++){const state=await evaluate('({state:window.__walkthrough,error:window.__walkthroughError})');if(state?.error)throw Error(state.error);if(state?.state&&Object.entries(expected).every(([k,v])=>state.state[k]===v))return state.state;await pause(50);}throw Error('Walkthrough state load timeout '+JSON.stringify(expected));}
async function imagesReady(){for(let i=0;i<200;i++){const images=await evaluate(`([...document.querySelectorAll('#step-body img')].map(i=>({src:i.getAttribute('src'),complete:i.complete,width:i.naturalWidth,height:i.naturalHeight,alt:i.alt})))`);if(images.every(i=>i.complete&&i.width>0&&i.height>0))return images;await pause(50);}throw Error('Step image load timeout');}
async function capture(name){const r=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});const b=Buffer.from(r.data,'base64');await fs.writeFile(out+'/'+name,b,{flag:'wx'});screenshots.push({path:name,sha256:hash(b),bytes:b.length});}
async function sourceJSON(relative){const r=await fetch(new URL(relative,url));const b=Buffer.from(await r.arrayBuffer());check(r.ok,'Source JSON HTTP available',{relative,status:r.status});const expected=published.outputs.find(o=>o.path===relative);check(expected?.sha256===hash(b),'Source JSON matches publication digest',{relative,sha256:hash(b)});artifactURLs.set(relative,expected.sha256);return JSON.parse(b);}
function expectedImages(item,pair,ni,step){const n=item.neighbors[ni],k=pair.slice(6),s=n.sources,c=n.comparisons[pair];let urls;
  if(step===1)urls=[item.ref_full_overlay_url,item.ref_context_url];
  else if(step===2)urls=[s.prior?.full_overlay_url,s[k]?.full_overlay_url];
  else if(step===3)urls=[item.ref_patch_url,s.prior?.warped_patch_url,s[k]?.warped_patch_url,item.ref_context_url,s.prior?.warped_context_url,s[k]?.warped_context_url];
  else if(step===4)urls=[s.prior?.valid_mask_url,s[k]?.valid_mask_url,c.common_valid_mask_url];
  else if(step===5)urls=[c.standardized_reference_url,c.standardized_source_urls?.prior,c.standardized_source_urls?.[k],c.normalized_residual_urls?.prior,c.normalized_residual_urls?.[k]];
  else urls=[];
  return urls.filter(Boolean).map(relativeAsset);
}
async function checkStage(item,pair,ni,step,mode='desktop'){
  const expected={caseId:item.case_id,pair,neighbor:ni,step};const state=await ready(expected);const images=await imagesReady();
  check(same(images.map(i=>i.src),expectedImages(item,pair,ni,step)),'Stage PNG sources bind exact case/pair/neighbor',{...expected,mode,images});
  for(const image of images){const output=published.outputs.find(o=>o.path===image.src);check(!!output,'Displayed image is sealed output',image.src);artifactURLs.set(image.src,output.sha256);}
  const ui=await evaluate(`({heading:document.querySelector('#step-body h2')?.textContent,metrics:[...document.querySelectorAll('#step-body .metric .value')].map(e=>e.textContent),rows:[...document.querySelectorAll('#step-body tbody tr')].map(r=>[...r.cells].map(c=>c.textContent.trim())),selectedRows:[...document.querySelectorAll('#score-table tbody tr')].map((r,i)=>r.classList.contains('selected')?i:null).filter(x=>x!==null),stepPosition:document.querySelector('#step-position').textContent,previousDisabled:document.querySelector('#prev').disabled,nextDisabled:document.querySelector('#next').disabled,activeSteps:[...document.querySelectorAll('.steps [aria-current="step"]')].map(e=>Number(e.dataset.step)),status:document.querySelector('#step-body .status')?.textContent,caseLink:document.querySelector('#case-link').getAttribute('href'),dimensions:{viewport:innerWidth,document:document.documentElement.scrollWidth},tables:[...document.querySelectorAll('.table-wrap')].map(e=>({client:e.clientWidth,scroll:e.scrollWidth,overflow:getComputedStyle(e).overflowX}))})`);
  check(ui.heading?.startsWith(step+'.')&&ui.stepPosition===step+' / 6 단계'&&same(ui.activeSteps,[step])&&ui.previousDisabled===(step===1)&&ui.nextDisabled===(step===6),'Stage navigation state consistent',{...expected,mode});
  const c=item.neighbors[ni].comparisons[pair],k=pair.slice(6),a=c.scores?.prior||{},b=c.scores?.[k]||{};
  if(step===1){const d=item.depths||item.center_depths||{};check(same(ui.metrics,[formatted(d.prior,3),formatted(d[k],3),(item.exact_patch_size||9)+' × '+(item.exact_patch_size||9)]),'Camera Z and exact score patch values match case JSON',{...expected,mode,actual:ui.metrics});}
  if(step===4){check(same(ui.metrics,[String(c.common_count??'미측정')])&&ui.status?.includes(statusLabel(c.status)),'Pairwise common count and translated validity status match case JSON',{...expected,mode,actual:ui.metrics,status:ui.status});}
  if(step===5){const expectedRows=[['Prior',formatted(a.std_reference),formatted(a.std_warp)],[sourceName(k),formatted(b.std_reference),formatted(b.std_warp)]];check(same(ui.rows,expectedRows),'Both normalization standard deviations match case JSON',{...expected,mode,actual:ui.rows});}
  if(step===6){const expectedRows=item.neighbors.map(n=>{const c=n.comparisons[pair],p=c.scores?.prior||{},i=c.scores?.[k]||{};return [n.camera_id,String(c.common_count??'—'),formatted(p.zncc),formatted(i.zncc),formatted(p.cost),formatted(i.cost),statusLabel(c.status),'패치 보기'];});
    check(same(ui.rows,expectedRows)&&same(ui.selectedRows,[ni]),'All neighbor ZNCC cost counts and statuses match case JSON',{...expected,mode,actual:ui.rows});
    const tableGeometry=await evaluate(`({cameraWidths:[...document.querySelectorAll('#score-table td.camera')].map(e=>e.getBoundingClientRect().width),rowHeights:[...document.querySelectorAll('#score-table tbody tr')].map(e=>e.getBoundingClientRect().height)})`);
    check(tableGeometry.cameraWidths.every(w=>w>=150)&&tableGeometry.rowHeights.every(h=>h<=160),'Score table retains readable camera column and bounded row height',{...expected,mode,...tableGeometry});
    const all=item.neighbors.map(n=>n.comparisons[pair]).filter(c=>finite(c.scores?.prior?.cost)&&finite(c.scores?.[k]?.cost));const prior=all.map(c=>c.scores.prior.cost),image=all.map(c=>c.scores[k].cost),paired=all.map(c=>c.scores.prior.cost-c.scores[k].cost);
    check(same(ui.metrics,[median(prior),median(image),median(paired)].map(x=>formatted(x))),'Cost medians use the same jointly finite neighbors; paired difference sign is Prior minus Image',{...expected,mode,actual:ui.metrics,jointly_finite_neighbor_count:all.length});
  }
  const guide=await evaluate(`({selection:document.querySelector('#selection-guide')?.textContent,support:[...document.querySelectorAll('#projection-support .support-card')].map(e=>({source:e.dataset.source,text:e.textContent})),patch:document.querySelector('#patch-size-guide')?.textContent,mask:document.querySelector('#mask-legend')?.textContent,swatches:[...document.querySelectorAll('#mask-legend .swatch')].map(e=>getComputedStyle(e).backgroundColor),reading:document.querySelector('#reading-guide')?.textContent,neighbors:[...document.querySelectorAll('#neighbor-select option')].map(e=>e.textContent)})`);
  check(same(guide.neighbors,item.neighbors.map((n,i)=>(i+1)+'. '+n.camera_id+' · 공통 '+(n.comparisons[pair].common_count??0)+'/'+(item.exact_patch_size||9)**2+'픽셀')),'Neighbor labels retain every original camera and pair-specific support count',{...expected,mode});
  if(step===1){const s=item.selection||{},counts='Prior '+s.prior_count+' / DA3 '+s.da3_count+' / MVS '+s.mvs_count+'개',disagreement='Prior–DA3 절대 차이 중앙값: '+formatted(s.median_prior_da3_disagreement_m,4)+'m';
    check(guide.selection?.includes(counts)&&guide.selection.includes(disagreement)&&guide.selection.includes('64픽셀')&&guide.selection.includes('처음 만족한 위치')&&guide.selection.includes('RGB 무늬·점수·GT·학습 결과로 고른 위치가 아닙니다.'),'Selection explanation matches raw depth counts and disagreement median',{...expected,mode,counts,disagreement});}
  if(step===2){check(same(guide.support.map(x=>x.source),['prior',k]),'Projection explanation retains independent source cards',{...expected,mode});for(const key of ['prior',k]){const s=item.neighbors[ni].sources[key],p=s.center_projection_steps||{},uv=p.projected_uv||[],cam=item.neighbors[ni].neighbor_camera_model,card=guide.support.find(x=>x.source===key).text,total=(item.exact_patch_size||9)**2;
      const raw='원 depth '+s.raw_target_valid_count+' / '+total+'개 → 이웃 RGB 조회 가능 '+s.projectable_sample_count+' / '+total+'개',center='중심 투영 (u, v) = ('+formatted(uv[0],1)+', '+formatted(uv[1],1)+')',bounds='사진 범위 u: 0–'+(cam.width-1)+', v: 0–'+(cam.height-1);
      check(card.includes(raw)&&card.includes(center)&&card.includes(bounds),'Projection source counts center UV and image bounds match original JSON',{...expected,mode,source:key,raw,center,bounds});
      check(s.raw_target_valid_count===0?card.includes('원 depth가 모두 결손'):s.projectable_sample_count===0?card.includes('원 depth는 있지만'):card.includes('색을 가져올 수 있습니다.'),'Missing depth and zero projected support are distinguished',{...expected,mode,source:key});
      const outside=uv.length===2&&uv.every(finite)&&(uv[0]<0||uv[0]>cam.width-1||uv[1]<0||uv[1]>cam.height-1);check(card.includes('중심 투영은 사진 범위 밖입니다.')===outside,'Outside-image explanation follows actual center coordinates',{...expected,mode,source:key,outside});}}
  if(step===3)check(['9×9','최대 81개','고정한 진단용 크기','최적 크기로 검증된 값','65×65는 위치 이해용','크기별 민감도 검증이 남아'].every(x=>guide.patch?.includes(x)),'Patch-size guide states fixed diagnostic support and unresolved sensitivity',{...expected,mode});
  if(step===4)check(['흰색 = 1','검은색 = 0','“오차 0”이나 “정답”의 색이 아닙니다.'].every(x=>guide.mask?.includes(x))&&same(guide.swatches,['rgb(255, 255, 255)','rgb(0, 0, 0)']),'Mask legend maps white to valid1 and black to invalid0 without truth claim',{...expected,mode});
  if(step===6){const paired=item.neighbors.filter(n=>finite(n.comparisons[pair].scores?.prior?.cost)&&finite(n.comparisons[pair].scores?.[k]?.cost)),pc=paired.filter(n=>n.comparisons[pair].scores.prior.cost<n.comparisons[pair].scores[k].cost).length,ic=paired.filter(n=>n.comparisons[pair].scores[k].cost<n.comparisons[pair].scores.prior.cost).length,count='선정 이웃 '+item.neighbors.length+'장 중 이 비교쌍의 점수 계산 '+paired.length+'장',wins='Prior '+pc+'장, '+k.toUpperCase()+' '+ic+'장, 동률 '+(paired.length-pc-ic)+'장';
    check(guide.reading?.includes(count)&&(paired.length?guide.reading.includes(wins):guide.reading.includes('적합도 우열을 말할 수 없습니다.'))&&guide.reading.includes('자동 가중치 결정으로 연결하지 않습니다.'),'Reading guide uses jointly scored neighbor counts and descriptive preference counts only',{...expected,mode,count,wins});
    if(item.neighbors.every(n=>n.sources[k].raw_target_valid_count===0))check(guide.reading.includes(k.toUpperCase()+' 원 depth가 작은 패치에서 모두 결손입니다.')&&guide.reading.includes('Prior가 정답이라는 뜻은 아닙니다.'),'Source-hole explanation does not award the competing source correctness',{...expected,mode});}
  check(ui.dimensions.document<=ui.dimensions.viewport+1&&ui.tables.every(t=>t.scroll<=t.client+1||['auto','scroll'].includes(t.overflow)),'No page horizontal overflow; wide tables scroll internally',{...expected,mode,dimensions:ui.dimensions});
  states.push({...expected,mode,image_count:images.length});return {state,ui,images};
}

try{
  currentBefore=await fs.readFile(site+'/current.json');receipt.current_pointer_before_sha256=hash(currentBefore);
  const r=await fetch(new URL('receipt.json',url)),b=Buffer.from(await r.arrayBuffer());published=JSON.parse(b);receipt.publication_receipt_sha256=hash(b);
  check(r.ok&&published.status==='PASS'&&published.scope==='INTERNAL_FIT_DIAGNOSTIC_STATIC_PUBLICATION'&&published.scientific_verdict===null,'Publication is sealed input-only diagnostic',published.status);
  check(published.current_pointer_updated===false&&published.current_before_sha256===published.current_after_sha256&&published.current_pointer_observed_change===false,'Publisher preserved existing viewer pointer');
  const data=await sourceJSON('data.json');check(data.scientific_verdict===null&&data.context_used_for_score===false&&data.winner_selection===false&&data.q_computed===false,'Published scope retains null verdict and no winner or q');
  const cases=[];for(const entry of data.cases){const relative=relativeAsset(entry.path||entry.case_json||entry.case_url),item=await sourceJSON(relative);check(item.case_id===entry.case_id&&item.scientific_verdict===null&&item.neighbors.length>0,'Case identity and observed neighbors match manifest',entry.case_id);cases.push(item);}
  check(cases.length===published.cases.length&&new Set(cases.map(c=>c.case_id)).size===cases.length,'Every declared case uniquely included',cases.length);
  receipt.case_count=cases.length;receipt.neighbor_counts=cases.map(c=>({case_id:c.case_id,count:c.neighbors.length}));
  const profile=await fs.mkdtemp('/tmp/lc-photo-qa-');for(const p of ['config','cache','data'])await fs.mkdir(profile+'/'+p);
  browser=spawn('/usr/bin/chromium',['--headless=new','--no-sandbox','--no-first-run','--disable-dev-shm-usage','--disable-gpu','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{env:{...process.env,XDG_CONFIG_HOME:profile+'/config',XDG_CACHE_HOME:profile+'/cache',XDG_DATA_HOME:profile+'/data'}});
  browser.stderr.on('data',b=>chromeLog.push(b.toString()));
  let port;for(let i=0;i<150;i++){try{port=(await fs.readFile(profile+'/DevToolsActivePort','utf8')).split('\n')[0];break;}catch{await pause(100);}}if(!port)throw Error('Chromium startup timeout');
  const pages=await(await fetch('http://127.0.0.1:'+port+'/json/list')).json(),page=pages.find(p=>p.type==='page'&&p.url==='about:blank');if(!page)throw Error('Dedicated blank page missing');
  socket=new WebSocket(page.webSocketDebuggerUrl);await new Promise((r,j)=>{socket.onopen=r;socket.onerror=j;});
  socket.onmessage=e=>{const m=JSON.parse(e.data);if(m.method==='Runtime.exceptionThrown')runtimeErrors.push(m.params);if(m.method==='Runtime.consoleAPICalled'&&m.params.type==='error')consoleErrors.push(m.params);if(m.method==='Network.loadingFailed'&&!m.params.canceled)networkFailures.push(m.params);if(pending.has(m.id)){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m.result);}};
  await send('Page.enable');await send('Runtime.enable');await send('Network.enable');await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1100,deviceScaleFactor:1,mobile:false});await send('Page.navigate',{url});
  const defaultIndex=Math.max(0,cases.findIndex(c=>c.case_id==='P2_low_disagreement')),defaultItem=cases[defaultIndex],defaultNeighbor=initialNeighbor(defaultItem,'prior_da3');
  await ready({caseId:defaultItem.case_id,neighbor:defaultNeighbor,pair:'prior_da3',step:1});check(await evaluate('location.href')===url,'Browser remains on explicit immutable packet URL');
  check(await evaluate("document.querySelector('#case-select').value")===String(defaultIndex),'Declared initial case and first supported neighbor selected without score ranking',{caseId:defaultItem.case_id,neighbor:defaultNeighbor});
  await imagesReady();await capture('desktop_initial.png');
  check(await evaluate("document.querySelectorAll('#case-select option').length")===cases.length,'All actual cases selectable');
  for(let ci=0;ci<cases.length;ci++){
    const item=cases[ci];await choose('case-select',ci);await ready({caseId:item.case_id});
    for(const pair of ['prior_da3','prior_mvs']){await choose('pair-select',pair);
      for(let ni=0;ni<item.neighbors.length;ni++){await choose('neighbor-select',ni);
        for(let step=1;step<=6;step++){await evaluate(`document.querySelector('[data-step="${step}"]').click()`);await checkStage(item,pair,ni,step);}
        await evaluate(`document.querySelector('[data-view="${ni}"]').click()`);await ready({caseId:item.case_id,pair,neighbor:ni,step:3});check(await evaluate("document.querySelector('#neighbor-select').value")===String(ni),'Score-table patch button selects matching neighbor',{case_id:item.case_id,pair,neighbor:ni});
      }
    }
  }
  // Deterministic screenshot coverage: every case's exact patches and scores;
  // declared default case also documents position, warp, masks and normalization.
  for(let ci=0;ci<cases.length;ci++){
    await choose('case-select',ci);await ready({caseId:cases[ci].case_id});await choose('pair-select','prior_da3');const ni=Math.max(0,cases[ci].neighbors.findIndex(n=>Number(n.comparisons.prior_da3.common_count)>=2));await choose('neighbor-select',ni);
    for(const step of ci===defaultIndex?[1,2,3,4,5,6]:[3,6]){await evaluate(`document.querySelector('[data-step="${step}"]').click()`);await checkStage(cases[ci],'prior_da3',ni,step);await evaluate("document.querySelector('#step-body').scrollIntoView({block:'start'})");await capture('desktop_'+cases[ci].case_id+'_step'+step+'.png');}
  }
  await choose('case-select',0);await ready({caseId:cases[0].case_id});await evaluate("document.querySelector('[data-step=\"3\"]').click()");await imagesReady();
  const dialogSource=await evaluate("document.querySelector('[data-image]').dataset.image");await evaluate("document.querySelector('[data-image]').click()");
  for(let i=0;i<100;i++){if(await evaluate("document.querySelector('#zoom').open&&document.querySelector('#zoom-image').complete&&document.querySelector('#zoom-image').naturalWidth>0"))break;await pause(50);}
  check(await evaluate("document.querySelector('#zoom').open&&document.querySelector('#zoom-image').getAttribute('src')")===dialogSource,'Image dialog opens exact selected PNG');
  const dialogGeometry=await evaluate("(()=>{const e=document.querySelector('#zoom-image'),r=e.getBoundingClientRect();return {naturalWidth:e.naturalWidth,naturalHeight:e.naturalHeight,width:r.width,height:r.height}})()");
  check(Math.min(dialogGeometry.width,dialogGeometry.height)>=200,'Exact small patch is enlarged to a readable modal size',dialogGeometry);
  await capture('desktop_image_dialog.png');await evaluate("document.querySelector('#close-zoom').click()");check(await evaluate("document.querySelector('#zoom').open")===false,'Image dialog closes');
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
  for(let ci=0;ci<cases.length;ci++){await choose('case-select',ci);await ready({caseId:cases[ci].case_id});await choose('neighbor-select',0);for(const pair of ['prior_da3','prior_mvs']){await choose('pair-select',pair);for(let step=1;step<=6;step++){await evaluate(`document.querySelector('[data-step="${step}"]').click()`);await checkStage(cases[ci],pair,0,step,'mobile');}}}
  await choose('case-select',defaultIndex);await ready({caseId:defaultItem.case_id});await choose('pair-select','prior_da3');await choose('neighbor-select',defaultNeighbor);await evaluate("document.querySelector('[data-step=\"1\"]').click();scrollTo(0,0)");await imagesReady();await capture('mobile_top.png');
  for(const step of [3,6]){await evaluate(`document.querySelector('[data-step="${step}"]').click();document.querySelector('#step-body').scrollIntoView({block:'start'})`);await imagesReady();await capture('mobile_step'+step+'.png');}
  const scrolledTable=await evaluate("(()=>{const e=document.querySelector('#score-table').parentElement;e.scrollLeft=e.scrollWidth;return {left:e.scrollLeft,client:e.clientWidth,scroll:e.scrollWidth}})()");
  check(scrolledTable.left>0&&scrolledTable.scroll>scrolledTable.client,'Mobile score table scrolls horizontally to remaining columns',scrolledTable);await capture('mobile_step6_right.png');
  // Target the user's confusing cases explicitly: unsupported first neighbor,
  // fourth neighbor with available prior projection, and paired-reading limits.
  for(const mode of [{id:'desktop',width:1440,height:1100,mobile:false},{id:'mobile',width:390,height:844,mobile:true}]){
    await send('Emulation.setDeviceMetricsOverride',{width:mode.width,height:mode.height,deviceScaleFactor:1,mobile:mode.mobile});
    for(const [caseId,pair] of [['P2_low_disagreement','prior_da3'],['P2_mvs_hole','prior_mvs']]){const ci=cases.findIndex(c=>c.case_id===caseId);check(ci>=0,'Requested explanation case is actually published',caseId);const item=cases[ci],wanted=initialNeighbor(item,pair);await choose('pair-select',pair);if(await evaluate('window.__walkthrough.caseId')===caseId)await choose('neighbor-select',wanted===0?1:0);await choose('case-select',ci);await ready({caseId,pair,neighbor:wanted});
      check(await evaluate("document.querySelector('#neighbor-select').value")===String(wanted),'Initial neighbor follows support-first then any-projectable fallback',{caseId,pair,mode:mode.id,neighbor:wanted});
      if(caseId==='P2_mvs_hole')check(wanted===3,'P2 MVS hole opens fourth original neighbor with Prior projection',mode.id);
      for(const ni of [0,3]){await choose('neighbor-select',ni);await evaluate("document.querySelector('[data-step=\"2\"]').click()");await checkStage(item,pair,ni,2,mode.id);await evaluate("document.querySelector('#step-body').scrollIntoView({block:'start'})");await capture(mode.id+'_explain_'+caseId+'_neighbor'+(ni+1)+'_step2.png');await evaluate("document.querySelector('#projection-support').scrollIntoView({block:'center'})");await capture(mode.id+'_explain_'+caseId+'_neighbor'+(ni+1)+'_support.png');}
      await evaluate("document.querySelector('[data-step=\"6\"]').click()");await checkStage(item,pair,3,6,mode.id);await evaluate("document.querySelector('#reading-guide').scrollIntoView({block:'center'})");await capture(mode.id+'_explain_'+caseId+'_reading.png');
    }
  }
  for(const [relative,expected] of artifactURLs){const r=await fetch(new URL(relative,url)),b=Buffer.from(await r.arrayBuffer()),actual=hash(b);const detail={relative,status:r.status,bytes:b.length,sha256:actual,expected_sha256:expected};httpFiles.push(detail);check(r.ok&&expected===actual,'Displayed source HTTP bytes match sealed output',detail);}
  check(runtimeErrors.length===0&&consoleErrors.length===0&&networkFailures.length===0,'No browser exceptions, console errors or resource failures',{runtimeErrors,consoleErrors,networkFailures});
  const currentAfter=await fs.readFile(site+'/current.json');receipt.current_pointer_after_sha256=hash(currentAfter);check(hash(currentBefore)===hash(currentAfter),'Browser QA preserved original current viewer pointer');
  receipt.status='PASS_ACTUAL_PHOTOMETRIC_WALKTHROUGH_BROWSER';
}catch(e){receipt.status='FAIL';receipt.error=String(e);process.exitCode=1;if(socket?.readyState===1){try{receipt.failure_page=await evaluate('({url:location.href,state:window.__walkthrough,error:window.__walkthroughError,body:document.body?.innerText})');await capture('failure.png');}catch{}}}
finally{receipt.finished_at=new Date().toISOString();receipt.check_count=checks.length;receipt.state_count=states.length;receipt.unique_http_asset_count=httpFiles.length;await fs.writeFile(out+'/receipt.json',JSON.stringify(receipt,null,2)+'\n',{flag:'wx'});await fs.writeFile(out+'/chromium.log',chromeLog.join(''),{flag:'wx'});socket?.close();browser?.kill('SIGTERM');}
console.log(JSON.stringify({status:receipt.status,checks:checks.length,states:states.length,cases:receipt.case_count,unique_http_assets:httpFiles.length,error:receipt.error,scientific_verdict:null}));
