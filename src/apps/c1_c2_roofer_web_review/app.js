import * as THREE from 'three';

const COLORS = {
  lidarMesh: 0x19dc64,
  mvsMesh: 0xe62dd2,
  footprint: 0xffffff,
  curtain: 0xb8c0cc,
  measure: 0xffe34d,
  groundRgb: [145 / 255, 145 / 255, 145 / 255],
  lidarPointRgb: [40 / 255, 150 / 255, 1],
  mvsPointRgb: [1, 145 / 255, 35 / 255],
};
const STORAGE_KEY = 'jointbuildgs-c1-c2-roofer-ox-v1';
const manifest = await fetchJson('./viewer_manifest.json');
const state = {
  buildingIndex: 0,
  activeViewer: 0,
  sync: true,
  showPoints: true,
  showRoofer: true,
  showFootprint: true,
  showCurtain: false,
  wireframe: false,
  colorMode: 'rgb',
  pointSize: 3.5,
  meshOpacity: 0.72,
  clipEnabled: false,
  clipHeight: 0,
  measureMode: false,
  measurementPoints: [],
  reviews: loadReviews(),
};

const elements = Object.fromEntries([
  'buildingSelect', 'prevBuilding', 'nextBuilding', 'buildingStatus', 'message',
  'syncCamera', 'colorMode', 'showPoints', 'showRoofer', 'showFootprint', 'showCurtain',
  'wireframe', 'fitView', 'pointSize', 'pointSizeValue', 'meshOpacity', 'meshOpacityValue',
  'clipEnabled', 'clipHeight', 'clipHeightValue', 'measureMode', 'clearMeasure',
  'measureResult', 'lidarReview', 'mvsReview', 'lidarReviewO', 'lidarReviewX',
  'mvsReviewO', 'mvsReviewX', 'lidarReviewCurrent', 'mvsReviewCurrent',
  'reviewNote', 'exportCsv', 'loading', 'miniMapCanvas', 'miniMapBuilding', 'miniMapStatus',
  'photoDrawer', 'photoTitle', 'projectedRowImage',
].map((id) => [id, document.getElementById(id)]));

const clippingPlane = new THREE.Plane(new THREE.Vector3(0, 0, -1), 1e6);
const viewers = [];

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
  if (!header.includes('format binary_little_endian 1.0')) throw new Error('unsupported PLY format');
  const countMatch = header.match(/element vertex (\d+)/);
  if (!countMatch) throw new Error('PLY vertex count missing');
  const count = Number(countMatch[1]);
  const hasClassification = header.includes('property uchar classification');
  const stride = hasClassification ? 16 : 15;
  if (bodyOffset + count * stride !== buffer.byteLength) throw new Error('PLY body length mismatch');
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
    classifications[i] = hasClassification ? view.getUint8(offset + 15) : 6;
  }
  return { count, positions, rgbColors, classifications };
}

function makeConditionColors(method, classifications) {
  const colors = new Float32Array(classifications.length * 3);
  const building = method === 'lidar' ? COLORS.lidarPointRgb : COLORS.mvsPointRgb;
  for (let i = 0; i < classifications.length; i += 1) {
    const color = classifications[i] === 2 ? COLORS.groundRgb : building;
    colors.set(color, i * 3);
  }
  return colors;
}

function parseObj(text) {
  const vertices = [];
  const triangles = [];
  const segments = [];
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith('#')) continue;
    const parts = line.split(/\s+/);
    if (parts[0] === 'v') {
      vertices.push(parts.slice(1, 4).map(Number));
    } else if (parts[0] === 'f') {
      const ids = parts.slice(1).map((token) => Number(token.split('/')[0]) - 1);
      for (let i = 1; i + 1 < ids.length; i += 1) {
        for (const id of [ids[0], ids[i], ids[i + 1]]) triangles.push(...vertices[id]);
      }
    } else if (parts[0] === 'l') {
      const ids = parts.slice(1).map((token) => Number(token.split('/')[0]) - 1);
      for (let i = 0; i + 1 < ids.length; i += 1) segments.push(...vertices[ids[i]], ...vertices[ids[i + 1]]);
    }
  }
  return {
    triangles: new Float32Array(triangles),
    segments: new Float32Array(segments),
  };
}

