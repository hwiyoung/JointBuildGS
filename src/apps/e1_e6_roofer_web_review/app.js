import * as THREE from 'three';

const manifest = await (await fetch('./viewer_manifest.json', {cache: 'no-store'})).json();
const grid = document.getElementById('grid');
const info = document.getElementById('info');
const initialOrbit = {target: new THREE.Vector3(0, 0, -20), distance: 650, yaw: -0.9, pitch: 0.85};
const orbit = {target: initialOrbit.target.clone(), distance: initialOrbit.distance, yaw: initialOrbit.yaw, pitch: initialOrbit.pitch};
const viewers = [];
const initialParameters = new URLSearchParams(window.location.search);
const initialMode = initialParameters.get('mode');
const initialE3Variant = initialParameters.get('e3');
let realCandidatesVisible = false;
let syntheticRegionsVisible = false;
let rooferPointcloudsVisible = initialMode !== 'surface';
let surfaceMeshesVisible = initialMode === 'surface';
let rooferMeshesVisible = initialMode !== 'surface';

function regionOverlay(regions, name, opacity) {
  const group = new THREE.Group();
  group.name = name;
  const bottomZ = -80;
  const topZ = 15;
  for (const region of regions || []) {
    const positions = [];
    for (const ring of region.rings_local_xy) {
      for (let index = 0; index + 1 < ring.length; index++) {
        const [x0, y0] = ring[index];
        const [x1, y1] = ring[index + 1];
        positions.push(x0, y0, bottomZ, x1, y1, bottomZ);
        positions.push(x0, y0, topZ, x1, y1, topZ);
      }
      if (ring.length) {
        const [x0, y0] = ring[0];
        positions.push(x0, y0, bottomZ, x0, y0, topZ);
      }
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
    const lines = new THREE.LineSegments(
      geometry,
      new THREE.LineBasicMaterial({color: region.color, transparent: true, opacity, depthTest: false}),
    );
    lines.renderOrder = 10;
    lines.userData.changeRegion = region;
    group.add(lines);
  }
  return group;
}

async function rooferPointcloud(spec) {
  const group = new THREE.Group();
  group.name = `${spec.condition}-roofer-input-display-adapter`;
  if (!spec.roofer_pointcloud) return group;
  const styles = {
    ground: {color: '#64748b', size: 1.0},
    building: {color: '#f8fafc', size: 1.35},
  };
  for (const className of ['ground', 'building']) {
    const asset = spec.roofer_pointcloud.assets[className];
    const positions = new Float32Array(await (await fetch(asset)).arrayBuffer());
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    group.add(new THREE.Points(
      geometry,
      new THREE.PointsMaterial({
        color: styles[className].color,
        size: styles[className].size,
        sizeAttenuation: false,
        transparent: true,
        opacity: className === 'ground' ? 0.58 : 0.82,
      }),
    ));
  }
  return group;
}

function surfaceMesh(spec) {
  const group = new THREE.Group();
  group.name = `${spec.condition || 'reference'}-surface-mesh-display-adapter`;
  group.userData.loaded = !spec.surface_mesh;
  group.userData.load = async () => {
    if (group.userData.loaded || !spec.surface_mesh) return;
    const positions = new Float32Array(await (await fetch(spec.surface_mesh.asset)).arrayBuffer());
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.computeVertexNormals();
    group.add(new THREE.Mesh(
      geometry,
      new THREE.MeshStandardMaterial({
        color: spec.color || '#e2e8f0',
        roughness: 0.88,
        metalness: 0.0,
        side: THREE.DoubleSide,
        flatShading: true,
      }),
    ));
    group.userData.loaded = true;
  };
  return group;
}

function parseObj(text) {
  const vertices = [], triangles = [];
  for (const raw of text.split(/\r?\n/)) {
    const parts = raw.trim().split(/\s+/);
    if (parts[0] === 'v') vertices.push(parts.slice(1, 4).map(Number));
    else if (parts[0] === 'f') {
      const ids = parts.slice(1).map(value => Number(value.split('/')[0]) - 1);
      for (let index = 1; index + 1 < ids.length; index++) {
        triangles.push(...vertices[ids[0]], ...vertices[ids[index]], ...vertices[ids[index + 1]]);
      }
    }
  }
  return new Float32Array(triangles);
}

async function panelObject(spec) {
  if (spec.type === 'mesh') {
    const positions = parseObj(await (await fetch(spec.asset)).text());
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.computeVertexNormals();
    return new THREE.Mesh(
      geometry,
      new THREE.MeshStandardMaterial({color: spec.color, roughness: 0.82, metalness: 0.04, side: THREE.DoubleSide}),
    );
  }
  const positions = new Float32Array(await (await fetch(spec.asset)).arrayBuffer());
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  return new THREE.Points(
    geometry,
    new THREE.PointsMaterial({color: spec.color, size: 1.4, sizeAttenuation: false}),
  );
}

function applyCamera(camera) {
  const cosine = Math.cos(orbit.pitch);
  camera.position.set(
    orbit.target.x + orbit.distance * cosine * Math.cos(orbit.yaw),
    orbit.target.y + orbit.distance * cosine * Math.sin(orbit.yaw),
    orbit.target.z + orbit.distance * Math.sin(orbit.pitch),
  );
  camera.up.set(0, 0, 1);
  camera.lookAt(orbit.target);
  camera.updateMatrixWorld();
}

function panCamera(viewer, dx, dy) {
  applyCamera(viewer.camera);
  const right = new THREE.Vector3().setFromMatrixColumn(viewer.camera.matrixWorld, 0);
  const up = new THREE.Vector3().setFromMatrixColumn(viewer.camera.matrixWorld, 1);
  const scale = orbit.distance * 0.0016;
  orbit.target.addScaledVector(right, -dx * scale);
  orbit.target.addScaledVector(up, dy * scale);
}

function resetView() {
  orbit.target.copy(initialOrbit.target);
  orbit.distance = initialOrbit.distance;
  orbit.yaw = initialOrbit.yaw;
  orbit.pitch = initialOrbit.pitch;
  info.textContent = '초기 시점 복원 · 카메라 동기화 ON';
}

function focusBuilding(stableId) {
  const building = manifest.buildings.find(item => item.stable_id === stableId);
  if (!building) return;
  const [minx, miny, maxx, maxy] = building.bbox_local_xy;
  orbit.target.set((minx + maxx) / 2, (miny + maxy) / 2, -20);
  orbit.distance = Math.max(70, 2.2 * Math.max(maxx - minx, maxy - miny));
  orbit.yaw = -0.9;
  orbit.pitch = 0.85;
  info.textContent = `${stableId} 중심 보기 · 모든 패널 카메라 동기화 ON`;
}

async function createPanel(spec) {
  const shell = document.createElement('section');
  shell.className = 'panel';
  shell.innerHTML = `<div class="label" style="border-left:4px solid ${spec.color}">${spec.label}</div><div class="view"></div>`;
  grid.appendChild(shell);
  const root = shell.querySelector('.view');
  const renderer = new THREE.WebGLRenderer({antialias: true});
  renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5));
  root.appendChild(renderer.domElement);
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x05070a);
  scene.add(new THREE.HemisphereLight(0xffffff, 0x233044, 1.6));
  const directional = new THREE.DirectionalLight(0xffffff, 1.1);
  directional.position.set(100, -150, 250);
  scene.add(directional);
  const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 5000);
  let object = await panelObject(spec);
  object.visible = rooferMeshesVisible;
  scene.add(object);
  const evidence = await rooferPointcloud(spec);
  evidence.visible = rooferPointcloudsVisible;
  scene.add(evidence);
  const surface = surfaceMesh(spec);
  surface.visible = surfaceMeshesVisible;
  if (surfaceMeshesVisible) await surface.userData.load();
  scene.add(surface);
  const realCandidates = regionOverlay(manifest.real_change_candidates, 'real-change-candidates', 0.98);
  realCandidates.visible = realCandidatesVisible;
  scene.add(realCandidates);
  const syntheticRegions = regionOverlay(manifest.synthetic_change_regions, 'synthetic-evaluation-regions', 0.65);
  syntheticRegions.visible = syntheticRegionsVisible;
  scene.add(syntheticRegions);
  const viewer = {root, renderer, scene, camera, object, evidence, surface, realCandidates, syntheticRegions, spec};
  viewer.variantStates = new Map([[spec.id || 'default', {spec, object, evidence, surface}]]);
  for (const variant of spec.variants || []) {
    if (variant.id === spec.id) continue;
    const variantObject = await panelObject(variant);
    const variantEvidence = await rooferPointcloud(variant);
    const variantSurface = surfaceMesh(variant);
    variantObject.visible = false;
    variantEvidence.visible = false;
    variantSurface.visible = false;
    scene.add(variantObject, variantEvidence, variantSurface);
    viewer.variantStates.set(variant.id, {
      spec: variant,
      object: variantObject,
      evidence: variantEvidence,
      surface: variantSurface,
    });
  }
  viewer.setVariant = async variantId => {
    const next = viewer.variantStates.get(variantId);
    if (!next) return;
    viewer.object.visible = false;
    viewer.evidence.visible = false;
    viewer.surface.visible = false;
    viewer.object = next.object;
    viewer.evidence = next.evidence;
    viewer.surface = next.surface;
    viewer.spec = next.spec;
    viewer.object.visible = rooferMeshesVisible;
    viewer.evidence.visible = rooferPointcloudsVisible;
    if (surfaceMeshesVisible) await viewer.surface.userData.load();
    viewer.surface.visible = surfaceMeshesVisible;
    shell.querySelector('.label').textContent = next.spec.label;
    info.textContent = `${next.spec.label} · Roofer/입력점군/TSDF mesh 동시 전환`;
  };
  viewers.push(viewer);

  let drag = null;
  renderer.domElement.addEventListener('contextmenu', event => event.preventDefault());
  renderer.domElement.addEventListener('pointerdown', event => {
    if (event.button !== 0 && event.button !== 1 && event.button !== 2) return;
    drag = {
      x: event.clientX,
      y: event.clientY,
      moved: false,
      mode: event.button === 2 || event.button === 1 || event.shiftKey ? 'pan' : 'rotate',
    };
    renderer.domElement.setPointerCapture(event.pointerId);
  });
  renderer.domElement.addEventListener('pointermove', event => {
    if (!drag) return;
    const dx = event.clientX - drag.x;
    const dy = event.clientY - drag.y;
    drag.moved ||= Math.abs(dx) + Math.abs(dy) > 3;
    if (drag.mode === 'pan') panCamera(viewer, dx, dy);
    else {
      orbit.yaw -= dx * 0.006;
      orbit.pitch = Math.max(0.08, Math.min(1.48, orbit.pitch + dy * 0.006));
    }
    drag.x = event.clientX;
    drag.y = event.clientY;
  });
  renderer.domElement.addEventListener('pointerup', event => {
    if (drag && !drag.moved && drag.mode === 'rotate') pick(viewer, event);
    drag = null;
  });
  renderer.domElement.addEventListener('pointercancel', () => { drag = null; });
  renderer.domElement.addEventListener('dblclick', resetView);
  renderer.domElement.addEventListener('wheel', event => {
    event.preventDefault();
    orbit.distance = Math.max(8, Math.min(2000, orbit.distance * Math.exp(event.deltaY * 0.001)));
  }, {passive: false});
  return viewer;
}

