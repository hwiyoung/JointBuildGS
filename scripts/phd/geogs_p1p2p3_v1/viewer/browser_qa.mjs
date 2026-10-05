// Runs in the dedicated browser Docker image, against actual local exports only.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {spawn} from 'node:child_process';

const [url, output = '/out'] = process.argv.slice(2);
if (!url || !['127.0.0.1', 'localhost'].includes(new URL(url).hostname)) throw Error('Actual local viewer URL required');
const requestedMode = new URL(url).searchParams.get('qa_mode');
const qaMode = requestedMode || ((new URL(url).searchParams.get('manifest') || '').includes('/viewer_preflight/') ? 'preflight' : 'full');
if (!['preflight', 'full'].includes(qaMode)) throw Error('qa_mode must be preflight or full');
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const profile = await fs.mkdtemp('/tmp/geogs-browser-');
const chromeLog = [];
const virtualDisplay = spawn('/usr/bin/Xvfb', ['-displayfd', '1', '-screen', '0', '1800x1240x24', '-nolisten', 'tcp']);
virtualDisplay.stderr.on('data', chunk => chromeLog.push('Xvfb: ' + chunk));
const displayNumber = await new Promise((resolve, reject) => {
  const timeout = setTimeout(() => reject(Error('Dedicated Xvfb start timeout')), 10000);
  virtualDisplay.stdout.once('data', bytes => { clearTimeout(timeout); const value = bytes.toString().trim(); /^\d+$/.test(value) ? resolve(value) : reject(Error('Invalid dedicated display number')); });
  virtualDisplay.once('exit', code => { clearTimeout(timeout); reject(Error('Dedicated Xvfb exited: ' + code)); });
});
for (const suffix of ['config', 'cache', 'data']) await fs.mkdir(profile + '/' + suffix);
const chromeArgs = ['--headless=new', '--no-sandbox', '--no-first-run', '--no-default-browser-check', '--enable-automation', '--disable-dev-shm-usage', '--ozone-platform=headless', '--use-gl=angle', '--use-angle=gl', '--ignore-gpu-blocklist', '--disable-vulkan', '--remote-debugging-address=127.0.0.1', '--remote-debugging-port=0', '--user-data-dir=' + profile, 'about:blank'];
const browser = spawn(process.env.CHROME_BIN || '/usr/bin/chromium', chromeArgs, {env: {...process.env, DISPLAY: ':' + displayNumber, LIBGL_ALWAYS_SOFTWARE: '1', XDG_CONFIG_HOME: profile + '/config', XDG_CACHE_HOME: profile + '/cache', XDG_DATA_HOME: profile + '/data'}});
browser.stderr.on('data', chunk => chromeLog.push(chunk.toString()));
let socket, sequence = 0, manifestResolutions = [];
const pending = new Map(), events = [], checks = [], screenshots = [];
const receipt = {schema: 'geogs_viewer_browser_qa_v4', started_at: new Date().toISOString(), url, qa_mode: qaMode, image_id: process.env.GEOGS_QA_IMAGE_ID, chrome_args: chromeArgs, dedicated_xvfb_display: displayNumber, software_webgl: 'Dedicated container Xvfb + ANGLE GL with LIBGL_ALWAYS_SOFTWARE=1; no existing host X or GPU access', scientific_verdict: null, actual_data_only: true, checks, screenshots, regions: [], controls: [], filter_gallery_casepoints: [], recorded_cases: [], coverage_policy: {surfaces: 'all registered regions, conditions, resolutions and supported raw/post surfaces in both points and mesh modes; exact registered triangles or explicit point-only fallback; no resolution fallback on resource failure', rasterization: 'nonbackground WebGL pixels at every surface/representation matrix state, plus actual renderer draw calls and primitive counts', representations: ['points', 'mesh'], cases_per_region_max: 3, section_selections_per_region_max: 3, render_domains_per_region_max: 3, photos_per_domain_max: 2, comparisons_per_photo_max: 2, screenshots_per_region_max: 7, mesh_screenshots_per_region_max: 1, mesh_screenshot_selection: 'native raw at first registered 1024/512 resolution with a registered available native mesh; deterministic order, no quality ranking', selection: 'deterministic first/middle/last in registered order; no image-quality or outcome ranking', unavailable_geometry: 'explicit reconstruction_failure, reference_unavailable, failed or technical_resource_unavailable stays visible; full mode rejects pending', asynchronous_generation_guards: 'covered by the separate synthetic delayed-response QA; this actual-data run does not inject timing changes'}};
function check(pass, name, details) { checks.push({name, pass: !!pass, details}); if (!pass) throw Error(name); }
receipt.coverage_policy.sections_per_recorded_case_max = 2;
receipt.coverage_policy.renders_per_recorded_case_max = 1;
receipt.coverage_policy.reference_absence_boundary = 'no_geometry_reference_absent retains the exact visible no-geometry/no-reference reason and zero display primitives, without a reconstruction-failure or zero-score interpretation; positive geometry without reference remains available';
receipt.coverage_policy.mesh_screenshot_requirement = 'Required iff a native raw candidate at a selected registered resolution has status available and mesh_data; otherwise explicit no-available-native-mesh state evidence, without a quality verdict';
receipt.mesh_screenshot_availability = [];
function send(method, params = {}) {
  const id = ++sequence;
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => { pending.delete(id); reject(Error('CDP timeout: ' + method)); }, 30000);
    pending.set(id, {resolve: value => { clearTimeout(timeout); resolve(value); }, reject: error => { clearTimeout(timeout); reject(error); }});
    socket.send(JSON.stringify({id, method, params}));
  });
}
async function evaluate(expression) {
  const result = await send('Runtime.evaluate', {expression, returnByValue: true, awaitPromise: true});
  if (result.exceptionDetails) throw Error(JSON.stringify(result.exceptionDetails));
  return result.result?.value;
}
async function ready(id, condition, expected = {}) {
  for (let i = 0; i < 600; i++) {
    const q = await evaluate('window.__GEOGS_QA || null');
    if (q?.errors?.length) throw Error(JSON.stringify(q.errors));
    if (q?.ready && (!id || q.region === id) && (!condition || q.condition === condition) && Object.entries(expected).every(([key, value]) => q[key] === value)) return q;
    await pause(100);
  }
  throw Error('Viewer actual data load timed out');
}
async function choose(id, value) {
  await evaluate(`(()=>{const el=document.getElementById(${JSON.stringify(id)});if(!el||![...el.options].some(option=>option.value===${JSON.stringify(value)}&&!option.disabled))throw Error('QA option missing or disabled: '+${JSON.stringify(id)});el.value=${JSON.stringify(value)};el.dispatchEvent(new Event('change',{bubbles:true}));})()`);
}
async function selectState(id) {
  return evaluate(`(()=>{const el=document.getElementById(${JSON.stringify(id)});return el?{value:el.value,disabled:el.disabled,options:[...el.options].map(option=>({value:option.value,disabled:option.disabled}))}:null})()`);
}
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const nearVector = (a, b) => Array.isArray(a) && a.length === b.length && a.every((value, index) => Math.abs(value - b[index]) < 1e-8);
function bounded(values, limit) {
  if (values.length <= limit) return values;
  return [...new Set(Array.from({length: limit}, (_, index) => Math.round(index * (values.length - 1) / (limit - 1))))].map(index => values[index]);
}
function expectedPanels(spec, condition, surface, prior, resolutionID) {
  const ids = {...spec.panel_candidates, changed: spec.conditions?.find(item => item.id === condition)?.candidate_id || null};
  const resolution = manifestResolutions.find(item => item.id === resolutionID);
  for (const key of ['anchor', 'vanilla', 'changed']) {
    if (!ids[key]) continue;
    if (resolution) {
      const parts = ids[key].split('.');
      if (parts.length < 3) throw Error('Invalid QA manifest surface candidate: ' + ids[key]);
      parts[parts.length - 2] = key === 'anchor' ? resolution.anchor_variant : resolution.final_variant;
      parts[parts.length - 1] = surface;
      ids[key] = parts.join('.');
    } else if (/\.(raw|post)$/.test(ids[key])) ids[key] = ids[key].replace(/\.(raw|post)$/, '.' + surface);
  }
  if (prior === 'points') ids.prior = 'als_points';
  else if (spec.candidates.some(item => item.id === 'prior_mesh')) ids.prior = 'prior_mesh';
  return ids;
}
function assertPanels(state, spec, condition, surface, prior, point) {
  const resolution = manifestResolutions.find(item => item.id === state.resolution_mode);
  check(manifestResolutions.length ? !!resolution && state.mesh_res === resolution.mesh_res : state.resolution_mode === null && state.mesh_res === null, 'qa_resolution_matches_declared_mode', {region: spec.id, point, resolution_mode: state.resolution_mode, mesh_res: state.mesh_res});
  const expected = expectedPanels(spec, condition, surface, prior, state.resolution_mode);
  for (const key of ['prior', 'mvs', 'anchor', 'vanilla', 'changed', 'reference']) {
    const actual = state.panels[key], meta = spec.candidates.find(item => item.id === expected[key]);
    check(actual?.candidate === (expected[key] || null), 'panel_candidate_matches_selected_manifest_record', {region: spec.id, condition, surface, prior, point, panel: key, expected: expected[key] || null, actual});
    const allowed = ['available', 'reference_unavailable', 'no_geometry_reference_absent', 'reconstruction_failure', 'failed', 'technical_resource_unavailable', 'TECHNICAL_RESOURCE_UNAVAILABLE', ...(qaMode === 'preflight' ? ['pending'] : [])];
    check(allowed.includes(actual.status) && actual.status === (meta?.status || 'pending'), 'panel_status_matches_explicit_artifact_state', {region: spec.id, point, panel: key, status: actual.status});
    check(actual.status === 'available' ? actual.count > 0 && actual.display_only === true : actual.count === 0, 'available_samples_or_explicit_absence', {region: spec.id, point, panel: key, status: actual.status, count: actual.count});
    if (actual.status === 'failed' || /resource_unavailable/i.test(actual.status)) check(typeof meta.reason === 'string' && meta.reason.length > 0 && actual.reason === meta.reason, 'failed_candidate_retains_explicit_reason_without_resolution_fallback', {region: spec.id, point, panel: key, candidate: actual.candidate, reason: actual.reason});
    if (actual.status === 'no_geometry_reference_absent') check(meta.reason === '표시 기하 없음 · 참조 부재로 품질평가 불가' && actual.reason === meta.reason,
      'absent_geometry_without_reference_is_explicitly_unevaluable_not_reconstruction_failure', {region: spec.id, point, panel: key, status: actual.status, reason: actual.reason});
    if (actual.status === 'available') {
      const expectedRepresentation = state.representation_mode === 'mesh' && meta.mesh_data ? 'mesh' : 'points';
      check(actual.representation === expectedRepresentation && actual.requested_representation === state.representation_mode,
        'actual_panel_representation_matches_registered_data_and_requested_mode', {region: spec.id, point, panel: key, expected: expectedRepresentation, actual: actual.representation, requested: state.representation_mode});
      if (expectedRepresentation === 'mesh') {
        const mesh = actual.loaded_metadata?.mesh;
        check(actual.draw_calls > 0 && actual.rendered_triangles > 0 && actual.rendered_triangles === actual.mesh_triangle_count &&
          actual.mesh_triangle_count === mesh?.triangle_count && actual.mesh_vertex_count === mesh?.vertex_count &&
          actual.renderer_info?.render?.triangles === actual.rendered_triangles && actual.renderer_info?.render?.calls === actual.draw_calls &&
          actual.rendered_points === 0 && mesh?.representation === 'EXACT_EVALUATION_CLIPPED_TRIANGLES' &&
          mesh.display_only === true && mesh.topology_simplified === false && mesh.artificial_clip_caps === false,
        'registered_exact_mesh_actually_draws_all_declared_triangles', {region: spec.id, point, panel: key, triangles: actual.rendered_triangles, metadata_triangles: mesh?.triangle_count, draw_calls: actual.draw_calls, renderer_info: actual.renderer_info});
      } else {
        check(actual.draw_calls > 0 && actual.rendered_points === actual.count && actual.rendered_triangles === 0 &&
          actual.display_sample_count === actual.count && actual.renderer_info?.render?.points === actual.count,
        'point_representation_actually_draws_loaded_display_samples', {region: spec.id, point, panel: key, count: actual.count, rendered_points: actual.rendered_points, draw_calls: actual.draw_calls});
        if (state.representation_mode === 'mesh') check(!meta.mesh_data && actual.representation_fallback === 'NO_REGISTERED_MESH_DATA',
          'point_only_source_has_explicit_mesh_mode_fallback', {region: spec.id, point, panel: key, fallback: actual.representation_fallback});
      }
    } else check(actual.representation === 'none' && actual.rendered_triangles === 0 && actual.rendered_points === 0,
      'unavailable_candidate_does_not_reuse_previous_geometry', {region: spec.id, point, panel: key, representation: actual.representation});
  }
  check(cameraSync(state), 'selected_control_preserves_shared_camera', {region: spec.id, point});
  receipt.controls.push({region: spec.id, condition, point, surface, prior, representation_mode: state.representation_mode, resolution_mode: state.resolution_mode, mesh_res: state.mesh_res, expected_panels: expected, panels: state.panels});
}
async function checkFailureMessages(state) {
  const messages = await evaluate(`Object.fromEntries([...document.querySelectorAll('.panel')].map(panel=>{const message=panel.querySelector('.missing');return [panel.dataset.panel,{hidden:message.hidden,text:message.textContent,status:panel.querySelector('.status').dataset.status}]}))`);
  for (const [key, panel] of Object.entries(state.panels)) if (panel.status === 'failed' || panel.status === 'no_geometry_reference_absent' || /resource_unavailable/i.test(panel.status)) check(messages[key]?.status === panel.status && !messages[key].hidden && messages[key].text === panel.reason, 'unavailable_geometry_or_extraction_reason_actually_visible_in_panel', {region: state.region, condition: state.condition, resolution_mode: state.resolution_mode, representation_mode: state.representation_mode, surface: state.surface_mode, panel: key, message: messages[key]});
}
async function checkRasterizedPanels(state, point) {
  const webgl = await evaluate(`(()=>{return [...document.querySelectorAll('.panel')].map(panel=>{const c=panel.querySelector('canvas'),gl=c.getContext('webgl2')||c.getContext('webgl');if(!gl)return {panel:panel.dataset.panel,webgl:false};const pixels=new Uint8Array(c.width*c.height*4);gl.readPixels(0,0,c.width,c.height,gl.RGBA,gl.UNSIGNED_BYTE,pixels);let differing=0;for(let i=4;i<pixels.length;i+=4)if(pixels[i]!==pixels[0]||pixels[i+1]!==pixels[1]||pixels[i+2]!==pixels[2])differing++;return {panel:panel.dataset.panel,webgl:true,differing_pixels:differing,width:c.width,height:c.height}})})()`);
  for (const panel of webgl) check(panel.webgl && (state.panels[panel.panel]?.count === 0 || panel.differing_pixels > 10), 'available_surface_actually_rasterized', {region: state.region, condition: state.condition, resolution_mode: state.resolution_mode, representation_mode: state.representation_mode, point, ...panel});
}
async function settleImages() {
  for (let i = 0; i < 300; i++) {
    const state = await evaluate(`(()=>{const images=[...document.querySelectorAll('figure:not([hidden]) img')];return {all:images.every(x=>x.complete&&x.naturalWidth>0),images:images.map(x=>({src:x.src,width:x.naturalWidth,height:x.naturalHeight}))}})()`);
    if (state.all) return state.images;
    await pause(100);
  }
  throw Error('Actual evidence figure did not load');
}
async function capture(name) {
  await evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))');
  const result = await send('Page.captureScreenshot', {format: 'png', captureBeyondViewport: false});
  const bytes = Buffer.from(result.data, 'base64'); await fs.writeFile(path.join(output, name), bytes, {flag: 'wx'});
  screenshots.push({filename: name, sha256: crypto.createHash('sha256').update(bytes).digest('hex')});
}
function cameraSync(q) {
  const cameras = Object.values(q.cameras), first = cameras[0];
  return cameras.length === 6 && cameras.every(c => JSON.stringify(c.position) === JSON.stringify(first.position) && JSON.stringify(c.target) === JSON.stringify(first.target) && Math.abs(c.meters_per_pixel - first.meters_per_pixel) < 1e-9);
}
async function galleryPoint(spec, condition, manifestURL, point) {
  const images = await settleImages();
  const snapshot = await evaluate(`(()=>{const qa=window.__GEOGS_QA;const control=id=>{const el=document.getElementById(id);return {value:el.value,disabled:el.disabled,options:[...el.options].map(option=>option.value)}};const figure=kind=>({id:document.getElementById(kind+'-select').value,hidden:document.getElementById(kind+'-figure').hidden,src:document.getElementById(kind+'-image').getAttribute('src'),href:document.getElementById(kind+'-link').href,caption:document.getElementById(kind+'-caption').textContent});return {region:qa.region,condition:qa.condition,gallery_filter:qa.gallery_filter,gallery_registered_count:qa.gallery_registered_count,domain:control('render-domain-select'),photo:control('render-image-select'),render:control('render-select'),section:control('section-select'),render_figure:figure('render'),section_figure:figure('section'),images_with_src:document.querySelectorAll('figure img[src]').length}})()`);
  const all = (spec.renders || []).filter(item => !item.condition_id || item.condition_id === condition);
  const domains = [...new Set(all.map(item => item.domain || 'unspecified'))];
  const scoped = all.filter(item => (item.domain || 'unspecified') === snapshot.domain.value);
  const photos = [...new Set(scoped.map(item => item.image_name || item.id))];
  const rendered = scoped.filter(item => (item.image_name || item.id) === snapshot.photo.value);
  const sections = (spec.sections || []).filter(item => !item.condition_id || item.condition_id === condition);
  check(snapshot.region === spec.id && snapshot.condition === condition && snapshot.gallery_registered_count === all.length, 'gallery_condition_and_registered_count_match_manifest', {region: spec.id, point, actual: snapshot.gallery_registered_count, expected: all.length});
  check(same(snapshot.domain.options, domains) && same(snapshot.photo.options, photos) && same(snapshot.render.options, rendered.map(item => item.id)) && same(snapshot.section.options, sections.map(item => item.id)), 'gallery_options_match_condition_domain_and_photo', {region: spec.id, point, domain: snapshot.domain, photo: snapshot.photo, render: snapshot.render, section: snapshot.section});
  check(same(snapshot.gallery_filter, {domain: snapshot.domain.value, image_name: snapshot.photo.value}), 'gallery_qa_filter_matches_controls', {region: spec.id, point, filter: snapshot.gallery_filter});
  for (const [kind, items] of [['render', rendered], ['section', sections]]) {
    const figure = snapshot[kind + '_figure'], selected = items.find(item => item.id === figure.id);
    const expectedURL = selected ? new URL(selected.url || selected.path, manifestURL).href : null;
    check(selected ? !figure.hidden && figure.src === expectedURL && figure.href === expectedURL && images.some(image => image.src === expectedURL && image.width > 0 && image.height > 0) : figure.hidden && !figure.src, 'selected_actual_figure_url_loaded_or_explicitly_absent', {region: spec.id, point, kind, selected_id: selected?.id || null, comparison_family: selected?.comparison_family || null, expected_url: expectedURL, figure});
    if (selected?.comparison_family) {
      const family = {primary_1024: '주 최종 비교 · 1024', anchor_refinement_512: 'Anchor/refinement 동일 해상도 · 512'}[selected.comparison_family] || selected.comparison_family;
      check(figure.caption.includes('그림 비교 범위: ' + family), 'selected_figure_declares_its_own_comparison_family', {region: spec.id, point, kind, comparison_family: selected.comparison_family});
    }
  }
  check(snapshot.images_with_src <= 2, 'gallery_fetches_only_selected_section_and_render', {region: spec.id, point, images_with_src: snapshot.images_with_src});
  receipt.filter_gallery_casepoints.push({region: spec.id, condition, point, snapshot, images});
  return snapshot;
}
async function checkControlsAndGallery(spec, manifestURL) {
  const region = spec.id;
  const native = spec.conditions?.find(item => item.id === 'D005_Pnative') || spec.conditions?.[0];
  if (native) await choose('condition-select', native.id);
  let state = await ready(region, native?.id);
  const surface = await selectState('surface-select'), prior = await selectState('prior-select');
  if (qaMode === 'full') {
    check(surface && !surface.disabled && ['raw', 'post'].every(value => surface.options.some(option => option.value === value && !option.disabled)), 'full_result_supports_raw_and_post', region);
    check(prior && ['mesh', 'points'].every(value => prior.options.some(option => option.value === value && !option.disabled)), 'full_result_supports_ALS_surface_and_original_points', region);
  }
  if (prior?.options.some(option => option.value === 'points' && !option.disabled)) {
    const cameras = state.cameras;
    await choose('prior-select', 'points'); state = await ready(region, native?.id, {prior_source: 'points'});
    assertPanels(state, spec, state.condition, state.surface_mode, 'points', 'ALS_original_points');
    check(same(cameras, state.cameras), 'ALS_representation_switch_keeps_identical_camera', region);
    if (surface && !surface.disabled) {
      await choose('surface-select', 'post'); state = await ready(region, native?.id, {surface_mode: 'post'});
      assertPanels(state, spec, state.condition, 'post', 'points', 'post_with_ALS_original_points');
    }
    await capture(`${region}_post_ALS_points.png`);
    await choose('prior-select', 'mesh'); state = await ready(region, native?.id, {prior_source: 'mesh'});
    assertPanels(state, spec, state.condition, state.surface_mode, 'mesh', 'ALS_converted_surface_restored');
  } else receipt.controls.push({region, point: 'ALS_original_points', skipped: 'Option absent or disabled in preflight'});
  if (surface && !surface.disabled) { await choose('surface-select', 'raw'); await ready(region, native?.id, {surface_mode: 'raw'}); }
  const records = spec.cases || [];
  if (qaMode === 'full') check(records.length > 0, 'full_result_has_recorded_cases', region);
  const selectedCases = bounded(records, 3);
  for (let index = 0; index < selectedCases.length; index++) {
    const item = selectedCases[index];
    const caseCondition = item.condition_id || state.condition;
    await choose('case-select', item.id); state = await ready(region, caseCondition);
    check(state.case?.id === item.id && nearVector(state.case.center, item.center) && state.case.extent_m === item.extent_m, 'selected_case_matches_recorded_center_and_extent', {region, case: item, qa_case: state.case});
    check(cameraSync(state) && Object.values(state.cameras).every(camera => nearVector(camera.target, item.center)), 'recorded_case_targets_all_six_cameras', {region, case_id: item.id, cameras: state.cameras});
    const aspects = await evaluate(`Object.fromEntries([...document.querySelectorAll('.panel')].map(panel=>{const host=panel.querySelector('.viewport');return [panel.dataset.panel,Math.max(1,host.clientHeight/host.clientWidth)]}))`);
    check(Object.entries(state.cameras).every(([key, camera]) => Math.abs((camera.top - camera.bottom) - item.extent_m * aspects[key]) < 1e-8), 'recorded_case_uses_common_metric_extent_with_declared_viewport_aspect', {region, case_id: item.id, extent_m: item.extent_m, viewport_aspect_factors: aspects});
    assertPanels(state, spec, state.condition, state.surface_mode, state.prior_source, 'recorded_case:' + item.id);
    if (index === 0 && manifestResolutions.length) {
      const originalResolution = state.resolution_mode, cameras = state.cameras, recordedCase = state.case;
      for (const resolution of manifestResolutions) {
        await choose('resolution-select', resolution.id); state = await ready(region, caseCondition, {resolution_mode: resolution.id, mesh_res: resolution.mesh_res});
        assertPanels(state, spec, state.condition, state.surface_mode, state.prior_source, 'recorded_case_resolution:' + item.id);
        check(same(cameras, state.cameras) && same(recordedCase, state.case), 'resolution_switch_keeps_recorded_case_focus_and_metric_scale', {region, case_id: item.id, resolution_mode: resolution.id, cameras: state.cameras, recorded_case: state.case});
        await checkFailureMessages(state);
        if (resolution.id === '512') await capture(`${region}_recorded_case_512.png`);
      }
      await choose('resolution-select', originalResolution); state = await ready(region, caseCondition, {resolution_mode: originalResolution});
    }
    const description = await evaluate(`({hidden:document.getElementById('case-description').hidden,text:document.getElementById('case-description').textContent})`);
    check(!description.hidden && description.text.length > 0, 'recorded_case_description_visible', {region, case_id: item.id, description});
    const sections = bounded((spec.sections || []).filter(figure => figure.case_id === item.id && (!figure.condition_id || figure.condition_id === state.condition)), 2);
    const render = (spec.renders || []).find(figure => figure.case_id === item.id && (!figure.condition_id || figure.condition_id === state.condition));
    if (render) {
      await choose('render-domain-select', render.domain || 'unspecified');
      await choose('render-image-select', render.image_name || render.id);
      await choose('render-select', render.id);
    }
    for (const section of sections.length ? sections : [null]) {
      if (section) await choose('section-select', section.id);
      const snapshot = await galleryPoint(spec, state.condition, manifestURL, 'recorded_case:' + item.id + ':' + (section?.comparison_family || 'legacy'));
      if (section) check(snapshot.section.value === section.id, 'recorded_case_section_matches_exact_case_id', {region, case_id: item.id, section_id: section.id, comparison_family: section.comparison_family || null});
      if (render) check(snapshot.render.value === render.id, 'recorded_case_render_matches_exact_case_id', {region, case_id: item.id, render_id: render.id});
    }
    receipt.recorded_cases.push({region, selected: item, state, section_ids: sections.map(section => section.id), render_id: render?.id || null, description});
    if (index === 0 && !manifestResolutions.some(resolution => resolution.id === '512')) await capture(`${region}_recorded_case.png`);
  }
  await choose('case-select', ''); state = await ready(region);
  const midpoint = spec.bounds.min.map((value, index) => (value + spec.bounds.max[index]) / 2);
  check(state.case === null && cameraSync(state) && nearVector(state.cameras.prior.target, midpoint), 'clear_case_restores_region_center', region);
  if (native) { await choose('condition-select', native.id); state = await ready(region, native.id); }
  const condition = state.condition;
  const sections = (spec.sections || []).filter(item => !item.condition_id || item.condition_id === condition);
  const gallery = (spec.renders || []).filter(item => !item.condition_id || item.condition_id === condition);
  if (qaMode === 'full') check(sections.length > 0 && gallery.length > 0, 'full_result_has_actual_sections_and_render_gallery', {region, sections: sections.length, renders: gallery.length});
  for (const item of bounded(sections, 3)) {
    await choose('section-select', item.id);
    const snapshot = await galleryPoint(spec, condition, manifestURL, 'section:' + item.id);
    check(snapshot.section.value === item.id, 'section_selector_switches_to_requested_record', {region, selected_id: item.id});
  }
  const domains = [...new Set(gallery.map(item => item.domain || 'unspecified'))];
  for (const domain of bounded(domains, 3)) {
    await choose('render-domain-select', domain);
    const scoped = gallery.filter(item => (item.domain || 'unspecified') === domain);
    const photos = [...new Set(scoped.map(item => item.image_name || item.id))];
    for (const photo of bounded(photos, 2)) {
      await choose('render-image-select', photo);
      const comparisons = scoped.filter(item => (item.image_name || item.id) === photo);
      for (const item of bounded(comparisons, 2)) {
        await choose('render-select', item.id);
        const snapshot = await galleryPoint(spec, condition, manifestURL, 'render:' + item.id);
        check(snapshot.domain.value === domain && snapshot.photo.value === photo && snapshot.render.value === item.id, 'render_domain_photo_and_comparison_switch_to_requested_records', {region, domain, photo, selected_id: item.id});
      }
    }
  }
  if (gallery.length || sections.length) {
    await evaluate(`document.getElementById('render-figure').hidden?document.getElementById('section-figure').scrollIntoView({block:'center'}):document.getElementById('render-figure').scrollIntoView({block:'center'})`);
    await capture(`${region}_selected_evidence_gallery.png`);
    await evaluate('window.scrollTo(0,0)');
  }
}
try {
  let port;
  for (let i = 0; i < 150; i++) { try { port = (await fs.readFile(path.join(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0]; break; } catch { await pause(100); } }
  if (!port) throw Error('Dedicated container Chromium did not start');
  const pages = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  const page = pages.find(p => p.type === 'page'); if (!page) throw Error('Dedicated Chromium page absent');
  socket = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { socket.addEventListener('open', resolve, {once: true}); socket.addEventListener('error', reject, {once: true}); });
  socket.addEventListener('message', event => { const m = JSON.parse(event.data); if (m.id) { const p = pending.get(m.id); if (p) { pending.delete(m.id); m.error ? p.reject(Error(JSON.stringify(m.error))) : p.resolve(m.result); } } else events.push(m); });
  receipt.browser = await send('Browser.getVersion');
  await send('Page.enable'); await send('Runtime.enable'); await send('Network.enable');
  await send('Emulation.setDeviceMetricsOverride', {width: 1800, height: 1240, deviceScaleFactor: 1, mobile: false});
  await send('Page.navigate', {url}); const firstState = await ready();
  // The unchanged shell wrapper snapshots viewer.js/resolution.mjs. Bind the
  // newly imported helper from the actual HTTP endpoint in this same attempt.
  const displayHelperURL = new URL('./display_data.mjs', url).href;
  const displayHelperResponse = await fetch(displayHelperURL);
  if (!displayHelperResponse.ok) throw Error('Actual display helper source fetch failed: ' + displayHelperResponse.status);
  const displayHelperBytes = Buffer.from(await displayHelperResponse.arrayBuffer());
  await fs.writeFile(path.join(output, 'display_data_source.mjs'), displayHelperBytes, {flag: 'wx'});
  receipt.display_helper_source = {url: displayHelperURL, filename: 'display_data_source.mjs', bytes: displayHelperBytes.length,
    sha256: crypto.createHash('sha256').update(displayHelperBytes).digest('hex'), binding: 'Fetched actual served display helper during this browser attempt'};
  const manifestResponse = await fetch(firstState.manifest);
  if (!manifestResponse.ok) throw Error('Actual manifest fetch failed: ' + manifestResponse.status);
  const manifestBytes = Buffer.from(await manifestResponse.arrayBuffer()), manifest = JSON.parse(manifestBytes.toString('utf8'));
  manifestResolutions = manifest.resolution_modes || [];
  receipt.manifest = {url: firstState.manifest, schema: manifest.schema, sha256: crypto.createHash('sha256').update(manifestBytes).digest('hex'), previous_manifest_sha256: manifest.previous_manifest_sha256 || null, resolution_modes: manifestResolutions, default_resolution: manifest.default_resolution || null};
  const resolutionControl = await selectState('resolution-select');
  const representationControl = await selectState('representation-select');
  check(representationControl && ['points', 'mesh'].every(value => representationControl.options.some(option => option.value === value && !option.disabled)),
    'point_and_actual_triangle_representation_controls_available', representationControl);
  check(same(resolutionControl?.options.map(item => item.value), manifestResolutions.map(item => item.id)), 'resolution_options_match_actual_manifest_or_legacy_empty', resolutionControl);
  check(await evaluate("document.getElementById('resolution-label').hidden") === !manifestResolutions.length, 'legacy_manifest_hides_unused_resolution_selector', {resolution_modes: manifestResolutions});
  if (manifestResolutions.length) check(firstState.resolution_mode === (manifest.default_resolution || manifestResolutions[0].id), 'initial_resolution_matches_manifest_default', {actual: firstState.resolution_mode});
  const regions = await evaluate(`[...document.getElementById('region-select').options].map(x=>x.value)`);
  check(same(regions, manifest.regions.map(item => item.id)), 'region_options_match_actual_manifest', regions);
  for (const region of regions) {
    const spec = manifest.regions.find(item => item.id === region);
    for (const figure of [...spec.sections || [], ...spec.renders || []]) if (figure.case_id) check((spec.cases || []).some(item => item.id === figure.case_id && (!figure.condition_id || figure.condition_id === item.condition_id)), 'registered_case_figure_references_existing_case_and_condition', {region, figure_id: figure.id, case_id: figure.case_id, condition_id: figure.condition_id || null});
    await choose('region-select', region); let state = await ready(region);
    await choose('color-select', 'source'); state = await ready(region, undefined, {mode: 'source'});
    let meshScreenshotCaptured = false;
    const conditionIDs = await evaluate(`[...document.getElementById('condition-select').options].map(x=>x.value)`);
    const nativeScreenCondition = conditionIDs.includes('D005_Pnative') ? 'D005_Pnative' : conditionIDs[0] || null;
    check(same(conditionIDs, (spec.conditions || []).map(item => item.id)), 'condition_options_match_actual_manifest_including_supplemental_repeat', {region, conditionIDs});
    for (const resolution of manifestResolutions.length ? manifestResolutions : [null]) {
      if (resolution) {
        const cameras = state.cameras;
        await choose('resolution-select', resolution.id); state = await ready(region, undefined, {resolution_mode: resolution.id, mesh_res: resolution.mesh_res});
        check(same(cameras, state.cameras), 'resolution_switch_keeps_identical_camera', {region, resolution_mode: resolution.id});
      }
      for (const condition of conditionIDs.length ? conditionIDs : [null]) {
        if (condition) { await choose('condition-select', condition); state = await ready(region, condition); }
        const surface = await selectState('surface-select');
        for (const selectedSurface of surface && !surface.disabled ? ['raw', 'post'] : [state.surface_mode]) {
          if (surface && !surface.disabled) { await choose('surface-select', selectedSurface); state = await ready(region, condition, {surface_mode: selectedSurface}); }
          for (const representation of ['points', 'mesh']) {
            const cameras = state.cameras;
            if (state.representation_mode !== representation) {
              await choose('representation-select', representation);
              state = await ready(region, condition, {surface_mode: selectedSurface, representation_mode: representation});
            }
            check(same(cameras, state.cameras), 'point_mesh_switch_keeps_identical_camera_and_scale', {region, condition, resolution_mode: state.resolution_mode, surface: selectedSurface, representation});
            assertPanels(state, spec, condition, selectedSurface, state.prior_source, 'resolution_condition_surface_representation_matrix');
            await checkFailureMessages(state);
            check(cameraSync(state), 'six_cameras_same_pose_target_and_metric_scale', {region, condition, resolution_mode: state.resolution_mode, surface: selectedSurface, representation});
            check(Object.values(state.panels).every(p => p.count === 0 || p.display_only === true), 'all_display_samples_explicit_display_only', {region, condition, representation});
            await checkRasterizedPanels(state, 'resolution_condition_surface_representation_matrix');
            const images = await settleImages();
            receipt.regions.push({region, condition, resolution_mode: state.resolution_mode, mesh_res: state.mesh_res, surface: selectedSurface, representation_mode: representation, state, images});
            if (representation === 'mesh' && condition === nativeScreenCondition && selectedSurface === 'raw' &&
                state.panels.vanilla.representation === 'mesh' && !meshScreenshotCaptured) {
              await capture(`${region}_native_${state.resolution_mode || 'legacy'}_raw_mesh.png`);
              meshScreenshotCaptured = true;
            }
            if (condition === 'native_repeat_1') {
              const finalVariant = resolution?.final_variant || 'final', anchorVariant = resolution?.anchor_variant || 'anchor';
              check(state.panels.changed.candidate === `native_repeat_1.${finalVariant}.${selectedSurface}` && state.panels.vanilla.candidate === `D005_Pnative.${finalVariant}.${selectedSurface}` && state.panels.anchor.candidate === `D005_Pnative.${anchorVariant}.${selectedSurface}`, 'supplemental_repeat_uses_selected_resolution_and_shared_primary_anchor', {region, resolution_mode: state.resolution_mode, surface: selectedSurface, representation, changed: state.panels.changed, vanilla: state.panels.vanilla, anchor: state.panels.anchor});
              if (representation === 'points') await galleryPoint(spec, condition, firstState.manifest, 'native_repeat_1:' + state.resolution_mode + ':' + selectedSurface);
            }
          }
        }
      }
    }
    const nativeRawInventory = (manifestResolutions.length ? manifestResolutions : [null]).map(resolution => {
      const id = expectedPanels(spec, 'D005_Pnative', 'raw', state.prior_source, resolution?.id).vanilla;
      const candidate = spec.candidates.find(item => item.id === id);
      return {candidate: id || null, resolution_mode: resolution?.id || null, status: candidate?.status || 'pending',
        registered_mesh_data: !!candidate?.mesh_data, reason: candidate?.reason || null};
    });
    const availableNativeRawMesh = nativeRawInventory.some(item => item.status === 'available' && item.registered_mesh_data);
    if (qaMode === 'full' && availableNativeRawMesh) check(meshScreenshotCaptured,
      'available_native_actual_triangle_screenshot_captured_for_region', {region, native_raw_candidates: nativeRawInventory});
    receipt.mesh_screenshot_availability.push({region, native_raw_candidates: nativeRawInventory,
      screenshot_required: qaMode === 'full' && availableNativeRawMesh, screenshot_captured: meshScreenshotCaptured,
      status: meshScreenshotCaptured ? 'ACTUAL_MESH_SCREENSHOT_CAPTURED' : availableNativeRawMesh ? 'NOT_CAPTURED_PREFLIGHT_NATIVE_MESH_AVAILABLE' : 'NO_AVAILABLE_NATIVE_RAW_MESH_SCREENSHOT',
      reason: meshScreenshotCaptured ? null : availableNativeRawMesh ? 'An available native raw mesh is registered; its screenshot is mandatory only in full QA.' : 'No selected registered native raw candidate has both available status and mesh_data; explicit panel states are retained in the matrix checks.',
      assessment: 'DISPLAY_STATE_ONLY_NO_QUALITY_VERDICT', scientific_verdict: null});
    // Distance, input-source, gallery and camera controls below retain their
    // original point-display semantics and do not color triangles as distances.
    await choose('representation-select', 'points'); state = await ready(region, undefined, {representation_mode: 'points'});
    if (manifestResolutions.length) {
      const defaultResolution = manifest.default_resolution || manifestResolutions[0].id;
      await choose('resolution-select', defaultResolution); state = await ready(region, undefined, {resolution_mode: defaultResolution});
    }
    const surfaceControl = await selectState('surface-select');
    if (surfaceControl && !surfaceControl.disabled) { await choose('surface-select', 'raw'); state = await ready(region, undefined, {surface_mode: 'raw'}); }
    await choose('color-select', 'source'); await capture(`${region}_source.png`);
    await choose('color-select', 'distance'); state = await ready(region); check(state.mode === 'distance', 'distance_mode_active', region); await capture(`${region}_distance.png`);
    const before = state.cameras.prior.position;
    await evaluate(`document.getElementById('top-view').click()`); state = await ready(region);
    check(cameraSync(state) && JSON.stringify(before) !== JSON.stringify(state.cameras.prior.position), 'preset_changes_all_cameras_together', region); await capture(`${region}_top_distance.png`);
    await evaluate(`document.getElementById('reset-view').click()`);
    const mouse = await evaluate(`(()=>{const r=document.querySelector('.viewport canvas').getBoundingClientRect();return {x:r.x+r.width*.4,y:r.y+r.height*.4}})()`);
    let controlBefore = await ready(region);
    await send('Input.dispatchMouseEvent', {type: 'mousePressed', ...mouse, button: 'left', clickCount: 1});
    await send('Input.dispatchMouseEvent', {type: 'mouseMoved', x: mouse.x + 45, y: mouse.y + 15, button: 'left', buttons: 1});
    await send('Input.dispatchMouseEvent', {type: 'mouseReleased', x: mouse.x + 45, y: mouse.y + 15, button: 'left', clickCount: 1});
    let controlAfter = await ready(region);
    check(cameraSync(controlAfter) && JSON.stringify(controlAfter.cameras.prior.position) !== JSON.stringify(controlBefore.cameras.prior.position), 'pointer_drag_rotates_all_panels', region);
    controlBefore = controlAfter;
    await send('Input.dispatchMouseEvent', {type: 'mouseWheel', ...mouse, deltaX: 0, deltaY: -120});
    await pause(100); controlAfter = await ready(region);
    check(cameraSync(controlAfter) && controlAfter.cameras.prior.meters_per_pixel < controlBefore.cameras.prior.meters_per_pixel, 'wheel_zoom_matches_metric_scale_across_panels', region);
    controlBefore = controlAfter;
    await send('Input.dispatchMouseEvent', {type: 'mousePressed', ...mouse, button: 'right', clickCount: 1});
    await send('Input.dispatchMouseEvent', {type: 'mouseMoved', x: mouse.x + 25, y: mouse.y + 10, button: 'right', buttons: 2});
    await send('Input.dispatchMouseEvent', {type: 'mouseReleased', x: mouse.x + 25, y: mouse.y + 10, button: 'right', clickCount: 1});
    controlAfter = await ready(region);
    check(cameraSync(controlAfter) && JSON.stringify(controlAfter.cameras.prior.target) !== JSON.stringify(controlBefore.cameras.prior.target), 'right_drag_pans_shared_target', region);
    await evaluate(`document.getElementById('reset-view').click()`); state = await ready(region);
    await checkRasterizedPanels(state, 'camera_controls');
    await checkControlsAndGallery(spec, firstState.manifest);
  }
  const failures = events.filter(e => e.method === 'Runtime.exceptionThrown' || e.method === 'Network.loadingFailed' || (e.method === 'Network.responseReceived' && e.params.response.status >= 400));
  check(failures.length === 0, 'no_browser_exceptions_or_failed_requests', failures);
  receipt.status = qaMode === 'full' ? 'PASS_ACTUAL_RESULT_CONTROLS_AND_SELECTED_EVIDENCE_DISPLAYED' : 'PASS_ACTUAL_AVAILABLE_ARTIFACTS_DISPLAYED';
  receipt.limitations = 'All registered regions, resolutions, conditions and supported raw/post candidates are checked in points and mesh modes. Registered exact meshes must draw every declared triangle with nonbackground pixels; point-only sources retain explicit fallback. Resource failure never substitutes another resolution. A native mesh screenshot is required in full mode only where a selected registered native raw candidate is available with mesh_data; otherwise its explicit display state is recorded without a quality verdict. Existing distance/gallery/control checks run in points mode. Gallery and case coverage remains bounded and recorded, not every image/case. Delayed-response generation guards belong to separate synthetic QA. Explicit reconstruction failure, technical extraction failure and reference absence are allowed; no_geometry_reference_absent means no display geometry and no reference for quality assessment, never a reconstruction failure or zero metric. Positive geometry without reference remains available. Pending is allowed only in preflight. Display checks do not establish scientific quality or complete the experiment.';
} catch (error) {
  receipt.status = 'FAIL'; receipt.error = String(error); process.exitCode = 1;
} finally {
  receipt.completed_at = new Date().toISOString();
  await fs.writeFile(path.join(output, 'browser_qa.json'), JSON.stringify(receipt, null, 2), {flag: 'wx'});
  await fs.writeFile(path.join(output, 'chrome.log'), chromeLog.join(''), {flag: 'wx'});
  if (socket) socket.close(); browser.kill('SIGTERM'); virtualDisplay.kill('SIGTERM');
}