function percentile(values, fraction) {
  if (!values.length) return null;
  values.sort((a, b) => a - b);
  return values[Math.min(values.length - 1, Math.floor((values.length - 1) * fraction))];
}

function drawMiniMap(building) {
  const canvas = elements.miniMapCanvas;
  const width = Math.max(1, Math.round(canvas.clientWidth));
  const height = Math.max(1, Math.round(canvas.clientHeight));
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  if (canvas.width !== Math.round(width * ratio) || canvas.height !== Math.round(height * ratio)) {
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
  }
  const context = canvas.getContext('2d');
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  context.clearRect(0, 0, width, height);

  const overviewBuildings = manifest.overview.buildings;
  const allBounds = overviewBuildings.map((item) => item.bbox_local_xy);
  const minX = Math.min(...allBounds.map((value) => value[0]));
  const minY = Math.min(...allBounds.map((value) => value[1]));
  const maxX = Math.max(...allBounds.map((value) => value[2]));
  const maxY = Math.max(...allBounds.map((value) => value[3]));
  const padding = 8;
  const scale = Math.min((width - 2 * padding) / Math.max(1, maxX - minX), (height - 2 * padding) / Math.max(1, maxY - minY));
  const offsetX = (width - (maxX - minX) * scale) / 2;
  const offsetY = (height - (maxY - minY) * scale) / 2;
  const detailById = new Map(manifest.buildings.map((item) => [item.stable_id, item]));
  const project = (x, y) => [offsetX + (x - minX) * scale, height - offsetY - (y - minY) * scale];

  for (const item of overviewBuildings) {
    const detail = detailById.get(item.stable_id);
    const lidar = (detail?.lidar.point_count || 0) > 0;
    const mvs = (detail?.mvs.point_count || 0) > 0;
    const [x1, y1] = project(item.bbox_local_xy[0], item.bbox_local_xy[1]);
    const [x2, y2] = project(item.bbox_local_xy[2], item.bbox_local_xy[3]);
    const rectX = Math.min(x1, x2);
    const rectY = Math.min(y1, y2);
    const rectWidth = Math.max(1.2, Math.abs(x2 - x1));
    const rectHeight = Math.max(1.2, Math.abs(y2 - y1));
    context.fillStyle = !lidar && !mvs ? 'rgba(251,113,133,.72)'
      : lidar && mvs ? 'rgba(128,208,210,.66)'
        : lidar ? 'rgba(107,213,255,.72)' : 'rgba(255,145,51,.72)';
    context.fillRect(rectX, rectY, rectWidth, rectHeight);
  }

  const selected = overviewBuildings.find((item) => item.stable_id === building.stable_id);
  if (selected) {
    const [cx, cy] = project(selected.center_local_xyz[0], selected.center_local_xyz[1]);
    context.strokeStyle = '#ffe34d';
    context.lineWidth = 2;
    context.beginPath();
    context.arc(cx, cy, 5.5, 0, Math.PI * 2);
    context.stroke();
    context.beginPath();
    context.moveTo(cx - 9, cy); context.lineTo(cx + 9, cy);
    context.moveTo(cx, cy - 9); context.lineTo(cx, cy + 9);
    context.stroke();
  }

  const lidarCount = building.lidar.point_count;
  const mvsCount = building.mvs.point_count;
  const absence = lidarCount === 0 && mvsCount === 0 ? ' · 두 조건 모두 표시점 없음' : '';
  elements.miniMapBuilding.textContent = `B${String(building.population_index).padStart(3, '0')}`;
  elements.miniMapStatus.textContent = `LiDAR ${lidarCount.toLocaleString()} · MVS ${mvsCount.toLocaleString()}${absence}`;
}

