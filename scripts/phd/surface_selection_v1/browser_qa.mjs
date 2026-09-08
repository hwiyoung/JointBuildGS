// Actual local surface-selection viewer QA. Run only in the dedicated browser image.
// Node built-ins + Chromium CDP; no downloaded browser or project dependencies.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {spawn} from 'node:child_process';

const [url, output = '/out'] = process.argv.slice(2);
if (!url || !['127.0.0.1', 'localhost'].includes(new URL(url).hostname)) throw Error('An actual local viewer URL is required');
await fs.access('/.dockerenv');
await fs.mkdir(output, {recursive: true});
try { await fs.access(path.join(output, 'browser_qa.json')); throw Error('QA output already contains a receipt; use a fresh directory'); }
catch (error) { if (error.code !== 'ENOENT') throw error; }
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const digest = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const checks = [], screenshots = [], events = [], chromeLog = [], pending = new Map();
let browser, virtualDisplay, socket, sequence = 0, currentPhase = 'startup', failureIndex = 0;
const receipt = {
  schema: 'jointbuildgs.surface_selection_viewer.browser_qa.v1', url,
  started_at: new Date().toISOString(), image_id: process.env.SURFACE_VIEWER_QA_IMAGE_ID || null,
  script_sha256: digest(await fs.readFile(new URL(import.meta.url))), scientific_verdict: null,
  scope: 'Browser interaction, actual image decoding and display provenance only; no scientific accuracy or currentness verdict.',
  actual_data_only: true, checks, screenshots, cases: [], transitions: [], responsive: [],
  viewport: {width: 1600, height: 1000, deviceScaleFactor: 1},
  expected_counts: {}, case_membership: {}, skipped: [],
  coverage: {regions: [], stages: [1, 2, 3, 4], responsive_widths: [1600, 1024, 768],
    scope: 'Source surfaces, source graphs, boundary units, native photos, exact patches and directly supported selection scope.'}

};

