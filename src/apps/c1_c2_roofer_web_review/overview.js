import * as THREE from 'three';

const manifest = await fetchJson('./viewer_manifest.json');
if (!manifest.overview) throw new Error('overview manifest is missing');

const COLORS = {
  lidarMesh: 0x19dc64,
  mvsMesh: 0xe62dd2,
  footprint: 0xffffff,
  marker: 0xffd83d,
  selected: 0xff5c35,
  ground: [145 / 255, 145 / 255, 145 / 255],
  lidar: [40 / 255, 150 / 255, 1],
  mvs: [1, 145 / 255, 35 / 255],
};

const state = {
  method: 'lidar', colorMode: 'rgb', pointSize: 3.5, meshOpacity: 0.65,
  showPoints: true, showRoofer: true, showFootprints: true, showMarkers: true,
  selectedIndex: 0,
};

const elements = Object.fromEntries([
  'overviewMethod', 'buildingSelect', 'focusBuilding', 'openDetail', 'message',
  'colorMode', 'showPoints', 'showRoofer', 'showFootprints', 'showMarkers',
  'pointSize', 'pointSizeValue', 'meshOpacity', 'meshOpacityValue', 'fitScene',
  'overviewViewport', 'stats', 'loading',
].map((id) => [id, document.getElementById(id)]));

async function fetchJson(url) {
  const response = await fetch(url, { cache: 'no-store' });
  if (!response.ok) throw new Error(`${url}: ${response.status} ${response.statusText}`);
  return response.json();
}

async function fetchBuffer(url) {
  const response = await fetch(url, { cache: 'force-cache' });
  if (!response.ok) throw new Error(`${url}: ${response.status} ${response.statusText}`);
  return response.arrayBuffer();
}

async function fetchText(url) {
  const response = await fetch(url, { cache: 'force-cache' });
  if (!response.ok) throw new Error(`${url}: ${response.status} ${response.statusText}`);
  return response.text();
}

function parseBinaryPly(buffer) {
  const bytes = new Uint8Array(buffer);
  const marker = new TextEncoder().encode('end_header\n');
  let bodyOffset = -1;
  outer: for (let i = 0; i <= bytes.length - marker.length; i += 1) {
    for (let j = 0; j < marker.length; j += 1) if (bytes[i + j] !== marker[j]) continue outer;
    bodyOffset = i + marker.length;
    break;
  }
  if (bodyOffset < 0) throw new Error('PLY header terminator missing');
  const header = new TextDecoder().decode(bytes.subarray(0, bodyOffset));
  const countMatch = header.match(/element vertex (\d+)/);
  if (!header.includes('format binary_little_endian 1.0') || !countMatch || !header.includes('property uchar classification')) {
    throw new Error('unsupported overview PLY schema');
  }
  const count = Number(countMatch[1]);
  const stride = 16;
  if (bodyOffset + count * stride !== buffer.byteLength) throw new Error('overview PLY body length mismatch');
  const view = new DataView(buffer, bodyOffset);
  const positions = new Float32Array(count * 3);
  const rgbColors = new Float32Array(count * 3);
  const classifications = new Uint8Array(count);
  for (let i = 0; i < count; i += 1) {
    const offset = i * stride;
    positions[i * 3] = view.getFloat32(offset, true);
    positions[i * 3 + 1] = view.getFloat32(offset + 4, true);
    positions[i * 3 + 2] = view.getFloat32(offset + 8, true);
    rgbColors[i * 3] = view.getUint8(offset + 12) / 255;
    rgbColors[i * 3 + 1] = view.getUint8(offset + 13) / 255;
    rgbColors[i * 3 + 2] = view.getUint8(offset + 14) / 255;
    classifications[i] = view.getUint8(offset + 15);
  }
  return { count, positions, rgbColors, classifications };
}

function parseObj(text) {
  const vertices = [];
  const triangles = [];
  const segments = [];
  for (const rawLine of text.split(/\r?\n/)) {
    const parts = rawLine.trim().split(/\s+/);
    if (parts[0] === 'v') vertices.push(parts.slice(1, 4).map(Number));
    else if (parts[0] === 'f') {
      const ids = parts.slice(1).map((token) => Number(token.split('/')[0]) - 1);
      for (let i = 1; i + 1 < ids.length; i += 1) for (const id of [ids[0], ids[i], ids[i + 1]]) triangles.push(...vertices[id]);
    } else if (parts[0] === 'l') {
      const ids = parts.slice(1).map((token) => Number(token.split('/')[0]) - 1);
      for (let i = 0; i + 1 < ids.length; i += 1) segments.push(...vertices[ids[i]], ...vertices[ids[i + 1]]);
    }
  }
  return { triangles: new Float32Array(triangles), segments: new Float32Array(segments) };
}