function roofFocus(ply, footprint, roofer) {
  const footprintBounds = new THREE.Box3().setFromObject(footprint);
  const positions = ply.positions;
  const roofCandidates = [];
  const xyMargin = 0.15;
  for (let i = 0; i < ply.count; i += 1) {
    const x = positions[i * 3];
    const y = positions[i * 3 + 1];
    if (x < footprintBounds.min.x - xyMargin || x > footprintBounds.max.x + xyMargin
        || y < footprintBounds.min.y - xyMargin || y > footprintBounds.max.y + xyMargin) continue;
    if (ply.classifications[i] === 6) {
      roofCandidates.push(positions[i * 3 + 2]);
    }
  }
  let roofZ = percentile(roofCandidates, 0.75);
  if (roofZ === null && roofer) roofZ = new THREE.Box3().setFromObject(roofer).max.z;
  if (roofZ === null) roofZ = footprintBounds.max.z;
  const footprintPositions = footprint.geometry.getAttribute('position');
  for (let i = 0; i < footprintPositions.count; i += 1) footprintPositions.setZ(i, roofZ + 0.05);
  footprintPositions.needsUpdate = true;
  footprint.geometry.computeBoundingBox();
  const horizontalSpan = Math.max(
    footprintBounds.max.x - footprintBounds.min.x,
    footprintBounds.max.y - footprintBounds.min.y,
  );
  const zHalfSpan = Math.max(1, horizontalSpan * 0.35);
  return {
    bounds: new THREE.Box3(
      new THREE.Vector3(footprintBounds.min.x, footprintBounds.min.y, roofZ - zHalfSpan),
      new THREE.Vector3(footprintBounds.max.x, footprintBounds.max.y, roofZ + zHalfSpan),
    ),
    roofZ,
    supportCount: roofCandidates.length,
  };
}

class OrbitState {
  constructor() {
    this.target = new THREE.Vector3();
    this.distance = 30;
    this.yaw = -0.8;
    this.pitch = 0.55;
  }
  copyFrom(other) {
    this.target.copy(other.target);
    this.distance = other.distance;
    this.yaw = other.yaw;
    this.pitch = other.pitch;
  }
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

class ReviewViewer {
  constructor(rootId, statsId, method, index) {
    this.root = document.getElementById(rootId);
    this.stats = document.getElementById(statsId);
    this.method = method;
    this.index = index;
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x05070a);
    this.camera = new THREE.PerspectiveCamera(45, 1, 0.03, 3000);
    this.orbit = new OrbitState();
    this.renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
    this.renderer.localClippingEnabled = true;
    this.root.appendChild(this.renderer.domElement);
    this.content = new THREE.Group();
    this.measurement = new THREE.Group();
    this.scene.add(this.content, this.measurement);
    this.scene.add(new THREE.HemisphereLight(0xffffff, 0x28313e, 1.35));
    const light = new THREE.DirectionalLight(0xffffff, 1.2);
    light.position.set(20, -25, 40);
    this.scene.add(light);
    this.points = null;
    this.roofer = null;
    this.footprint = null;
    this.curtain = null;
    this.focus = null;
    this.baseStats = '';
    this.rgbColors = null;
    this.conditionColors = null;
    this.drag = null;
    this.bounds = new THREE.Box3();
    this.installControls();
  }

