'use strict';

(() => {
  const $ = id => document.getElementById(id);
  const state = window.p2ViewerState = {
    ready: false, viewId: null,
    selectedModels: ['mvs_initial', 'mvs_sh3_uniform', 'mvs_sh3_residual_weighted'],
    zoom: 1, center: {x: 0, y: 0}, mode: 'grid', fit: true,
    wipeLeft: 'target', wipeModel: 'mvs_sh3_residual_weighted', wipePosition: 0.5,
    loading: false, error: null, loadedImages: [],
  };
  let data, currentView, loadVersion = 0, framePending = false;
  const cache = new Map();
  const canvases = [$('canvas-target'), ...[0, 1, 2].map(i => $(`canvas-render-${i}`)), $('canvas-wipe')];
  const gridCanvases = canvases.slice(0, 4);
  const defaults = [...state.selectedModels];

  function model(id) { return data.models.find(item => item.id === id); }
  function label(id) {
    if (id === 'target') return '현재 사진';
    const item = model(id);
    return item ? `${item.label}${item.source === 'ALS' ? ' · A 미적용 과거 ALS 진단' : ''}` : id;
  }
  function number(value, digits = 5) {
    return Number.isFinite(value) ? value.toFixed(digits) : '평가 불가';
  }
  function showError(message) {
    state.error = message;
    $('error-message').textContent = message || '';
    $('error-message').hidden = !message;
  }
  function pathFor(id) {
    return id === 'target' ? currentView.target : currentView.images[id];
  }
  function safeImageURL(path) {
    if (typeof path !== 'string' || !path.startsWith('images/') ||
        path.split('/').includes('..') || /[\\?#]/.test(path)) {
      throw new Error('허용되지 않은 이미지 경로입니다.');
    }
    const base = new URL('.', window.location.href);
    const url = new URL(path, base);
    if (url.origin !== base.origin || !url.pathname.startsWith(base.pathname + 'images/')) {
      throw new Error('이미지는 이 비교 자료 안의 파일만 사용할 수 있습니다.');
    }
    return url.href;
  }
  function loadImage(path) {
    const url = safeImageURL(path);
    if (cache.has(url)) return cache.get(url).promise;
    const entry = {image: null};
    entry.promise = new Promise((resolve, reject) => {
      const image = new Image();
      image.decoding = 'async';
      image.onload = () => {
        entry.image = image;
        resolve(image);
      };
      image.onerror = () => {
        cache.delete(url);
        reject(new Error(`이미지를 불러오지 못했습니다: ${path}`));
      };
      image.src = url;
    });
    cache.set(url, entry);
    return entry.promise;
  }
  function getImage(id) {
    const path = pathFor(id);
    if (!path) return null;
    try { return cache.get(safeImageURL(path))?.image || null; }
    catch (_) { return null; }
  }
  function activeCanvases() { return state.mode === 'grid' ? gridCanvases : [canvases[4]]; }
  function fitZoom() {
    if (!currentView) return 1;
    return Math.min(...activeCanvases().map(canvas => {
      const box = canvas.getBoundingClientRect();
      return Math.min(box.width / currentView.width, box.height / currentView.height);
    }));
  }
  function resetFit() {
    if (!currentView) return;
    state.fit = true;
    state.center = {x: currentView.width / 2, y: currentView.height / 2};
    state.zoom = fitZoom();
    scheduleDraw();
  }
  function changeZoom(value, canvas = null, clientX = null, clientY = null) {
    if (!currentView) return;
    const previous = state.zoom;
    const next = Math.max(Math.max(fitZoom() / 8, 0.005), Math.min(value, 16));
    if (canvas && clientX !== null) {
      const box = canvas.getBoundingClientRect();
      const dx = clientX - box.left - box.width / 2;
      const dy = clientY - box.top - box.height / 2;
      state.center.x += dx / previous - dx / next;
      state.center.y += dy / previous - dy / next;
    }
    state.zoom = next;
    state.fit = false;
    scheduleDraw();
  }
  function paintImage(ctx, image, width, height) {
    if (!image) return;
    ctx.imageSmoothingEnabled = state.zoom < 1;
    ctx.drawImage(image, width / 2 - state.center.x * state.zoom,
      height / 2 - state.center.y * state.zoom,
      currentView.width * state.zoom, currentView.height * state.zoom);
  }
  function drawCanvas(canvas, id, wipe = false) {
    const box = canvas.getBoundingClientRect();
    if (!box.width || !box.height) return;
    const dpr = window.devicePixelRatio || 1;
    const backingWidth = Math.round(box.width * dpr), backingHeight = Math.round(box.height * dpr);
    if (canvas.width !== backingWidth || canvas.height !== backingHeight) {
      canvas.width = backingWidth; canvas.height = backingHeight;
    }
    const ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.fillStyle = '#080d12';
    ctx.fillRect(0, 0, box.width, box.height);
    if (!currentView) return;
    if (wipe) {
      paintImage(ctx, getImage(state.wipeModel), box.width, box.height);
      const split = box.width * state.wipePosition;
      ctx.save(); ctx.beginPath(); ctx.rect(0, 0, split, box.height); ctx.clip();
      ctx.fillStyle = '#080d12'; ctx.fillRect(0, 0, box.width, box.height);
      paintImage(ctx, getImage(state.wipeLeft), box.width, box.height);
      ctx.restore();
      ctx.strokeStyle = '#71dcc2'; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(split, 0); ctx.lineTo(split, box.height); ctx.stroke();
      ctx.fillStyle = '#71dcc2'; ctx.beginPath(); ctx.arc(split, box.height / 2, 12, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = '#12322d'; ctx.font = 'bold 14px system-ui'; ctx.textAlign = 'center';
      ctx.fillText('↔', split, box.height / 2 + 5);
    } else {
      paintImage(ctx, getImage(id), box.width, box.height);
    }
  }
  function draw() {
    framePending = false;
    if (state.fit && currentView) state.zoom = fitZoom();
    if (state.mode === 'grid') {
      drawCanvas(canvases[0], 'target');
      state.selectedModels.forEach((id, i) => drawCanvas(canvases[i + 1], id));
    } else drawCanvas(canvases[4], null, true);
    $('zoom-readout').value = `${Math.round(state.zoom * 100)}%`;
  }
  function scheduleDraw() {
    if (!framePending) { framePending = true; requestAnimationFrame(draw); }
  }
  function metricCaption(element, id) {
    const item = currentView.metrics?.[id] || {};
    element.replaceChildren();
    if (model(id)?.kind && model(id).kind !== 'rgb') {
      element.textContent = model(id).kind === 'mask' ? (model(id).phase === 'initial' ? 'A 관측 구간을 얻은 위치 · 중심 투영 (표시 3픽셀)' : '최종 1mm 초과 기하 갱신 위치 · 중심 투영 (표시 3픽셀)') : model(id).kind === 'normal' ? '출력 표면 법선 · RGB 품질 지표 아님' : '초기 대비 깊이 변화 · 0–0.3m';
      return;
    }
    if (model(id)?.source === 'ALS') {
      const legacy = document.createElement('span');
      legacy.className = 'legacy'; legacy.textContent = 'A 미적용 과거 ALS 진단 · ';
      element.append(legacy);
    }
    element.append('공통 픽셀 MAE ');
    const value = document.createElement('span'); value.className = 'metric-number';
    value.textContent = number(item.mae); element.append(value);
    element.append(` · PSNR ${number(item.psnr_db, 2)}${Number.isFinite(item.psnr_db) ? ' dB' : ''}`);
    if (Number.isFinite(item.geometry_present_fraction)) {
      element.append(` · 기하 출력 ${(item.geometry_present_fraction * 100).toFixed(1)}%`);
    }
  }
  function updateCaptions() {
    if (!currentView) return;
    state.selectedModels.forEach((id, i) => metricCaption($(`metric-${i}`), id));
    metricCaption($('metric-wipe'), state.wipeModel);
    $('view-context').textContent = `뷰 ${currentView.image_id} · ${currentView.width.toLocaleString()} × ${currentView.height.toLocaleString()} px · 공통 평가 ${(currentView.common_pixels ?? 0).toLocaleString()} px`;
  }
  async function ensureImages() {
    const version = ++loadVersion;
    const view = currentView;
    state.loading = true; state.ready = false;
    $('loading-message').hidden = false; showError(null);
    const ids = [...new Set(['target', ...state.selectedModels, state.wipeLeft, state.wipeModel])];
    try {
      const results = await Promise.all(ids.map(async id => {
        const image = await loadImage(pathFor(id));
        if (image.naturalWidth !== view.width || image.naturalHeight !== view.height) {
          throw new Error(`뷰 ${view.image_id}의 이미지 크기가 공통 좌표와 다릅니다: ${id}`);
        }
        return id;
      }));
      if (version !== loadVersion) return;
      state.loadedImages = results; state.ready = true;
    } catch (error) {
      if (version !== loadVersion) return;
      showError(error.message || String(error)); state.ready = false;
    } finally {
      if (version === loadVersion) {
        state.loading = false; $('loading-message').hidden = true; scheduleDraw();
      }
    }
  }
  async function setView(id) {
    currentView = data.views.find(view => String(view.image_id) === String(id));
    if (!currentView) throw new Error('해당 사진 뷰가 없습니다.');
    state.viewId = currentView.image_id;
    $('view-select').value = String(currentView.image_id);
    for (const [button, viewId] of [['view-roof', 333], ['view-window', 361]]) {
      $(button).classList.toggle('active', String(currentView.image_id) === String(viewId));
    }
    const location = new URL(window.location.href);
    location.searchParams.set('view', String(currentView.image_id));
    window.history.replaceState(null, '', location);
    state.loadedImages = [];
    resetFit(); updateCaptions(); scheduleDraw();
    await ensureImages();
  }
  async function setModel(panel, id) {
    if (!model(id)) throw new Error('해당 결과가 없습니다.');
    if (!Number.isInteger(panel) || panel < 0 || panel > 2) throw new Error('결과 화면 번호가 잘못됐습니다.');
    state.selectedModels[panel] = id;
    $(`model-select-${panel}`).value = id;
    updateCaptions(); scheduleDraw(); await ensureImages();
  }
  function setMode(mode) {
    if (!['grid', 'wipe'].includes(mode)) throw new Error('알 수 없는 비교 방식입니다.');
    state.mode = mode;
    $('grid-mode').hidden = mode !== 'grid'; $('wipe-mode').hidden = mode !== 'wipe';
    for (const item of ['grid', 'wipe']) {
      $(`mode-${item}`).classList.toggle('active', mode === item);
      $(`mode-${item}`).setAttribute('aria-pressed', String(mode === item));
    }
    scheduleDraw();
  }
  function setWipePosition(value) {
    state.wipePosition = Math.max(0, Math.min(1, Number(value)));
    $('wipe-position').value = state.wipePosition * 100;
    $('wipe-position-output').value = `${Math.round(state.wipePosition * 100)}%`;
    scheduleDraw();
  }
  function bindCanvas(canvas) {
    let drag = null;
    canvas.addEventListener('wheel', event => {
      event.preventDefault();
      changeZoom(state.zoom * Math.exp(-event.deltaY * 0.0015), canvas, event.clientX, event.clientY);
    }, {passive: false});
    canvas.addEventListener('pointerdown', event => {
      if (event.button !== 0 || !currentView) return;
      const box = canvas.getBoundingClientRect();
      const divider = canvas.id === 'canvas-wipe' && Math.abs(event.clientX - box.left - box.width * state.wipePosition) < 18;
      drag = {x: event.clientX, y: event.clientY, pointer: event.pointerId, divider};
      canvas.setPointerCapture(event.pointerId); canvas.classList.add('dragging');
    });
    canvas.addEventListener('pointermove', event => {
      if (!drag || drag.pointer !== event.pointerId) return;
      if (drag.divider) {
        const box = canvas.getBoundingClientRect();
        setWipePosition((event.clientX - box.left) / box.width);
      } else {
        state.center.x -= (event.clientX - drag.x) / state.zoom;
        state.center.y -= (event.clientY - drag.y) / state.zoom;
        state.fit = false; scheduleDraw();
      }
      drag.x = event.clientX; drag.y = event.clientY;
    });
    const end = () => { drag = null; canvas.classList.remove('dragging'); };
    canvas.addEventListener('pointerup', end); canvas.addEventListener('pointercancel', end);
    canvas.addEventListener('lostpointercapture', end);
    canvas.addEventListener('dblclick', resetFit);
    canvas.addEventListener('keydown', event => {
      const movement = {ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1]}[event.key];
      if (movement) {
        event.preventDefault(); state.center.x += movement[0] * 45 / state.zoom;
        state.center.y += movement[1] * 45 / state.zoom; state.fit = false; scheduleDraw();
      } else if (event.key === '+' || event.key === '=') { event.preventDefault(); changeZoom(state.zoom * 1.3); }
      else if (event.key === '-') { event.preventDefault(); changeZoom(state.zoom / 1.3); }
      else if (event.key === '0') { event.preventDefault(); resetFit(); }
    });
  }
  function fillModelSelect(select, value) {
    for (const source of ['MVS', 'ALS']) {
      const group = document.createElement('optgroup');
      group.label = source === 'MVS' ? '현재 MVS 초기화' : 'A 미적용 과거 ALS 진단';
      for (const item of data.models.filter(item => item.source === source)) {
        group.append(new Option(label(item.id), item.id));
      }
      select.append(group);
    }
    select.value = value; select.disabled = false;
  }
  async function init() {
    try {
      const response = await fetch('data.json', {cache: 'no-store'});
      if (!response.ok) throw new Error(`비교 자료를 읽지 못했습니다 (${response.status}).`);
      data = await response.json();
      if (!Array.isArray(data.views) || !data.views.length || !Array.isArray(data.models)) {
        throw new Error('사진·결과 목록이 없는 비교 자료입니다.');
      }
      for (const item of data.views) {
        if (!Number.isFinite(item.width) || !Number.isFinite(item.height) || item.width <= 0 || item.height <= 0) {
          throw new Error('사진 크기 정보가 잘못됐습니다.');
        }
        $('view-select').append(new Option(`뷰 ${item.image_id}`, item.image_id));
      }
      for (const id of defaults) if (!model(id)) throw new Error(`기본 비교 결과가 없습니다: ${id}`);
      $('view-select').disabled = false;
      for (const [button, viewId] of [['view-roof', 333], ['view-window', 361]]) {
        $(button).disabled = !data.views.some(view => String(view.image_id) === String(viewId));
        $(button).addEventListener('click', () => setView(viewId).catch(error => showError(error.message)));
      }
      state.selectedModels.forEach((id, i) => fillModelSelect($(`model-select-${i}`), id));
      fillModelSelect($('wipe-model'), state.wipeModel);
      for (const item of data.models.filter(item => item.phase === 'initial')) {
        $('wipe-left').append(new Option(label(item.id), item.id));
      }
      const scope = document.createElement('pre');
      scope.textContent = JSON.stringify({scope: data.scope || {}, summary: data.summary || {}}, null, 2);
      $('technical-content').append(scope);
      $('view-select').addEventListener('change', event => setView(event.target.value).catch(error => showError(error.message)));
      state.selectedModels.forEach((_, i) => $(`model-select-${i}`).addEventListener('change', event => setModel(i, event.target.value).catch(error => showError(error.message))));
      $('wipe-model').addEventListener('change', event => {
        state.wipeModel = event.target.value; updateCaptions(); scheduleDraw(); ensureImages();
      });
      $('wipe-left').addEventListener('change', event => { state.wipeLeft = event.target.value; scheduleDraw(); ensureImages(); });
      $('wipe-position').addEventListener('input', event => setWipePosition(Number(event.target.value) / 100));
      $('mode-grid').addEventListener('click', () => setMode('grid'));
      $('mode-wipe').addEventListener('click', () => setMode('wipe'));
      $('zoom-in').addEventListener('click', () => changeZoom(state.zoom * 1.4));
      $('zoom-out').addEventListener('click', () => changeZoom(state.zoom / 1.4));
      $('fit-button').addEventListener('click', resetFit);
      $('native-button').addEventListener('click', () => changeZoom(1));
      canvases.forEach(bindCanvas);
      new ResizeObserver(scheduleDraw).observe($('grid-mode'));
      window.addEventListener('resize', scheduleDraw);
      const requestedView = new URLSearchParams(window.location.search).get('view');
      const initialView = requestedView !== null && data.views.some(view => String(view.image_id) === requestedView)
        ? requestedView : (data.default_view_id ?? 361);
      await setView(initialView);
    } catch (error) {
      state.ready = false; state.loading = false; $('loading-message').hidden = true;
      showError(error.message || String(error));
    }
  }
  window.p2Viewer = {setView, setModel, setMode, fit: resetFit, zoomTo: changeZoom,
    setWipePosition, redraw: scheduleDraw};
  init();
})();