function conditionColors(method, classes) {
  const output = new Float32Array(classes.length * 3);
  const building = COLORS[method];
  for (let i = 0; i < classes.length; i += 1) output.set(classes[i] === 2 ? COLORS.ground : building, i * 3);
  return output;
}

class Orbit {
  constructor() { this.target = new THREE.Vector3(); this.distance = 400; this.yaw = -0.8; this.pitch = 0.58; }
  apply(camera) {
    const cp = Math.cos(this.pitch);
    camera.position.set(
      this.target.x + this.distance * cp * Math.cos(this.yaw),
      this.target.y + this.distance * cp * Math.sin(this.yaw),
      this.target.z + this.distance * Math.sin(this.pitch),
    );
    camera.up.set(0, 0, 1);
    camera.lookAt(this.target);
  }
}

class OverviewViewer {
  constructor(root) {
    this.root = root;
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x030507);
    this.camera = new THREE.PerspectiveCamera(45, 1, 0.1, 5000);
    this.renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
    root.appendChild(this.renderer.domElement);
    this.scene.add(new THREE.HemisphereLight(0xffffff, 0x263446, 1.35));
    const light = new THREE.DirectionalLight(0xffffff, 1.1); light.position.set(50, -70, 120); this.scene.add(light);
    this.orbit = new Orbit();
    this.methodGroups = new Map();
    this.bounds = new THREE.Box3();
    this.drag = null;
    this.installControls();
  }

  async initialize() {
    const [footprintText] = await Promise.all([fetchText(manifest.overview.footprints)]);
    const footprintParsed = parseObj(footprintText);
    const footprintGeometry = new THREE.BufferGeometry();
    footprintGeometry.setAttribute('position', new THREE.BufferAttribute(footprintParsed.segments, 3));
    this.footprints = new THREE.LineSegments(footprintGeometry, new THREE.LineBasicMaterial({ color: COLORS.footprint, transparent: true, opacity: 0.72 }));
    this.scene.add(this.footprints);
    const markerGeometry = new THREE.SphereGeometry(0.9, 10, 7);
    const markerMaterial = new THREE.MeshBasicMaterial({ color: COLORS.marker, transparent: true, opacity: 0.78, depthTest: false });
    this.markers = new THREE.InstancedMesh(markerGeometry, markerMaterial, manifest.overview.buildings.length);
    const matrix = new THREE.Matrix4();
    manifest.overview.buildings.forEach((building, index) => {
      matrix.makeTranslation(...building.center_local_xyz);
      this.markers.setMatrixAt(index, matrix);
    });
    this.markers.instanceMatrix.needsUpdate = true;
    this.markers.renderOrder = 10;
    this.scene.add(this.markers);
    this.highlight = new THREE.Mesh(
      new THREE.RingGeometry(1.2, 1.8, 32),
      new THREE.MeshBasicMaterial({ color: COLORS.selected, side: THREE.DoubleSide, depthTest: false }),
    );
    this.highlight.renderOrder = 12;
    this.scene.add(this.highlight);
    await this.setMethod(state.method, true);
  }

  async loadMethod(method) {
    if (this.methodGroups.has(method)) return this.methodGroups.get(method);
    const spec = manifest.overview.methods[method];
    const [pointBuffer, rooferText] = await Promise.all([fetchBuffer(spec.points), fetchText(spec.roofer)]);
    const ply = parseBinaryPly(pointBuffer);
    const pointGeometry = new THREE.BufferGeometry();
    pointGeometry.setAttribute('position', new THREE.BufferAttribute(ply.positions, 3));
    const rgb = new THREE.BufferAttribute(ply.rgbColors, 3);
    const condition = new THREE.BufferAttribute(conditionColors(method, ply.classifications), 3);
    pointGeometry.setAttribute('color', state.colorMode === 'rgb' ? rgb : condition);
    pointGeometry.computeBoundingBox();
    const points = new THREE.Points(pointGeometry, new THREE.PointsMaterial({ size: state.pointSize, sizeAttenuation: false, vertexColors: true }));
    const parsed = parseObj(rooferText);
    const meshGeometry = new THREE.BufferGeometry();
    meshGeometry.setAttribute('position', new THREE.BufferAttribute(parsed.triangles, 3));
    meshGeometry.computeVertexNormals();
    const mesh = new THREE.Mesh(meshGeometry, new THREE.MeshStandardMaterial({
      color: method === 'lidar' ? COLORS.lidarMesh : COLORS.mvsMesh,
      transparent: true, opacity: state.meshOpacity, side: THREE.DoubleSide, depthWrite: false, roughness: 0.75,
    }));
    const group = new THREE.Group();
    group.add(points, mesh);
    group.userData = { points, mesh, rgb, condition, count: ply.count, triangles: parsed.triangles.length / 9 };
    group.visible = false;
    this.scene.add(group);
    this.methodGroups.set(method, group);
    return group;
  }

  async setMethod(method, fit = false) {
    elements.loading.hidden = false;
    elements.message.textContent = `${method.toUpperCase()} 전체 scene 불러오는 중`;
    try {
      const group = await this.loadMethod(method);
      for (const [key, value] of this.methodGroups) value.visible = key === method;
      state.method = method;
      this.bounds.copy(group.userData.points.geometry.boundingBox);
      this.applySettings();
      if (fit) this.fit('oblique');
      elements.stats.textContent = `${method.toUpperCase()} · ${group.userData.count.toLocaleString()} LOD points · ${group.userData.triangles.toLocaleString()} Roofer triangles · 199 footprints`;
      elements.message.textContent = `${method.toUpperCase()} scene 준비 완료`;
      this.selectBuilding(state.selectedIndex, false);
    } finally { elements.loading.hidden = true; }
  }

  applySettings() {
    for (const [method, group] of this.methodGroups) {
      const data = group.userData;
      data.points.visible = state.showPoints;
      data.points.material.size = state.pointSize;
      data.points.geometry.setAttribute('color', state.colorMode === 'rgb' ? data.rgb : data.condition);
      data.points.geometry.getAttribute('color').needsUpdate = true;
      data.mesh.visible = state.showRoofer;
      data.mesh.material.opacity = state.meshOpacity;
    }
    this.footprints.visible = state.showFootprints;
    this.markers.visible = state.showMarkers;
    this.highlight.visible = state.showMarkers;
  }

  selectBuilding(index, focus) {
    state.selectedIndex = index;
    const building = manifest.overview.buildings[index];
    this.highlight.position.fromArray(building.center_local_xyz);
    this.highlight.position.z += 0.25;
    elements.buildingSelect.value = String(index);
    elements.message.textContent = `B${String(building.population_index).padStart(3, '0')} ${building.stable_id} · ${state.method.toUpperCase()} ${building[state.method].technical_status}`;
    elements.openDetail.hidden = !building.detail_available;
    if (building.detail_available) elements.openDetail.href = `./index.html?building=${building.population_index}`;
    if (focus) {
      this.orbit.target.fromArray(building.center_local_xyz);
      const span = Math.max(building.bbox_local_xy[2] - building.bbox_local_xy[0], building.bbox_local_xy[3] - building.bbox_local_xy[1]);
      this.orbit.distance = Math.max(24, span * 4.5);
      this.setView('oblique', true);
    }
    const url = new URL(window.location.href);
    url.searchParams.set('method', state.method);
    url.searchParams.set('building', building.population_index);
    history.replaceState(null, '', url);
  }

  fit(view) {
    if (this.bounds.isEmpty()) return;
    this.bounds.getCenter(this.orbit.target);
    this.orbit.distance = Math.max(100, this.bounds.getSize(new THREE.Vector3()).length() * 0.78);
    this.setView(view, true);
  }

  setView(view, keepTarget = true) {
    if (!keepTarget && !this.bounds.isEmpty()) this.bounds.getCenter(this.orbit.target);
    if (view === 'top') { this.orbit.yaw = -Math.PI / 2; this.orbit.pitch = 1.53; }
    else if (view === 'side') { this.orbit.yaw = 0; this.orbit.pitch = 0.08; }
    else { this.orbit.yaw = -0.8; this.orbit.pitch = 0.58; }
    this.orbit.apply(this.camera);
  }

  installControls() {
    const canvas = this.renderer.domElement;
    canvas.addEventListener('contextmenu', (event) => event.preventDefault());
    canvas.addEventListener('pointerdown', (event) => {
      canvas.setPointerCapture(event.pointerId);
      this.drag = { x:event.clientX, y:event.clientY, sx:event.clientX, sy:event.clientY, mode:event.button === 2 || event.shiftKey ? 'pan' : 'rotate' };
    });
    canvas.addEventListener('pointermove', (event) => {
      if (!this.drag) return;
      const dx=event.clientX-this.drag.x, dy=event.clientY-this.drag.y; this.drag.x=event.clientX; this.drag.y=event.clientY;
      if (this.drag.mode === 'pan') this.pan(dx,dy);
      else { this.orbit.yaw -= dx*0.005; this.orbit.pitch=Math.max(-1.48,Math.min(1.53,this.orbit.pitch+dy*0.005)); }
      this.orbit.apply(this.camera);
    });
    canvas.addEventListener('pointerup', (event) => {
      if (!this.drag) return;
      const moved=Math.hypot(event.clientX-this.drag.sx,event.clientY-this.drag.sy); this.drag=null;
      if (moved < 4 && state.showMarkers) this.pickBuilding(event);
    });
    canvas.addEventListener('wheel', (event) => {
      event.preventDefault(); this.orbit.distance=Math.max(1,Math.min(4000,this.orbit.distance*Math.exp(event.deltaY*0.0012))); this.orbit.apply(this.camera);
    }, { passive:false });
  }

  pan(dx,dy) {
    this.camera.updateMatrixWorld();
    const right=new THREE.Vector3().setFromMatrixColumn(this.camera.matrixWorld,0), up=new THREE.Vector3().setFromMatrixColumn(this.camera.matrixWorld,1);
    const speed=this.orbit.distance*0.0013; this.orbit.target.addScaledVector(right,-dx*speed); this.orbit.target.addScaledVector(up,dy*speed);
  }

  pickBuilding(event) {
    const rect=this.renderer.domElement.getBoundingClientRect();
    const mouse=new THREE.Vector2(((event.clientX-rect.left)/rect.width)*2-1,-((event.clientY-rect.top)/rect.height)*2+1);
    const raycaster=new THREE.Raycaster(); raycaster.setFromCamera(mouse,this.camera);
    const hit=raycaster.intersectObject(this.markers,false)[0];
    if (hit && Number.isInteger(hit.instanceId)) this.selectBuilding(hit.instanceId,true);
  }

  render() {
    const width=Math.max(1,this.root.clientWidth), height=Math.max(1,this.root.clientHeight), ratio=this.renderer.getPixelRatio();
    if (this.renderer.domElement.width !== Math.floor(width*ratio) || this.renderer.domElement.height !== Math.floor(height*ratio)) {
      this.renderer.setSize(width,height,false); this.camera.aspect=width/height; this.camera.updateProjectionMatrix();
    }
    this.renderer.render(this.scene,this.camera);
  }
}