  async load(building) {
    this.disposeContent();
    this.stats.textContent = '자산 불러오는 중';
    const spec = building[this.method];
    const [plyBuffer, footprintText, curtainText, rooferText] = await Promise.all([
      fetchBuffer(spec.points),
      fetchText(building.footprint),
      fetchText(building.curtain),
      spec.roofer ? fetchText(spec.roofer) : Promise.resolve(null),
    ]);
    const ply = parseBinaryPly(plyBuffer);
    const pointGeometry = new THREE.BufferGeometry();
    pointGeometry.setAttribute('position', new THREE.BufferAttribute(ply.positions, 3));
    this.rgbColors = new THREE.BufferAttribute(ply.rgbColors, 3);
    this.conditionColors = new THREE.BufferAttribute(makeConditionColors(this.method, ply.classifications), 3);
    pointGeometry.setAttribute('color', state.colorMode === 'rgb' ? this.rgbColors : this.conditionColors);
    pointGeometry.computeBoundingBox();
    const pointMaterial = new THREE.PointsMaterial({
      size: state.pointSize,
      sizeAttenuation: false,
      vertexColors: true,
      clippingPlanes: [clippingPlane],
    });
    this.points = new THREE.Points(pointGeometry, pointMaterial);
    this.points.name = `${this.method}-points`;
    this.content.add(this.points);

    this.footprint = this.makeLines(parseObj(footprintText).segments, COLORS.footprint, 2.2);
    this.footprint.name = 'footprint';
    this.content.add(this.footprint);
    this.curtain = this.makeMesh(parseObj(curtainText).triangles, COLORS.curtain, 0.16);
    this.curtain.name = 'footprint-curtain';
    this.content.add(this.curtain);
    if (rooferText) {
      const color = this.method === 'lidar' ? COLORS.lidarMesh : COLORS.mvsMesh;
      this.roofer = this.makeMesh(parseObj(rooferText).triangles, color, state.meshOpacity);
      this.roofer.name = `${this.method}-roofer`;
      this.content.add(this.roofer);
    }
    const sceneBounds = new THREE.Box3().setFromObject(this.points);
    if (this.roofer) sceneBounds.expandByObject(this.roofer);
    this.focus = roofFocus(ply, this.footprint, this.roofer);
    this.bounds.copy(this.focus.bounds);
    this.applyDisplaySettings();
    this.fit('oblique');
    const roofLabel = this.roofer ? `${spec.roofer_triangles.toLocaleString()} triangles` : 'Roofer MISSING';
    this.baseStats = `${ply.count.toLocaleString()} points · ${roofLabel} · ${spec.technical_status}`;
    this.updateFocusStats();
    return sceneBounds;
  }

  updateFocusStats() {
    const source = this.focus.sharedFrom ? `0 direct pts; shared from ${this.focus.sharedFrom}` : `${this.focus.supportCount} pts`;
    this.stats.textContent = `${this.baseStats} · roof focus ${this.focus.roofZ.toFixed(2)} m (${source})`;
  }

  shareRoofFocus(roofZ, sharedFrom) {
    if (!this.focus || this.focus.supportCount > 0) return;
    const halfSpan = (this.bounds.max.z - this.bounds.min.z) / 2;
    this.bounds.min.z = roofZ - halfSpan;
    this.bounds.max.z = roofZ + halfSpan;
    const positions = this.footprint.geometry.getAttribute('position');
    for (let i = 0; i < positions.count; i += 1) positions.setZ(i, roofZ + 0.05);
    positions.needsUpdate = true;
    this.focus.roofZ = roofZ;
    this.focus.sharedFrom = sharedFrom;
    this.updateFocusStats();
  }

  makeMesh(positions, color, opacity) {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.computeVertexNormals();
    const material = new THREE.MeshStandardMaterial({
      color,
      transparent: opacity < 1,
      opacity,
      roughness: 0.72,
      metalness: 0,
      side: THREE.DoubleSide,
      depthWrite: opacity >= 0.95,
      clippingPlanes: [clippingPlane],
    });
    return new THREE.Mesh(geometry, material);
  }

  makeLines(positions, color, linewidth) {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    return new THREE.LineSegments(geometry, new THREE.LineBasicMaterial({ color, linewidth, clippingPlanes: [clippingPlane] }));
  }

  disposeContent() {
    for (const object of [...this.content.children]) {
      this.content.remove(object);
      object.geometry?.dispose();
      object.material?.dispose();
    }
    this.points = this.roofer = this.footprint = this.curtain = this.focus = null;
    this.rgbColors = this.conditionColors = null;
    this.clearMeasurement();
  }

  applyDisplaySettings() {
    if (this.points) {
      this.points.visible = state.showPoints;
      this.points.geometry.setAttribute('color', state.colorMode === 'rgb' ? this.rgbColors : this.conditionColors);
      this.points.geometry.getAttribute('color').needsUpdate = true;
      this.points.material.size = state.pointSize;
      this.points.material.clippingPlanes = state.clipEnabled ? [clippingPlane] : [];
    }
    if (this.roofer) {
      this.roofer.visible = state.showRoofer;
      this.roofer.material.opacity = state.meshOpacity;
      this.roofer.material.transparent = state.meshOpacity < 1;
      this.roofer.material.depthWrite = state.meshOpacity >= 0.95;
      this.roofer.material.wireframe = state.wireframe;
      this.roofer.material.clippingPlanes = state.clipEnabled ? [clippingPlane] : [];
    }
    if (this.footprint) {
      this.footprint.visible = state.showFootprint;
      this.footprint.material.clippingPlanes = state.clipEnabled ? [clippingPlane] : [];
    }
    if (this.curtain) {
      this.curtain.visible = state.showCurtain;
      this.curtain.material.wireframe = state.wireframe;
      this.curtain.material.clippingPlanes = state.clipEnabled ? [clippingPlane] : [];
    }
  }

