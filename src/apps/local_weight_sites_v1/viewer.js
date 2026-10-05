import * as THREE from '/vendor/three.module.min.js';

const $ = id => document.getElementById(id);
const labels = {prior:'Existing ALS Prior', input:'현재 MVS 입력', mvs:'MVS–GeoGS', da3:'DA3–GeoGS', local_prior0:'기존 국소 prior0 결과'};
const colors = {prior:'#299c7d', input:'#20bed0', mvs:'#438fe0', da3:'#e3a14c', local_prior0:'#bd7dda'};
const groups = {preservation:'보존 검토', correction:'보정 검토', missing_observation:'관측 부족 검토', held:'대응·관측 보류', extraction:'추출 우선 진단', partial:'부분 개선·잔여 검토', recovered:'MVS 회복 대조', excluded:'비건물 제외 기록'};
const qa = window.__LOCAL_WEIGHT_QA__ = {ready:false, caseID:null, errors:[], panels:[], scientific_verdict:null};
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number = (value, digits=3) => value == null ? '관측 없음' : Number(value).toFixed(digits);
let catalog, selected, arrays, auditSummary, requestID = 0, controller;
let target = new THREE.Vector3(), yaw = -Math.PI / 2, pitch = 0, span = 10, scheduled = false;
let mapBounds, mapDrag, mapHit = [];
const panels = [];

