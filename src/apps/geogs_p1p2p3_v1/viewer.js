import * as THREE from '../gs3d_4way_viewer/build/three.module.min.js';
import {resolutionModes, resolvePanels} from './resolution.mjs';
import {pointMetadata, colorProvenance, sourceColor, validateMeshMetadata, meshArrays} from './display_data.mjs';

const $ = id => document.getElementById(id);
const panelKeys = ['prior', 'mvs', 'anchor', 'vanilla', 'changed', 'reference'];
const panelLabels = {prior: '① 입력 ALS prior', mvs: '② 영상 기하', anchor: '③ Anchor 직후', vanilla: '④ GeoGS 원설정', changed: '⑤ 제어 변경', reference: '⑥ 현재 UAS 참조'};
const statusLabels = {available: '실제 산출물', pending: '산출물 대기', reference_unavailable: '참조 부재', no_geometry_reference_absent: '표시 기하 없음 · 참조 부재', reconstruction_failure: '복원 실패', failed: '실행 / 추출 실패', technical_resource_unavailable: '추출 자원 부족', TECHNICAL_RESOURCE_UNAVAILABLE: '추출 자원 부족', display_error: '표시 오류'};
const roleRGB = {prior: [180, 137, 76], mvs: [48, 142, 191], anchor: [155, 140, 175], vanilla: [65, 150, 139], changed: [66, 127, 183], reference: [113, 125, 137]};
const panels = new Map();
const qa = window.__GEOGS_QA = {ready: false, errors: [], frames: 0, scientific_verdict: null};
const manifestURL = new URL(new URLSearchParams(location.search).get('manifest') || './manifest.json', location.href);
let manifest, region, selectedCondition, active = {}, requestToken = 0, activeController = null;
let resolutionMode = null;
let mode = 'source', surfaceMode = 'raw', priorSource = 'mesh', representationMode = 'points', azimuth = -.8, elevation = .65, zoom = 1, pan = [0, 0, 0];