  fit(view = 'oblique') {
    if (this.bounds.isEmpty()) return;
    const center = this.bounds.getCenter(new THREE.Vector3());
    const size = this.bounds.getSize(new THREE.Vector3());
    this.orbit.target.copy(center);
    this.orbit.distance = Math.max(3, size.length() * 1.45);
    this.setView(view, false);
  }

  setView(view, keepTarget = true) {
    if (!keepTarget && !this.bounds.isEmpty()) this.bounds.getCenter(this.orbit.target);
    if (view === 'top') {
      this.orbit.yaw = -Math.PI / 2;
      this.orbit.pitch = 1.53;
    } else if (view === 'side') {
      this.orbit.yaw = 0;
      this.orbit.pitch = 0.08;
    } else {
      this.orbit.yaw = -0.8;
      this.orbit.pitch = 0.58;
    }
    this.orbit.apply(this.camera);
  }

  installControls() {
    const canvas = this.renderer.domElement;
    canvas.addEventListener('contextmenu', (event) => event.preventDefault());
    canvas.addEventListener('pointerdown', (event) => {
      state.activeViewer = this.index;
      canvas.setPointerCapture(event.pointerId);
      this.drag = { x: event.clientX, y: event.clientY, startX: event.clientX, startY: event.clientY, mode: event.button === 2 || event.shiftKey ? 'pan' : 'rotate' };
    });
    canvas.addEventListener('pointermove', (event) => {
      if (!this.drag) return;
      const dx = event.clientX - this.drag.x;
      const dy = event.clientY - this.drag.y;
      this.drag.x = event.clientX;
      this.drag.y = event.clientY;
      if (this.drag.mode === 'pan') this.pan(dx, dy);
      else {
        this.orbit.yaw -= dx * 0.005;
        this.orbit.pitch = Math.max(-1.48, Math.min(1.53, this.orbit.pitch + dy * 0.005));
      }
      this.orbit.apply(this.camera);
    });
    canvas.addEventListener('pointerup', (event) => {
      if (!this.drag) return;
      const moved = Math.hypot(event.clientX - this.drag.startX, event.clientY - this.drag.startY);
      this.drag = null;
      if (state.measureMode && moved < 4) this.pickMeasurement(event);
    });
    canvas.addEventListener('wheel', (event) => {
      event.preventDefault();
      state.activeViewer = this.index;
      this.orbit.distance = Math.max(0.3, Math.min(1200, this.orbit.distance * Math.exp(event.deltaY * 0.0012)));
      this.orbit.apply(this.camera);
    }, { passive: false });
  }

  pan(dx, dy) {
    this.camera.updateMatrixWorld();
    const right = new THREE.Vector3().setFromMatrixColumn(this.camera.matrixWorld, 0);
    const up = new THREE.Vector3().setFromMatrixColumn(this.camera.matrixWorld, 1);
    const speed = this.orbit.distance * 0.0015;
    this.orbit.target.addScaledVector(right, -dx * speed);
    this.orbit.target.addScaledVector(up, dy * speed);
  }

  pickMeasurement(event) {
    const rect = this.renderer.domElement.getBoundingClientRect();
    const mouse = new THREE.Vector2(
      ((event.clientX - rect.left) / rect.width) * 2 - 1,
      -((event.clientY - rect.top) / rect.height) * 2 + 1,
    );
    const raycaster = new THREE.Raycaster();
    raycaster.params.Points.threshold = Math.max(0.08, this.orbit.distance * 0.003);
    raycaster.setFromCamera(mouse, this.camera);
    const candidates = [this.points, this.roofer].filter((object) => object?.visible);
    const hits = raycaster.intersectObjects(candidates, false);
    if (!hits.length) {
      elements.measureResult.textContent = '선택 가능한 점/메시를 찾지 못했습니다';
      return;
    }
    addMeasurementPoint(hits[0].point.clone());
  }