function fail(error) {
  if (error.name === 'AbortError') return;
  qa.errors.push(String(error));
  $('error').textContent = '표시 오류: ' + error.message;
  $('error').hidden = false;
  $('load-state').textContent = '불러오기 실패 · 위 오류를 확인하세요';
  console.error(error);
}
async function json(url, signal) {
  const response = await fetch(url, {signal});
  if (!response.ok) throw Error(`${url}: HTTP ${response.status}`);
  return response.json();
}
async function binary(descriptor, Type, signal) {
  const response = await fetch(descriptor.url, {signal});
  if (!response.ok) throw Error(`${descriptor.url}: HTTP ${response.status}`);
  const bytes = await response.arrayBuffer();
  if (bytes.byteLength !== descriptor.bytes) throw Error(`기하 크기 불일치: ${descriptor.url}`);
  if (crypto.subtle) {
    const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), b => b.toString(16).padStart(2, '0')).join('');
    if (digest !== descriptor.sha256) throw Error(`기하 SHA256 불일치: ${descriptor.url}`);
  }
  return new Type(bytes);
}
function geometry(values, indices) {
  const result = new THREE.BufferGeometry();
  result.setAttribute('position', new THREE.BufferAttribute(values, 3));
  if (indices) result.setIndex(new THREE.BufferAttribute(indices, 1));
  return result;
}
function cohort() { return selected.cohorts[$('cohort').value] || selected.cohorts.all; }
function sectionAxis() { return $('section-axis').value === 'u' ? 1 : 0; }
function clippingPlanes() {
  const low = [...selected.display_box[0]], high = [...selected.display_box[1]], axis = sectionAxis();
  if ($('slice').value !== 'all') {
    const half = Number($('slice').value) / 2;
    low[axis] = selected.center[axis] - half;
    high[axis] = selected.center[axis] + half;
  }
  return [new THREE.Plane(new THREE.Vector3(1,0,0),-low[0]), new THREE.Plane(new THREE.Vector3(-1,0,0),high[0]),
    new THREE.Plane(new THREE.Vector3(0,1,0),-low[1]), new THREE.Plane(new THREE.Vector3(0,-1,0),high[1]),
    new THREE.Plane(new THREE.Vector3(0,0,1),-low[2]), new THREE.Plane(new THREE.Vector3(0,0,-1),high[2])];
}
function subset(values, indices) {
  const result = new Float32Array(indices.length * 3);
  indices.forEach((index, row) => result.set(values.subarray(index * 3, index * 3 + 3), row * 3));
  return result;
}
function pointObject(values, color, size, opacity=1) {
  return new THREE.Points(geometry(values), new THREE.PointsMaterial({color, size, sizeAttenuation:false, transparent:opacity<1, opacity}));
}
function makePanels() {
  for (let index=0; index<4; index++) {
    const card = document.createElement('article'); card.className='panel';
    card.innerHTML='<div class="panel-title"></div><div class="view"></div><div class="panel-note"></div>';
    $('panels').append(card);
    const renderer = new THREE.WebGLRenderer({antialias:true, preserveDrawingBuffer:true});
    renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5)); renderer.localClippingEnabled=true;
    const host = card.querySelector('.view'); host.append(renderer.domElement);
    const camera = new THREE.OrthographicCamera(-10,10,5,-5,.01,2000); camera.up.set(0,0,1);
    panels.push({card, host, renderer, camera, scene:null, role:null, objects:[]});
    renderer.domElement.addEventListener('webglcontextlost', event => {event.preventDefault(); fail(Error('3D 그래픽 컨텍스트가 중단되었습니다. 페이지를 새로 열어 주세요.'));});
    interact(renderer.domElement);
  }
}
function buildScenes() {
  const roles = ['prior', 'input', 'mvs', $('fourth').value];
  panels.forEach((panel, index) => {
    if (panel.scene) panel.scene.traverse(object => {object.geometry?.dispose(); if (object.material) object.material.dispose();});
    panel.role=roles[index]; panel.card.dataset.role=panel.role;
    panel.card.querySelector('.panel-title').textContent = labels[panel.role] + (['mvs','da3'].includes(panel.role) ? ' · prior 0.005' : '');
    const scene = panel.scene = new THREE.Scene(); scene.background = new THREE.Color('#142235');
    scene.add(new THREE.HemisphereLight(0xffffff, 0x667c92, 2.4));
    const light = new THREE.DirectionalLight(0xffffff, 2.2); light.position.set(25,-30,40); scene.add(light);
    panel.surface=null;
    if (panel.role !== 'input') {
      const model = arrays.models[panel.role];
      panel.surface = new THREE.Mesh(geometry(model.xyz, model.indices), new THREE.MeshStandardMaterial({color:colors[panel.role], side:THREE.DoubleSide, flatShading:true, roughness:1}));
      scene.add(panel.surface);
    }
    panel.uas = pointObject(arrays.uas, '#a2afbd', 1.8, .55); scene.add(panel.uas);
    panel.mvs = pointObject(arrays.mvs_input, colors.input, 3); scene.add(panel.mvs);
    const exact = subset(arrays.scored, cohort().indices);
    panel.scored = pointObject(exact, '#f4c74f', 4.4); panel.scored.renderOrder=5; scene.add(panel.scored);
    const lineValues=[];
    if (panel.role !== 'input') {
      const nearest = subset(arrays.models[panel.role].closest, cohort().indices);
      for (let k=0; k<exact.length; k+=3) lineValues.push(...exact.subarray(k,k+3), ...nearest.subarray(k,k+3));
    }
    panel.lines = new THREE.LineSegments(geometry(new Float32Array(lineValues)), new THREE.LineBasicMaterial({color:'#f4c74f', transparent:true, opacity:.65}));
    panel.lines.renderOrder=4; scene.add(panel.lines);
    const size = selected.case_box[1].map((value, axis) => Math.max(.02, value-selected.case_box[0][axis]));
    const box = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(...size)), new THREE.LineBasicMaterial({color:'#ed6670', depthTest:false}));
    box.position.fromArray(selected.case_box[0].map((v,i) => (v+selected.case_box[1][i])/2)); box.renderOrder=6; scene.add(box);
    const grid=[]; const [low, high] = selected.display_box; const y=high[1]+.03;
    for (let x=Math.ceil(low[0]);x<=high[0];x++) grid.push(x,y,low[2],x,y,high[2]);
    for (let z=Math.ceil(low[2]);z<=high[2];z++) grid.push(low[0],y,z,high[0],y,z);
    scene.add(new THREE.LineSegments(geometry(new Float32Array(grid)), new THREE.LineBasicMaterial({color:'#273b50'})));
    panel.objects=[panel.surface,panel.uas,panel.mvs,panel.scored,panel.lines].filter(Boolean);
  });
  panelMetrics(); highlightPhotoPoint(); draw();
}
function panelMetrics() {
  for (const panel of panels) {
    const text = panel.role === 'input' ? `실제 MVS 입력 표본 ${arrays.mvs_input.length/3}점 · 메시 보간 없음` : `${selected.metric_basis} ${cohort().n}점 → 표면 중앙값 ${number(cohort().metrics[panel.role].median_m)} m`;
    panel.card.querySelector('.panel-note').textContent=text;
  }
}
function draw() {
  if (scheduled || !arrays) return;
  scheduled=true;
  requestAnimationFrame(() => {
    try {
      const clipping=clippingPlanes();
      for (const panel of panels) {
        const w=panel.host.clientWidth,h=panel.host.clientHeight,aspect=w/h;
        panel.renderer.setSize(w,h,false);
        Object.assign(panel.camera,{left:-span*aspect/2,right:span*aspect/2,top:span/2,bottom:-span/2});
        panel.camera.updateProjectionMatrix();
        panel.camera.position.copy(target).add(new THREE.Vector3(Math.cos(pitch)*Math.cos(yaw),Math.cos(pitch)*Math.sin(yaw),Math.sin(pitch)).multiplyScalar(200));
        panel.camera.lookAt(target);
        for (const object of panel.objects) object.material.clippingPlanes=clipping;
        if (panel.surface) panel.surface.material.wireframe=$('wireframe').checked;
        panel.uas.visible=$('show-uas').checked;
        panel.mvs.visible=panel.role==='input'||$('show-mvs').checked;
        panel.scored.visible=$('show-scored').checked;
        panel.scored.material.depthTest=!$('xray').checked;
        panel.lines.visible=$('connectors').checked;
        panel.lines.material.depthTest=!$('xray').checked;
        panel.renderer.render(panel.scene,panel.camera);
      }
      qa.panels=panels.map(panel=>({role:panel.role,camera:panel.camera.position.toArray(),triangles:panel.surface?panel.surface.geometry.index.count/3:0,scored:cohort().n,meters_per_pixel:span/panel.host.clientHeight,drawn:true}));
      qa.cohort=$('cohort').value; qa.slice=$('slice').value; qa.axis=$('section-axis').value;
      qa.ready=true; $('load-state').textContent='동일 위치 · 카메라 동기화';
    } catch(error) {fail(error);} finally {scheduled=false;}
  });
}
function preset(kind) {
  if (kind==='side') {yaw=sectionAxis()===1?-Math.PI/2:Math.PI;pitch=0;}
  if (kind==='oblique') {yaw=-1.05;pitch=.55;}
  if (kind==='top') {yaw=-Math.PI/2;pitch=Math.PI/2-.001;}
  ['side','oblique','top'].forEach(id=>$(id).setAttribute('aria-pressed',String(id===kind)));
  draw();
}
function reset() {
  target.fromArray(selected.center); span=Math.max(9,selected.case_box[1][2]-selected.case_box[0][2]+6);
  const spatialCase=selected.metric_basis==='MVS';
  if(spatialCase)span=Math.max(span,12);
  $('slice').value=spatialCase?'all':'0.5'; preset(spatialCase?'oblique':'side'); sectionPlot();
}
function interact(canvas) {
  let drag;
  canvas.addEventListener('pointerdown',event=>{drag=[event.clientX,event.clientY];canvas.setPointerCapture(event.pointerId);});
  ['pointerup','pointercancel'].forEach(name=>canvas.addEventListener(name,()=>drag=null));
  canvas.addEventListener('pointermove',event=>{
    if (!drag) return;
    const dx=event.clientX-drag[0],dy=event.clientY-drag[1];drag=[event.clientX,event.clientY];
    if(event.shiftKey){const right=new THREE.Vector3(-Math.sin(yaw),Math.cos(yaw),0),up=new THREE.Vector3(-Math.sin(pitch)*Math.cos(yaw),-Math.sin(pitch)*Math.sin(yaw),Math.cos(pitch));target.addScaledVector(right,-dx*span/canvas.clientHeight).addScaledVector(up,dy*span/canvas.clientHeight);}
    else {yaw-=dx*.006;pitch=Math.max(-1.5,Math.min(1.569,pitch+dy*.006));}
    draw();
  });
  canvas.addEventListener('wheel',event=>{event.preventDefault();span=Math.max(.5,Math.min(120,span*Math.exp(event.deltaY*.001)));draw();},{passive:false});
}

