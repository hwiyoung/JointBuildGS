// Browser QA infrastructure only: Node built-ins, CDP, dedicated Chrome profile.
import net from 'node:net';
import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';

const [url, out, profile, port = '9235'] = process.argv.slice(2);
if (!url || !out || !profile?.startsWith('/tmp/jbgs-wu-p3-qa.')) throw Error('URL OUTPUT FRESH_PROFILE [PORT] required');
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
let browser, copiedAssetCount = 0;
try {
  const command = await send('Browser.getBrowserCommandLine');
  check(command.arguments.includes('--user-data-dir=' + profile), 'dedicated_fresh_profile');
  check(command.arguments.includes('--remote-debugging-port=' + port), 'dedicated_debug_port');
  browser = await send('Browser.getVersion');
  for (const name of ['Page', 'Runtime', 'Network', 'Log']) await send(name + '.enable');
  await send('Emulation.setDeviceMetricsOverride', {width: 1560, height: 1100, deviceScaleFactor: 1, mobile: false});
  await send('Page.navigate', {url});
  const first = await imagesReady(); check(first.count === 5, 'target_and_four_actual_render_panels', first.images);
  const evidence = await evaluate(`JSON.parse(document.getElementById('evidence-data').textContent)`);
  const manifest = await evaluate(`fetch('viewer_manifest.json').then(r=>{if(!r.ok)throw Error('viewer manifest HTTP '+r.status);return r.json()})`);
  check(evidence.viewIds.length === 8 && new Set(evidence.viewIds).size === 8, 'eight_unique_evaluation_views', evidence.viewIds);
  check(evidence.arms.length === 4 && evidence.b.scientific_verdict === null && evidence.evaluation.scientific_verdict === null, 'four_arms_and_null_scientific_verdict');
  check(evidence.b.wu_vallet_original_reproduced === false && evidence.b.actual_A_decision_consumed === false, 'source_conditioned_interpretation');
  const visibleText = await evaluate('document.body.innerText');
  check(visibleText.includes('Wu–Vallet 원방법 전체 미재현') && visibleText.includes('소스별 사용을 가정한 비교') && visibleText.includes('scientific_verdict: null'), 'visible_scope_limits');
  check(await evaluate(`document.getElementById('view-select').options.length===8&&document.querySelectorAll('#metrics-body tr').length===4`), 'view_select_and_metric_rows');
  const maximumSupport = Math.max(...Object.values(evidence.images).map(v => v.display_crop.frozen_union_support_pixels));
  check(evidence.images[String(evidence.defaultViewId)].display_crop.frozen_union_support_pixels === maximumSupport,
    'default_view_uses_maximum_frozen_support_not_performance', {image_id: evidence.defaultViewId, support_pixels: maximumSupport});
  check(await evaluate(`document.getElementById('display-select').value==='crop'&&Number(document.getElementById('view-select').value)===${evidence.defaultViewId}`), 'default_common_crop_and_source_selected_view');
  await capture('desktop_overview.png');

  // Visit both phases at every evaluation view; paths must follow actual copied assets.
  for (const iid of evidence.viewIds) {
    await choose('view-select', iid);
    for (const extent of ['crop', 'full']) {
      await choose('display-select', extent);
      for (const phase of ['initial', 'final']) {
      await evaluate(`document.querySelector('#phase-controls [data-phase="${phase}"]').click()`);
      const loaded = await imagesReady();
      const base = evidence.images[String(iid)], assets = extent === 'crop' ? base.crop : base;
      const expected = [assets.target, ...evidence.arms.map(a => assets.arms[a][phase])];
      check(loaded.images.every((image, i) => image.src === expected[i]), `actual_image_paths_${iid}_${phase}_${extent}`, loaded.images);
      check(loaded.images.every(image => image.width === loaded.images[0].width && image.height === loaded.images[0].height), `matched_image_dimensions_${iid}_${phase}_${extent}`);
      const [x0,y0,x1,y1] = base.display_crop.bbox_xyxy;
      const expectedHW = extent === 'crop' ? [y1-y0,x1-x0] : base.display_crop.original_shape_hw;
      check(loaded.images.every(image => image.width === expectedHW[1] && image.height === expectedHW[0]), `common_crop_dimensions_${iid}_${phase}_${extent}`, {expectedHW});
      const labels = await evaluate(`({selected:document.querySelector('#phase-controls [aria-pressed="true"]').dataset.phase,labels:[...document.querySelectorAll('#gallery .card-head small')].slice(1).map(e=>e.textContent),hint:document.getElementById('gallery-hint').textContent})`);
      check(labels.selected === phase && labels.labels.every(s => s === (phase === 'initial' ? '초기 Gaussian 렌더' : '학습 후 Gaussian 렌더')), `phase_labels_${iid}_${phase}_${extent}`, labels);
      }
    }
    console.log(JSON.stringify({checked_view: iid, phases: 2, display_extents: 2, panels_per_phase: 5}));
  }
  await choose('display-select', 'crop');

  // Validate displayed scalar values against the immutable JSON rather than DOM presence alone.
  for (const phase of ['initial', 'final']) {
    await evaluate(`document.querySelector('#phase-controls [data-phase="${phase}"]').click()`);
    for (const mask of ['union', 'intersection']) {
      await choose('mask-select', mask);
      const comparison = await evaluate(`(()=>{const d=JSON.parse(document.getElementById('evidence-data').textContent),rows=[...document.querySelectorAll('#metrics-body tr')],f=x=>x===null||x===undefined?'—':Number(x).toLocaleString('ko-KR',{maximumFractionDigits:3,minimumFractionDigits:3});return rows.map((row,i)=>({arm:d.arms[i],displayed:row.cells[2].textContent,expected:f(d.b.arms.find(a=>a.arm===d.arms[i])[${JSON.stringify(phase)}].aggregate[${JSON.stringify(mask)}].mae),geometry:row.cells[4].textContent,missing:row.cells[3].textContent}));})()`);
      check(comparison.every(row => row.displayed === row.expected), `json_backed_metric_values_${phase}_${mask}`, comparison);
      await evaluate(`document.getElementById('overlay-toggle').checked=true;document.getElementById('overlay-toggle').dispatchEvent(new Event('change',{bubbles:true}))`);
      await imagesReady('#gallery img.mask');
      const overlay = await evaluate(`[...document.querySelectorAll('#gallery img.mask')].map(i=>({hidden:i.hidden,src:i.getAttribute('src'),opacity:getComputedStyle(i).opacity}))`);
      check(overlay.length === 5 && overlay.every(i => !i.hidden && i.src.endsWith('/' + mask + '_support.png') && Number(i.opacity) > 0), `fixed_${mask}_mask_overlay_${phase}`, overlay);
    }
  }
  await capture('desktop_mask_overlay.png');
  await evaluate(`document.getElementById('overlay-toggle').checked=false;document.getElementById('overlay-toggle').dispatchEvent(new Event('change',{bubbles:true}))`);
  check(await evaluate(`[...document.querySelectorAll('#gallery img.mask')].every(i=>i.hidden)`), 'mask_overlay_off');
  await choose('mask-select', 'union');
  await choose('view-select', evidence.defaultViewId);
  await evaluate(`document.querySelector('#gallery .photo-button').click()`);
  await imagesReady('#zoom-image');
  check(await evaluate(`document.getElementById('zoom').open&&document.getElementById('zoom-title').textContent==='현재 사진'`), 'actual_photo_zoom_dialog');
  await capture('desktop_photo_zoom.png');
  await evaluate(`document.getElementById('zoom-close').click()`);
  check(!(await evaluate(`document.getElementById('zoom').open`)), 'zoom_close');

  const figureTabs = await evaluate(`[...document.querySelectorAll('#figure-tabs button')].map(b=>({kind:b.dataset.kind,text:b.textContent}))`);
  check(figureTabs.length === 6, 'six_geometry_evidence_tabs');
  for (const tab of figureTabs) {
    await evaluate(`document.querySelector('#figure-tabs [data-kind=${JSON.stringify(tab.kind)}]').click()`);
    const loaded = await imagesReady('#figure-image');
    check(loaded.count === 1 && loaded.images[0].src.startsWith('figures/'), `actual_figure_${tab.kind}`, loaded.images);
    check(await evaluate(`document.querySelector('#figure-tabs [aria-pressed="true"]').dataset.kind===${JSON.stringify(tab.kind)}`), `figure_selected_${tab.kind}`);
    if (tab.kind === 'arm-section') {
      for (const arm of evidence.arms) {
        await choose('section-select', arm);
        const section = await imagesReady('#figure-image');
        check(section.images[0].src.endsWith('/cross_sections_' + arm + '.png'), `initial_final_section_${arm}`);
      }
    }
  }
  await evaluate(`document.querySelector('#figure-tabs [data-kind="source"]').click();document.getElementById('geometry-title').scrollIntoView({block:'start'})`);
  await imagesReady('#figure-image'); await capture('desktop_source_map.png');
  await evaluate(`document.querySelector('#figure-tabs [data-kind="arm-section"]').click()`);
  await choose('section-select', 'als_bounded_normal'); await imagesReady('#figure-image'); await capture('desktop_initial_final_section.png');

  // Every copied image/receipt is fetched and SHA256 checked from the served gallery.
  for (const [asset, expected] of Object.entries({...manifest.copied_assets,...manifest.display_derivatives})) {
    const actual = await evaluate(`(async()=>{const r=await fetch(${JSON.stringify(asset)});if(!r.ok)throw Error('Asset HTTP '+r.status);const bytes=await r.arrayBuffer();return {bytes:bytes.byteLength,sha256:[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(x=>x.toString(16).padStart(2,'0')).join('')}})()`);
    check(actual.sha256 === expected.sha256 && actual.bytes === expected.bytes, `copied_asset_integrity_${asset}`, actual);
    copiedAssetCount++;
  }

  await send('Emulation.setDeviceMetricsOverride', {width: 390, height: 844, deviceScaleFactor: 1, mobile: true});
  await evaluate(`window.scrollTo({top:0,behavior:'instant'})`); await settle();
  const mobile = await evaluate(`(()=>{const r=document.getElementById('gallery');return {viewport:document.documentElement.clientWidth,page:document.documentElement.scrollWidth,railClient:r.clientWidth,railScroll:r.scrollWidth,cards:r.children.length}})()`);
  check(mobile.page <= mobile.viewport + 1 && mobile.railScroll > mobile.railClient && mobile.cards === 5, 'mobile_page_fits_and_gallery_scrolls', mobile);
  await capture('mobile_overview.png');
  await evaluate(`document.getElementById('render-title').scrollIntoView({block:'start'});document.getElementById('gallery').scrollLeft=10000`); await settle();
  check(await evaluate(`document.getElementById('gallery').scrollLeft>0`), 'mobile_all_method_cards_reachable'); await capture('mobile_last_method.png');
  await choose('view-select', evidence.viewIds.at(-1)); await imagesReady();
  await evaluate(`document.querySelector('#phase-controls [data-phase="initial"]').click()`); await imagesReady();
  check(await evaluate(`document.querySelector('#phase-controls [aria-pressed="true"]').dataset.phase==='initial'`), 'mobile_view_and_phase_controls');
  await evaluate(`document.getElementById('metric-title').scrollIntoView({block:'start'})`); await settle(); await capture('mobile_metrics.png');
  await evaluate(`document.getElementById('geometry-title').scrollIntoView({block:'start'})`); await imagesReady('#figure-image'); await capture('mobile_geometry.png');
  const errors = events.filter(e => e.method === 'Runtime.exceptionThrown' ||
    (e.method === 'Runtime.consoleAPICalled' && ['error', 'assert'].includes(e.params.type)) ||
    (e.method === 'Log.entryAdded' && e.params.entry.level === 'error') ||
    (e.method === 'Network.responseReceived' && e.params.response.status >= 400) ||
    e.method === 'Network.loadingFailed');
  check(errors.length === 0, 'no_console_javascript_http_or_loading_errors', errors);
  const receipt = {status: 'PASS', scientific_verdict: null, url, profile, debug_port: Number(port), browser,
    checks, screenshots, copied_asset_count: copiedAssetCount, view_count: 8, render_arm_count: 4,
    runtime: {node: process.version, execution: 'HOST_BROWSER_QA_INFRASTRUCTURE_NODE_BUILTINS',
      reason: 'Pinned jointbuildgs:dev has no node or Chrome; source processing/build/training/evaluation run in Docker; this harness drives only a fresh host browser profile'},
    server_lifecycle_modified: false, existing_browser_profiles_modified: false};
  await fs.writeFile(path.join(out, 'browser_qa.json'), JSON.stringify(receipt, null, 2) + '\n', {flag: 'wx'});
  console.log(JSON.stringify({status: 'PASS', checks: checks.length, screenshots: screenshots.length, assets: copiedAssetCount}));
} catch (error) {
  await fs.writeFile(path.join(out, 'FAILED.json'), JSON.stringify({error: String(error), checks, screenshots, events, scientific_verdict: null}, null, 2) + '\n', {flag: 'wx'});
  throw error;
} finally { socket.end(); }
