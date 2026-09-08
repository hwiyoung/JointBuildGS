// Actual local source-candidate viewer QA. Run only in the dedicated browser image.
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
  schema: 'jointbuildgs.source_candidate_viewer.browser_qa.v1', url,
  started_at: new Date().toISOString(), image_id: process.env.SOURCE_VIEWER_QA_IMAGE_ID || null,
  script_sha256: digest(await fs.readFile(new URL(import.meta.url))), scientific_verdict: null,
  scope: 'Browser interaction, actual image decoding and display provenance only; no scientific accuracy or currentness verdict.',
  actual_data_only: true, checks, screenshots, cases: [], transitions: [], responsive: [],
  viewport: {width: 1600, height: 1000, deviceScaleFactor: 1},
  expected_counts: {P1: {total: 225, accepted: 0}, P2: {total: 552, accepted: 41}, P3: {total: 540, accepted: 1}},
  case_membership: {P1: [16, 0], P2: [5, 120, 195], P3: [43, 498]},
  coverage: {regions: ['P1', 'P2', 'P3'], stages: [1, 2, 3], responsive_widths: [1024, 768],
    photo_geometry: 'Decoded native image dimensions and nonblank photo/patch canvases; finite selected evidence or explicit absence.',
    asynchronous: 'Rapid real UI region transitions with network cache disabled and artificial 120ms network latency; final state must remain stable.',
    canvas_minimums: {desktop_cloud: [400, 300], desktop_photo: [350, 250], responsive_canvas: [240, 200]}}
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
async function state() { return evaluate('window.sourceViewerState ? JSON.parse(JSON.stringify(window.sourceViewerState)) : null'); }
async function evidence(region, cellId) {
  const response = await fetch(new URL(`/api/evidence/${region}/${cellId}`, url));
  if (!response.ok) throw Error('Actual evidence descriptor request failed: ' + response.status);
  const value = await response.json();
  requireCheck(value.region === region && value.cell_id === cellId, 'evidence_descriptor_matches_exact_cell', {region, cellId, actual: {region: value.region, cellId: value.cell_id}});
  return value;
}
async function ready(expected = {}, timeoutMs = 60000) {
  const until = Date.now() + timeoutMs;
  let value;
  do {
    value = await state();
    if (value?.error) throw Error('Viewer error: ' + JSON.stringify(value.error));
    if (value?.ready && !value.loading && Object.entries(expected).every(([key, val]) => value[key] === val)) {
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
async function cell(id, region) {
  await choose('cell-filter', 'all');
  await evaluate(`(()=>{const e=document.getElementById('cell-search');e.value=${JSON.stringify(String(id))};e.dispatchEvent(new Event('input',{bubbles:true}));document.getElementById('cell-jump').click()})()`);
  return ready({region, cellId: id});
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
async function images(context, requirePhotos = true) {
  const decoded = await evaluate(`async()=>{const ids=['reference-image','target-image'];const result=[];for(const id of ids){const e=document.getElementById(id);if(e&&e.getAttribute('src')){try{await e.decode()}catch{}result.push({id,src:e.currentSrc||e.src,complete:e.complete,naturalWidth:e.naturalWidth,naturalHeight:e.naturalHeight})}}return result}`.replace('async()=>', '(async()=>') + ')()');
  check(!requirePhotos || decoded.length === 2, 'photo_evidence_present_when_case_has_observations', {context, decoded});
  check(decoded.every(i => i.complete && i.naturalWidth > 0 && i.naturalHeight > 0), 'actual_photo_bytes_decode', {context, decoded});
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

try {
  const profile = await fs.mkdtemp('/tmp/source-candidate-browser-');
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

  await section('rapid_region_transitions', async () => {
    await send('Network.emulateNetworkConditions', {offline: false, latency: 120, downloadThroughput: -1, uploadThroughput: -1});
    await evaluate(`['P2','P3','P2','P1','P3'].forEach(id=>document.querySelector('[data-testid="region-'+id+'"]').click())`);
    const first = await ready({region: 'P3'});
    await pause(1800);
    const final = await ready({region: 'P3'});
    check(first.region === 'P3' && final.region === 'P3' && !final.loading && !final.error, 'latest_region_wins_after_outstanding_requests_settle', {first, final});
    receipt.transitions.push({sequence: ['P2','P3','P2','P1','P3'], first, final});
    await send('Network.emulateNetworkConditions', {offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1});
  });

  for (const region of ['P1', 'P2', 'P3']) {
    await section(region + '_stage_matrix', async () => {
      await click(`[data-testid="region-${region}"]`); await ready({region});
      await cell(receipt.case_membership[region][0], region);
      for (const stage of [1, 2, 3]) {
        await click(`[data-testid="stage-${stage}"]`);
        const current = await ready({region, stage});
        check(current.region === region && current.stage === stage, 'stage_region_state_matches_visible_control', {region, stage, state: current});
        await evaluate('window.scrollTo(0,0)');
        await screenshot(`${region}_stage${stage}_1600x1000.png`);
        if (stage === 1) await assertCanvases(['cloud-canvas'], [400, 300], {region, stage});
        if (stage === 2) { const expected = await evidence(region,current.cellId); await images({region, stage, expectedAvailable: expected.available},expected.available); await assertCanvases(['reference-canvas','target-canvas'], [350,250], {region, stage}); }
      }
      const current = await state();
      const counts = current.counts || current.summary || {};
      const accepted = current.acceptedCount ?? counts.accepted ?? counts.accepted_cells;
      const total = current.totalCells ?? counts.total ?? counts.total_cells;
      check(accepted === receipt.expected_counts[region].accepted && total === receipt.expected_counts[region].total, 'region_counts_match_sealed_decisions', {region, expected: receipt.expected_counts[region], accepted, total, state: current});
    });
    await section(region + '_recorded_cells', async () => {
      await click(`[data-testid="region-${region}"]`); await ready({region});
      await click('[data-testid="stage-2"]');
      for (const id of receipt.case_membership[region]) {
        const current = await cell(id, region);
        check(current.cellId === id, 'numeric_cell_search_selects_exact_cell', {region, id});
        const expected = await evidence(region,id);
        const decoded = await images({region, cell: id, expectedAvailable: expected.available, reason: expected.reason},expected.available);
        const selectors = {pair: await control('pair-select'), anchor: await control('anchor-select')};
        if (!expected.available) {
          check((!selectors.pair || selectors.pair.disabled || !selectors.pair.options?.some(o=>!o.disabled)) && decoded.length === 0, 'missing_observation_cell_clears_previous_photo_evidence', {region, cell: id, reason: expected.reason, selectors, decoded});
        }
        receipt.cases.push({region, cellId: id, state: current, expected_evidence: {available:expected.available,reason:expected.reason||null}, images: decoded, selectors});
        await evaluate('window.scrollTo(0,0)'); await screenshot(`${region}_cell${id}_observation.png`);
      }
    });
  }

  await section('pair_anchor_and_photo_controls', async () => {
    await click('[data-testid="region-P2"]'); await ready({region: 'P2'});
    await click('[data-testid="stage-2"]'); await cell(5, 'P2');
    let pairs = await control('pair-select');
    requireCheck(pairs && pairs.options.filter(o=>!o.disabled).length >= 2, 'recorded_case_has_multiple_pairs', pairs);
    const originalPair = pairs.value, alternatePair = pairs.options.find(o=>!o.disabled && o.value !== originalPair).value;
    const beforeImages = await images({case: 'P2/5', point: 'before_pair'});
    await choose('pair-select', alternatePair); await ready({region:'P2',cellId:5,stage:2});
    const afterImages = await images({case: 'P2/5', point: 'after_pair'});
    check((await control('pair-select')).value === alternatePair && JSON.stringify(beforeImages.map(i=>i.src)) !== JSON.stringify(afterImages.map(i=>i.src)), 'pair_switch_changes_actual_decoded_image_membership', {originalPair, alternatePair, beforeImages, afterImages});
    await choose('pair-select', originalPair); await ready({region:'P2',cellId:5,stage:2});
    const anchors = await control('anchor-select');
    requireCheck(anchors && anchors.options.filter(o=>!o.disabled).length >= 2, 'recorded_pair_has_multiple_anchors', anchors);
    const originalAnchor = anchors.value, alternateAnchor = anchors.options.find(o=>!o.disabled&&o.value!==originalAnchor).value;
    const beforePatch = await screenshot(null, '#patch-reference');
    await choose('anchor-select', alternateAnchor); await ready({region:'P2',cellId:5,stage:2});
    const afterPatch = await screenshot(null, '#patch-reference');
    check((await control('anchor-select')).value === alternateAnchor && beforePatch.sha256 !== afterPatch.sha256 && beforePatch.canvas && afterPatch.canvas && beforePatch.canvas.sha256 !== afterPatch.canvas.sha256, 'anchor_switch_changes_actual_reference_patch', {originalAnchor, alternateAnchor, beforePatch, afterPatch});
    await choose('anchor-select', originalAnchor); await ready({region:'P2',cellId:5,stage:2});
    await click('[data-photo="reference"][data-photo-action="fit"]');
    const fitted = await screenshot(null,'#reference-canvas');
    await wheel('#reference-canvas'); const zoomed = await screenshot(null,'#reference-canvas');
    check(fitted.sha256 !== zoomed.sha256, 'photo_wheel_changes_rendered_zoom', {fitted, zoomed});
    await drag('#reference-canvas'); const panned = await screenshot(null,'#reference-canvas');
    check(panned.sha256 !== zoomed.sha256, 'photo_pointer_drag_changes_rendered_pan', {zoomed,panned});
    await click('[data-photo="reference"][data-photo-action="fit"]'); const reset = await screenshot(null,'#reference-canvas');
    check(reset.sha256 === fitted.sha256, 'photo_fit_restores_same_rendered_view', {fitted,reset});
    for (const action of ['actual','focus']) { await click(`[data-photo="reference"][data-photo-action="${action}"]`); await screenshot(`photo_reference_${action}.png`, '#reference-canvas'); }
    await pointerClick('[data-photo="reference"][data-photo-action="full"]');
    await pause(150);
    const lightbox = await evaluate(`(async()=>{const d=document.getElementById('lightbox'),i=document.getElementById('lightbox-image');if(i?.getAttribute('src'))try{await i.decode()}catch{}return {open:!!d?.open,image:i?{src:i.currentSrc||i.src,naturalWidth:i.naturalWidth,naturalHeight:i.naturalHeight}:null}})()`);
    check(lightbox.open && lightbox.image?.naturalWidth > 0 && lightbox.image?.naturalHeight > 0, 'expanded_view_decodes_actual_original_image', lightbox);
    await assertCanvases(['lightbox-canvas'],[1000,600],{point:'expanded_photo'});
    await screenshot('photo_reference_expanded.png','#lightbox-canvas');
    await pointerClick('#lightbox-close');
    check(await evaluate('!document.getElementById("lightbox").open'),'expanded_photo_closes_through_visible_control');
    await click('[data-photo="reference"][data-photo-action="fit"]');
  });

  await section('cell_filter_map_and_3d_controls', async () => {
    await click('[data-testid="region-P2"]'); await ready({region:'P2'});
    await click('[data-testid="stage-1"]'); await cell(5,'P2');
    await choose('cell-filter','IMAGE');
    const filter = await control('cell-select');
    check(filter && filter.options.length === 38, 'IMAGE_filter_contains_exact_sealed_count', filter);
    await choose('cell-filter','PRIOR');
    const prior = await control('cell-select');
    check(prior && prior.options.length === 3, 'PRIOR_filter_contains_exact_sealed_count', prior);
    await choose('cell-filter','all'); await cell(5,'P2');
    await choose('map-layer','gap');
    const map = await evaluate(`(()=>{const m=document.getElementById('cell-map');const r=m.getBoundingClientRect();return {cells:m.querySelectorAll('[data-cell-id]').length,width:r.width,height:r.height}})()`);
    check(map.cells === 552 && map.width > 100 && map.height > 100, 'cell_map_displays_full_region_census',map);
    await pointerClick('#cell-map [data-cell-id="120"]'); await ready({region:'P2',cellId:120});
    check((await state()).cellId === 120, 'map_click_selects_actual_cell');
    await choose('map-layer','action');
    await choose('view-scope','region'); await ready({region:'P2'});
    await click('[data-view="iso"]'); await click('#cloud-reset');
    const both = await screenshot(null,'#cloud-canvas');
    await click('#source-mvs'); const alsOnly = await screenshot(null,'#cloud-canvas');
    check((await control('source-mvs')).checked === false && both.sha256 !== alsOnly.sha256, 'source_visibility_changes_actual_cloud_render', {both,alsOnly});
    await click('#source-mvs');
    await click('[data-view="top"]'); const top = await screenshot(null,'#cloud-canvas');
    check(top.sha256 !== both.sha256, 'top_view_changes_actual_cloud_projection', {both,top});
    await click('[data-view="iso"]'); await click('#cloud-reset');
    const fitted = await screenshot(null,'#cloud-canvas');
    await wheel('#cloud-canvas'); const zoomed = await screenshot(null,'#cloud-canvas');
    check(fitted.sha256 !== zoomed.sha256,'cloud_wheel_changes_rendered_zoom',{fitted,zoomed});
    await drag('#cloud-canvas','right'); const panned=await screenshot(null,'#cloud-canvas');
    check(panned.sha256 !== zoomed.sha256,'cloud_pointer_pan_changes_render',{zoomed,panned});
    await click('#cloud-reset'); const reset=await screenshot(null,'#cloud-canvas');
    check(fitted.sha256 === reset.sha256,'cloud_reset_restores_same_rendered_view',{fitted,reset});
    await screenshot('P2_cloud_controls.png','#cloud-canvas');
  });

  for (const width of [1024,768]) await section('responsive_'+width,async()=>{
    await setViewport(width,1000);
    await click('[data-testid="region-P2"]'); await ready({region:'P2'}); await cell(5,'P2');
    for(const stage of [1,2,3]){
      await click(`[data-testid="stage-${stage}"]`);const current=await ready({region:'P2',stage});
      const layout=await evaluate('({width:innerWidth,documentWidth:document.documentElement.scrollWidth,bodyWidth:document.body.scrollWidth})');
      check(layout.documentWidth<=width+2 && layout.bodyWidth<=width+2,'responsive_page_has_no_horizontal_overflow',{width,stage,layout});
      if(stage===1) await assertCanvases(['cloud-canvas'],[240,200],{width,stage});
      if(stage===2){await images({width,stage});await assertCanvases(['reference-canvas','target-canvas'],[240,200],{width,stage});}
      await evaluate('window.scrollTo(0,0)');await screenshot(`P2_stage${stage}_${width}x1000.png`);
      receipt.responsive.push({width,stage,state:current,layout});
    }
  });
  await setViewport(1600);
  currentPhase='final_browser_audit';
  await pause(300);
  const exceptions=events.filter(e=>e.method==='Runtime.exceptionThrown');
  const consoleErrors=events.filter(e=>e.method==='Runtime.consoleAPICalled'&&e.params.type==='error');
  const httpErrors=events.filter(e=>e.method==='Network.responseReceived'&&e.params.response.status>=400);
  const loadingFailures=events.filter(e=>e.method==='Network.loadingFailed');
  const expectedAborts=loadingFailures.filter(e=>e.params.canceled&&e.params.errorText==='net::ERR_ABORTED'&&e.qa_phase==='rapid_region_transitions');
  const unexpectedFailures=loadingFailures.filter(e=>!expectedAborts.includes(e));
  const browserErrors=await evaluate('window.__sourceQABrowserErrors||[]');
  receipt.network={http_errors:httpErrors,loading_failures:loadingFailures,expected_transition_cancellations:expectedAborts,unexpected_failures:unexpectedFailures};
  receipt.console_errors=consoleErrors;receipt.runtime_exceptions=exceptions;receipt.browser_errors=browserErrors;
  check(httpErrors.length===0,'no_HTTP_errors_including_404',httpErrors);
  check(exceptions.length===0&&consoleErrors.length===0&&browserErrors.length===0,'no_console_or_unhandled_browser_errors',{exceptions,consoleErrors,browserErrors});
  check(unexpectedFailures.length===0,'no_unexpected_network_failures',unexpectedFailures);
  check(screenshots.filter(s=>/^P[123]_stage[123]_1600x1000\.png$/.test(s.filename)).length===9,'complete_three_region_three_stage_screenshot_matrix');
  receipt.final_state=await state();
  receipt.status=checks.every(c=>c.pass)?'PASS_ACTUAL_VIEWER_DISPLAY_AND_CONTROLS':'FAIL';
  if(receipt.status==='FAIL')process.exitCode=1;
} catch(error){receipt.status='FAIL';receipt.error=String(error);process.exitCode=1;}
finally{
  receipt.completed_at=new Date().toISOString();receipt.check_count=checks.length;receipt.failed_checks=checks.filter(c=>!c.pass);
  await fs.writeFile(path.join(output,'browser_qa.json'),JSON.stringify(receipt,null,2),{flag:'wx'});
  await fs.writeFile(path.join(output,'chrome.log'),chromeLog.join(''),{flag:'wx'});
  await fs.writeFile(path.join(output,'browser_events.json'),JSON.stringify(events,null,2),{flag:'wx'});
  if(socket)socket.close();if(browser)browser.kill('SIGTERM');if(virtualDisplay)virtualDisplay.kill('SIGTERM');
  process.stdout.write(JSON.stringify({status:receipt.status,checks:checks.length,failed_checks:receipt.failed_checks.length,screenshots:screenshots.length,receipt:path.join(output,'browser_qa.json')})+'\n');
}