function fillNumbers() {
  const c=cohort(), max=Math.max(...['prior','mvs','da3'].map(role=>c.metrics[role].median_m),.01);
  const definition=selected.metric_basis==='UAS'?'UAS 참조 표본 → 각 표면 · 평가용 거리':'MVS 입력 표본 → 각 표면 · 입력 대비 잔차 (독립 정확도 아님)';
  $('metric-definition').textContent=`${definition} · 같은 ${c.n}점 · 단위 m`;
  $('metric-cards').innerHTML=['prior','mvs','da3'].map(role=>`<div class="metric-card"><span class="label">${labels[role]}</span><strong style="color:${colors[role]}">${number(c.metrics[role].median_m)}</strong><span class="unit">m</span><div class="metric-bar"><i style="width:${c.metrics[role].median_m/max*100}%;background:${colors[role]}"></i></div><span class="small">같은 ${c.n}점의 거리 중앙값</span></div>`).join('');
  $('cohort-note').textContent=selected.id==='C10'?`선택한 ${c.n}점 중 ${c.prior_near_mvs_far_count}점: Prior≤0.25m이고 MVS–GeoGS>1m. 상단 대응은 가시성 정답이 아니며, 보존 문제 검토를 위한 보조 검사입니다.`:selected.metric_basis==='UAS'?`동일 UAS ${c.n}점으로 세 표면을 비교합니다. 참조 표면 대응과 원인 판정은 위의 검토 상태를 함께 확인하세요.`:`기준은 동일 MVS 입력 ${c.n}점입니다. 가까운 UAS 표본의 별도 검사는 아래에 표시합니다.`;
  $('distribution-table').innerHTML=['prior','mvs','da3','local_prior0'].map(role=>`<tr><td>${labels[role]}</td><td>${c.n}</td><td>${number(c.metrics[role].median_m)}</td><td>${number(c.metrics[role].p90_m)}</td><td>${number(c.metrics[role].within_05m_percent,1)}%</td></tr>`).join('');
  const xMax=Math.max(...Object.values(c.metrics).map(x=>x.sorted_m.at(-1)),.1)*1.05;
  let markup='<rect x="50" y="15" width="680" height="145" fill="#f8fafc"/>';
  for(let i=0;i<=4;i++){const y=160-i*145/4;markup+=`<path d="M50 ${y}H730" stroke="#dce4ec"/><text x="42" y="${y+4}" text-anchor="end" font-size="11" fill="#5b6e80">${i*25}%</text>`;}
  for(let i=0;i<=4;i++)markup+=`<text x="${50+i*680/4}" y="180" text-anchor="middle" font-size="11" fill="#5b6e80">${number(xMax*i/4,2)}</text>`;
  for(const role of ['prior','mvs','da3','local_prior0']){const values=c.metrics[role].sorted_m;let path='M50 160';values.forEach((value,i)=>{path+=`H${(50+value/xMax*680).toFixed(2)}V${(160-(i+1)/values.length*145).toFixed(2)}`;});markup+=`<path d="${path}" fill="none" stroke="${colors[role]}" stroke-width="1.8"/>`;}
  markup+='<text x="390" y="201" text-anchor="middle" font-size="11" fill="#5b6e80">표본 → 표면 거리 (m), 누적 표본 비율</text>';
  $('distribution').innerHTML=markup;
}
function fillObservations() {
  const facts=$('support-facts'), table=$('observation-table');
  if(selected.metric_basis==='UAS') {
    const layer=selected.source_layer_audit;
    facts.innerHTML=`<div class="fact">원래 UAS 표본<strong>${selected.cohorts.all.n}점</strong></div><div class="fact">상단 관측 표본과 0.5m 이내<strong>${number(layer.fraction_within_05m_of_upper_sample*100,1)}%</strong></div><div class="fact">원영상 확인<strong>${selected.photo_count}시점</strong></div>`;
    $('observation-definition').textContent='각 입력 depth − 해당 UAS 점의 카메라 Z. 음수는 카메라 앞쪽입니다. 표본 80% 이상에 유효 depth가 있는 영상의 중앙값을 다시 요약했습니다. 가림이 섞일 수 있어 입력 오류로 단정하지 않습니다.';
    table.querySelector('thead').innerHTML='<tr><th>입력 depth</th><th>유효 영상 / 조사 영상</th><th>차이 중앙값 (m)</th></tr>';
    table.querySelector('tbody').innerHTML=['prior','mvs','da3'].map(role=>{const d=selected.depth_summary[role];return `<tr><td>${role==='prior'?'Prior':role.toUpperCase()} depth</td><td>${d.valid_views} / ${d.projected_views}</td><td>${number(d.median_of_view_medians_m)}</td></tr>`;}).join('');
    $('reference-secondary').hidden=true;
  } else {
    const support=selected.support,ref=selected.reference;
    facts.innerHTML=`<div class="fact">점별 지지 시점 중앙값<strong>${number(support.views.median,0)}개</strong></div><div class="fact">카메라 범위 중앙값<strong>${number(support.camera_span_m.median,1)}m</strong></div><div class="fact">MVS−Prior 카메라 Z<strong>${number(support.gap_camera_z.median)}m</strong></div><div class="fact">검사한 분리 시점<strong>${selected.photo_count}개</strong></div>`;
    $('observation-definition').textContent='현재 MVS target과 저장된 GeoGS 렌더 깊이의 절대 차이입니다. 같은 조사 시점·유효 투영점에서 계산한 camera-Z 잔차이며 위의 점→메시 거리와 다른 지표입니다. 전체 학습 영상의 loss 기여량은 아닙니다.';
    table.querySelector('thead').innerHTML='<tr><th>실제 원영상</th><th>지지점 / target 일치점</th><th>MVS 렌더 잔차 (m)</th><th>DA3 렌더 잔차 (m)</th></tr>';
    table.querySelector('tbody').innerHTML=selected.view_observations.map(view=>`<tr><td>${esc(view.name)}</td><td>${view.supported_points} / ${view.target_agreeing_points}</td><td>${number(view.metrics.mvs.abs_render_minus_mvs.median)}</td><td>${number(view.metrics.da3.abs_render_minus_mvs.median)}</td></tr>`).join('')||'<tr><td colspan="4">군집 절반 이상을 함께 보는 분리 시점을 확보하지 못했습니다.</td></tr>';
    $('reference-secondary').hidden=false;
    $('reference-secondary').innerHTML=`<h3>주변 UAS로 따로 확인한 범위</h3><p class="small">MVS 표본 중 UAS 최근접점이 0.5m 이내인 비율 ${number(ref.fraction_mvs_within_05m*100,1)}% · 대응한 고유 UAS ${ref.nearby_unique_uas}점. 근접성이 같은 표면임을 확정하지는 않습니다.</p>`;
    if(ref.nearby_unique_uas) $('reference-secondary').innerHTML+=`<div class="table-scroll"><table><thead><tr><th>같은 주변 UAS → 표면</th><th>Prior</th><th>MVS–GeoGS</th><th>DA3–GeoGS</th></tr></thead><tbody><tr><td>거리 중앙값 (m), n=${ref.nearby_unique_uas}</td>${['prior','mvs','da3'].map(role=>`<td>${number(ref.distances_on_nearby_uas[role].median)}</td>`).join('')}</tr></tbody></table></div>`;
  }
  $('raw-observations').href=selected.observations;
  $('raw-geometry').href='assets/'+selected.id+'.json';
  $('related').innerHTML=selected.related_case?`같은 지붕의 인접 패치: <a href="?case=${esc(selected.related_case)}" data-case="${esc(selected.related_case)}">${esc(selected.related_case)}</a>. 평가점·거리 정의가 다르므로 같은 표본이나 독립 건물 2건으로 합산하지 않습니다.`:'';
}
function fillReport() {
  document.title=selected.title+' · 국소 가중치 후보';
  $('case-title').textContent=selected.id+' · '+selected.title;
  $('status-badge').textContent=(selected.priority?'우선 가설 검토 · ':'')+groups[selected.group];
  $('status-badge').className='badge'+(selected.priority?' priority':'')+(selected.group==='excluded'?' excluded':'');
  $('case-baseline').textContent=selected.baseline_note || selected.baseline.replace('MVS_AND_DA3','MVS / DA3')+' 관련';
  $('reason').textContent=selected.reason;$('hypothesis').textContent=selected.hypothesis;$('limitation').textContent=selected.limitation;
  const [low,high]=selected.case_box;
  $('case-location').textContent=`${selected.region} / ${selected.zone} · 객체축 u ${number(low[0],2)}–${number(high[0],2)}, v ${number(-high[1],2)}–${number(-low[1],2)}, local z ${number(low[2],2)}–${number(high[2],2)} m`;
  $('cohort-control').hidden=selected.id!=='C10';$('cohort').value='all';
  setupPhotos();
  $('geometry-note').textContent='기존 전역 prior 0.005와 native 보호 규칙을 사용한 결과입니다. 네 번째 화면의 국소 prior0는 이전 보정 마스크의 결과이며 선택 위치에 맞춘 새 개선 실험이 아닙니다.';
  fillNumbers();fillObservations();fillList();fillMvsAudit();
}
function fillMvsAudit(){
  const a=selected.mvs_audit;$('mvs-audit-card').hidden=!a;if(!a)return;
  $('mvs-audit-status').textContent=a.label;$('mvs-audit-status').dataset.status=a.status;
  $('mvs-audit-reason').textContent=a.reason;
  const m=a.metrics.mvs,p=a.paired_prior_comparison;
  $('mvs-audit-facts').innerHTML=`<div class="fact">${a.metric_basis==='UAS'?'UAS 참조':'MVS 입력'} 표본<strong>${m.n}점</strong></div><div class="fact">MVS 거리 중앙값<strong>${number(m.median_m)}m</strong></div><div class="fact">MVS P90<strong>${number(m.p90_m)}m</strong></div><div class="fact">0.25m 이내<strong>${m.within_counts['0.25']} / ${m.n}점</strong></div>`;
  $('mvs-audit-paired').textContent=`동일 표본에서 MVS 결과가 prior보다 0.1m 넘게 먼 점 ${p.farther_over_01m_count}/${m.n}, 0.1m 넘게 가까운 점 ${p.closer_over_01m_count}/${m.n}. 점별 거리 차이 중앙값 ${number(p.median_m)}m (양수: prior보다 멂).`;
  if(auditSummary)$('mvs-audit-table').innerHTML=auditSummary.rows.map(r=>`<tr><td><a href="?case=${r.id}" data-case="${r.id}">${r.id} · ${r.region} ${r.zone}</a></td><td>${r.metric_basis==='UAS'?'UAS 참조':'MVS 입력'}</td><td>${number(r.metrics.mvs.median_m)}</td><td>${number(r.metrics.mvs.p90_m)}</td><td>${esc(r.label)}</td></tr>`).join('');
  qa.mvsAudit={status:a.status,n:m.n,median:m.median_m,p90:m.p90_m,farther:p.farther_over_01m_count};
}
function sectionPlot() {
  if(!arrays)return;
  const axis=$('section-axis').value, horizontal=axis==='u'?0:1, fixed=sectionAxis();
  const centerX=axis==='u'?selected.center[0]:-selected.center[1], centerZ=selected.center[2];
  const extentX=Math.max(10,(selected.case_box[1][horizontal]-selected.case_box[0][horizontal])/2+4);
  const extentZ=Math.max(5,(selected.case_box[1][2]-selected.case_box[0][2])/2+2);
  const scale=Math.min(850/(extentX*2),280/(extentZ*2)),left=480-extentX*scale,top=170-extentZ*scale,width=extentX*2*scale,height=extentZ*2*scale;
  const x=value=>480+(value-centerX)*scale,z=value=>170-(value-centerZ)*scale;
  const h=point=>axis==='u'?point[0]:-point[1];
  let markup=`<defs><clipPath id="sectionClip"><rect x="${left}" y="${top}" width="${width}" height="${height}"/></clipPath></defs><rect x="${left}" y="${top}" width="${width}" height="${height}" fill="#fafcfe" stroke="#cad6e0"/>`;
  const step=extentX>20?5:2;
  for(let value=Math.ceil((centerX-extentX)/step)*step;value<=centerX+extentX;value+=step)markup+=`<path d="M${x(value)} ${top}V${top+height}" stroke="#e0e7ee"/><text x="${x(value)}" y="${top+height+17}" text-anchor="middle" font-size="11" fill="#566b7e">${value}</text>`;
  for(let value=Math.ceil(centerZ-extentZ);value<=centerZ+extentZ;value+=2)markup+=`<path d="M${left} ${z(value)}H${left+width}" stroke="#e0e7ee"/><text x="${left-8}" y="${z(value)+4}" text-anchor="end" font-size="11" fill="#566b7e">${value}</text>`;
  markup+='<g clip-path="url(#sectionClip)">';
  for(const role of ['prior','mvs','da3','local_prior0']){
    const values=arrays.models[role].sections[axis];let path='';
    for(let i=0;i<values.length;i+=6)path+=`M${x(h(values.subarray(i,i+3))).toFixed(2)} ${z(values[i+2]).toFixed(2)}L${x(h(values.subarray(i+3,i+6))).toFixed(2)} ${z(values[i+5]).toFixed(2)}`;
    markup+=`<path d="${path}" fill="none" stroke="${colors[role]}" stroke-width="1.5"/>`;
  }
  const half=$('slice').value==='all'?Math.max(...selected.display_box[1].map((v,i)=>v-selected.display_box[0][i])):Number($('slice').value)/2;
  function points(values,color,radius,opacity){let result='';for(let i=0;i<values.length;i+=3){if(Math.abs(values[i+fixed]-selected.center[fixed])>half)continue;result+=`<circle cx="${x(h(values.subarray(i,i+3))).toFixed(2)}" cy="${z(values[i+2]).toFixed(2)}" r="${radius}" fill="${color}" opacity="${opacity}"/>`;}return result;}
  markup+=points(arrays.uas,'#5f6c79',1.2,.45)+points(arrays.mvs_input,colors.input,2,.75)+points(subset(arrays.scored,cohort().indices),'#d99215',2.5,1);
  const [lo,hi]=selected.case_box;const minX=axis==='u'?lo[0]:-hi[1],maxX=axis==='u'?hi[0]:-lo[1];
  markup+=`<rect x="${x(minX)}" y="${z(hi[2])}" width="${(maxX-minX)*scale}" height="${(hi[2]-lo[2])*scale}" fill="none" stroke="#ed6670" stroke-width="1.8"/></g>`;
  markup+=`<text x="480" y="350" text-anchor="middle" font-size="12" fill="#566b7e">${axis} (m)</text><text x="${Math.max(15,left-55)}" y="170" text-anchor="middle" font-size="12" fill="#566b7e" transform="rotate(-90 ${Math.max(15,left-55)} 170)">local z (m)</text>`;
  $('section-plot').innerHTML=markup;
  $('section-label').textContent=`${axis==='u'?'v':'u'} = ${number(axis==='u'?-selected.center[1]:selected.center[0],2)}m · 높이 과장 없음`;
  $('section-legend').innerHTML=['prior','mvs','da3','local_prior0'].map(role=>`<span><i style="background:${colors[role]}"></i>${labels[role]}</span>`).join('')+'<span><i style="background:#d99215"></i>평가점</span><span><i style="background:#20bed0"></i>MVS 입력</span>';
}