manifest.overview.buildings.forEach((building,index) => {
  const option=document.createElement('option'); option.value=String(index);
  option.textContent=`B${String(building.population_index).padStart(3,'0')} · ${building.stable_id}`;
  elements.buildingSelect.appendChild(option);
});
const params=new URLSearchParams(window.location.search);
const requestedMethod=params.get('method');
if (requestedMethod === 'mvs' || requestedMethod === 'lidar') state.method=requestedMethod;
const requestedBuilding=Number(String(params.get('building') || '').replace(/^B/i,''));
const requestedIndex=manifest.overview.buildings.findIndex((building) => building.population_index === requestedBuilding);
state.selectedIndex=Math.max(0,requestedIndex);
elements.overviewMethod.value=state.method;

const viewer=new OverviewViewer(elements.overviewViewport);
elements.overviewMethod.addEventListener('change', async (event) => viewer.setMethod(event.target.value,true));
elements.buildingSelect.addEventListener('change', (event) => viewer.selectBuilding(Number(event.target.value),true));
elements.focusBuilding.addEventListener('click', () => viewer.selectBuilding(Number(elements.buildingSelect.value),true));
elements.colorMode.addEventListener('change', (event) => { state.colorMode=event.target.value; viewer.applySettings(); });
for (const id of ['showPoints','showRoofer','showFootprints','showMarkers']) elements[id].addEventListener('change',(event)=>{ state[id]=event.target.checked; viewer.applySettings(); });
elements.pointSize.addEventListener('input',(event)=>{ state.pointSize=Number(event.target.value); elements.pointSizeValue.textContent=state.pointSize.toFixed(2); viewer.applySettings(); });
elements.meshOpacity.addEventListener('input',(event)=>{ state.meshOpacity=Number(event.target.value); elements.meshOpacityValue.textContent=state.meshOpacity.toFixed(2); viewer.applySettings(); });
elements.fitScene.addEventListener('click',()=>viewer.fit('oblique'));
document.querySelectorAll('[data-view]').forEach((button)=>button.addEventListener('click',()=>viewer.setView(button.dataset.view,true)));
await viewer.initialize();
viewer.selectBuilding(state.selectedIndex, requestedIndex >= 0);
function animate(){ viewer.render(); requestAnimationFrame(animate); }
animate();
