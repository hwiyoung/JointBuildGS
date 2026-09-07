// Browser QA infrastructure only: Node built-ins, CDP, dedicated Chrome profile.
import net from 'node:net';
import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';

const [url, out, profile, port = '9238'] = process.argv.slice(2);
if (!url || !out || !profile?.startsWith('/tmp/jbgs-wu-p3-regions-v4-qa.')) throw Error('URL OUTPUT FRESH_PROFILE [PORT] required');
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
async function ready(expectedRegion = null, expectedArm = null, expectedMode = null) {
  for (let attempt = 0; attempt < 150; attempt++) {
    const state = await evaluate('window.__WV_REGIONS_QA??null');
    if (state?.errors?.length) throw Error(JSON.stringify(state.errors));
    if (state?.ready && (!expectedRegion || state.region === expectedRegion) && (!expectedArm || state.arm === expectedArm) && (!expectedMode || state.mode === expectedMode)) {
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
  check(command.arguments.includes('--use-angle=swiftshader'), 'software_webgl_explicit');
  browser = await send('Browser.getVersion');
  for (const name of ['Page', 'Runtime', 'Network', 'Log']) await send(name + '.enable');
  await send('Emulation.setDeviceMetricsOverride', {width: 1560, height: 1100, deviceScaleFactor: 1, mobile: false});
  await send('Page.navigate', {url});
  const initial = await ready();
  const data = await evaluate("fetch('data.json').then(r=>r.json())");
  const manifest = await evaluate("fetch('viewer_manifest.json').then(r=>r.json())");
  check(data.scientific_verdict === null && data.native_2026_reproduction === false, 'scope_null_verdict_and_paper_based_reproduction');
  check(manifest.all_region_native_membership_and_metric_denominators === 'PASS', 'native_membership_and_full_metric_denominator_validation');
  check(initial.region === data.default_region && initial.frames >= 4, 'default_region_four_panels_drawn');
  check(await evaluate("document.querySelectorAll('#comparison .viewport canvas').length===4"), 'four_actual_webgl_point_panels');
  for (const region of data.regions) {
    await choose('region-select', region.id); await ready(region.id);
    await choose('update-mode', 'height'); await ready(region.id, null, 'height');
    for (const key of ['als', 'image', 'update', 'reference']) {
      const content = await evaluate(`(()=>{const src=document.querySelector('#view-${key} canvas'),c=document.createElement('canvas');c.width=src.width;c.height=src.height;const ctx=c.getContext('2d');ctx.drawImage(src,0,0);const bytes=ctx.getImageData(0,0,c.width,c.height).data,s=new Set();for(let i=0;i<bytes.length;i+=44)s.add((bytes[i]<<16)|(bytes[i+1]<<8)|bytes[i+2]);return {width:c.width,height:c.height,colors:s.size};})()`);
      check(content.colors > 10 && content.width > 250 && content.height > 200, `real_nonblank_cloud_${region.id}_${key}`, content);
    }
    let state = await ready(region.id);
    const cameras = Object.values(state.cameras).slice(0, 4);
    check(cameras.every(c => JSON.stringify(c.position) === JSON.stringify(cameras[0].position) && JSON.stringify(c.target) === JSON.stringify(cameras[0].target)), `synchronized_camera_positions_${region.id}`);
    check(cameras.every(c => JSON.stringify(c.heightRange) === JSON.stringify([region.bounds.min[2], region.bounds.max[2]])), `shared_height_color_range_${region.id}`);
    await evaluate("document.getElementById('comparison').scrollIntoView({block:'start'})"); await settle();
    await capture(`desktop_${region.id}_before_after_reference.png`);
    // Drive a real pointer gesture; a synthetic pointer cannot own pointer capture.
    const rect = await evaluate("(()=>{const r=document.querySelector('#view-als canvas').getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2};})()");
    const previous = state.cameras.als.position;
    await send('Input.dispatchMouseEvent', {type: 'mousePressed', x: rect.x, y: rect.y, button: 'left', clickCount: 1});
    await send('Input.dispatchMouseEvent', {type: 'mouseMoved', x: rect.x + 30, y: rect.y + 12, button: 'left', buttons: 1});
    await send('Input.dispatchMouseEvent', {type: 'mouseReleased', x: rect.x + 30, y: rect.y + 12, button: 'left', clickCount: 1});
    await settle(); state = await ready();
    check(JSON.stringify(previous) !== JSON.stringify(state.cameras.als.position), `actual_drag_changes_camera_${region.id}`);
    check(['image', 'update', 'reference'].every(k => JSON.stringify(state.cameras[k].position) === JSON.stringify(state.cameras.als.position)), `drag_updates_all_four_views_${region.id}`);
    await evaluate("document.getElementById('reset-view').click()"); await settle();
    for (const arm of region.arms) {
      await choose('arm-select', arm.name); await ready(region.id, arm.name);
      const counts = await evaluate("[...document.querySelectorAll('#change-counts b')].map(e=>Number(e.textContent.replaceAll(',','')))");
      const expected = ['retained_old', 'removed_old', 'admitted_new', 'updated'].map(k => arm.counts[k]);
      check(counts.every((v, i) => v === expected[i]), `native_update_counts_${region.id}_${arm.name}`);
      for (const mode of ['height', 'source', 'removed_old', 'added_new']) {
        await choose('update-mode', mode); const s = await ready(region.id, arm.name, mode);
        const selectedCloud = mode === 'removed_old' ? arm.removed_old : mode === 'added_new' ? arm.added_new : arm.cloud;
        check(s.visibleCounts.update === selectedCloud.display_count, `exact_after_subset_${region.id}_${arm.name}_${mode}`);
        if (region.id === 'P2_visible' && arm.name === region.default_arm && mode === 'source') {
          const palette = await evaluate(`(()=>{const src=document.querySelector('#view-update canvas'),canvas=document.createElement('canvas');canvas.width=src.width;canvas.height=src.height;const ctx=canvas.getContext('2d');ctx.drawImage(src,0,0);const p=ctx.getImageData(0,0,canvas.width,canvas.height).data,colors=[[184,135,66],[38,141,192]],counts=[0,0];for(let i=0;i<p.length;i+=4)for(let j=0;j<2;j++)if(colors[j].every((c,k)=>Math.abs(p[i+k]-c)<=2))counts[j]++;return {retainedALS:counts[0],addedImage:counts[1]};})()`);
          check(palette.retainedALS > 20 && palette.addedImage > 20, 'actual_webgl_srgb_colors_match_source_legend', palette);
        }
        for (const k of ['als', 'image', 'reference']) check(s.visibleCounts[k] === region.methods[k].display_count, `before_reference_unchanged_${region.id}_${arm.name}_${mode}_${k}`);
        for (const section of ['x', 'y']) {
          await choose('section-select', section); const slice = await ready();
          check(slice.sections.update.nativeCount === selectedCloud.sections[section].native_count, `full_native_section_${region.id}_${arm.name}_${mode}_${section}`);
          check(['als', 'image', 'reference'].every(k => slice.sections[k].nativeCount === region.methods[k].sections[section].native_count), `fixed_before_reference_section_${region.id}_${arm.name}_${mode}_${section}`);
        }
      }
    }
    for (const threshold of Object.values(region.evaluation.methods)[0].coverage.thresholds_m) {
      await choose('metric-threshold', threshold);
      const rows = await evaluate("[...document.querySelectorAll('#metrics-body tr')].map(r=>({name:r.dataset.method,values:[...r.cells].map(c=>c.textContent)}))");
      check(rows.length === Object.keys(region.evaluation.methods).length, `all_method_metric_rows_${region.id}_${threshold}`);
      for (const row of rows) {
        const value = region.evaluation.methods[row.name], k = value.coverage.thresholds_m.indexOf(threshold);
        check(row.values[2] === value.to_reference.p90_m.toFixed(3) + ' m' && row.values[3] === value.reference_to.p90_m.toFixed(3) + ' m', `bidirectional_frozen_distance_${region.id}_${row.name}_${threshold}`);
        check(row.values[4] === (100 * value.coverage.precision[k]).toFixed(2) + '%' && row.values[5] === (100 * value.coverage.recall[k]).toFixed(2) + '%', `frozen_precision_recall_${region.id}_${row.name}_${threshold}`);
      }
    }
    await choose('arm-select', region.default_arm); await ready(region.id, region.default_arm);
    await choose('update-mode', 'source'); await ready(null, null, 'source');
    await evaluate("document.getElementById('comparison').scrollIntoView({block:'start'})"); await settle();
    await capture(`desktop_${region.id}_updated_source.png`);
    await evaluate("document.getElementById('section-select').scrollIntoView({block:'start'})"); await settle();
    await capture(`desktop_${region.id}_native_sections.png`);
    await choose('metric-threshold', .5);
    await evaluate("document.getElementById('metrics-card').scrollIntoView({block:'start'})"); await settle();
    await capture(`desktop_${region.id}_metrics.png`);
    if (region.methods.mvs) {
      await evaluate("document.getElementById('context-toggle').click()");
      for (let i = 0; i < 100 && !await evaluate('window.__WV_REGIONS_QA.contextOpen'); i++) await pause(100);
      check(await evaluate('window.__WV_REGIONS_QA.contextOpen===true'), `native_mvs_context_separate_${region.id}`);
      await evaluate("document.getElementById('context-toggle').click()"); await settle();
    }
    if (region.photo) {
      const image = await imagesReady('#master-photo');
      check(image.images[0].width === region.photo.width && image.images[0].height === region.photo.height, `actual_photo_dimensions_${region.id}`);
    }
    for (const figure of region.figures) { await choose('figure-select', figure.id); await imagesReady('#evaluation-figure'); }
    console.log(JSON.stringify({checked_region: region.id, arms: region.arms.length, synchronized_panels: 4}));
  }
  let assets = 0;
  for (const [relative, expected] of Object.entries({...manifest.copied_assets, ...manifest.display_derivatives, 'data.json': manifest.data_json})) {
    const response = await fetch(new URL(relative, url));
    check(response.ok, 'asset_http_' + relative, response.status);
    const bytes = Buffer.from(await response.arrayBuffer()), actual = crypto.createHash('sha256').update(bytes).digest('hex');
    check(actual === expected.sha256 && bytes.length === expected.bytes, 'asset_exact_hash_' + relative, {bytes: bytes.length, sha256: actual});
    assets++;
  }
  await choose('region-select', data.default_region); await ready(data.default_region);
  await choose('update-mode', 'height'); await ready(null, null, 'height');
  await send('Emulation.setDeviceMetricsOverride', {width: 390, height: 844, deviceScaleFactor: 1, mobile: true});
  await evaluate("window.scrollTo({top:0,behavior:'instant'})"); await settle();
  const mobile = await evaluate('({width:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth})');
  check(mobile.scroll <= mobile.width + 1, 'mobile_no_horizontal_overflow', mobile);
  await capture('mobile_overview.png');
  for (const key of ['als', 'image', 'update', 'reference']) {
    await evaluate(`document.getElementById('view-${key}').scrollIntoView({block:'center'})`); await settle();
    check(await evaluate(`document.querySelector('#view-${key} canvas').clientWidth>250`), 'mobile_reachable_' + key);
    await capture('mobile_' + key + '.png');
  }
  const errors = events.filter(e => e.method === 'Runtime.exceptionThrown' ||
    (e.method === 'Runtime.consoleAPICalled' && ['error', 'assert'].includes(e.params.type)) ||
    (e.method === 'Log.entryAdded' && e.params.entry.level === 'error') ||
    (e.method === 'Network.responseReceived' && e.params.response.status >= 400) || e.method === 'Network.loadingFailed');
  check(errors.length === 0, 'no_javascript_console_http_loading_errors', errors);
  const receipt = {status: 'PASS', scientific_verdict: null, native_2026_reproduction: false, url, profile, debug_port: Number(port), browser, checks, screenshots, asset_count: assets,
    regions: data.regions.map(r => r.id), runtime: {node: process.version, execution: 'HOST_BROWSER_QA_INFRASTRUCTURE_NODE_BUILTINS',
      reason: 'Pinned project image lacks Chrome/Node; the dedicated fresh host browser checks only the trusted local viewer. Scientific processing and viewer generation remain Docker.', webgl_backend: 'explicit_swiftshader'},
    existing_browser_profiles_modified: false, server_lifecycle_modified: false};
  await fs.writeFile(path.join(out, 'browser_qa.json'), JSON.stringify(receipt, null, 2) + '\n', {flag: 'wx'});
  console.log(JSON.stringify({status: 'PASS', checks: checks.length, screenshots: screenshots.length, assets}));
} catch (error) {
  await fs.writeFile(path.join(out, 'FAILED.json'), JSON.stringify({error: String(error), checks, screenshots, events, scientific_verdict: null}, null, 2) + '\n', {flag: 'wx'});
  throw error;
} finally { socket.end(); }