function pick(viewer, event) {
  const rect = viewer.renderer.domElement.getBoundingClientRect();
  const mouse = new THREE.Vector2(
    (event.clientX - rect.left) / rect.width * 2 - 1,
    -((event.clientY - rect.top) / rect.height * 2 - 1),
  );
  const ray = new THREE.Raycaster();
  ray.params.Points.threshold = 2;
  ray.setFromCamera(mouse, viewer.camera);
  const hit = ray.intersectObject(viewer.object, false)[0];
  if (!hit) {
    info.textContent = '건물 표면 선택 없음';
    return;
  }
  const point = hit.point;
  const building = manifest.buildings.find(candidate => (
    point.x >= candidate.bbox_local_xy[0] && point.x <= candidate.bbox_local_xy[2]
    && point.y >= candidate.bbox_local_xy[1] && point.y <= candidate.bbox_local_xy[3]
  ));
  info.textContent = building
    ? `${building.stable_id} · w_b=${building.w_b.toFixed(4)} · ${building.support_status}${
      building.real_change_candidate ? ` · 시점차 자동 후보: ${building.real_change_candidate.label_ko} (${building.real_change_candidate.confidence})` : ''
    }${
      building.synthetic_change ? ` · 합성 평가영역: ${building.synthetic_change.label_ko}` : ''
    }`
    : 'footprint 밖 · w=1';
}