function matches(item) {
  const region=$('filter-region').value,role=$('filter-role').value;
  if(region!=='all'&&item.region!==region)return false;
  if(role==='priority')return item.priority;
  if(role==='mvs')return item.baseline.includes('MVS');
  if(role==='da3')return item.baseline.includes('DA3');
  if(role==='held'||role==='excluded')return item.group===role;
  return true;
}
function fillList() {
  if(!catalog)return;
  const visible=catalog.cases.filter(matches);
  $('case-count').textContent=`${visible.length} / ${catalog.case_count} 기록`;
  $('case-list').innerHTML=visible.map(item=>`<button type="button" class="case-item ${item.id===selected?.id?'selected':''}" data-case="${item.id}" aria-current="${item.id===selected?.id?'true':'false'}"><strong>${item.id}</strong><span><span class="name">${esc(item.title)}</span><span class="meta">${item.priority?'우선 · ':''}${groups[item.group]} · ${item.baseline.replace('MVS_AND_DA3','MVS/DA3')}</span></span></button>`).join('')||'<p class="empty">이 조건의 사례가 없습니다.</p>';
  drawMap();
}
function fitMap(region) {
  const regions=region?catalog.map_regions.filter(item=>item.id===region):catalog.map_regions;
  mapBounds=[[Math.min(...regions.map(r=>r.bounds[0][0]))-8,Math.min(...regions.map(r=>r.bounds[0][1]))-8],[Math.max(...regions.map(r=>r.bounds[1][0]))+8,Math.max(...regions.map(r=>r.bounds[1][1]))+8]];
  $('map-label').textContent=(region||'R1–R5')+' · MVS 관측 평면도';drawMap();
}
function mapProjection() {
  const canvas=$('map'),w=canvas.clientWidth,h=canvas.clientHeight;
  const scale=Math.min((w-24)/(mapBounds[1][0]-mapBounds[0][0]),(h-28)/(mapBounds[1][1]-mapBounds[0][1]));
  const center=mapBounds[0].map((v,i)=>(v+mapBounds[1][i])/2);
  return {w,h,scale,xy:uv=>[w/2+(uv[0]-center[0])*scale,h/2+(uv[1]-center[1])*scale]};
}
function drawMap() {
  if(!catalog||!mapBounds)return;
  const canvas=$('map'),ctx=canvas.getContext('2d'),{w,h,scale,xy}=mapProjection(),dpr=Math.min(devicePixelRatio,2);
  canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);ctx.scale(dpr,dpr);ctx.fillStyle='#edf2f5';ctx.fillRect(0,0,w,h);
  ctx.fillStyle='#9eacb8';for(const region of catalog.map_regions)for(const point of region.points){const p=xy(point);if(p[0]>=0&&p[0]<=w&&p[1]>=0&&p[1]<=h)ctx.fillRect(p[0],p[1],1,1);}
  mapHit=[];
  const items=catalog.cases.filter(matches);items.sort((a,b)=>Number(a.id===selected?.id)-Number(b.id===selected?.id));
  for(const item of items){const p=xy(item.center_uv),active=item.id===selected?.id;ctx.beginPath();ctx.arc(...p,active?7:4,0,Math.PI*2);ctx.fillStyle=active?'#d44543':item.priority?'#bb7f29':'#416e93';ctx.fill();ctx.strokeStyle='white';ctx.lineWidth=active?2:1;ctx.stroke();mapHit.push({id:item.id,x:p[0],y:p[1]});if(active){ctx.font='bold 11px system-ui';const tw=ctx.measureText(item.id+' '+item.region+' '+item.zone).width;const tx=Math.min(w-tw-6,Math.max(5,p[0]+10)),ty=Math.max(15,p[1]-10);ctx.fillStyle='#fffffff0';ctx.fillRect(tx-3,ty-12,tw+6,17);ctx.fillStyle='#9b302e';ctx.fillText(item.id+' '+item.region+' '+item.zone,tx,ty);}}
  const bar=scale*20;ctx.strokeStyle='#415a71';ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(10,h-12);ctx.lineTo(10+Math.min(bar,w-30),h-12);ctx.stroke();ctx.fillStyle='#415a71';ctx.font='10px system-ui';ctx.fillText(`${Math.min(20,(w-30)/scale).toFixed(0)}m`,12,h-18);ctx.fillText('u →  v ↓',w-65,h-8);
  qa.map={markers:mapHit,bounds:mapBounds,scale};
}
const map=$('map');
map.addEventListener('pointerdown',event=>{mapDrag={x:event.clientX,y:event.clientY,startX:event.clientX,startY:event.clientY,moved:false};map.setPointerCapture(event.pointerId);});
map.addEventListener('pointermove',event=>{if(!mapDrag||!mapBounds)return;const dx=event.clientX-mapDrag.x,dy=event.clientY-mapDrag.y,scale=mapProjection().scale;mapDrag.moved ||= Math.hypot(event.clientX-mapDrag.startX,event.clientY-mapDrag.startY)>4;mapDrag.x=event.clientX;mapDrag.y=event.clientY;if(mapDrag.moved){mapBounds=mapBounds.map(p=>[p[0]-dx/scale,p[1]-dy/scale]);drawMap();}});
map.addEventListener('pointerup',event=>{if(mapDrag&&!mapDrag.moved){const rect=map.getBoundingClientRect(),x=event.clientX-rect.left,y=event.clientY-rect.top;const nearby=mapHit.map(p=>({...p,d:Math.hypot(p.x-x,p.y-y)})).sort((a,b)=>a.d-b.d);if(nearby[0]?.d<16)selectCase(nearby[0].id);}mapDrag=null;});
map.addEventListener('pointercancel',()=>mapDrag=null);
map.addEventListener('wheel',event=>{if(!mapBounds)return;event.preventDefault();const factor=Math.exp(Math.max(-.5,Math.min(.5,event.deltaY*.001)));const center=mapBounds[0].map((v,i)=>(v+mapBounds[1][i])/2);mapBounds=mapBounds.map(p=>p.map((v,i)=>center[i]+(v-center[i])*factor));drawMap();},{passive:false});