const fmt = n => Number(n).toLocaleString('ko-KR');
const urlFor = value => { const url = new URL(value, manifestURL); if (!['http:', 'https:'].includes(url.protocol)) throw Error('Unsupported artifact URL protocol'); return url.href; };
const setText = (node, value) => node.textContent = value;
async function getJSON(url, signal) { const r = await fetch(url, {signal}); if (!r.ok) throw Error(`${url}: HTTP ${r.status}`); return r.json(); }
function fail(error) { qa.errors.push(String(error)); qa.ready = false; $('error').hidden = false; setText($('error'), `표시 검증 실패: ${error}`); $('loading').hidden = true; console.error(error); }
function addLink(host, label, url) { if (!url) return; const a = document.createElement('a'); a.href = urlFor(url); a.textContent = label; a.target = '_blank'; a.rel = 'noopener'; host.append(a); }
function srgbLinear(x) { x /= 255; return x <= .04045 ? x / 12.92 : ((x + .055) / 1.055) ** 2.4; }
function ramp(t) { const stops = [[38, 135, 186], [54, 189, 159], [233, 214, 106], [215, 66, 71]]; t = Math.max(0, Math.min(1, t)) * 3; const k = Math.min(2, Math.floor(t)), a = t - k; return stops[k].map((v, i) => v * (1 - a) + stops[k + 1][i] * a); }
function finiteVector(v) { return Array.isArray(v) && v.length === 3 && v.every(Number.isFinite); }
function validateManifest(value) {
  if (!['geogs_p1p2p3_viewer_v1', 'geogs_p1p2p3_viewer_cases_v2'].includes(value.schema) || value.scientific_verdict !== null || !Array.isArray(value.regions) || !value.regions.length) throw Error('Invalid GeoGS viewer manifest');
  if (value.schema === 'geogs_p1p2p3_viewer_cases_v2' && (typeof value.previous_manifest_sha256 !== 'string' || !/^[0-9a-f]{64}$/i.test(value.previous_manifest_sha256))) throw Error('Cases-v2 manifest requires its original manifest SHA256');
  resolutionModes(value);
  for (const r of value.regions) {
    if (!finiteVector(r.bounds?.min) || !finiteVector(r.bounds?.max) || !r.bounds.min.every((v, i) => v < r.bounds.max[i])) throw Error(`Invalid shared bounds: ${r.id}`);
    if (!Array.isArray(r.candidates) || new Set(r.candidates.map(c => c.id)).size !== r.candidates.length) throw Error(`Invalid candidate IDs: ${r.id}`);
    for (const c of r.candidates) {
      if (!statusLabels[c.status]) throw Error(`Unknown status: ${c.id}`);
      if (c.status === 'available' && (!c.data || !c.surface_kind || /gaussian.?cent(?:er|re)/i.test(c.surface_kind))) throw Error(`Surface provenance required (Gaussian centers are not a surface): ${c.id}`);
      if (c.mesh_data && (c.mesh_data.format !== 'json' || typeof c.mesh_data.url !== 'string')) throw Error(`Invalid actual mesh descriptor: ${c.id}`);
    }
  }
}
async function binaryBuffer(item, signal) {
  const url = typeof item === 'string' ? item : item.url;
  const response = await fetch(urlFor(url), {signal}); if (!response.ok) throw Error(`${url}: HTTP ${response.status}`);
  const buffer = await response.arrayBuffer();
  if (typeof item === 'object') {
    if (buffer.byteLength !== item.bytes) throw Error('Binary size differs: ' + url);
    if (globalThis.crypto?.subtle && item.sha256) {
      const digest = await crypto.subtle.digest('SHA-256', buffer);
      if (Array.from(new Uint8Array(digest), x => x.toString(16).padStart(2, '0')).join('') !== item.sha256.toLowerCase()) throw Error('Binary SHA256 differs: ' + url);
    }
  }
  if (signal?.aborted) throw new DOMException('Display selection replaced', 'AbortError');
  return buffer;
}
async function binary(item, Type, signal) { return new Type(await binaryBuffer(item, signal)); }
async function cloud(meta, cache, signal) {
  const cacheKey = 'points:' + JSON.stringify(meta.data);
  if (!cache.has(cacheKey)) cache.set(cacheKey, (async () => {
    const input = meta.data.format === 'json' ? await getJSON(urlFor(meta.data.url), signal) : meta.data;
    if (input.display_only !== true) throw Error(`DISPLAY_ONLY contract missing: ${meta.id}`);
    const [xyz, rgb, distance] = await Promise.all([
      input.xyz_f32 ? binary(input.xyz_f32, Float32Array, signal) : input.xyz,
      input.rgb_u8 ? binary(input.rgb_u8, Uint8Array, signal) : input.rgb,
      input.distance_f32 ? binary(input.distance_f32, Float32Array, signal) : input.distance_m,
    ]);
    if (!xyz || xyz.length % 3 || !xyz.length) throw Error(`No actual surface/source samples: ${meta.id}`);
    for (const v of xyz) if (!Number.isFinite(v)) throw Error(`Nonfinite XYZ: ${meta.id}`);
    if (rgb && (rgb.length !== xyz.length || Array.from(rgb).some(x => !Number.isFinite(x) || x < 0 || x > 255))) throw Error(`Invalid RGB: ${meta.id}`);
    if (distance && (distance.length !== xyz.length / 3 || Array.from(distance).some(x => x !== null && !Number.isNaN(x) && (!Number.isFinite(x) || x < 0)))) throw Error(`Invalid unsigned reference distance: ${meta.id}`);
    if (signal.aborted) throw new DOMException('Display selection replaced', 'AbortError');
    const counts = pointMetadata(input, xyz.length / 3);
    // Store metadata without a second copy of large inline display arrays.
    const {xyz: unusedXYZ, rgb: unusedRGB, distance_m: unusedDistance, ...metadata} = input;
    return {xyz: new Float32Array(xyz), rgb, distance, metadata, counts, color: colorProvenance(input)};
  })());
  return cache.get(cacheKey);
}
async function exactMesh(meta, cache, signal) {
  const key = 'mesh:' + JSON.stringify(meta.mesh_data);
  if (!cache.has(key)) cache.set(key, (async () => {
    const input = validateMeshMetadata(await getJSON(urlFor(meta.mesh_data.url), signal));
    const [vertices, triangles] = await Promise.all([binaryBuffer(input.vertices_f64, signal), binaryBuffer(input.triangles_u32, signal)]);
    if (signal.aborted) throw new DOMException('Display selection replaced', 'AbortError');
    const arrays = meshArrays(input, vertices, triangles);
    return {...arrays, metadata: input, binary_integrity: globalThis.crypto?.subtle ? 'SHA256_AND_BYTES_VERIFIED' : 'BYTES_VERIFIED_SHA256_API_UNAVAILABLE'};
  })());
  return cache.get(key);
}
function initPanel(key) {
  const article = document.createElement('article'); article.className = 'panel'; article.dataset.panel = key;
  article.innerHTML = '<div class="panel-heading"><h2></h2><span class="status"></span></div><div class="viewport"><div class="missing"></div></div><div class="panel-note"><div class="counts"></div><div class="source-note"></div><div class="panel-links"></div></div>';
  article.querySelector('h2').textContent = panelLabels[key]; $('panels').append(article);
  const host = article.querySelector('.viewport'), scene = new THREE.Scene(); scene.background = new THREE.Color('#eaf0f4');
  const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, .01, 10000);
  const renderer = new THREE.WebGLRenderer({antialias: true, preserveDrawingBuffer: true}); renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5)); renderer.domElement.setAttribute('aria-label', panelLabels[key] + ' 표면'); host.append(renderer.domElement);
  panels.set(key, {article, host, scene, camera, renderer});
  let drag = null;
  const canvas = renderer.domElement;
  canvas.addEventListener('contextmenu', e => e.preventDefault());
  canvas.addEventListener('pointerdown', e => { drag = {x: e.clientX, y: e.clientY, pan: e.shiftKey || e.button === 2}; canvas.setPointerCapture(e.pointerId); });
  for (const event of ['pointerup', 'pointercancel', 'lostpointercapture']) canvas.addEventListener(event, () => drag = null);
  canvas.addEventListener('pointermove', e => {
    if (!drag || !region) return;
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if (drag.pan) {
      const scale = (camera.top - camera.bottom) / host.clientHeight, right = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 0), up = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 1);
      for (let i = 0; i < 3; i++) pan[i] += (-dx * right.getComponent(i) + dy * up.getComponent(i)) * scale;
    } else { azimuth -= dx * .007; elevation = Math.max(-1.54, Math.min(1.54, elevation + dy * .007)); }
    drag.x = e.clientX; drag.y = e.clientY; cameraAll();
  });
  canvas.addEventListener('wheel', e => { e.preventDefault(); zoom = Math.max(.3, Math.min(30, zoom * Math.exp(-e.deltaY * .001))); cameraAll(); }, {passive: false});
}
function cameraAll() {
  if (!region) return;
  const b = region.bounds, center = b.min.map((v, i) => (v + b.max[i]) / 2 + pan[i]), span = Math.max(...b.max.map((v, i) => v - b.min[i]));
  qa.cameras = {};
  for (const [key, p] of panels) {
    const w = p.host.clientWidth, h = p.host.clientHeight; if (!w || !h) continue;
    const scale = span * .65 / zoom * Math.max(1, h / w);
    p.camera.left = -scale * w / h; p.camera.right = scale * w / h; p.camera.top = scale; p.camera.bottom = -scale;
    p.camera.near = .01; p.camera.far = span * 100;
    p.camera.position.set(center[0] + 3 * span * Math.cos(azimuth) * Math.cos(elevation), center[1] + 3 * span * Math.sin(azimuth) * Math.cos(elevation), center[2] + 3 * span * Math.sin(elevation));
    p.camera.up.set(0, 0, 1); p.camera.lookAt(...center); p.camera.updateProjectionMatrix(); p.camera.updateMatrixWorld();
    p.renderer.setSize(w, h, false); p.renderer.render(p.scene, p.camera); qa.frames++;
    qa.cameras[key] = {position: p.camera.position.toArray(), target: center, left: p.camera.left, right: p.camera.right, top: scale, bottom: -scale, meters_per_pixel: 2 * scale / h};
    if (qa.panels?.[key]) {
      const info = p.renderer.info;
      Object.assign(qa.panels[key], {rendered_triangles: info.render.triangles, rendered_points: info.render.points,
        draw_calls: info.render.calls, renderer_info: {render: {...info.render}, memory: {...info.memory}, programs: info.programs?.length || 0}});
    }
  }
}
function clearPanel(key) {
  const p = panels.get(key);
  if (p.object) { p.scene.remove(p.object); p.object.geometry.dispose(); p.object.material.dispose(); p.object = null; }
  // Drop renderer draw-list references to the disposed selection as well.
  p.renderer.renderLists?.dispose();
}
function rebuild(key) {
  clearPanel(key);
  const p = panels.get(key), entry = active[key]; if (!entry) return;
  const {meta, points, mesh} = entry, status = p.article.querySelector('.status'), missing = p.article.querySelector('.missing');
  const showMesh = representationMode === 'mesh' && !!mesh;
  const shown = !entry.error && !!points;
  setText(p.article.querySelector('h2'), panelLabels[key] + (meta?.label ? ' · ' + meta.label : ''));
  const currentStatus = entry.error ? 'display_error' : meta?.status || 'pending'; status.dataset.status = currentStatus; setText(status, statusLabels[currentStatus]);
  missing.hidden = shown;
  setText(missing, entry.error || meta?.reason || (currentStatus === 'available' ? '현재 선택의 실제 표시 자료를 읽는 중입니다.' : currentStatus === 'no_geometry_reference_absent' ? '표시 기하 없음 · 참조 부재로 품질평가 불가' : currentStatus === 'reference_unavailable' ? '이 범위의 참조가 없습니다.' : currentStatus === 'reconstruction_failure' ? '복원된 표면이 없습니다. 참조 부재와 구분한 복원 실패입니다.' : currentStatus === 'failed' ? '실행 / 표면 추출 실패가 기록되었습니다.' : /resource_unavailable/i.test(currentStatus) ? '추출 자원 부족으로 이 해상도의 표면을 제공할 수 없습니다.' : '아직 실제 산출물이 등록되지 않았습니다.'));
  const links = p.article.querySelector('.panel-links'); links.replaceChildren();
  for (const item of meta?.downloads || []) addLink(links, item.label, item.url || item.path);
  if (meta?.data?.url) addLink(links, '표시 표본', meta.data.url);
  if (meta?.mesh_data?.url) addLink(links, '실제 삼각형 표시 계보', meta.mesh_data.url);
  const counts = points?.counts;
  const countParts = !shown ? [] : [showMesh ? `실제 삼각형 ${fmt(mesh.index.length / 3)}개 · 정점 ${fmt(mesh.position.length / 3)}개` : `표시 표본 ${fmt(counts.display_sample_count)}점`,
    counts.full_evaluation_sample_count !== null ? `전체 평가 표본 ${fmt(counts.full_evaluation_sample_count)}점` : '전체 평가 표본 수 미기재',
    counts.original_points_in_roi !== null ? `ROI 원자료 ${fmt(counts.original_points_in_roi)}점` : ''];
  if (showMesh) countParts.push(`별도 점 표시 표본 ${fmt(counts.display_sample_count)}점`);
  setText(p.article.querySelector('.counts'), countParts.filter(Boolean).join(' · '));
  const sourceNote = p.article.querySelector('.source-note');
  const displayedColorProvenance = showMesh ? {kind: 'FIXED_SOURCE_COLOR', label: '소스 구분용 고정색',
    description: mesh.metadata.color?.description || '메시를 소스별 균일 색상으로 표시합니다.', metadata: mesh.metadata.color || null}
    : points?.rgb ? points.color : points ? {kind: 'FIXED_SOURCE_COLOR', label: '뷰어 소스 구분용 고정색',
      description: '등록된 RGB 배열이 없어 뷰어의 소스 고정색을 사용합니다.', metadata: null} : null;
  qa.panels[key] = {candidate: meta.id, status: currentStatus, reason: entry.error || meta.reason || null,
    representation: shown ? (showMesh ? 'mesh' : 'points') : 'none', requested_representation: representationMode,
    count: counts?.display_sample_count || 0, display_sample_count: counts?.display_sample_count ?? null,
    full_evaluation_sample_count: counts?.full_evaluation_sample_count ?? null,
    original_points_in_roi: counts?.original_points_in_roi ?? null,
    mesh_vertex_count: mesh?.metadata.vertex_count || 0, mesh_triangle_count: mesh?.metadata.triangle_count || 0,
    color_provenance: displayedColorProvenance, point_color_provenance: points?.color || null,
    loaded_metadata: {points: points?.metadata || null, mesh: mesh?.metadata || null},
    mesh_binary_integrity: mesh?.binary_integrity || null, surface_kind: meta.surface_kind,
    rendered_triangles: 0, rendered_points: 0, draw_calls: 0, display_only: true};
  if (!shown) { setText(sourceNote, meta?.surface_kind || ''); return; }
  if (showMesh) {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(mesh.position, 3));
    geometry.setIndex(new THREE.BufferAttribute(mesh.index, 1));
    const uniform = sourceColor(mesh.metadata, roleRGB[key]);
    if (mode === 'height') {
      const colors = new Float32Array(mesh.position.length), zr = region.bounds.max[2] - region.bounds.min[2];
      for (let i = 0; i < mesh.position.length / 3; i++) colors.set(ramp((mesh.position[3*i+2]-region.bounds.min[2])/zr).map(srgbLinear), i*3);
      geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    }
    p.object = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({side: THREE.DoubleSide, vertexColors: mode === 'height',
      color: mode === 'height' ? 0xffffff : new THREE.Color().setRGB(...uniform.map(srgbLinear))}));
    p.scene.add(p.object);
    const detail = mode === 'height' ? '공통 local Z 색상' : mode === 'distance' ? '거리 색상 적용 안 됨 · 현재 메시를 소스 고정색으로 유지합니다. 참조 거리는 표시 표본 모드에서 확인하세요.' : '소스 구분용 고정색 · 사진 텍스처 / 원색이 아닙니다.';
    setText(sourceNote, `${meta.surface_kind} · 평가 범위로 잘린 실제 삼각형 · 단순화 / 인공 절단면 없음 · ${detail}`);
    qa.panels[key].color_mode = mode === 'height' ? 'height' : 'fixed_source';
    qa.panels[key].distance_color_applied = false;
    return;
  }
  const colors = new Float32Array(points.xyz.length), zr = region.bounds.max[2] - region.bounds.min[2]; let unknownDistance = 0;
  for (let i = 0; i < points.xyz.length / 3; i++) {
    let rgb;
    if (mode === 'distance') {
      const d = points.distance?.[i];
      if (d === null || d === undefined || !Number.isFinite(d)) { rgb = [141, 150, 159]; unknownDistance++; } else rgb = ramp(d / 2);
    } else if (mode === 'height') rgb = ramp((points.xyz[3 * i + 2] - region.bounds.min[2]) / zr);
    else rgb = points.rgb ? [points.rgb[3 * i], points.rgb[3 * i + 1], points.rgb[3 * i + 2]] : roleRGB[key];
    colors.set(rgb.map(srgbLinear), i * 3);
  }
  const geometry = new THREE.BufferGeometry(); geometry.setAttribute('position', new THREE.BufferAttribute(points.xyz, 3)); geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  p.object = new THREE.Points(geometry, new THREE.PointsMaterial({size: Number($('point-size').value), sizeAttenuation: false, vertexColors: true})); p.scene.add(p.object);
  const colorDetail = points.rgb ? [points.color.label, points.color.description].filter(Boolean).join(' · ') : 'RGB 없음 · 뷰어 소스 구분용 고정색';
  const detail = mode === 'distance' ? `${points.metadata.distance_definition || meta.distance_definition || '표시점 → UAS 참조 최근접 거리'} · 거리 없음 ${fmt(unknownDistance)}점` : mode === 'height' ? '공통 범위의 local Z 색상' : colorDetail;
  const fallback = representationMode === 'mesh' ? '실제 삼각형 표시 자료 미등록 · 점 자료로 표시 · ' : '';
  const sampling = points.metadata.sampling_metadata;
  const samplingNote = sampling ? [sampling.display_voxel_m != null ? `표시 voxel ${sampling.display_voxel_m} m` : '',
    sampling.display_cap != null ? `표시 상한 ${fmt(sampling.display_cap)}점${sampling.display_cap_applied === true ? ' 적용' : sampling.display_cap_applied === false ? ' 미적용' : ' 적용 여부 미기재'}` : ''].filter(Boolean).join(' · ') : '표시 표본화 계보 미기재';
  setText(sourceNote, `${meta.surface_kind} · ${fallback}${detail} · ${samplingNote}`);
  Object.assign(qa.panels[key], {unknownDistance, color_mode: mode, distance_color_applied: mode === 'distance',
    representation_fallback: representationMode === 'mesh' ? 'NO_REGISTERED_MESH_DATA' : null});
}
function legend() {
  const host = $('legend'); host.replaceChildren();
  if (mode !== 'source') { const swatch = document.createElement('span'); swatch.className = 'gradient'; host.append(swatch); }
  host.append(document.createTextNode(mode === 'distance' ? '점: 0 → 2 m 이상 · 회색: 참조 거리 없음. 실제 삼각형: 소스 고정색 유지, 거리 색상 미적용.' : mode === 'height' ? `${region.bounds.min[2].toFixed(2)} → ${region.bounds.max[2].toFixed(2)} m · 공통 local Z` : '색상 출처는 패널별 실제 메타데이터를 따릅니다. 고정색·정점에서 옮긴 색·원 점자료 RGB·출처 미기재를 구분합니다. 삼각형은 소스 고정색입니다.'));
}
function conditionEvidence(kind) { const source = kind === 'section' ? region.sections : region.renders; return (source || []).filter(item => !item.condition_id || item.condition_id === selectedCondition?.id); }
function comparisonFamily(item) { return {primary_1024: '주 최종 비교 · 1024', anchor_refinement_512: 'Anchor/refinement 동일 해상도 · 512'}[item.comparison_family] || item.comparison_family || ''; }
function evidenceItems(kind) {
  const source = conditionEvidence(kind);
  if (kind !== 'render') return source;
  return source.filter(item => (item.domain || 'unspecified') === $('render-domain-select').value && (item.image_name || item.id) === $('render-image-select').value);
}
function optionsFrom(select, records, previous) {
  select.replaceChildren();
  for (const [value, label] of records) { const option = document.createElement('option'); option.value = value; option.textContent = label; select.append(option); }
  if ([...select.options].some(option => option.value === previous)) select.value = previous;
  select.disabled = select.options.length <= 1;
}
function renderFilters() {
  const all = conditionEvidence('render'), domain = $('render-domain-select'), photo = $('render-image-select');
  const domainLabels = {whole_original_frame: '원 사진 전체', fixed_projected_region_ROI: '고정 지역 ROI', unspecified: '범위 미기재'};
  optionsFrom(domain, [...new Set(all.map(item => item.domain || 'unspecified'))].map(value => [value, domainLabels[value] || value]), domain.value);
  const scoped = all.filter(item => (item.domain || 'unspecified') === domain.value);
  optionsFrom(photo, [...new Set(scoped.map(item => item.image_name || item.id))].map(value => [value, value]), photo.value);
  qa.gallery_registered_count = all.length;
  qa.gallery_filter = {domain: domain.value, image_name: photo.value};
}
function showFigure(kind) {
  const item = evidenceItems(kind).find(i => i.id === $(kind + '-select').value);
  $(kind + '-figure').hidden = !item; $(kind + '-empty').hidden = !!item;
  if (!item) { $(kind + '-image').removeAttribute('src'); return; }
  const url = urlFor(item.url || item.path); $(kind + '-link').href = url; $(kind + '-image').src = url;
  $(kind + '-image').onerror = () => fail(`Actual figure load failed: ${url}`);
  setText($(kind + '-caption'), [item.caption || item.label, comparisonFamily(item) ? `그림 비교 범위: ${comparisonFamily(item)}` : '', item.image_name ? `실제 사진: ${item.image_name} · 분할: ${item.split || '미기재'}` : '', item.selection_reason ? `선택 근거: ${item.selection_reason}` : '선택 근거가 이 그림에 개별 기재되지 않았습니다.', item.width_m != null ? `단면 전체 폭 ${item.width_m} m` : ''].filter(Boolean).join('\n'));
}
function updateEvidence() {
  renderFilters();
  for (const kind of ['section', 'render']) {
    const select = $(kind + '-select'), prior = select.value; select.replaceChildren();
    for (const item of evidenceItems(kind)) { const option = document.createElement('option'); option.value = item.id; option.textContent = [comparisonFamily(item), item.label || item.id].filter(Boolean).join(' · '); select.append(option); }
    if ([...select.options].some(o => o.value === prior)) select.value = prior;
    select.disabled = !select.options.length; showFigure(kind);
  }
  const downloads = $('downloads'); downloads.replaceChildren();
  addLink(downloads, '실제 표시 manifest', manifestURL.href);
  for (const item of [...manifest.downloads || [], ...region.downloads || [], ...selectedCondition?.downloads || []]) addLink(downloads, item.label, item.url || item.path);
  setText($('case-note'), region.case_selection_note || '대표 사례의 선택 근거와 실패 사례를 별도 평가 기록에서 확인합니다. 이 화면의 시점 조작은 학습·평가 조건을 바꾸지 않습니다.');
  updateProvenance();
}
function updateProvenance() {
  setText($('provenance'), JSON.stringify({scientific_verdict: null, display_only: true, region: region.id, bounds: region.bounds,
    frame: region.frame, notes: region.notes, condition: selectedCondition, resolution: resolutionMode,
    representation_mode: representationMode, color_mode: mode,
    candidates: Object.fromEntries(Object.entries(active).map(([key, value]) => [key, {candidate: value.meta || null,
      loaded_point_metadata: value.points?.metadata || null, loaded_mesh_metadata: value.mesh?.metadata || null,
      actual_display_counts: value.points?.counts || null, color_provenance: qa.panels?.[key]?.color_provenance || null,
      point_color_provenance: value.points?.color || null,
      displayed_representation: qa.panels?.[key]?.representation || 'none', mesh_binary_integrity: value.mesh?.binary_integrity || null}])),
    case_selection: region.case_selection}, null, 2));
}
async function selectCase(id) {
  const selected = (region.cases || []).find(item => item.id === id);
  if (!selected) { pan = [0, 0, 0]; zoom = 1; qa.case = null; $('case-description').hidden = true; cameraAll(); return; }
  if (!finiteVector(selected.center) || !Number.isFinite(selected.extent_m) || selected.extent_m <= 0) throw Error('Invalid recorded case camera: ' + id);
  if (selected.condition_id) {
    const condition = region.conditions?.find(item => item.id === selected.condition_id);
    if (!condition) throw Error('Recorded case references unknown condition: ' + id);
    selectedCondition = condition; $('condition-select').value = condition.id;
  }
  pan = selected.center.map((value, axis) => value - (region.bounds.min[axis] + region.bounds.max[axis]) / 2);
  const span = Math.max(...region.bounds.max.map((value, axis) => value - region.bounds.min[axis]));
  zoom = 1.3 * span / selected.extent_m;
  qa.case = {id, center: selected.center, extent_m: selected.extent_m};
  $('case-description').hidden = false;
  setText($('case-description'), `${selected.label || id} · 공통 중심 [${selected.center.map(x => x.toFixed(2)).join(', ')}] m · 세로 표시 범위 ${selected.extent_m} m · ${selected.description || '선택 설명 미기재'}`);
  await loadPanels();
}
async function loadPanels() {
  const token = ++requestToken; activeController?.abort();
  activeController = new AbortController();
  const signal = activeController.signal, cache = new Map(), requestedRepresentation = representationMode;
  qa.ready = false; qa.panels = {}; qa.request_generation = token; $('loading').hidden = false; $('error').hidden = true;
  const ids = resolvePanels(region, selectedCondition, surfaceMode, priorSource, resolutionMode);
  active = Object.fromEntries(panelKeys.map(key => [key, {meta: region.candidates.find(c => c.id === ids[key]) || {id: ids[key], status: 'pending', reason: `선택한 ${key === 'prior' ? 'prior 입력' : surfaceMode + ' 표면'} 산출물이 아직 등록되지 않았습니다.`}}]));
  const selection = active;
  for (const key of panelKeys) rebuild(key); cameraAll();
  await Promise.all(panelKeys.map(async key => {
    const entry = selection[key]; if (entry.meta?.status !== 'available') return;
    try {
      const [points, mesh] = await Promise.all([cloud(entry.meta, cache, signal),
        requestedRepresentation === 'mesh' && entry.meta.mesh_data ? exactMesh(entry.meta, cache, signal) : null]);
      if (token !== requestToken) return;
      entry.points = points; entry.mesh = mesh;
    }
    catch (error) { if (token !== requestToken) return; entry.error = String(error); qa.errors.push(entry.error); qa.panels[key] = {candidate: entry.meta.id, status: 'display_error', count: 0}; }
    if (token === requestToken) rebuild(key);
  }));
  cache.clear(); // Only the six current entries retain CPU arrays; no region/condition history cache.
  if (token !== requestToken) return;
  legend(); cameraAll(); updateEvidence(); $('loading').hidden = true;
  qa.region = region.id; qa.condition = selectedCondition?.id || null; qa.mode = mode; qa.surface_mode = surfaceMode; qa.prior_source = priorSource; qa.representation_mode = representationMode; qa.resolution_mode = resolutionMode?.id || null; qa.mesh_res = resolutionMode?.mesh_res || null; qa.ready = !Object.values(active).some(v => v.error);
  if (!qa.ready) { $('error').hidden = false; setText($('error'), '일부 실제 자료를 표시하지 못했습니다. 해당 패널의 오류와 원자료 링크를 확인하세요.'); }
}
async function switchRegion(id) {
  region = manifest.regions.find(r => r.id === id); if (!region) throw Error('Unknown region ' + id);
  $('region-select').value = id; $('condition-select').replaceChildren();
  for (const c of region.conditions || []) { const o = document.createElement('option'); o.value = c.id; o.textContent = c.label || c.id; $('condition-select').append(o); }
  selectedCondition = region.conditions?.find(c => c.id === region.default_condition) || region.conditions?.[0];
  if (selectedCondition) $('condition-select').value = selectedCondition.id;
  $('condition-select').disabled = !selectedCondition;
  optionsFrom($('case-select'), [['', '지역 전체'], ...(region.cases || []).map(item => [item.id, item.label || item.id])], '');
  qa.case = null; $('case-description').hidden = true;
  $('prior-select').querySelector('option[value="points"]').disabled = !region.candidates.some(c => c.id === 'als_points');
  if ($('prior-select').querySelector('option[value="points"]').disabled) { priorSource = 'mesh'; $('prior-select').value = 'mesh'; }
  $('surface-select').disabled = !region.candidates.some(c => /\.(raw|post)$/.test(c.id));
  setText($('region-note'), `${region.label || region.id} · 동일한 공통 평가 범위 · ${(region.notes || []).join(' ')}`);
  azimuth = -.8; elevation = .65; zoom = 1; pan = [0, 0, 0]; await loadPanels();
}
try {
  manifest = await getJSON(manifestURL.href); validateManifest(manifest); qa.manifest = manifestURL.href;
  const initialColor = new URLSearchParams(location.search).get('color');
  if (['source', 'distance', 'height'].includes(initialColor)) mode = initialColor;
  $('color-select').value = mode;
  const resolutions = resolutionModes(manifest);
  resolutionMode = resolutions.find(item => item.id === manifest.default_resolution) || resolutions[0] || null;
  optionsFrom($('resolution-select'), resolutions.map(item => [item.id, item.label || String(item.mesh_res)]), resolutionMode?.id);
  $('resolution-label').hidden = !resolutions.length; $('resolution-note').hidden = !resolutions.length;
  setText($('resolution-note'), 'Anchor·원설정·변경 결과를 선택한 동일 추출 해상도로 표시합니다. 1024는 주 최종 비교, 512는 anchor/refinement 비교입니다. 추출 실패는 해당 패널에 표시합니다. 단면 그림은 그림별 비교 범위와 해상도를 확인하세요.');
  panelKeys.forEach(initPanel);
  for (const r of manifest.regions) { const o = document.createElement('option'); o.value = r.id; o.textContent = r.label || r.id; $('region-select').append(o); }
  $('region-select').addEventListener('change', () => switchRegion($('region-select').value).catch(fail));
  $('condition-select').addEventListener('change', () => { selectedCondition = region.conditions.find(c => c.id === $('condition-select').value); loadPanels().catch(fail); });
  $('resolution-select').addEventListener('change', () => { resolutionMode = resolutions.find(item => item.id === $('resolution-select').value); loadPanels().catch(fail); });
  $('surface-select').addEventListener('change', () => { surfaceMode = $('surface-select').value; loadPanels().catch(fail); });
  $('prior-select').addEventListener('change', () => { priorSource = $('prior-select').value; loadPanels().catch(fail); });
  $('representation-select').addEventListener('change', () => { representationMode = $('representation-select').value; loadPanels().catch(fail); });
  $('case-select').addEventListener('change', () => selectCase($('case-select').value).catch(fail));
  $('color-select').addEventListener('change', () => { mode = $('color-select').value; panelKeys.forEach(rebuild); legend(); cameraAll(); updateProvenance(); qa.mode = mode; });
  $('point-size').addEventListener('input', () => { for (const p of panels.values()) if (p.object?.isPoints) p.object.material.size = Number($('point-size').value); cameraAll(); });
  $('reset-view').onclick = () => { azimuth = -.8; elevation = .65; zoom = 1; pan = [0, 0, 0]; qa.case = null; $('case-select').value = ''; $('case-description').hidden = true; cameraAll(); };
  $('top-view').onclick = () => { azimuth = -Math.PI / 2; elevation = 1.54; cameraAll(); };
  $('front-view').onclick = () => { azimuth = -Math.PI / 2; elevation = .03; cameraAll(); };
  $('section-select').onchange = () => showFigure('section'); $('render-select').onchange = () => showFigure('render');
  $('render-domain-select').onchange = updateEvidence; $('render-image-select').onchange = updateEvidence;
  let resized = false; window.addEventListener('resize', () => { if (resized) return; resized = true; requestAnimationFrame(() => { resized = false; cameraAll(); }); });
  await switchRegion(manifest.default_region || manifest.regions[0].id);
} catch (error) { fail(error); }