  clearMeasurement() {
    for (const object of [...this.measurement.children]) {
      this.measurement.remove(object);
      object.geometry?.dispose();
      object.material?.dispose();
    }
  }

  drawMeasurement(points) {
    this.clearMeasurement();
    for (const point of points) {
      const marker = new THREE.Mesh(
        new THREE.SphereGeometry(Math.max(0.06, this.orbit.distance * 0.004), 16, 10),
        new THREE.MeshBasicMaterial({ color: COLORS.measure, depthTest: false }),
      );
      marker.position.copy(point);
      marker.renderOrder = 20;
      this.measurement.add(marker);
    }
    if (points.length === 2) {
      const geometry = new THREE.BufferGeometry().setFromPoints(points);
      const line = new THREE.Line(geometry, new THREE.LineBasicMaterial({ color: COLORS.measure, depthTest: false }));
      line.renderOrder = 20;
      this.measurement.add(line);
    }
  }

  resize() {
    const width = Math.max(1, this.root.clientWidth);
    const height = Math.max(1, this.root.clientHeight);
    const ratio = this.renderer.getPixelRatio();
    const canvas = this.renderer.domElement;
    if (canvas.width !== Math.floor(width * ratio) || canvas.height !== Math.floor(height * ratio)) {
      this.renderer.setSize(width, height, false);
      this.camera.aspect = width / height;
      this.camera.updateProjectionMatrix();
    }
  }

  render() {
    this.resize();
    this.renderer.render(this.scene, this.camera);
  }
}

async function loadBuilding(index) {
  const normalized = (index + manifest.buildings.length) % manifest.buildings.length;
  state.buildingIndex = normalized;
  const building = manifest.buildings[normalized];
  drawMiniMap(building);
  renderPhotoEvidence(building);
  elements.loading.hidden = false;
  elements.message.textContent = `${building.stable_id} 불러오는 중`;
  clearMeasurement();
  try {
    const bounds = await Promise.all(viewers.map((viewer) => viewer.load(building)));
    const supportedViewer = viewers.find((viewer) => viewer.focus.supportCount > 0);
    if (supportedViewer) {
      for (const viewer of viewers) {
        if (viewer !== supportedViewer) viewer.shareRoofFocus(supportedViewer.focus.roofZ, supportedViewer.method.toUpperCase());
      }
    }
    const combined = bounds[0].clone().union(bounds[1]);
    const minZ = combined.min.z;
    const maxZ = combined.max.z;
    elements.clipHeight.min = String(Math.floor(minZ * 10) / 10);
    elements.clipHeight.max = String(Math.ceil(maxZ * 10) / 10);
    elements.clipHeight.value = String(maxZ);
    state.clipHeight = maxZ;
    updateClip();
    viewers[1].orbit.copyFrom(viewers[0].orbit);
    viewers[1].orbit.apply(viewers[1].camera);
    elements.buildingSelect.value = String(normalized);
    elements.buildingStatus.innerHTML = `LiDAR <strong>${building.lidar.technical_status}</strong> · MVS <strong>${building.mvs.technical_status}</strong>`;
    elements.message.textContent = `${normalized + 1}/${manifest.buildings.length} 로드 완료`;
    loadReviewForm(building.stable_id);
  } catch (error) {
    console.error(error);
    elements.message.textContent = `로드 오류: ${error.message || error}`;
  } finally {
    elements.loading.hidden = true;
  }
}

function applyDisplaySettings() {
  viewers.forEach((viewer) => viewer.applyDisplaySettings());
  elements.pointSizeValue.textContent = state.pointSize.toFixed(1);
  elements.meshOpacityValue.textContent = state.meshOpacity.toFixed(2);
}

function updateClip() {
  clippingPlane.constant = state.clipHeight;
  elements.clipHeightValue.textContent = state.clipEnabled ? `${state.clipHeight.toFixed(1)} m` : '-';
  applyDisplaySettings();
}