document.getElementById('resetView').addEventListener('click', resetView);
document.getElementById('focus4906982').addEventListener('click', () => focusBuilding('DEBY_LOD2_4906982'));
document.getElementById('toggleRealChanges').addEventListener('click', event => {
  realCandidatesVisible = !realCandidatesVisible;
  for (const viewer of viewers) viewer.realCandidates.visible = realCandidatesVisible;
  event.currentTarget.textContent = `시점차 후보 ${realCandidatesVisible ? 'ON' : 'OFF'}`;
  info.textContent = realCandidatesVisible ? `ALS/ULS 시점차 자동 후보 ${manifest.real_change_candidates.length}동 표시 · 실제 변화 GT 아님` : '시점차 후보 숨김';
});
document.getElementById('toggleSyntheticChanges').addEventListener('click', event => {
  syntheticRegionsVisible = !syntheticRegionsVisible;
  for (const viewer of viewers) viewer.syntheticRegions.visible = syntheticRegionsVisible;
  event.currentTarget.textContent = `합성 평가 ${syntheticRegionsVisible ? 'ON' : 'OFF'}`;
  info.textContent = syntheticRegionsVisible ? '합성 평가영역 9동 표시 · 실제 변화와 별개' : '합성 평가영역 숨김';
});
document.getElementById('togglePointclouds').addEventListener('click', event => {
  rooferPointcloudsVisible = !rooferPointcloudsVisible;
  for (const viewer of viewers) viewer.evidence.visible = rooferPointcloudsVisible;
  event.currentTarget.textContent = `Roofer점군 ${rooferPointcloudsVisible ? 'ON' : 'OFF'}`;
  info.textContent = rooferPointcloudsVisible ? 'E1-E6 실제 Roofer 입력의 class 2/6 표시 어댑터 ON' : 'Roofer 입력 점군 숨김';
});
document.getElementById('toggleSurfaceMeshes').addEventListener('click', async event => {
  surfaceMeshesVisible = !surfaceMeshesVisible;
  if (surfaceMeshesVisible) {
    info.textContent = '표면 mesh 불러오는 중';
    await Promise.all(viewers.map(viewer => viewer.surface.userData.load()));
  }
  for (const viewer of viewers) viewer.surface.visible = surfaceMeshesVisible;
  event.currentTarget.textContent = `표면mesh ${surfaceMeshesVisible ? 'ON' : 'OFF'}`;
  info.textContent = surfaceMeshesVisible
    ? 'E2 OpenMVS mesh + E3-E6 TSDF mesh 표시 · E1은 고정 surface mesh 없음'
    : '표면 mesh 숨김';
});
document.getElementById('toggleRooferMeshes').addEventListener('click', event => {
  rooferMeshesVisible = !rooferMeshesVisible;
  for (const viewer of viewers) viewer.object.visible = rooferMeshesVisible;
  event.currentTarget.textContent = `Roofer ${rooferMeshesVisible ? 'ON' : 'OFF'}`;
  info.textContent = rooferMeshesVisible ? 'Roofer LoD 출력 표시' : 'Roofer LoD 출력 숨김';
});
document.getElementById('toggleRooferMeshes').textContent = `Roofer ${rooferMeshesVisible ? 'ON' : 'OFF'}`;
document.getElementById('togglePointclouds').textContent = `Roofer점군 ${rooferPointcloudsVisible ? 'ON' : 'OFF'}`;
document.getElementById('toggleSurfaceMeshes').textContent = `표면mesh ${surfaceMeshesVisible ? 'ON' : 'OFF'}`;
document.getElementById('toggleRealChanges').textContent = `시점차 후보 ${realCandidatesVisible ? 'ON' : 'OFF'}`;
await Promise.all(manifest.panels.map(createPanel));
const e3Viewer = viewers.find(viewer => viewer.variantStates.size > 1);
if (e3Viewer) {
  const wrap = document.getElementById('e3VariantWrap');
  const select = document.getElementById('e3Variant');
  select.innerHTML = [...e3Viewer.variantStates.entries()]
    .map(([id, state]) => `<option value="${id}"${id === e3Viewer.spec.id ? ' selected' : ''}>${state.spec.label.replace('E3 image-only GS · 4906982 ', '')}</option>`)
    .join('');
  select.addEventListener('change', () => e3Viewer.setVariant(select.value));
  wrap.hidden = false;
  if (initialE3Variant && e3Viewer.variantStates.has(initialE3Variant)) {
    select.value = initialE3Variant;
    await e3Viewer.setVariant(initialE3Variant);
  }
}

function frame() {
  for (const viewer of viewers) {
    const width = Math.max(1, viewer.root.clientWidth);
    const height = Math.max(1, viewer.root.clientHeight);
    const pixelRatio = Math.min(devicePixelRatio, 1.5);
    if (viewer.renderer.domElement.width !== Math.round(width * pixelRatio)
      || viewer.renderer.domElement.height !== Math.round(height * pixelRatio)) {
      viewer.renderer.setSize(width, height, false);
    }
    viewer.camera.aspect = width / height;
    viewer.camera.updateProjectionMatrix();
    applyCamera(viewer.camera);
    viewer.renderer.render(viewer.scene, viewer.camera);
  }
  requestAnimationFrame(frame);
}

info.textContent = initialMode === 'surface'
  ? 'E2 OpenMVS + E3-E6 TSDF 표면 mesh 로드 완료 · E1 고정 mesh 없음'
  : '8개 패널 로드 완료 · Roofer + E1-E6 입력 점군 표시 · 시점차 후보 기본 OFF';
frame();