async function selectCase(id, push=true) {
  const entry=catalog.cases.find(item=>item.id===id);
  if(!entry){fail(Error('등록되지 않은 사례: '+id));return;}
  const serial=++requestID; controller?.abort();controller=new AbortController();const signal=controller.signal;
  qa.ready=false;$('load-state').textContent=id+' 기하를 불러오는 중…';$('error').hidden=true;
  try {
    const detail=await json(entry.file,signal);
    const loaded={models:{}};
    await Promise.all(['uas','mvs_input','scored'].map(async name=>{loaded[name]=await binary(detail[name],Float32Array,signal);}));
    await Promise.all(Object.entries(detail.models).map(async ([role,model])=>{
      const [xyz,indices,closest,u,v]=await Promise.all([binary(model.xyz,Float32Array,signal),binary(model.indices,Uint32Array,signal),binary(model.closest,Float32Array,signal),binary(model.sections.u,Float32Array,signal),binary(model.sections.v,Float32Array,signal)]);
      loaded.models[role]={xyz,indices,closest,sections:{u,v}};
    }));
    if(serial!==requestID)return;
    const previousRegion=selected?.region;selected=detail;arrays=loaded;qa.caseID=id;
    if(push)history.pushState({id},'', '?case='+encodeURIComponent(id));
    fillReport();buildScenes();reset();sectionPlot();
    if(!mapBounds||previousRegion!==selected.region)fitMap(selected.region);else drawMap();
  }catch(error){if(serial===requestID)fail(error);}
}
document.addEventListener('click',event=>{const link=event.target.closest('[data-case]');if(link){event.preventDefault();selectCase(link.dataset.case);}});
$('filter-region').onchange=()=>{fillList();fitMap($('filter-region').value==='all'?null:$('filter-region').value);};
$('filter-role').onchange=fillList;
$('map-all').onclick=()=>fitMap(null);$('map-region').onclick=()=>fitMap(selected.region);
for(const kind of ['side','oblique','top'])$(kind).onclick=()=>preset(kind);
$('reset').onclick=reset;
$('cohort').onchange=()=>{fillNumbers();syncPhotoCohort();buildScenes();sectionPlot();};
$('slice').onchange=()=>{draw();sectionPlot();};
$('section-axis').onchange=()=>{preset('side');sectionPlot();};
$('fourth').onchange=buildScenes;
for(const name of ['show-uas','show-mvs','show-scored','xray','connectors','wireframe'])$(name).onchange=draw;
function setupPhotos() {
  const views=selected.photo_views||[], available=views.length>0;
  for(const id of ['photos','photo-controls','photo-open','photo-original'])$(id).hidden=!available;
  $('photo-empty').hidden=available;
  $('photo-empty').textContent='W145는 군집 절반 이상을 함께 보는 시점이 없어 원영상 검토 패널을 확보하지 못했습니다. 개별 점의 관측 부재를 뜻하지는 않습니다.';
  $('photo-view').innerHTML=views.map((v,i)=>`<option value="${i}">${i+1} / ${views.length} · ${esc(v.name)}</option>`).join('');
  $('photo-point').value='all';$('photo-points').checked=true;
  $('photo-labels').checked=selected.cohorts.all.n<=20;
  $('photo-note').textContent=`${selected.metric_basis==='UAS'?'UAS 참조 평가점':'MVS 입력 평가점'}을 실제 학습 영상의 카메라에 투영했습니다. 같은 번호는 시점·확대·3D에서 같은 3D 점입니다. 투영 위치가 보인다는 것만으로 해당 표면의 가시성이 확인되지는 않습니다.`;
  syncPhotoCohort();
}
function syncPhotoCohort() {
  const old=$('photo-point').value, ids=cohort().indices;
  $('photo-point').innerHTML='<option value="all">전체 점</option>'+ids.map(i=>`<option value="${i+1}">점 ${i+1}</option>`).join('');
  $('photo-point').value=ids.includes(Number(old)-1)?old:'all';
  renderPhotos();
}
function highlightPhotoPoint() {
  if(!arrays)return;
  const id=Number($('photo-point').value);
  for(const panel of panels){
    if(!panel.scene)continue;
    if(panel.photoPoint){panel.scene.remove(panel.photoPoint);panel.photoPoint.geometry.dispose();panel.photoPoint.material.dispose();panel.photoPoint=null;}
    if(id>0&&cohort().indices.includes(id-1)){
      panel.photoPoint=pointObject(arrays.scored.slice((id-1)*3,id*3),'#ff3daa',11);
      panel.photoPoint.material.depthTest=false;panel.photoPoint.renderOrder=10;panel.scene.add(panel.photoPoint);
    }
  }
  draw();
}
function photoSvg(view, rect, context=false) {
  const [x,y,right,bottom]=rect,w=right-x,h=bottom-y,active=Number($('photo-point').value);
  const keep=new Set(cohort().indices.map(i=>i+1));
  const points=view.points.filter(p=>p.in_frame&&keep.has(p.id));
  let markup=`<image href="${esc(view.image)}" x="0" y="0" width="${view.width}" height="${view.height}"/>`;
  if($('photo-points').checked){
    if(context){const [a,b,c,d]=view.crop;markup+=`<rect x="${a}" y="${b}" width="${c-a}" height="${d-b}" fill="none" stroke="#ff426b" stroke-width="2.5" vector-effect="non-scaling-stroke"/>`;}
    for(const p of points){
      const chosen=p.id===active,color=chosen?'#ff3daa':selected.metric_basis==='MVS'&&!p.mvs_supported?'#ef7b37':'#ffdc39';
      const radius=w*(chosen?.013:.007);
      markup+=`<g class="photo-dot" data-point="${p.id}" role="button" tabindex="0" aria-label="평가점 ${p.id}"><title>점 ${p.id} · ${selected.metric_basis==='MVS'?(p.mvs_supported?'MVS 지지 있음':'이 시점의 지지 미확인'):'가시성 미확정'}</title><circle cx="${p.xy[0]}" cy="${p.xy[1]}" r="${radius}" fill="${color}" fill-opacity="${active&&!chosen?.4:.85}" stroke="#172331" stroke-width="1.2" vector-effect="non-scaling-stroke"/>`;
      if(chosen||(!context&&$('photo-labels').checked))markup+=`<text class="point-number" x="${p.xy[0]+radius*1.5}" y="${p.xy[1]-radius}" font-size="${w*.028}">${p.id}</text>`;
      markup+='</g>';
    }
    // Draw the selected point last so dense cohorts cannot cover it.
    const p=points.find(p=>p.id===active);
    if(p)markup+=`<circle cx="${p.xy[0]}" cy="${p.xy[1]}" r="${w*.018}" fill="none" stroke="#ff3daa" stroke-width="2.5" vector-effect="non-scaling-stroke" pointer-events="none"/>`;
  }
  return {markup,box:`${x} ${y} ${w} ${h}`,points};
}
function renderPhotos() {
  const view=selected.photo_views?.[Number($('photo-view').value)||0];
  if(!view){$('photo-context').innerHTML='';$('photo-detail').innerHTML='';$('photo-point-info').textContent='';$('photo-support-note').textContent='';qa.photo=null;return;}
  for(const [id,rect,context] of [['photo-context',[0,0,view.width,view.height],true],['photo-detail',view.crop,false]]){
    const data=photoSvg(view,rect,context);$(id).setAttribute('viewBox',data.box);$(id).innerHTML=data.markup;
  }
  $('photo-original').href=view.image;
  const keep=new Set(cohort().indices.map(i=>i+1)),shown=view.points.filter(p=>p.in_frame&&keep.has(p.id));
  const active=view.points.find(p=>p.id===Number($('photo-point').value));
  $('photo-point-info').textContent=active?`점 ${active.id} · 원자료 행 ${active.source_row} · 원영상 x=${number(active.xy[0],1)}, y=${number(active.xy[1],1)} px · ${active.in_frame?'영상 안에 투영됨':'영상 밖 또는 카메라 뒤'} · 분홍 점을 다른 시점·3D에서도 비교하세요.`:'확대 사진의 점을 누르거나 위에서 번호를 선택하세요. 선택한 점은 분홍색으로 강조합니다.';
  $('photo-support-note').textContent=`선택 표본 ${cohort().n}점 중 영상 안 ${shown.length}점`+(selected.metric_basis==='MVS'?` · 동결 MVS 지지점 ${shown.filter(p=>p.mvs_supported).length}점 · 주황 점은 이 시점에서 지지를 확인하지 못한 투영입니다.`:' · 노란 점은 참조의 투영이며 가림 검사를 통과했다는 뜻은 아닙니다.');
  qa.photo={caseID:selected.id,view:view.name,points:shown.length,supported:shown.filter(p=>p.mvs_supported).length,selected:active?.id||null,overlay:$('photo-points').checked,cohort:$('cohort').value};
  if($('photo-dialog').open)fillPhotoDialog();
  highlightPhotoPoint();
}
function fillPhotoDialog(){const svg=$('photo-detail').cloneNode(true);svg.removeAttribute('id');$('photo-large').replaceChildren(svg);}
function selectPhotoPoint(event){const target=event.target.closest('[data-point]');if(!target)return;if(event.type==='keydown'&&!['Enter',' '].includes(event.key))return;event.preventDefault();$('photo-point').value=target.dataset.point;renderPhotos();}
for(const id of ['photos','photo-large']){ $(id).addEventListener('click',selectPhotoPoint);$(id).addEventListener('keydown',selectPhotoPoint); }
for(const id of ['photo-view','photo-points','photo-labels','photo-point'])$(id).onchange=renderPhotos;
function openPhoto(){if(!selected.photo_views?.length)return;$('photo-large').style.width='100%';$('photo-zoom').value=100;fillPhotoDialog();$('photo-dialog').showModal();}
$('photo-open').onclick=openPhoto;$('photo-close').onclick=()=>$('photo-dialog').close();
$('photo-zoom').oninput=()=>{$('photo-large').style.width=$('photo-zoom').value+'%';};
window.addEventListener('resize',()=>{drawMap();draw();});
window.addEventListener('popstate',()=>selectCase(new URLSearchParams(location.search).get('case')||catalog.default_case,false));
Object.defineProperty(qa,'settled',{get:()=>qa.ready&&!scheduled});
async function start(){catalog=await json('catalog.json');if(catalog.mvs_reaudit)auditSummary=await json(catalog.mvs_reaudit);makePanels();fitMap(null);fillList();await selectCase(new URLSearchParams(location.search).get('case')||catalog.default_case,false);}
start().catch(fail);
