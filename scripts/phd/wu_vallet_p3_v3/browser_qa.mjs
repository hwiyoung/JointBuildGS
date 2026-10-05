// Browser QA infrastructure only: Node built-ins, CDP, dedicated Chrome profile.
import net from 'node:net';
import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';

const [url, out, profile, port = '9237'] = process.argv.slice(2);
if (!url || !out || !profile?.startsWith('/tmp/jbgs-wu-p3-v3-qa.')) throw Error('URL OUTPUT FRESH_PROFILE [PORT] required');
if (!['localhost', '127.0.0.1'].includes(new URL(url).hostname)) throw Error('Local gallery only');
await fs.mkdir(out, {recursive: false});
for (const [source, destination] of [[new URL(import.meta.url), 'browser_qa_source.mjs'], [new URL('./browser_qa.sh', import.meta.url), 'browser_qa_wrapper.sh']]) {
  await fs.writeFile(path.join(out, destination), await fs.readFile(source), {flag: 'wx'});
}
const pages = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
const page = pages.find(p => p.type === 'page');
if (!page?.webSocketDebuggerUrl) throw Error('Dedicated Chrome page missing');
const ws = new URL(page.webSocketDebuggerUrl);
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
      if (!stream.subarray(0, end).toString().startsWith('HTTP/1.1 101')) return reject(Error('CDP websocket handshake failed'));
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
  const result = await send('Runtime.evaluate', {expression, returnByValue: true, awaitPromise: true});
  if (result.exceptionDetails) throw Error(JSON.stringify(result.exceptionDetails));
  return result.result?.value;
}
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
function check(pass, name, detail = null) { checks.push({name, pass: !!pass, detail}); if (!pass) throw Error(name); }
async function settle() { await evaluate('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))'); }
async function imagesReady(selector = '#gallery img.photo') {
  for (let attempt = 0; attempt < 100; attempt++) {
    const result = await evaluate(`(()=>{const a=[...document.querySelectorAll(${JSON.stringify(selector)})];return {count:a.length,ready:a.length>0&&a.every(i=>i.complete&&i.naturalWidth>0),images:a.map(i=>({src:i.getAttribute('src'),width:i.naturalWidth,height:i.naturalHeight}))}})()`);
    if (result.ready) { await settle(); return result; }
    await pause(100);
  }
  throw Error('Images not loaded: ' + selector);
}
async function choose(id, value) {
  await evaluate(`(()=>{const e=document.getElementById(${JSON.stringify(id)});e.value=${JSON.stringify(String(value))};e.dispatchEvent(new Event('change',{bubbles:true}));})()`);
  await settle();
}
async function capture(name) {
  const response = await send('Page.captureScreenshot', {format: 'png', captureBeyondViewport: false});
  const bytes = Buffer.from(response.data, 'base64');
  await fs.writeFile(path.join(out, name), bytes, {flag: 'wx'});
  screenshots.push({filename: name, sha256: crypto.createHash('sha256').update(bytes).digest('hex')});
}
async function ready(expectedArm = null, expectedMode = null) {
  for (let attempt = 0; attempt < 150; attempt++) {
    const state = await evaluate('window.__WV_QA??null');
    if (state?.errors?.length) throw Error(JSON.stringify(state.errors));
    if (state?.ready && (!expectedArm || state.arm === expectedArm) && (!expectedMode || state.mode === expectedMode)) {
      await settle(); return state;
    }
    await pause(100);
  }
  throw Error('Point viewer did not reach expected ready state');
}
let browser;
try {
  const command = await send('Browser.getBrowserCommandLine');
  check(command.arguments.includes('--user-data-dir=' + profile), 'dedicated_fresh_profile');
  check(command.arguments.includes('--remote-debugging-port=' + port), 'dedicated_debug_port');
  check(command.arguments.includes('--use-angle=swiftshader'), 'explicit_software_webgl_for_local_point_scene');
  browser = await send('Browser.getVersion');
  for (const name of ['Page', 'Runtime', 'Network', 'Log']) await send(name + '.enable');
  await send('Emulation.setDeviceMetricsOverride', {width: 1560, height: 1100, deviceScaleFactor: 1, mobile: false});
  await send('Page.navigate', {url});
  const initial = await ready();
  const data = await evaluate("JSON.parse(document.getElementById('evidence-data').textContent)");
  const manifest = await evaluate("fetch('viewer_manifest.json').then(r=>r.json())");
  check(data.native_2026_reproduction === false && data.scientific_verdict === null, 'paper_based_scope_and_null_verdict');
  check(data.arms.length > 0 && data.arms.length === manifest.arm_count, 'completed_arm_count');
  check(manifest.all_arm_native_membership_xyz_and_source_validation === 'PASS', 'native_membership_verified_during_build');
  check(initial.frames > 0 && initial.visiblePoints.old + initial.visiblePoints.new > 0, 'actual_point_scene_drawn');
  check(manifest.forensics_native_pixel_and_xyz_validation === 'PASS', 'forensic_native_pixel_xyz_validation');
  check(data.forensics.baseline_arm === 'v2_a1' && data.forensics.default_arm === 'corrected_area1', 'same_area_v2_v3_default_comparison');
  check(initial.photoLoaded && initial.nativePhoto.width === data.forensics.photo.width && initial.nativePhoto.height === data.forensics.photo.height && initial.nativePhoto.imageId === 133, 'actual_master_133_photo_loaded');
  check(data.forensics.distance_threshold_m === 2 && data.forensics.diagnosis_role === 'EVALUATION_ONLY_not_used_to_select_or_filter_points', 'reference_distance_overlay_evaluation_only');
  const text = await evaluate('document.body.innerText');
  check(text.includes('저자 코드의 동일 재현은 아닙니다') && text.includes('COLMAP') && text.includes('PSMNet') && text.includes('추정'), 'visible_origin_and_geometry_substitution_limits');
  check(text.includes('사진이나 Gaussian 렌더가 아닙니다') && text.includes('scientific_verdict: null'), 'point_view_not_misrepresented_as_image_render');
  check(await evaluate("document.querySelectorAll('#arm-select option').length===document.querySelectorAll('#arm-table tr').length"), 'arm_controls_match_table');
  if (data.evaluation) {
    const metrics = await evaluate("[...document.querySelectorAll('#evaluation-table tr')].map(r=>[...r.cells].map(c=>c.textContent))");
    const expected = Object.entries(data.evaluation.methods);
    check(metrics.length === expected.length, 'all_reference_only_evaluation_rows');
    check(metrics.every((row, i) => row[5] === expected[i][1].updated_to_reference.p90_m.toFixed(3) + ' m' && row[6] === expected[i][1].reference_to_updated.p90_m.toFixed(3) + ' m' && Number(row[3].replaceAll(',', '')) === expected[i][1].new.large_discrepancy_retained), 'evaluation_values_match_frozen_json');
    check(await evaluate("document.getElementById('evaluation-summary').textContent.includes('EPSG:32632')&&document.getElementById('evaluation-summary').textContent.includes('EPSG:25832')"), 'evaluation_datum_limitation_visible');
  }
  const nonblank = await evaluate(`(()=>{const src=document.querySelector('#viewport canvas'),c=document.createElement('canvas');c.width=src.width;c.height=src.height;const ctx=c.getContext('2d');ctx.drawImage(src,0,0);const p=ctx.getImageData(0,0,c.width,c.height).data,s=new Set();for(let i=0;i<p.length;i+=4*11)s.add((p[i]<<16)|(p[i+1]<<8)|p[i+2]);return {colors:s.size,width:c.width,height:c.height}})()`);
  check(nonblank.colors > 20 && nonblank.width > 0 && nonblank.height > 0, 'webgl_canvas_has_point_content', nonblank);
  await capture('desktop_point_update.png');
  await evaluate("document.getElementById('photo-card').scrollIntoView({block:'start'})");
  await settle();
  await capture('desktop_photo_overview.png');
  for (const roi of data.forensics.rois) {
    await choose('roi-select', roi.id);
    await choose('photo-mode', 'all');
    const state = await ready();
    check(state.photo.roi === roi.id && state.selectedPoint.new_native_index === roi.representative_new_index, `photo_roi_native_point_${roi.id}`);
    const pixelId = state.selectedPoint.depth_pixel_id;
    const expectedPixel = [(pixelId % data.forensics.depth_shape[1]) * data.forensics.photo.width / data.forensics.depth_shape[1], Math.floor(pixelId / data.forensics.depth_shape[1]) * data.forensics.photo.height / data.forensics.depth_shape[0]];
    check(expectedPixel.every((value, i) => Math.abs(value - state.selectedPoint.master_pixel_xy[i]) < .001), `native_pixel_photo_scaling_${roi.id}`);
    const clickResult = await evaluate(`(()=>{const canvas=document.getElementById('photo-canvas'),rect=canvas.getBoundingClientRect(),s=window.__WV_QA,box=s.photo.box,p=s.selectedPoint.master_pixel_xy,scale=Math.min(rect.width/(box[2]-box[0]),rect.height/(box[3]-box[1])),ox=(rect.width-(box[2]-box[0])*scale)/2,oy=(rect.height-(box[3]-box[1])*scale)/2;canvas.dispatchEvent(new MouseEvent('click',{clientX:rect.left+ox+(p[0]-box[0])*scale,clientY:rect.top+oy+(p[1]-box[1])*scale,bubbles:true}));return window.__WV_QA.selectedPoint.new_native_index;})()`);
    check(clickResult === roi.representative_new_index, `photo_click_resolves_exact_native_point_${roi.id}`);
    for (const mode of ['admitted', 'removed', 'large', 'all', 'none']) {
      await choose('photo-mode', mode);
      const update = await ready();
      check(update.photo.mode === mode && update.photo.arm === update.arm, `photo_overlay_${roi.id}_${mode}`);
      if (mode === 'none') check(update.photo.points === 0, `photo_only_no_overlay_${roi.id}`);
    }
    await choose('photo-mode', 'large');
    await evaluate("document.getElementById('photo-card').scrollIntoView({block:'start'})");
    await settle();
    await capture(`desktop_photo_roi_${roi.id.replaceAll(/[^A-Za-z0-9_-]/g, '_')}.png`);
  }
  if (data.forensics.figures.length) {
    for (const figure of data.forensics.figures) {
      await choose('figure-select', figure.id);
      await imagesReady('#forensic-figure');
      check(await evaluate("document.getElementById('forensic-figure').getAttribute('src')") === figure.path, `exact_forensic_figure_${figure.id}`);
    }
  }
  for (const arm of data.arms) {
    await choose('arm-select', arm.name); await ready(arm.name);
    const stats = await evaluate("[...document.querySelectorAll('#stats b')].map(e=>Number(e.textContent.replaceAll(',','')))");
    const expected = ['retained_old', 'removed_old', 'admitted_new', 'updated'].map(k => arm.counts[k]);
    check(stats.every((value, i) => value === expected[i]), `native_counts_${arm.name}`, {stats, expected});
    const links = await evaluate("Object.fromEntries(['json','npz','ply'].map(k=>[k,document.getElementById('arm-'+k).getAttribute('href')]))");
    check(Object.keys(links).every(k => links[k] === arm.downloads[k]), `original_download_paths_${arm.name}`, links);
    for (const mode of ['updated', 'inputs', 'old', 'new', 'labels', 'removed', 'added', 'region_removed', 'discrepancy']) {
      await choose('mode-select', mode); const state = await ready(arm.name, mode);
      if (mode === 'inputs' || mode === 'labels') check(state.visiblePoints.old === data.sources.old.display_count && state.visiblePoints.new === data.sources.new.display_count, `both_native_display_sources_${arm.name}_${mode}`);
      if (mode === 'removed') check(state.visiblePoints.new === 0, `removed_old_only_${arm.name}`);
      if (mode === 'added') check(state.visiblePoints.old === 0, `admitted_new_only_${arm.name}`);
      if (mode === 'new' || mode === 'region_removed' || mode === 'discrepancy') check(state.visiblePoints.old === 0, `native_new_only_${arm.name}_${mode}`);
      if (mode === 'old') check(state.visiblePoints.new === 0 && state.visiblePoints.old === data.sources.old.display_count, `native_old_only_${arm.name}`);
      check(await evaluate("document.getElementById('view-caption').textContent.includes(document.getElementById('arm-select').value)"), `caption_tracks_arm_${arm.name}_${mode}`);
    }
    for (const section of ['x', 'y']) {
      await choose('section-select', section);
      check((await ready()).section === section, `fixed_section_${arm.name}_${section}`);
    }
    check((await ready()).photo.arm === arm.name, `photo_arm_synchronized_${arm.name}`);
    console.log(JSON.stringify({checked_arm: arm.name, modes: 9, sections: 2}));
  }
  await choose('arm-select', data.arms[0].name); await ready(data.arms[0].name);
  await choose('mode-select', 'labels'); await ready(null, 'labels');
  await evaluate("document.getElementById('viewport').scrollIntoView({block:'center'})"); await settle();
  await capture('desktop_native_classification.png');
  await evaluate("document.getElementById('top-view').click()"); await settle();
  await capture('desktop_top_view.png');
  await evaluate("document.getElementById('reset-view').click();document.getElementById('map-canvas').scrollIntoView({block:'center'})");
  await settle(); await capture('desktop_maps_sections.png');
  // Hash every served original and DISPLAY_ONLY binary against the manifest.
  // Compute large download hashes in Node to avoid holding artifact copies in the page.
  let assets = 0;
  for (const [relative, expected] of Object.entries({...manifest.copied_assets, ...manifest.display_derivatives})) {
    const response = await fetch(new URL(relative, url));
    check(response.ok, `asset_http_${relative}`, response.status);
    const bytes = Buffer.from(await response.arrayBuffer()), actual = crypto.createHash('sha256').update(bytes).digest('hex');
    check(actual === expected.sha256 && bytes.length === expected.bytes, `asset_hash_${relative}`, {bytes: bytes.length, sha256: actual});
    assets++;
  }
  await send('Emulation.setDeviceMetricsOverride', {width: 390, height: 844, deviceScaleFactor: 1, mobile: true});
  await evaluate("window.scrollTo({top:0,behavior:'instant'})"); await settle();
  const mobile = await evaluate("({viewport:document.documentElement.clientWidth,page:document.documentElement.scrollWidth,canvas:document.querySelector('#viewport canvas').clientWidth})");
  check(mobile.page <= mobile.viewport + 1, 'mobile_page_fits', mobile);
  await capture('mobile_overview.png');
  await evaluate("document.getElementById('photo-canvas').scrollIntoView({block:'start'})"); await settle();
  await capture('mobile_actual_photo.png');
  await evaluate("document.getElementById('viewport').scrollIntoView({block:'start'})"); await settle();
  await capture('mobile_point_scene.png');
  await choose('arm-select', data.arms.at(-1).name); await ready(data.arms.at(-1).name);
  await choose('mode-select', 'updated'); await ready(null, 'updated');
  check(await evaluate("document.querySelector('#viewport canvas').clientWidth>250"), 'mobile_point_canvas_reachable');
  await evaluate("document.getElementById('arm-table').scrollIntoView({block:'center'})"); await settle();
  await capture('mobile_sensitivity_table.png');
  const errors = events.filter(e => e.method === 'Runtime.exceptionThrown' ||
    (e.method === 'Runtime.consoleAPICalled' && ['error', 'assert'].includes(e.params.type)) ||
    (e.method === 'Log.entryAdded' && e.params.entry.level === 'error') ||
    (e.method === 'Network.responseReceived' && e.params.response.status >= 400) || e.method === 'Network.loadingFailed');
  check(errors.length === 0, 'no_console_javascript_http_loading_errors', errors);
  const receipt = {status: 'PASS', scientific_verdict: null, native_2026_reproduction: false, url, profile,
    debug_port: Number(port), browser, checks, screenshots, asset_count: assets, arm_count: data.arms.length,
    runtime: {node: process.version, execution: 'HOST_BROWSER_QA_INFRASTRUCTURE_NODE_BUILTINS',
      webgl_backend: 'explicit_swiftshader_for_trusted_local_viewer_in_fresh_dedicated_profile',
      reason: 'Pinned project image has no node/Chrome; this harness drives only a fresh host browser profile. Scientific processing and viewer build remain Docker.'},
    server_lifecycle_modified: false, existing_browser_profiles_modified: false};
  await fs.writeFile(path.join(out, 'browser_qa.json'), JSON.stringify(receipt, null, 2) + '\n', {flag: 'wx'});
  console.log(JSON.stringify({status: 'PASS', checks: checks.length, screenshots: screenshots.length, assets}));
} catch (error) {
  await fs.writeFile(path.join(out, 'FAILED.json'), JSON.stringify({error: String(error), checks, screenshots, events, scientific_verdict: null}, null, 2) + '\n', {flag: 'wx'});
  throw error;
} finally { socket.end(); }
