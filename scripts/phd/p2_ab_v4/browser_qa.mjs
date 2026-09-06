// Local browser QA only: Node built-ins and a fresh isolated Chrome profile.
import net from 'node:net';
import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';

const [url, out, profile, port = '9230'] = process.argv.slice(2);
if (!url || !out || !profile?.startsWith('/tmp/jbgs-p2-ab-v4-qa.')) throw Error('Expected URL OUTPUT FRESH_PROFILE [PORT]');
if (!['127.0.0.1', 'localhost'].includes(new URL(url).hostname)) throw Error('Local viewer only');
await fs.mkdir(out, {recursive: false});
await fs.writeFile(path.join(out, 'browser_qa_source.mjs'), await fs.readFile(new URL(import.meta.url)), {flag: 'wx'});
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
  check(data.views.length === 11 && new Set(data.views.map(v => v.image_id)).size === 11, 'all_11_views');
  check(data.models.length === 10 && new Set(data.models.map(m => m.id)).size === 10, 'all_10_models');
  check(initial.selectedModels.join(',') === 'mvs_initial,mvs_sh3_uniform,mvs_sh3_residual_weighted', 'current_mvs_default');
  await capture('roof_overview.png');
  for (const view of data.views) {
    await evaluate(`p2Viewer.setView(${view.image_id})`); await ready();
    const rows = await evaluate(`(async()=>{const view=${JSON.stringify(view)};const rows=[];for(const [key,p] of Object.entries({target:view.target,...view.images})){
      const response=await fetch(p);if(!response.ok)throw Error('image '+response.status);const bytes=await response.arrayBuffer();const im=new Image();im.src=p;await im.decode();
      rows.push({key,path:p,width:im.naturalWidth,height:im.naturalHeight,sha256:[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(x=>x.toString(16).padStart(2,'0')).join('')});}return rows;})()`);
    for (const row of rows) check(row.width === view.width && row.height === view.height && row.sha256 === receipt.output_sha256[row.path], `original_pixels_${view.image_id}_${row.key}`, row);
    for (const m of data.models) {
      await evaluate(`p2Viewer.setModel(0,${JSON.stringify(m.id)})`); const s = await ready();
      check(s.selectedModels[0] === m.id && s.loadedImages.includes(m.id), `selected_model_${view.image_id}_${m.id}`);
      const metric = await evaluate(`document.querySelector('#metric-0 .metric-number').textContent`);
      check(metric === view.metrics[m.id].mae.toFixed(5), `fixed_pixel_metric_${view.image_id}_${m.id}`);
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
  await evaluate(`p2Viewer.setModel(0,'als_initial')`); await ready();
  check((await evaluate('p2ViewerState.zoom')) === 1, 'method_switch_preserves_zoom');
  check((await evaluate(`document.getElementById('metric-0').textContent`)).includes('A 미적용'), 'legacy_als_labeled');
  await evaluate(`p2Viewer.fit()`); await ready(); await capture('roof_als_context.png');
  await evaluate(`p2Viewer.setModel(0,'mvs_initial');p2Viewer.setMode('wipe');p2Viewer.fit()`); await ready();
  await evaluate(`p2Viewer.setWipePosition(.25)`); await ready(); const wipeBefore = await fingerprint('canvas-wipe');
  await evaluate(`p2Viewer.setWipePosition(.75)`); await ready();
  check(wipeBefore !== await fingerprint('canvas-wipe'), 'wipe_changes_actual_pixels'); await capture('roof_wipe.png');
  await evaluate(`document.getElementById('view-window').click()`); await ready();
  check((await evaluate('p2ViewerState.viewId')) === 361, 'window_preset');
  await evaluate(`p2Viewer.setMode('grid');p2Viewer.fit()`); await ready(); await capture('window_support_limit.png');
  await send('Emulation.setDeviceMetricsOverride', {width: 390, height: 844, deviceScaleFactor: 1, mobile: true});
  await pause(150); await ready();
  const mobile = await evaluate(`({width:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth,canvases:[...document.querySelectorAll('#grid-mode canvas')].map(c=>{const r=c.getBoundingClientRect();return {left:r.left,right:r.right,width:r.width}})})`);
  check(mobile.scroll <= mobile.width && mobile.canvases.every(c => c.width > 0 && c.left >= 0 && c.right <= mobile.width + 1), 'mobile_layout', mobile);
  await capture('mobile.png');
  const failures = events.filter(e => e.method === 'Runtime.exceptionThrown' || (e.method === 'Network.responseReceived' && e.params.response.status >= 400) || e.method === 'Network.loadingFailed');
  check(failures.length === 0, 'no_browser_or_http_errors', failures);
  await fs.writeFile(path.join(out, 'browser_qa.json'), JSON.stringify({status: 'PASS', scientific_verdict: null, url, profile, browser, checks, screenshots, original_image_count: 121, view_count: 11, model_count: 10}, null, 2) + '\n', {flag: 'wx'});
  console.log(JSON.stringify({status: 'PASS', checks: checks.length, screenshots: screenshots.length}));
} catch (error) {
  await fs.writeFile(path.join(out, 'FAILED.json'), JSON.stringify({error: String(error), checks, screenshots, events, scientific_verdict: null}, null, 2) + '\n', {flag: 'wx'});
  throw error;
} finally { socket.end(); }