function check(pass, name, details = null) { checks.push({name, pass: !!pass, phase: currentPhase, details}); return !!pass; }
function requireCheck(pass, name, details = null) { if (!check(pass, name, details)) throw Error(name); }
function send(method, params = {}) {
  const id = ++sequence;
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => { pending.delete(id); reject(Error('CDP timeout: ' + method)); }, 30000);
    pending.set(id, {resolve: result => { clearTimeout(timeout); resolve(result); }, reject: error => { clearTimeout(timeout); reject(error); }});
    socket.send(JSON.stringify({id, method, params}));
  });
}
async function evaluate(expression) {
  const r = await send('Runtime.evaluate', {expression, returnByValue: true, awaitPromise: true});
  if (r.exceptionDetails) throw Error(JSON.stringify(r.exceptionDetails));
  return r.result?.value;
}
async function state() { return evaluate('window.surfaceViewerState ? JSON.parse(JSON.stringify(window.surfaceViewerState)) : null'); }
async function api(route) {
  const response = await fetch(new URL(route, url));
  if (!response.ok) throw Error('Actual API read failed: ' + response.status + ' ' + route);
  return response.json();
}
async function evidence(region, unitId, pairId = null, anchor = null) {
  const query = new URLSearchParams();
  if (pairId !== null) query.set('pair_id', pairId);
  if (anchor !== null) query.set('anchor', anchor);
  const value = await api(`/api/evidence/${region}/${unitId}${query.size?'?'+query:''}`);
  requireCheck(value.region === region && String(value.unit_id) === String(unitId), 'evidence_descriptor_matches_exact_unit', {region, unitId, actual: {region: value.region, unitId: value.unit_id}});
  return value;
}
async function ready(expected = {}, timeoutMs = 60000) {
  const until = Date.now() + timeoutMs;
  let value;
  do {
    value = await state();
    if (value?.error) throw Error('Viewer error: ' + JSON.stringify(value.error));
    if (value?.ready && !value.loading && Object.entries(expected).every(([key, val]) => String(value[key]) === String(val))) {
      await evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))');
      return state();
    }
    await pause(100);
  } while (Date.now() < until);
  throw Error('Viewer readiness timeout: ' + JSON.stringify({expected, actual: value}));
}
async function click(selector) {
  await evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});if(!e||e.disabled)throw Error('Missing/disabled QA control: '+${JSON.stringify(selector)});if(typeof e.click==='function')e.click();else e.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true,view:window}))})()`);
}
async function choose(id, value) {
  await evaluate(`(()=>{const e=document.getElementById(${JSON.stringify(id)});if(!e||e.disabled||![...e.options].some(o=>o.value===${JSON.stringify(String(value))}&&!o.disabled))throw Error('Missing/disabled QA option: '+${JSON.stringify(id + ':' + value)});e.value=${JSON.stringify(String(value))};e.dispatchEvent(new Event('change',{bubbles:true}))})()`);
}
async function control(id) {
  return evaluate(`(()=>{const e=document.getElementById(${JSON.stringify(id)});return e?{value:e.value,disabled:e.disabled,checked:e.checked,options:e.options?[...e.options].map(o=>({value:o.value,text:o.textContent,disabled:o.disabled})):null}:null})()`);
}
async function unit(id, region) {
  await choose('unit-filter', 'all');
  await choose('unit-select', String(id));
  return ready({region, unitId: id});
}
async function rect(selector, scroll = true) {
  return evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});if(!e)throw Error('Element absent: '+${JSON.stringify(selector)});${scroll ? "e.scrollIntoView({block:'center',inline:'nearest'});" : ''}const r=e.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height}})()`);
}
async function pointerClick(selector) {
  await rect(selector);
  await evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))');
  const r = await rect(selector,false), x = r.x+r.width/2, y = r.y+r.height/2;
  const target = await evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(selector)}),top=document.elementFromPoint(${x},${y});return {visible:!!top&&(top===e||e.contains(top)),top:top?.id||top?.tagName,disabled:!!e.disabled}})()`);
  requireCheck(target.visible&&!target.disabled,'pointer_target_is_visible_and_unobstructed',{selector,target});
  await send('Input.dispatchMouseEvent',{type:'mousePressed',x,y,button:'left',buttons:1,clickCount:1});
  await send('Input.dispatchMouseEvent',{type:'mouseReleased',x,y,button:'left',buttons:0,clickCount:1});
}
async function canvasInfo(id) {
  return evaluate(`(()=>{const c=document.getElementById(${JSON.stringify(id)});if(!c)return null;const r=c.getBoundingClientRect();return {id:c.id,width:c.width,height:c.height,cssWidth:r.width,cssHeight:r.height,visible:!!(r.width&&r.height),display:getComputedStyle(c).display}})()`);
}
async function screenshot(name, selector = null) {
  let clip, viewportRect, canvas;
  if (selector) {
    await rect(selector);
    await evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))');
    const r = await rect(selector,false);
    const viewport = await evaluate('({width:innerWidth,height:innerHeight,scrollX,scrollY})');
    const left=Math.max(0,r.x),top=Math.max(0,r.y);
    viewportRect={x:left,y:top,width:Math.min(r.x+r.width,viewport.width)-left,height:Math.min(r.y+r.height,viewport.height)-top};
    // getBoundingClientRect is viewport-relative, but CDP's clip uses document
    // coordinates. Omitting scroll offsets can capture a blank page rectangle.
    clip = {x:left+viewport.scrollX,y:top+viewport.scrollY,width:viewportRect.width,height:viewportRect.height,scale:1};
    if (clip.width < 1 || clip.height < 1) throw Error('Screenshot element is outside viewport');
    const direct=await evaluate(`(()=>{const c=document.querySelector(${JSON.stringify(selector)});return c instanceof HTMLCanvasElement?{data:c.toDataURL('image/png'),width:c.width,height:c.height}:null})()`);
    if(direct){const bytes=Buffer.from(direct.data.split(',')[1],'base64');canvas={sha256:digest(bytes),bytes:bytes.length,width:direct.width,height:direct.height,method:'HTMLCanvasElement.toDataURL(image/png); independent of page scroll/crop'};}
  }
  await evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))');
  const result = await send('Page.captureScreenshot', {format: 'png', captureBeyondViewport: false, ...(clip ? {clip} : {})});
  const bytes = Buffer.from(result.data, 'base64');
  const metadata = {filename: name, sha256: digest(bytes), bytes: bytes.length, phase: currentPhase, ...(selector ? {selector,clip,viewport_rect:viewportRect,canvas} : {})};
  if (name) { await fs.writeFile(path.join(output, name), bytes, {flag: 'wx'}); screenshots.push(metadata); }
  return metadata;
}
async function section(name, fn) {
  currentPhase = name;
  try { await fn(); }
  catch (error) {
    check(false, 'section_completed', {error: String(error)});
    try { await screenshot(`failure_${++failureIndex}_${name.replace(/[^a-z0-9_-]/gi, '_')}.png`); } catch (captureError) { chromeLog.push('Failure screenshot: ' + captureError); }
  }
}
async function setViewport(width, height = 1000) {
  await send('Emulation.setDeviceMetricsOverride', {width, height, deviceScaleFactor: 1, mobile: false});
  await evaluate('window.dispatchEvent(new Event("resize"))');
  await pause(250);
}
async function assertCanvases(ids, minimum, context) {
  for (const id of ids) {
    const info = await canvasInfo(id);
    check(info && info.visible && info.cssWidth >= minimum[0] && info.cssHeight >= minimum[1] && info.width >= Math.floor(info.cssWidth) && info.height >= Math.floor(info.cssHeight), 'canvas_has_useful_native_viewport', {context, minimum, ...info});
  }
}
async function images(context, requirePhotos = true, expected = null) {
  const decoded = await evaluate(`async()=>{const ids=['reference-image','target-image'];const result=[];for(const id of ids){const e=document.getElementById(id);if(e&&e.getAttribute('src')){try{await e.decode()}catch{}result.push({id,src:e.currentSrc||e.src,complete:e.complete,naturalWidth:e.naturalWidth,naturalHeight:e.naturalHeight})}}return result}`.replace('async()=>', '(async()=>') + ')()');
  check(!requirePhotos || decoded.length === 2, 'photo_evidence_present_when_case_has_observations', {context, decoded});
  check(decoded.every(i => i.complete && i.naturalWidth > 0 && i.naturalHeight > 0), 'actual_photo_bytes_decode', {context, decoded});
  if (expected?.available) for (const source of ['reference','target']) {
    const actual=decoded.find(i=>i.id===source+'-image'), declared=expected[source];
    check(actual && actual.naturalWidth===declared.width && actual.naturalHeight===declared.height && actual.naturalWidth===1400 && actual.naturalHeight===1013,
      'decoded_original_dimensions_match_exact_camera_metadata', {context,source,actual,declared:{width:declared.width,height:declared.height,id:declared.id}});
  }
  return decoded;
}
async function drag(selector, button = 'left', dx = 42, dy = 18) {
  const r = await rect(selector);
  const x = r.x + r.width * .45, y = r.y + r.height * .45, buttons = button === 'right' ? 2 : 1;
  await send('Input.dispatchMouseEvent', {type: 'mousePressed', x, y, button, buttons, clickCount: 1});
  for (let step = 1; step <= 5; step++) await send('Input.dispatchMouseEvent', {type: 'mouseMoved', x: x + dx * step / 5, y: y + dy * step / 5, button, buttons});
  await send('Input.dispatchMouseEvent', {type: 'mouseReleased', x: x + dx, y: y + dy, button, buttons: 0, clickCount: 1});
  await pause(100);
}
async function wheel(selector) {
  const r = await rect(selector);
  await send('Input.dispatchMouseEvent', {type: 'mouseWheel', x: r.x + r.width / 2, y: r.y + r.height / 2, deltaX: 0, deltaY: -240});
  await pause(150);
}

function skip(name, reason, details = null) { receipt.skipped.push({name, reason, phase: currentPhase, details}); }
const finite = value => value !== null && value !== undefined && Number.isFinite(Number(value));
const same = (a,b) => String(a)===String(b);
const endpoints=e=>[e.a??e.source_id??e.from??e.i??e.source,e.b??e.target_id??e.to??e.j??e.target];
const caseKey = (region,id) => region+'/'+id;
const data = new Map(), caseData = new Map(), regionCases = new Map(), photoCases = [];
function validPatches(item) {
  const rows = item.observation?.patches || [];
  return rows.filter(p=>Object.values(p.paired_costs || {}).some(finite) || Object.values(p.own_costs || {}).some(finite))
    .sort((a,b)=>Number(Object.values(b.paired_costs || {}).every(finite))-Number(Object.values(a.paired_costs || {}).every(finite)));
}
async function chooseScoredPatch(region,id,patch) {
  await unit(id,region);
  await click('[data-testid="stage-3"]');await ready({region,unitId:id,stage:3});
  await choose('pair-select',patch.pair_id);await ready({region,unitId:id,stage:3,pairId:patch.pair_id});
  await choose('anchor-select',patch.patch_index);
  await ready({region,unitId:id,stage:3,pairId:patch.pair_id,anchorIndex:patch.patch_index});
  return evidence(region,id,patch.pair_id,patch.patch_index);
}
async function canvasSample(id) {
  const value=await evaluate(`(()=>{const c=document.getElementById(${JSON.stringify(id)});if(!c)return null;const b=document.createElement('canvas');b.width=64;b.height=64;const x=b.getContext('2d');x.drawImage(c,0,0,64,64);const p=x.getImageData(0,0,64,64).data,counts=new Map();let low=255,high=0;for(let i=0;i<p.length;i+=4){const k=p[i]+','+p[i+1]+','+p[i+2]+','+p[i+3];counts.set(k,(counts.get(k)||0)+1);for(let j=0;j<3;j++){low=Math.min(low,p[i+j]);high=Math.max(high,p[i+j]);}}return {png:c.toDataURL('image/png'),colors:counts.size,dominantFraction:Math.max(...counts.values())/4096,low,high}})()`);
  if(!value)return null;
  const bytes=Buffer.from(value.png.split(',')[1],'base64');delete value.png;
  return {...value,sha256:digest(bytes),bytes:bytes.length};
}
async function actualCanvas(id, context) {
  const sample=await canvasSample(id);
  check(sample && sample.colors>=8 && sample.dominantFraction<.999 && sample.bytes>200,'canvas_contains_actual_nonuniform_render',{id,context,sample});
  return sample;
}
async function detailRows(id) {
  return evaluate(`(()=>{const e=document.getElementById(${JSON.stringify(id)});return e?[...e.querySelectorAll('.detail-row')].map(r=>({label:r.querySelector('dt')?.textContent,value:r.querySelector('dd')?.textContent})):[]})()`);
}
async function verifyPatchDisplay(expected,context) {
  const p=expected.patch,common=expected.comparison_mode==='COMMON_MASK_COMPARISON';
  const result=await evaluate(`(()=>{const p=${JSON.stringify(p)},common=${JSON.stringify(common)},out={};for(const s of ['reference','mvs','als']){const c=document.getElementById('patch-'+s),pixels=c.getContext('2d').getImageData(0,0,c.width,c.height).data,present=Array.isArray(p[s]),mask=s==='reference'?p.mask:present?(common?p.mask:p.source_masks?.[s]||[]):[];let mismatch=0;for(let i=0;i<p.width*p.width;i++){const val=new Uint8ClampedArray([mask[i]?Math.max(0,Math.min(255,p[s]?.[i]??188)):188])[0];if(pixels[4*i]!==val||pixels[4*i+1]!==val||pixels[4*i+2]!==val||pixels[4*i+3]!==255)mismatch++;}out[s]={mismatch,width:c.width,height:c.height,present,mask_count:mask.filter(Boolean).length};}return {sources:out,mode:window.surfaceViewerState.comparisonMode}})()`);
  check(result.mode===expected.comparison_mode&&Object.values(result.sources).every(s=>s.mismatch===0&&s.width===p.width&&s.height===p.width),
    'displayed_patch_pixels_use_exact_common_or_own_source_masks',{context,expectedMode:expected.comparison_mode,result});
}
function displayedNumber(rows,label) {const value=rows.find(r=>r.label===label)?.value;return value===undefined?null:Number(value.replace(/,/g,'').match(/[-+]?\d*\.?\d+/)?.[0]);}
async function verifyScope(region,id) {
  const item=caseData.get(caseKey(region,id)) || await api(`/api/unit/${region}/${id}`), d=item.decision;
  await click('[data-testid="stage-4"]');await ready({region,unitId:id,stage:4});
  const rows=await detailRows('decision-evidence'), rendered=displayedNumber(rows,'직접 지지해 선택한 면적');
  check(Math.abs(rendered-(d.accepted_scope?.sampled_area_m2 || 0))<=.0051,'selected_area_is_exact_accepted_scope_not_whole_unit',{region,id,rendered,expected:d.accepted_scope?.sampled_area_m2 || 0,whole_unit_area:item.unit.area_m2});
  const record=await evaluate('JSON.parse(document.getElementById("raw-record").textContent)');
  check(JSON.stringify(record.decision.accepted_scope)===JSON.stringify(d.accepted_scope) && record.decision.unknown_tile_count===d.unknown_tile_count,
    'visible_record_preserves_exact_accepted_tiles_and_unknown_scope',{region,id,accepted:d.accepted_scope?.tile_ids?.length || 0,unknown:d.unknown_tile_count});
  check(await evaluate(`document.getElementById('decision-card').dataset.action===${JSON.stringify(d.action)}`),'decision_card_matches_actual_source_action',{region,id,action:d.action});
  const regionData=data.get(region), expected=regionData.units.reduce((s,u)=>s+(u.decision?.accepted_scope?.sampled_area_m2 || 0),0);
  const metric=await evaluate(`(()=>{const ms=[...document.querySelectorAll('#region-stats .metric')];const m=ms.find(m=>m.querySelector('.label')?.textContent==='직접 지지해 선택한 면적');return m?.querySelector('strong')?.textContent})()`);
  check(metric!==null && Math.abs(Number(String(metric).replace(/,/g,''))-expected)<=.051,'region_coverage_sums_only_directly_selected_scope',{region,rendered:metric,expected});
}
async function visibleGraphTarget(host, attribute) {
  return evaluate(`(()=>{const host=document.querySelector(${JSON.stringify(host)});host.scrollIntoView({block:'center'});for(const g of host.querySelectorAll(${JSON.stringify('['+attribute+']')})){const e=g.querySelector('circle')||g.querySelector('rect')||g,r=e.getBoundingClientRect(),x=r.x+r.width/2,y=r.y+r.height/2,t=document.elementFromPoint(x,y);if(r.width>0&&r.height>0&&y>0&&y<innerHeight&&x>0&&x<innerWidth&&(t===e||g.contains(t)))return {id:g.getAttribute(${JSON.stringify(attribute)}),source:g.dataset.source,tag:e.tagName};}return null})()`);
}

try {
  const profile = await fs.mkdtemp('/tmp/surface-selection-browser-');
  virtualDisplay = spawn('/usr/bin/Xvfb', ['-displayfd', '1', '-screen', '0', '1600x1200x24', '-nolisten', 'tcp']);
  virtualDisplay.stderr.on('data', bytes => chromeLog.push('Xvfb: ' + bytes));
  const display = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(Error('Xvfb startup timeout')), 10000);
    virtualDisplay.stdout.once('data', bytes => { clearTimeout(timer); const value = bytes.toString().trim(); /^\d+$/.test(value) ? resolve(value) : reject(Error('Invalid Xvfb display')); });
    virtualDisplay.once('error', reject);
  });
  for (const suffix of ['config', 'cache', 'data']) await fs.mkdir(path.join(profile, suffix));
  const args = ['--headless=new', '--no-sandbox', '--no-first-run', '--no-default-browser-check', '--enable-automation', '--disable-dev-shm-usage', '--ozone-platform=headless', '--use-gl=angle', '--use-angle=gl', '--ignore-gpu-blocklist', '--disable-vulkan', '--remote-debugging-address=127.0.0.1', '--remote-debugging-port=0', '--user-data-dir=' + profile, 'about:blank'];
  browser = spawn(process.env.CHROME_BIN || '/usr/bin/chromium', args, {env: {...process.env, DISPLAY: ':' + display, LIBGL_ALWAYS_SOFTWARE: '1', XDG_CONFIG_HOME: profile + '/config', XDG_CACHE_HOME: profile + '/cache', XDG_DATA_HOME: profile + '/data'}});
  browser.stderr.on('data', bytes => chromeLog.push(bytes.toString()));
  receipt.chrome_args = args; receipt.dedicated_xvfb_display = display;
  receipt.software_webgl = 'Dedicated Docker Xvfb + ANGLE GL with LIBGL_ALWAYS_SOFTWARE=1';
  let port;
  for (let i = 0; i < 150; i++) { try { port = (await fs.readFile(path.join(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0]; break; } catch { await pause(100); } }
  if (!port) throw Error('Dedicated Chromium startup failed');
  const pages = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  const page = pages.find(p => p.type === 'page');
  if (!page) throw Error('Dedicated Chromium page absent');
  socket = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { socket.addEventListener('open', resolve, {once: true}); socket.addEventListener('error', reject, {once: true}); });
  socket.addEventListener('message', event => {
    const message = JSON.parse(event.data);
    if (message.id) { const p = pending.get(message.id); if (p) { pending.delete(message.id); message.error ? p.reject(Error(JSON.stringify(message.error))) : p.resolve(message.result); } }
    else if (['Runtime.exceptionThrown', 'Runtime.consoleAPICalled', 'Network.responseReceived', 'Network.loadingFailed'].includes(message.method)) events.push({...message, qa_phase: currentPhase});
  });
  receipt.browser = await send('Browser.getVersion');
  await send('Page.enable'); await send('Runtime.enable'); await send('Network.enable');
  await send('Network.setCacheDisabled', {cacheDisabled: true});
  await send('Page.addScriptToEvaluateOnNewDocument', {source: `window.__sourceQABrowserErrors=[];addEventListener('unhandledrejection',e=>window.__sourceQABrowserErrors.push({type:'unhandledrejection',message:String(e.reason)}));addEventListener('error',e=>window.__sourceQABrowserErrors.push({type:'error',message:e.message}));`});
  await setViewport(1600);
  await send('Page.navigate', {url});
  receipt.initial_state = await ready();

  const manifest=await api('/api/manifest');
  receipt.manifest={task_id:manifest.task_id,method_seal_sha256:manifest.method_seal_sha256,verified_image_count:manifest.verified_image_count};
  receipt.coverage.regions=manifest.regions.map(r=>r.id);
  requireCheck(['P1','P2','P3'].every(id=>receipt.coverage.regions.includes(id)),'all_requested_actual_regions_available',receipt.coverage.regions);
  for(const regionInfo of manifest.regions){
    const region=regionInfo.id,regionData=await api(`/api/region/${region}`);data.set(region,regionData);
    const us=regionData.units,cases=new Map(),add=(u,reason)=>{if(u){const id=u.id;cases.set(id,{id,reasons:[...(cases.get(id)?.reasons || []),reason]});}};
    const largest=predicate=>us.filter(predicate).sort((a,b)=>b.area_m2-a.area_m2||a.id-b.id)[0];
    add(us.find(u=>same(u.id,regionInfo.default_unit_id)),'manifest_default');
    for(const action of ['IMAGE','PRIOR'])add(us.find(u=>u.decision.action===action),'first_'+action);
    add(largest(u=>u.ambiguous),'largest_ambiguous');
    add(largest(u=>u.status==='NO_SEGMENTED_SUPPORT'),'largest_no_segmented_support');
    add(largest(u=>u.decision.action==='ABSTAIN'),'largest_abstain');
    add(largest(u=>u.status==='PAIRED'),'largest_paired');
    add(largest(u=>u.status==='SINGLE_SOURCE'),'largest_single_source');
    for(const item of cases.values())caseData.set(caseKey(region,item.id),await api(`/api/unit/${region}/${item.id}`));
    // If the source-frozen default has no finite patch, inspect a bounded set of
    // large units. Absence is retained rather than substituting synthetic data.
    if(![...cases.values()].some(c=>validPatches(caseData.get(caseKey(region,c.id))).length)){
      for(const u of [...us].filter(u=>!u.ambiguous&&u.status!=='NO_SEGMENTED_SUPPORT').sort((a,b)=>b.area_m2-a.area_m2).slice(0,20)){
        if(!caseData.has(caseKey(region,u.id)))caseData.set(caseKey(region,u.id),await api(`/api/unit/${region}/${u.id}`));
        if(validPatches(caseData.get(caseKey(region,u.id))).length){add(u,'first_finite_patch_in_bounded_large_unit_scan');break;}
      }
    }
    const selected=[...cases.values()];regionCases.set(region,selected);receipt.case_membership[region]=selected;
    const counts=Object.fromEntries(['IMAGE','PRIOR','ABSTAIN'].map(a=>[a,us.filter(u=>u.decision.action===a).length]));
    receipt.expected_counts[region]={total:us.length,actions:counts,components:Object.fromEntries(['mvs','als'].map(s=>[s,regionData.components[s].length])),
      selected_area_m2:us.reduce((sum,u)=>sum+(u.decision.accepted_scope?.sampled_area_m2 || 0),0)};
    for(const c of selected){const item=caseData.get(caseKey(region,c.id)),patches=validPatches(item);if(patches.length)photoCases.push({region,id:c.id,patches,item});}
  }

  await section('rapid_region_transitions',async()=>{
    await send('Network.emulateNetworkConditions',{offline:false,latency:120,downloadThroughput:-1,uploadThroughput:-1});
    await evaluate(`['P2','P3','P1','P2','P3'].forEach(id=>document.querySelector('[data-testid="region-'+id+'"]').click())`);
    const first=await ready({region:'P3'});await pause(1800);const final=await ready({region:'P3'});
    check(first.region==='P3'&&final.region==='P3'&&same(final.unitId,manifest.regions.find(r=>r.id==='P3').default_unit_id)&&!final.error,
      'latest_region_and_default_unit_survive_outstanding_requests',{first,final});
    receipt.transitions.push({sequence:['P2','P3','P1','P2','P3'],first,final});
    await send('Network.emulateNetworkConditions',{offline:false,latency:0,downloadThroughput:-1,uploadThroughput:-1});
  });

  for(const regionInfo of manifest.regions){const region=regionInfo.id;
    await section(region+'_four_stage_matrix',async()=>{
      await click(`[data-testid="region-${region}"]`);await ready({region});await unit(regionInfo.default_unit_id,region);
      for(const stage of [1,2,3,4]){
        await click(`[data-testid="stage-${stage}"]`);const current=await ready({region,stage,unitId:regionInfo.default_unit_id});
        const visible=await evaluate(`(()=>{const p=document.getElementById('stage-${stage}'),b=document.querySelector('[data-testid="stage-${stage}"]');return {panel:!p.hidden,selected:b.getAttribute('aria-selected')}})()`);
        check(visible.panel&&visible.selected==='true'&&current.totalUnits===data.get(region).units.length,'visible_stage_and_region_census_match_api',{region,stage,visible,actualTotal:current.totalUnits,expected:data.get(region).units.length});
        if(stage===1){
          await assertCanvases(['cloud-canvas'],[400,300],{region,stage});await actualCanvas('cloud-canvas',{region,stage});check(current.scene.renderedPoints>0,'native_points_are_actually_rendered',{region,scene:current.scene});
          await choose('unit-filter','observed');const actual=await control('unit-select');
          const expected=data.get(region).units.filter(u=>u.observation?.status==='SCORED').length;
          check(actual.options.length===expected&&actual.disabled===(expected===0),'observed_filter_includes_independent_and_common_scored_units',{region,actual:actual.options.length,disabled:actual.disabled,expected});
          await choose('unit-filter','all');
        }
        if(stage===2){
          for(const source of ['mvs','als']){
            const graph=await evaluate(`(()=>{const g=document.getElementById('${source}-graph');return {nodes:g.querySelectorAll('[data-component-id]').length,edges:g.querySelectorAll('line').length,svg:!!g.querySelector('svg')}})()`);
            const rd=data.get(region),ids=new Set(rd.components[source].map(c=>String(c.id))),expectedEdges=rd.graphs[source].edges.filter(e=>endpoints(e).every(id=>ids.has(String(id)))).length;
            check(graph.svg&&graph.nodes===rd.components[source].length&&graph.edges===expectedEdges,'source_graph_contains_actual_components_and_adjacencies',{region,source,graph,expected:{nodes:ids.size,edges:expectedEdges}});
          }
          const units=await evaluate('document.querySelectorAll("#unit-graph [data-unit-id]").length');
          check(units===data.get(region).units.length,'boundary_unit_graph_retains_full_partition',{region,rendered:units,expected:data.get(region).units.length});
        }
        if(stage===3){const expected=await evidence(region,current.unitId);await images({region,stage},expected.available,expected);if(expected.available){await assertCanvases(['reference-canvas','target-canvas'],[350,250],{region,stage});await actualCanvas('reference-canvas',{region,stage});}}
        if(stage===4)await verifyScope(region,current.unitId);
        await evaluate('window.scrollTo(0,0)');await screenshot(`${region}_stage${stage}_1600x1000.png`);
      }
    });
    await section(region+'_representative_units',async()=>{
      await click(`[data-testid="region-${region}"]`);await ready({region});
      for(const c of regionCases.get(region)){
        await unit(c.id,region);await click('[data-testid="stage-3"]');const current=await ready({region,stage:3,unitId:c.id});
        const item=caseData.get(caseKey(region,c.id)),patches=validPatches(item),expected=await evidence(region,c.id);
        const decoded=await images({region,unitId:c.id,reasons:c.reasons},expected.available,expected);
        if(!patches.length){
          const absent=await evaluate('({visible:!document.getElementById("evidence-unavailable").hidden,text:document.getElementById("evidence-unavailable").textContent,patchHidden:document.getElementById("patch-panel").hidden})');
          check(!expected.available&&decoded.length===0&&absent.visible&&absent.patchHidden&&absent.text.length>10,'no_eligible_score_has_explicit_absence_and_no_stale_photos',{region,id:c.id,available:expected.available,absent,decoded});
        }else{
          const exact=await chooseScoredPatch(region,c.id,patches[0]);await images({region,unitId:c.id,scoredPatch:true},true,exact);
          check(exact.available&&Object.values(exact.patch?.costs || exact.costs || {}).some(finite),'finite_saved_measurement_is_displayed',{region,id:c.id,pair:patches[0].pair_id,anchor:patches[0].patch_index});
          await verifyPatchDisplay(exact,{region,id:c.id,pair:patches[0].pair_id,anchor:patches[0].patch_index});
        }
        receipt.cases.push({region,id:c.id,reasons:c.reasons,action:item.decision.action,finite_patch_count:patches.length,state:current,evidence_available:expected.available});
        await evaluate('window.scrollTo(0,0)');await screenshot(`${region}_unit${c.id}_observation.png`);
        await verifyScope(region,c.id);
      }
    });
  }

  await section('source_graph_and_boundary_unit_interaction',async()=>{
    const region=manifest.regions.find(r=>data.get(r.id).components.mvs.length>1&&data.get(r.id).components.als.length>1)?.id || manifest.regions[0].id;
    await click(`[data-testid="region-${region}"]`);await ready({region});await click('[data-testid="stage-2"]');await ready({region,stage:2});
    for(const source of ['mvs','als']){
      const target=await visibleGraphTarget('#'+source+'-graph','data-component-id');
      if(!target){skip(source+'_graph_pointer','No unobstructed graph node exists in actual data',{region});continue;}
      await pointerClick(`#${source}-graph [data-component-id="${target.id}"] circle`);
      const current=await state();
      check(current.componentSource===source&&same(current.componentId,target.id),'graph_pointer_selects_actual_source_component',{region,source,target,state:current});
      const raw=await evaluate('JSON.parse(document.getElementById("raw-graph").textContent)');
      check(raw.selected.source===source&&same(raw.selected.id,target.id)&&raw.edges.every(e=>endpoints(e).some(id=>same(id,target.id))),
        'selected_graph_details_reference_clicked_component',{region,source,target,edgeCount:raw.edges.length});
    }
    const target=await visibleGraphTarget('#unit-graph','data-unit-id');
    requireCheck(!!target,'boundary_unit_graph_has_clickable_actual_tile',{region,target});
    await pointerClick(`#unit-graph [data-unit-id="${target.id}"] rect`);await ready({region,unitId:target.id,stage:2});
    check(same((await state()).unitId,target.id),'boundary_tile_pointer_selects_exact_unit',{region,target});
    for(const host of ['mvs-graph','unit-graph']){
      const before=await evaluate(`document.querySelector('#${host} svg').getAttribute('viewBox')`);
      await wheel('#'+host);const zoomed=await evaluate(`document.querySelector('#${host} svg').getAttribute('viewBox')`);
      await drag('#'+host);const panned=await evaluate(`document.querySelector('#${host} svg').getAttribute('viewBox')`);
      check(before!==zoomed&&zoomed!==panned,'graph_wheel_and_drag_change_actual_viewbox',{host,before,zoomed,panned});
    }
    await screenshot('source_graphs_and_boundary_unit.png');
  });

  await section('native_cloud_and_component_filters',async()=>{
    const region=manifest.regions[0].id;
    await click(`[data-testid="region-${region}"]`);await ready({region});await click('[data-testid="stage-1"]');await ready({region,stage:1});
    for(const action of ['IMAGE','PRIOR','ABSTAIN']){
      await choose('unit-filter',action);const filtered=await control('unit-select');
      check(filtered.options.length===receipt.expected_counts[region].actions[action],'unit_filter_matches_frozen_source_count',{region,action,actual:filtered.options.length,expected:receipt.expected_counts[region].actions[action]});
    }
    await choose('unit-filter','all');await choose('view-scope','region');await click('#cloud-reset');
    const both=await actualCanvas('cloud-canvas',{region,scope:'region'}),allState=await state();
    await click('#source-mvs');const alsOnly=await canvasSample('cloud-canvas'),alsState=await state();
    check(both.sha256!==alsOnly.sha256&&alsState.scene.renderedPoints<allState.scene.renderedPoints&&!alsState.scene.visibility.mvs,'source_visibility_changes_native_rendered_points',{both,alsOnly,before:allState.scene,after:alsState.scene});
    await click('#source-mvs');await click('[data-view="top"]');const top=await canvasSample('cloud-canvas');
    check(top.sha256!==both.sha256&&(await state()).scene.view==='top','top_view_changes_native_point_projection',{both,top});
    await click('#cloud-reset');const fitted=await canvasSample('cloud-canvas');await wheel('#cloud-canvas');const zoomed=await canvasSample('cloud-canvas');
    check(fitted.sha256!==zoomed.sha256&&(await state()).scene.zoom>1,'cloud_wheel_changes_projection',{fitted,zoomed});
    await drag('#cloud-canvas','right');const panned=await canvasSample('cloud-canvas');check(panned.sha256!==zoomed.sha256,'cloud_pointer_pan_changes_render',{zoomed,panned});
    await click('#cloud-reset');const reset=await canvasSample('cloud-canvas');check(reset.sha256===fitted.sha256,'cloud_reset_restores_native_projection',{fitted,reset});
    const component=[...data.get(region).components.mvs].sort((a,b)=>(b.native_count??b.count??0)-(a.native_count??a.count??0))[0];
    if(component){
      await choose('component-source','mvs');await choose('component-select',component.id);await choose('view-scope','component');
      const selected=await actualCanvas('cloud-canvas',{region,component:component.id}),current=await state();
      check(same(current.componentId,component.id)&&current.componentSource==='mvs'&&current.scene.renderedPoints>0&&current.scene.renderedPoints<allState.scene.renderedPoints,
        'component_selector_filters_to_actual_native_membership',{region,component:component.id,state:current.scene,selected});
    }else skip('component_filter','No source component in actual region',{region});
    await choose('view-scope','region');await choose('point-color','source');const sourceColors=await canvasSample('cloud-canvas');
    await choose('point-color','component');const componentColors=await canvasSample('cloud-canvas');
    check(sourceColors.sha256!==componentColors.sha256,'source_and_surface_colors_change_actual_native_display',{sourceColors,componentColors});
    const withResidual=(await state()).scene.renderedPoints;await click('#show-residual');const withoutResidual=(await state()).scene.renderedPoints;
    check(withoutResidual<=withResidual,'residual_filter_preserves_only_segmented_native_rows',{withResidual,withoutResidual});
    await click('#show-residual');await screenshot('native_surface_cloud_controls.png','#cloud-canvas');
  });

  await section('original_photo_pair_patch_and_modal_controls',async()=>{
    const chosen=photoCases.find(c=>new Set(c.patches.map(p=>p.pair_id)).size>=2)||photoCases[0];
    requireCheck(!!chosen,'actual_data_contains_a_finite_photo_case',{photoCaseCount:photoCases.length});
    const {region,id,patches}=chosen;await click(`[data-testid="region-${region}"]`);await ready({region});
    let expected=await chooseScoredPatch(region,id,patches[0]);const originalPatch=patches[0];
    const beforeImages=await images({region,id,point:'first_pair'},true,expected);
    const alternate=patches.find(p=>p.pair_id!==originalPatch.pair_id);
    if(alternate){
      expected=await chooseScoredPatch(region,id,alternate);const afterImages=await images({region,id,point:'alternate_pair'},true,expected);
      check(JSON.stringify(beforeImages.map(i=>i.src))!==JSON.stringify(afterImages.map(i=>i.src)),'camera_pair_switch_changes_decoded_original_membership',{region,id,beforeImages,afterImages});
    }else skip('pair_switch','Only one finite saved pair in actual data',{region,id});
    expected=await chooseScoredPatch(region,id,originalPatch);const before=await canvasSample('patch-reference');
    const candidates=patches.filter(p=>p.pair_id===originalPatch.pair_id&&p.patch_index!==originalPatch.patch_index).slice(0,10);
    let different;
    for(const patch of candidates){const next=await evidence(region,id,patch.pair_id,patch.patch_index);if(JSON.stringify(next.patch?.reference || next.patches?.reference)!==JSON.stringify(expected.patch?.reference || expected.patches?.reference)){different=patch;break;}}
    if(different){await chooseScoredPatch(region,id,different);const after=await canvasSample('patch-reference');
      check(after.sha256!==before.sha256,'patch_selector_changes_actual_scored_reference_pixels',{region,id,before,after,original:originalPatch.patch_index,alternate:different.patch_index});
    }else skip('patch_switch','No alternate finite patch with distinct actual reference pixels',{region,id,scanned:candidates.length});
    expected=await chooseScoredPatch(region,id,originalPatch);
    for(const layer of ['accepted','independent','preference']){
      await choose('support-layer',layer);const shown=await evaluate('({rects:document.querySelectorAll("#support-map rect").length,circles:document.querySelectorAll("#support-map circle").length})');
      const item=chosen.item,o=item.observation,base=item.unit.footprint_xy.length;
      let overlay=0;
      if(layer==='accepted')overlay=item.decision.accepted_scope?.footprint_xy?.length || 0;
      if(layer==='independent')overlay=new Set([...(o.spatial?.directly_supported_tile_ids?.mvs||[]),...(o.spatial?.directly_supported_tile_ids?.als||[])]).size;
      if(layer==='preference')overlay=Object.values(o.spatial?.source_preference_tiles||{}).reduce((sum,rows)=>sum+rows.length,0);
      check(shown.rects===base+overlay&&shown.circles===(o.anchors?.length||0),'support_layer_displays_exact_sampled_positions',{region,id,layer,shown,expected:{rects:base+overlay,circles:o.anchors?.length||0}});
    }
    await choose('support-layer','accepted');
    await click('[data-photo="reference"][data-photo-action="fit"]');const fitted=await canvasSample('reference-canvas');
    await wheel('#reference-canvas');const zoomed=await canvasSample('reference-canvas');check(fitted.sha256!==zoomed.sha256,'photo_wheel_changes_actual_photo_zoom',{fitted,zoomed});
    await drag('#reference-canvas');const panned=await canvasSample('reference-canvas');check(panned.sha256!==zoomed.sha256,'photo_drag_changes_actual_photo_pan',{zoomed,panned});
    await click('[data-photo="reference"][data-photo-action="fit"]');const reset=await canvasSample('reference-canvas');check(reset.sha256===fitted.sha256,'photo_fit_restores_same_original_view',{fitted,reset});
    for(const action of ['actual','focus']){await click(`[data-photo="reference"][data-photo-action="${action}"]`);await actualCanvas('reference-canvas',{region,id,action});}
    await pointerClick('[data-photo="reference"][data-photo-action="full"]');await pause(150);
    const modal=await evaluate(`(async()=>{const d=document.getElementById('lightbox'),i=document.getElementById('lightbox-image');if(i.getAttribute('src'))await i.decode();return {open:d.open,src:i.currentSrc,width:i.naturalWidth,height:i.naturalHeight}})()`);
    check(modal.open&&modal.width===expected.reference.width&&modal.height===expected.reference.height,'expanded_modal_decodes_same_exact_original',{modal,expected:{width:expected.reference.width,height:expected.reference.height}});
    await assertCanvases(['lightbox-canvas'],[1000,600],{region,id});await actualCanvas('lightbox-canvas',{region,id});await screenshot('original_photo_expanded.png','#lightbox-canvas');
    await pointerClick('#lightbox-close');check(await evaluate('!document.getElementById("lightbox").open'),'expanded_photo_closes_through_visible_control');
  });

  for(const width of [1024,768])await section('responsive_'+width,async()=>{
    await setViewport(width);const chosen=photoCases[0]||{region:manifest.regions[0].id,id:manifest.regions[0].default_unit_id};
    await click(`[data-testid="region-${chosen.region}"]`);await ready({region:chosen.region});await unit(chosen.id,chosen.region);
    for(const stage of [1,2,3,4]){
      await click(`[data-testid="stage-${stage}"]`);await ready({region:chosen.region,unitId:chosen.id,stage});
      const layout=await evaluate('({width:innerWidth,documentWidth:document.documentElement.scrollWidth,bodyWidth:document.body.scrollWidth})');
      check(layout.documentWidth<=width+2&&layout.bodyWidth<=width+2,'responsive_stage_has_no_horizontal_overflow',{width,stage,layout});
      if(stage===1)await assertCanvases(['cloud-canvas'],[240,200],{width,stage});
      if(stage===3){const expected=await evidence(chosen.region,chosen.id);await images({width,stage},expected.available,expected);if(expected.available)await assertCanvases(['reference-canvas','target-canvas'],[240,200],{width,stage});}
      await evaluate('window.scrollTo(0,0)');await screenshot(`${chosen.region}_stage${stage}_${width}x1000.png`);receipt.responsive.push({width,stage,layout});
    }
  });
  await setViewport(1600);currentPhase='final_browser_audit';await pause(300);
  const exceptions=events.filter(e=>e.method==='Runtime.exceptionThrown');
  const consoleErrors=events.filter(e=>e.method==='Runtime.consoleAPICalled'&&e.params.type==='error');
  const httpErrors=events.filter(e=>e.method==='Network.responseReceived'&&e.params.response.status>=400);
  const loadingFailures=events.filter(e=>e.method==='Network.loadingFailed');
  const expectedAborts=loadingFailures.filter(e=>e.params.canceled&&e.params.errorText==='net::ERR_ABORTED'&&e.qa_phase==='rapid_region_transitions');
  const unexpectedFailures=loadingFailures.filter(e=>!expectedAborts.includes(e));
  const browserErrors=await evaluate('window.__sourceQABrowserErrors||[]');
  receipt.network={http_errors:httpErrors,loading_failures:loadingFailures,expected_transition_cancellations:expectedAborts,unexpected_failures:unexpectedFailures};
  receipt.console_errors=consoleErrors;receipt.runtime_exceptions=exceptions;receipt.browser_errors=browserErrors;
  check(httpErrors.length===0,'no_HTTP_errors_in_actual_viewer',httpErrors);
  check(exceptions.length===0&&consoleErrors.length===0&&browserErrors.length===0,'no_console_or_unhandled_browser_errors',{exceptions,consoleErrors,browserErrors});
  check(unexpectedFailures.length===0,'no_unexpected_network_failures',unexpectedFailures);
  check(screenshots.filter(s=>/^P[123]_stage[1234]_1600x1000\.png$/.test(s.filename)).length===12,'complete_three_region_four_stage_screenshot_matrix');
  receipt.final_state=await state();
  receipt.status=checks.every(c=>c.pass)?'PASS_ACTUAL_SURFACE_VIEWER_DISPLAY_AND_CONTROLS':'FAIL';
  if(receipt.status==='FAIL')process.exitCode=1;
}catch(error){receipt.status='FAIL';receipt.error=String(error);process.exitCode=1;}
finally{
  receipt.completed_at=new Date().toISOString();receipt.check_count=checks.length;receipt.failed_checks=checks.filter(c=>!c.pass);
  await fs.writeFile(path.join(output,'browser_qa.json'),JSON.stringify(receipt,null,2),{flag:'wx'});
  await fs.writeFile(path.join(output,'chrome.log'),chromeLog.join(''),{flag:'wx'});
  await fs.writeFile(path.join(output,'browser_events.json'),JSON.stringify(events,null,2),{flag:'wx'});
  if(socket)socket.close();if(browser)browser.kill('SIGTERM');if(virtualDisplay)virtualDisplay.kill('SIGTERM');
  process.stdout.write(JSON.stringify({status:receipt.status,checks:checks.length,failed_checks:receipt.failed_checks.length,screenshots:screenshots.length,receipt:path.join(output,'browser_qa.json')})+'\n');
}