function addMeasurementPoint(point) {
  if (state.measurementPoints.length >= 2) state.measurementPoints = [];
  state.measurementPoints.push(point);
  viewers.forEach((viewer) => viewer.drawMeasurement(state.measurementPoints));
  if (state.measurementPoints.length === 1) {
    elements.measureResult.textContent = `P1 (${point.x.toFixed(2)}, ${point.y.toFixed(2)}, ${point.z.toFixed(2)})`;
  } else {
    const [a, b] = state.measurementPoints;
    elements.measureResult.textContent = `거리 ${a.distanceTo(b).toFixed(3)} m · ΔZ ${Math.abs(a.z - b.z).toFixed(3)} m`;
  }
}

function clearMeasurement() {
  state.measurementPoints = [];
  viewers.forEach((viewer) => viewer.clearMeasurement());
  elements.measureResult.textContent = '점 두 개를 선택하세요';
}

function installUi() {
  elements.prevBuilding.addEventListener('click', () => loadBuilding(state.buildingIndex - 1));
  elements.nextBuilding.addEventListener('click', () => loadBuilding(state.buildingIndex + 1));
  elements.buildingSelect.addEventListener('change', (event) => loadBuilding(Number(event.target.value)));
  elements.syncCamera.addEventListener('change', (event) => { state.sync = event.target.checked; });
  elements.colorMode.addEventListener('change', (event) => { state.colorMode = event.target.value; applyDisplaySettings(); });
  for (const id of ['showPoints', 'showRoofer', 'showFootprint', 'showCurtain', 'wireframe']) {
    elements[id].addEventListener('change', (event) => {
      state[id] = event.target.checked;
      applyDisplaySettings();
    });
  }
  elements.pointSize.addEventListener('input', (event) => { state.pointSize = Number(event.target.value); applyDisplaySettings(); });
  elements.meshOpacity.addEventListener('input', (event) => { state.meshOpacity = Number(event.target.value); applyDisplaySettings(); });
  elements.clipEnabled.addEventListener('change', (event) => { state.clipEnabled = event.target.checked; updateClip(); });
  elements.clipHeight.addEventListener('input', (event) => { state.clipHeight = Number(event.target.value); updateClip(); });
  document.querySelectorAll('[data-view]').forEach((button) => button.addEventListener('click', () => {
    viewers.forEach((viewer) => viewer.setView(button.dataset.view));
  }));
  elements.fitView.addEventListener('click', () => viewers.forEach((viewer) => viewer.fit('oblique')));
  elements.measureMode.addEventListener('click', () => {
    state.measureMode = !state.measureMode;
    elements.measureMode.setAttribute('aria-pressed', String(state.measureMode));
    elements.measureMode.textContent = state.measureMode ? '거리 측정 중' : '두 점 거리 측정';
  });
  elements.clearMeasure.addEventListener('click', clearMeasurement);
  document.querySelectorAll('[data-review-method]').forEach((button) => button.addEventListener('click', () => {
    const method = button.dataset.reviewMethod;
    const current = selectedReviewValue(method);
    setReviewButtons(method, current === button.dataset.value ? '' : button.dataset.value);
    saveReviewForm();
  }));
  elements.reviewNote.addEventListener('input', saveReviewForm);
  elements.exportCsv.addEventListener('click', exportReviewsCsv);
  elements.miniMapCanvas.addEventListener('click', () => {
    const building = manifest.buildings[state.buildingIndex];
    window.location.href = `./overview.html?building=${building.population_index}`;
  });
  new ResizeObserver(() => drawMiniMap(manifest.buildings[state.buildingIndex])).observe(elements.miniMapCanvas.parentElement);
  window.addEventListener('keydown', (event) => {
    if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement || event.target instanceof HTMLSelectElement) return;
    if (event.key === 'ArrowLeft') loadBuilding(state.buildingIndex - 1);
    if (event.key === 'ArrowRight') loadBuilding(state.buildingIndex + 1);
    if (event.key.toLowerCase() === 't') viewers.forEach((viewer) => viewer.setView('top'));
    if (event.key.toLowerCase() === 'o') viewers.forEach((viewer) => viewer.setView('oblique'));
    if (event.key.toLowerCase() === 's') viewers.forEach((viewer) => viewer.setView('side'));
  });
}

