// Local browser QA only: Node built-ins and a fresh isolated Chrome profile.
import net from 'node:net';
import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';

const [url, out, profile, port = '9231'] = process.argv.slice(2);
if (!url || !out || !profile?.startsWith('/tmp/jbgs-p2-ab-v6-qa.')) throw Error('Expected URL OUTPUT FRESH_PROFILE [PORT]');
if (!['127.0.0.1', 'localhost'].includes(new URL(url).hostname)) throw Error('Local viewer only');
await fs.mkdir(out, {recursive: false});
await fs.writeFile(path.join(out, 'browser_qa_source.mjs'), await fs.readFile(new URL(import.meta.url)), {flag: 'wx'});
await fs.writeFile(path.join(out, 'browser_qa_wrapper.sh'), await fs.readFile(new URL('./browser_qa.sh', import.meta.url)), {flag: 'wx'});
const pages = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
const ws = new URL(pages.find(p => p.type === 'page').webSocketDebuggerUrl);
const socket = net.createConnection({host: ws.hostname, port: Number(ws.port)});
let stream = Buffer.alloc(0), handshake = false, nextId = 1, fragments = [];
const pending = new Map(), events = [], checks = [], screenshots = [];
await new Promise((resolve, reject) => {
  socket.on('error', reject);
  socket.on('connect', () => socket.write(`GET ${ws.pathname} HTTP/1.1\r\nHost: ${ws.host}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: ${crypto.randomBytes(16).toString('base64')}\r\nSec-WebSocket-Version: 13\r\n\r\n`));
  socket.on('data', data => {
    stream = Buffer.concat([stream, data]);
    if (!handshake) {
      const end = stream.indexOf('\r\n\r\n'); if (end < 0) return;
      if (!stream.subarray(0, end).toString().startsWith('HTTP/1.1 101')) return reject(Error('CDP websocket handshake'));
      stream = stream.subarray(end + 4); handshake = true; resolve();
    }
    while (stream.length >= 2) {
      const final = !!(stream[0] & 128), opcode = stream[0] & 15; let length = stream[1] & 127, offset = 2;
      if (length === 126) { if (stream.length < 4) return; length = stream.readUInt16BE(2); offset = 4; }
      else if (length === 127) { if (stream.length < 10) return; length = Number(stream.readBigUInt64BE(2)); offset = 10; }
      if (stream.length < offset + length) return;
      const body = stream.subarray(offset, offset + length); stream = stream.subarray(offset + length);
      if (opcode !== 0 && opcode !== 1) continue;
      fragments.push(body); if (!final) continue;
      const message = JSON.parse(Buffer.concat(fragments).toString()); fragments = [];
      if (message.id) { const p = pending.get(message.id); if (p) { pending.delete(message.id); message.error ? p.reject(Error(JSON.stringify(message.error))) : p.resolve(message.result); } }
      else events.push(message);
    }
  });
});
function send(method, params = {}) {
  const id = nextId++, body = Buffer.from(JSON.stringify({id, method, params})), mask = crypto.randomBytes(4);
  let header;
  if (body.length < 126) header = Buffer.from([0x81, 0x80 | body.length]);
  else if (body.length < 65536) { header = Buffer.from([0x81, 0xfe, 0, 0]); header.writeUInt16BE(body.length, 2); }
  else { header = Buffer.alloc(10); header[0] = 0x81; header[1] = 0xff; header.writeBigUInt64BE(BigInt(body.length), 2); }
  for (let i = 0; i < body.length; i++) body[i] ^= mask[i % 4];
  return new Promise((resolve, reject) => {
    pending.set(id, {resolve, reject}); socket.write(Buffer.concat([header, mask, body]));
    setTimeout(() => { if (pending.delete(id)) reject(Error('CDP timeout: ' + method)); }, 30000).unref();
  });
}
async function evaluate(expression) {
  const response = await send('Runtime.evaluate', {expression, returnByValue: true, awaitPromise: true});
  if (response.exceptionDetails) throw Error(JSON.stringify(response.exceptionDetails));
  return response.result?.value;
}
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
function check(condition, name, detail = null) { checks.push({name, pass: !!condition, detail}); if (!condition) throw Error(name); }
async function ready() {
  for (let i = 0; i < 120; i++) {
    const s = await evaluate('window.p2ViewerState');
    if (s?.error) throw Error(s.error);
    if (s?.ready && !s.loading) { await evaluate('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))'); return s; }
    await pause(100);
  }
  throw Error('Viewer did not become ready');
}
async function capture(name) {
  const result = await send('Page.captureScreenshot', {format: 'png', captureBeyondViewport: false});
  const bytes = Buffer.from(result.data, 'base64'); await fs.writeFile(path.join(out, name), bytes, {flag: 'wx'});
  screenshots.push({filename: name, sha256: crypto.createHash('sha256').update(bytes).digest('hex')});
}
async function fingerprint(id) {
  return evaluate(`(async()=>{const c=document.getElementById(${JSON.stringify(id)}),a=c.getContext('2d').getImageData(0,0,c.width,c.height).data;return [...new Uint8Array(await crypto.subtle.digest('SHA-256',a))].map(x=>x.toString(16).padStart(2,'0')).join('')})()`);
}
async function evidenceReady() {
  for (let i = 0; i < 120; i++) {
    const value = await evaluate(`window.p2Evidence && {data:window.p2Evidence,options:document.getElementById('evidence-case').options.length,tableRows:document.querySelectorAll('#result-table tbody tr').length}`);
    if (value?.data?.cases?.length && value.options === value.data.cases.length && value.tableRows === value.data.results.length) return value.data;
    await pause(100);
  }
  throw Error('A evidence panel did not become ready');
}
async function settleFrames() {
  await evaluate('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))');
}
async function setEvidenceCase(index) {
  await evaluate(`(()=>{const s=document.getElementById('evidence-case');s.value=${JSON.stringify(String(index))};s.dispatchEvent(new Event('change',{bubbles:true}));})()`);
  await settleFrames();
}
async function locateEvidence(item) {
  await evaluate(`document.getElementById('evidence-locate').click()`);
  for (let attempt = 0; attempt < 120; attempt++) {
    const state = await ready();
    if (state.viewId === item.projection.image_id && state.zoom === 2 && Math.abs(state.center.x-item.projection.u) < 1e-6 && Math.abs(state.center.y-item.projection.v) < 1e-6) return state;
    await pause(50);
  }
  throw Error('Evidence locate did not synchronize the exact image coordinates');
}
try {
  const command = await send('Browser.getBrowserCommandLine');
  check(command.arguments.includes('--user-data-dir=' + profile), 'isolated_profile');
  const browser = await send('Browser.getVersion');
  for (const name of ['Page', 'Runtime', 'Network', 'Log']) await send(name + '.enable');
  await send('Emulation.setDeviceMetricsOverride', {width: 1480, height: 1180, deviceScaleFactor: 1, mobile: false});
  await send('Page.navigate', {url});
  const initial = await ready(); check(initial.viewId === 333, 'roof_url_preset', initial);
  const data = await evaluate(`fetch('data.json').then(r=>r.json())`);
  const receipt = await evaluate(`fetch('technical_receipt.json').then(r=>r.json())`);
  const evidence = await evidenceReady();
  check(data.views.length === 11 && new Set(data.views.map(v => v.image_id)).size === 11, 'all_11_views');
  check(data.models.length === 23 && new Set(data.models.map(m => m.id)).size === 23, 'all_23_models');
  check(JSON.stringify(data.models.reduce((o,m)=>(o[m.kind]=(o[m.kind]||0)+1,o),{})) === JSON.stringify({rgb:6,normal:6,mask:6,depth_change:5}), 'six_rgb_and_seventeen_geometry_diagnostics');
  check(data.views.reduce((sum,view)=>sum+view.common_pixels,0) === 5150892, 'fixed_common_5150892_pixel_denominator');
  check(initial.selectedModels.join(',') === 'mvs_initial,mvs_sh3_uniform,mvs_sh3_residual_weighted', 'current_mvs_default');
  await capture('roof_overview.png');
  let assetCount = 0, modelAssetCount = 0;
  for (const view of data.views) {
    await evaluate(`p2Viewer.setView(${view.image_id})`); await ready();
    const rows = await evaluate(`(async()=>{const view=${JSON.stringify(view)};const rows=[];for(const [key,p] of Object.entries({target:view.target,...view.images,support:view.support})){
      const response=await fetch(p);if(!response.ok)throw Error('image '+response.status);const bytes=await response.arrayBuffer();const im=new Image();im.src=p;await im.decode();
      rows.push({key,path:p,width:im.naturalWidth,height:im.naturalHeight,sha256:[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(x=>x.toString(16).padStart(2,'0')).join('')});}return rows;})()`);
    for (const row of rows) check(row.width === view.width && row.height === view.height && row.sha256 === receipt.output_sha256[row.path], `original_pixels_${view.image_id}_${row.key}`, row);
    assetCount += rows.length; modelAssetCount += Object.keys(view.images).length;
    for (const m of data.models) {
      await evaluate(`p2Viewer.setModel(0,${JSON.stringify(m.id)})`); const s = await ready();
      check(s.selectedModels[0] === m.id && s.loadedImages.includes(m.id), `selected_model_${view.image_id}_${m.id}`);
      const caption = await evaluate(`({number:document.querySelector('#metric-0 .metric-number')?.textContent??null,text:document.getElementById('metric-0').textContent})`);
      if (m.kind === 'rgb') {
        check(caption.number === view.metrics[m.id].mae.toFixed(5) && caption.text.includes(view.metrics[m.id].psnr_db.toFixed(2)) && view.metrics[m.id].pixels === view.common_pixels, `fixed_pixel_rgb_metric_${view.image_id}_${m.id}`, caption);
      } else {
        const expected = m.kind === 'normal' ? '법선' : m.kind === 'depth_change' ? '0–0.3m' : '위치';
        check(caption.number === null && !/MAE|PSNR/.test(caption.text) && caption.text.includes(expected) && view.metrics[m.id].mae === null && view.metrics[m.id].psnr_db === null, `diagnostic_not_rgb_metric_${view.image_id}_${m.id}`, caption);
        if(m.kind === 'mask') check(m.phase === 'initial' ? caption.text.includes('A 관측') : caption.text.includes('최종 1mm 초과'), `mask_semantics_${view.image_id}_${m.id}`, caption);
      }
    }
    console.log(JSON.stringify({checked_view: view.image_id, original_images: rows.length, models: data.models.length}));
  }
  await evaluate(`p2Viewer.setView(333)`); await ready();
  await evaluate(`Promise.all([p2Viewer.setModel(0,'mvs_initial'),p2Viewer.setModel(1,'mvs_sh3_uniform'),p2Viewer.setModel(2,'mvs_sh3_residual_weighted')])`); await ready();
  await evaluate(`document.getElementById('native-button').click()`); await ready();
  check((await evaluate('p2ViewerState.zoom')) === 1, 'native_one_to_one_zoom');
  const before = await fingerprint('canvas-render-0');
  await capture('roof_native_pixels.png');
  const box = await evaluate(`(()=>{const r=document.getElementById('canvas-target').getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height}})()`);
  await send('Input.dispatchMouseEvent', {type: 'mousePressed', x: box.x + box.width / 2, y: box.y + box.height / 2, button: 'left', clickCount: 1});
  await send('Input.dispatchMouseEvent', {type: 'mouseMoved', x: box.x + box.width / 2 + 60, y: box.y + box.height / 2 + 30, button: 'left', buttons: 1});
  await send('Input.dispatchMouseEvent', {type: 'mouseReleased', x: box.x + box.width / 2 + 60, y: box.y + box.height / 2 + 30, button: 'left', clickCount: 1});
  await ready(); check(before !== await fingerprint('canvas-render-0'), 'target_drag_changes_other_panel');
  await evaluate(`p2Viewer.setModel(0,'dynamic_surface_guard_normal')`); await ready();
  check((await evaluate('p2ViewerState.zoom')) === 1, 'method_switch_preserves_zoom');
  await evaluate(`Promise.all([p2Viewer.setModel(1,'dynamic_surface_guard_mask'),p2Viewer.setModel(2,'dynamic_surface_guard_depth_change')]);p2Viewer.fit()`); await ready(); await capture('roof_geometry_diagnostics.png');
  await evaluate(`p2Viewer.setModel(0,'mvs_initial');p2Viewer.setMode('wipe');p2Viewer.fit()`); await ready();
  await evaluate(`p2Viewer.setWipePosition(.25)`); await ready(); const wipeBefore = await fingerprint('canvas-wipe');
  await evaluate(`p2Viewer.setWipePosition(.75)`); await ready();
  check(wipeBefore !== await fingerprint('canvas-wipe'), 'wipe_changes_actual_pixels'); await capture('roof_wipe.png');
  await evaluate(`(()=>{const s=document.getElementById('wipe-model');s.value='dynamic_surface_guard_depth_change';s.dispatchEvent(new Event('change',{bubbles:true}));})()`); await ready();
  const diagnosticWipe = await evaluate(`({model:p2ViewerState.wipeModel,caption:document.getElementById('metric-wipe').textContent,number:document.querySelector('#metric-wipe .metric-number')?.textContent??null})`);
  check(diagnosticWipe.model === 'dynamic_surface_guard_depth_change' && diagnosticWipe.number === null && !/MAE|PSNR/.test(diagnosticWipe.caption), 'wipe_diagnostic_has_no_rgb_score', diagnosticWipe);
  await capture('roof_depth_change_wipe.png');
  check(evidence.cases.length > 1 && evidence.results.length === 5 && evidence.offsets.length === 13, 'actual_A_cases_and_five_results', {cases:evidence.cases.length,results:evidence.results.length,offsets:evidence.offsets.length});
  const table=await evaluate(`({headers:[...document.querySelectorAll('#result-table th')].map(x=>x.textContent),rows:[...document.querySelectorAll('#result-table tbody tr')].map(r=>[...r.cells].map(c=>c.textContent))})`);
  check(table.headers.includes('미해결 관측점') && table.rows.length === evidence.results.length && table.rows.every((row,i)=>row[4] === String(evidence.results[i].unresolved)), 'unresolved_count_remains_visible', table);
  let previousPlot = null, previousPlotValues = null, locatedCount = 0;
  for (let i=0; i<evidence.cases.length; i++) {
    const item=evidence.cases[i];
    check(item.cost.length === 2 && item.cost.every(row=>row.length === evidence.offsets.length && row.every(Number.isFinite)), `actual_two_group_cost_curve_${item.seed_id}`);
    await setEvidenceCase(i);
    const numbers=await evaluate(`document.getElementById('evidence-numbers').textContent`);
    check(numbers.includes(item.observation.map(v=>v.toFixed(3)).join(', ')) && numbers.includes(item.allowed.map(v=>v.toFixed(3)).join(', ')) && numbers.includes(item.final_offset.toFixed(4)), `displayed_A_values_${item.seed_id}`, numbers);
    check(typeof item.conditional_eligible === 'boolean' && (item.conditional_eligible ? numbers.includes('조건부 위치 구간 통과') : numbers.includes('미해결')), `A_case_conditional_status_${item.seed_id}`, numbers);
    const plot=await fingerprint('evidence-plot');
    const plotValues=JSON.stringify([item.cost,item.observation,item.allowed,item.final_offset]);
    if(previousPlot !== null && plotValues !== previousPlotValues) check(plot !== previousPlot, `A_case_changes_drawn_curve_${item.seed_id}`);
    previousPlot=plot;previousPlotValues=plotValues;
    if(item.projection) {
      const state=await locateEvidence(item);locatedCount++;
      check(state.mode === 'grid' && state.viewId === item.projection.image_id && state.zoom === 2 && Math.abs(state.center.x-item.projection.u)<1e-6 && Math.abs(state.center.y-item.projection.v)<1e-6, `A_locate_exact_coordinates_${item.seed_id}`, {view:state.viewId,mode:state.mode,center:state.center});
    }
  }
  check(locatedCount>0, 'at_least_one_actual_A_case_located', {locatedCount});
  await setEvidenceCase(0);
  await evaluate(`document.querySelector('.evidence-panel').scrollIntoView({block:'start',behavior:'instant'})`);await settleFrames();await capture('actual_A_evidence_panel.png');
  const firstLocated=evidence.cases.findIndex(item=>item.projection);
  await setEvidenceCase(firstLocated);await evaluate(`p2Viewer.setMode('grid')`);await locateEvidence(evidence.cases[firstLocated]);
  await evaluate(`document.getElementById('grid-mode').scrollIntoView({block:'start',behavior:'instant'})`);await pause(300);await capture('actual_A_case_located.png');
  const projectedCases=evidence.cases.map((item,index)=>({item,index})).filter(({item})=>item.projection);
  const maxChanged=projectedCases.reduce((best,current)=>Math.abs(current.item.final_offset)>Math.abs(best.item.final_offset)?current:best);
  await setEvidenceCase(maxChanged.index);
  await evaluate(`Promise.all([p2Viewer.setModel(0,'mvs_sh3_residual_weighted'),p2Viewer.setModel(1,'dynamic_surface_guard_normal'),p2Viewer.setModel(2,'dynamic_surface_guard_depth_change')])`);await ready();
  await locateEvidence(maxChanged.item);await evaluate(`document.getElementById('grid-mode').scrollIntoView({block:'start',behavior:'instant'})`);await pause(300);await capture('largest_displayed_final_offset_rgb_normal_depth.png');
  screenshots.at(-1).selection={criterion:'maximum absolute final offset among displayed A cases having an evaluation-view projection; not best visual quality',seed_id:maxChanged.item.seed_id,final_offset_m:maxChanged.item.final_offset,view_id:maxChanged.item.projection.image_id};
  await evaluate(`document.querySelector('.evidence-panel').scrollIntoView({block:'start',behavior:'instant'})`);await settleFrames();await capture('largest_displayed_final_offset_A_curve.png');
  screenshots.at(-1).selection={criterion:'same maximum-offset displayed case',seed_id:maxChanged.item.seed_id,final_offset_m:maxChanged.item.final_offset};
  const unresolved=projectedCases.find(({item})=>!item.conditional_eligible);
  check(!!unresolved,'unresolved_example_available');
  await setEvidenceCase(unresolved.index);await locateEvidence(unresolved.item);await evaluate(`document.getElementById('grid-mode').scrollIntoView({block:'start',behavior:'instant'})`);await pause(300);await capture('first_unresolved_case_rgb_normal_depth.png');
  screenshots.at(-1).selection={criterion:'first displayed unresolved A case having an evaluation-view projection',seed_id:unresolved.item.seed_id,final_offset_m:unresolved.item.final_offset,view_id:unresolved.item.projection.image_id};
  await evaluate(`document.querySelector('.evidence-panel').scrollIntoView({block:'start',behavior:'instant'})`);await settleFrames();await capture('first_unresolved_case_A_curve.png');
  screenshots.at(-1).selection={criterion:'same first unresolved displayed case',seed_id:unresolved.item.seed_id,final_offset_m:unresolved.item.final_offset};
  await evaluate(`document.getElementById('view-window').click()`); await ready();
  check((await evaluate('p2ViewerState.viewId')) === 361, 'window_preset');
  await evaluate(`p2Viewer.setMode('grid');p2Viewer.fit();window.scrollTo({top:0,behavior:'instant'})`); await ready(); await capture('window_support_limit.png');
  await send('Emulation.setDeviceMetricsOverride', {width: 390, height: 844, deviceScaleFactor: 1, mobile: true});
  await pause(150); await ready();
  await evaluate(`window.scrollTo({top:0,behavior:'instant'})`);await settleFrames();
  const mobile = await evaluate(`({width:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth,canvases:[...document.querySelectorAll('#grid-mode canvas,#evidence-plot')].map(c=>{const r=c.getBoundingClientRect();return {left:r.left,right:r.right,width:r.width}})})`);
  check(mobile.scroll <= mobile.width && mobile.canvases.every(c => c.width > 0 && c.left >= 0 && c.right <= mobile.width + 1), 'mobile_layout', mobile);
  await capture('mobile.png');
  await evaluate(`document.querySelector('.evidence-panel').scrollIntoView({block:'start',behavior:'instant'})`);await settleFrames();await capture('mobile_A_evidence.png');
  const failures = events.filter(e => e.method === 'Runtime.exceptionThrown' || (e.method === 'Network.responseReceived' && e.params.response.status >= 400) || e.method === 'Network.loadingFailed');
  check(failures.length === 0, 'no_browser_or_http_errors', failures);
  await fs.writeFile(path.join(out, 'browser_qa.json'), JSON.stringify({status: 'PASS', scientific_verdict: null, url, profile, browser, checks, screenshots, original_asset_count: assetCount, model_image_count:modelAssetCount, target_image_count:data.views.length, support_image_count:data.views.length, view_count: data.views.length, model_count: data.models.length, evidence_case_count:evidence.cases.length, located_case_count:locatedCount}, null, 2) + '\n', {flag: 'wx'});
  console.log(JSON.stringify({status: 'PASS', checks: checks.length, screenshots: screenshots.length}));
} catch (error) {
  await fs.writeFile(path.join(out, 'FAILED.json'), JSON.stringify({error: String(error), checks, screenshots, events, scientific_verdict: null}, null, 2) + '\n', {flag: 'wx'});
  throw error;
} finally { socket.end(); }