function loadReviews() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}'); }
  catch { return {}; }
}

function loadReviewForm(stableId) {
  const review = state.reviews[stableId] || {};
  setReviewButtons('lidar', review.lidar || '');
  setReviewButtons('mvs', review.mvs || '');
  elements.reviewNote.value = review.note || '';
}

function selectedReviewValue(method) {
  for (const value of ['O', 'X']) {
    if (elements[`${method}Review${value}`].getAttribute('aria-pressed') === 'true') return value;
  }
  return '';
}

function setReviewButtons(method, value) {
  for (const candidate of ['O', 'X']) {
    elements[`${method}Review${candidate}`].setAttribute('aria-pressed', String(value === candidate));
  }
  elements[`${method}ReviewCurrent`].textContent = value || '미평가';
}

function saveReviewForm() {
  const building = manifest.buildings[state.buildingIndex];
  const previous = state.reviews[building.stable_id] || {};
  state.reviews[building.stable_id] = {
    ...previous,
    lidar: selectedReviewValue('lidar'),
    mvs: selectedReviewValue('mvs'),
    note: elements.reviewNote.value,
  };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state.reviews));
}

function csvCell(value) {
  const text = String(value ?? '');
  return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function exportReviewsCsv() {
  saveReviewForm();
  const rows = [[
    'population_index', 'stable_id', 'lidar_technical_status', 'mvs_technical_status',
    'criterion_id', 'lidar_human_ox', 'mvs_human_ox', 'reviewer_note',
  ]];
  for (const building of manifest.buildings) {
    const review = state.reviews[building.stable_id] || {};
    rows.push([
      building.population_index, building.stable_id,
      building.lidar.technical_status, building.mvs.technical_status,
      manifest.review_criterion_id, review.lidar || '', review.mvs || '', review.note || '',
    ]);
  }
  const blob = new Blob([rows.map((row) => row.map(csvCell).join(',')).join('\n') + '\n'], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'JointBuildGS_WEB_REVIEW199_evaluation.csv';
  link.click();
  URL.revokeObjectURL(url);
}

function renderPhotoEvidence(building) {
  elements.photoTitle.textContent = `투영 사진 · ${String(building.population_index).padStart(3, '0')}/199 · ${building.stable_id}`;
  if (!building.projected_row) {
    elements.projectedRowImage.removeAttribute('src');
    elements.projectedRowImage.alt = `${building.stable_id} 투영 PNG 없음`;
    return;
  }
  elements.projectedRowImage.src = `./${building.projected_row.path}`;
  elements.projectedRowImage.alt = `${building.stable_id} TOP 및 RANDOM 1-3 동결 투영 PNG`;
}

function animate() {
  if (state.sync && viewers.length === 2) {
    const source = viewers[state.activeViewer];
    const target = viewers[1 - state.activeViewer];
    target.orbit.copyFrom(source.orbit);
    target.orbit.apply(target.camera);
  }
  viewers.forEach((viewer) => viewer.render());
  requestAnimationFrame(animate);
}

viewers.push(
  new ReviewViewer('lidarViewport', 'lidarStats', 'lidar', 0),
  new ReviewViewer('mvsViewport', 'mvsStats', 'mvs', 1),
);
manifest.buildings.forEach((building, index) => {
  const option = document.createElement('option');
  option.value = String(index);
  option.textContent = `${String(index + 1).padStart(3, '0')}/${manifest.buildings.length} · B${String(building.population_index).padStart(3, '0')} · ${building.stable_id}`;
  elements.buildingSelect.appendChild(option);
});
installUi();
const requestedBuilding = new URLSearchParams(window.location.search).get('building');
const requestedPopulationIndex = Number(String(requestedBuilding || '').replace(/^B/i, ''));
const initialBuildingIndex = Number.isFinite(requestedPopulationIndex)
  ? Math.max(0, manifest.buildings.findIndex((building) => building.population_index === requestedPopulationIndex))
  : 0;
await loadBuilding(initialBuildingIndex);
animate();
