import * as THREE from '/vendor/three.module.min.js';

const $ = id => document.getElementById(id);
const pageConfig = JSON.parse(document.getElementById('comparison-config')?.textContent || '{}');
const roles = pageConfig.roles || ['da3', 'mvs', 'mvs_pgsr'];
const titles = pageConfig.titles || {da3:'DA3 · prior 0.005', mvs:'MVS · prior 0.005', mvs_pgsr:'MVS + PGSR · prior 0.005'};
const statusLabels = {available:'표시 가능', pending:'준비 대기', failed:'실패', loading:'불러오는 중', error:'표시 오류'};
const manifestURL = new URL(pageConfig.manifest || '/data/matched/manifest.json', location.href);
const panels = new Map(), bufferCache = new Map();
let manifest = null, region = null, representation = 'mesh', refreshBusy = false, inflight = 0, renderQueued = false;
const shared = {target:new THREE.Vector3(), yaw:-.8, pitch:.66, radius:100, span:30, zoom:1};
const qa = window.__GEOGS_MATCHED_QA__ = {ready:false, errors:[], panels:{}, images:{}, cameras:{}, frames:0, scientific_verdict:null};
Object.defineProperty(qa, 'settled', {enumerable:true, get:()=>qa.ready && !refreshBusy && inflight===0 && !renderQueued});
const linearRGB = new Float32Array(256);
for (let i=0;i<256;i++) {const c=i/255; linearRGB[i]=c<=.04045 ? c/12.92 : ((c+.055)/1.055)**2.4;}
const countLabel = n => Number(n).toLocaleString('ko-KR');
const vectorValid = v => Array.isArray(v) && v.length===3 && v.every(Number.isFinite);
const conditionFor = role => region?.conditions.find(c=>c.id===role);
function displayReason(value){
  if(!value)return '';
  if(value.startsWith('FAIL '))return '실행 중 오류가 발생했습니다. 해당 실험 로그를 확인해야 합니다.';
  return ({QUEUED:'앞선 실험 완료 후 자동 시작',PREFLIGHT_PRIOR_0005_R1_4:'학습 전 적용 조건 검증 중',VALIDATING_PREFLIGHT:'사전 실행 결과 확인 중',TRAIN_PRIOR_0005_R1_4:'30,000회까지 학습 중',EXTRACTION:'최종 표면과 RGB·depth 생성 중',PUBLISHING:'최종 결과를 뷰어에 연결 중'})[value] || value;
}

function urlFor(path) {
  const url = new URL(path, manifestURL);
  if (!['http:', 'https:'].includes(url.protocol)) throw Error('자료 URL 형식이 올바르지 않습니다.');
  return url.href;
}
function report(error, context=null) {
  const message=String(error?.message || error);
  qa.errors.push({message, context}); if (qa.errors.length>40) qa.errors.shift();
  if (!context) {$('error').hidden=false; $('error').textContent=message;}
  console.error(error);
}
function validateManifest(value) {
  if (value?.schema!==(pageConfig.schema || 'geogs_matched_comparison_v1') || value.scientific_verdict!==null || !Array.isArray(value.regions) || !value.regions.length) throw Error('동일 조건 비교 manifest를 확인할 수 없습니다.');
  const seen=new Set();
  for (const r of value.regions) {
    if (!(pageConfig.regions || ['P1','P2']).includes(r.id) || seen.has(r.id) || !vectorValid(r.bounds?.min) || !vectorValid(r.bounds?.max) || !r.bounds.min.every((v,i)=>v<r.bounds.max[i])) throw Error('공통 좌표 범위가 올바르지 않습니다.');
    seen.add(r.id);
    if (!Array.isArray(r.conditions) || r.conditions.length!==roles.length || roles.some(role=>r.conditions.filter(c=>c.id===role).length!==1)) throw Error(`${r.id}: 비교 조건을 명시해야 합니다.`);
    for (const c of r.conditions) if (!['available','pending','failed'].includes(c.status)) throw Error(`${r.id}/${c.id}: 알 수 없는 자료 상태입니다.`);
    if (r.views!==undefined && !Array.isArray(r.views)) throw Error(`${r.id}: 촬영 뷰 목록이 올바르지 않습니다.`);
    if (new Set((r.views || []).map(v=>v.id)).size!==(r.views || []).length) throw Error(`${r.id}: 촬영 뷰 ID가 중복됩니다.`);
  }
}
async function fetchBuffer(descriptor, required=true) {
  if (!descriptor || typeof descriptor.url!=='string') throw Error('자료 파일 URL이 없습니다.');
  if (required && (!Number.isSafeInteger(descriptor.bytes) || descriptor.bytes<0 || !/^[a-f0-9]{64}$/i.test(descriptor.sha256 || ''))) throw Error('기하 파일의 크기 또는 SHA256이 없습니다.');
  const response=await fetch(urlFor(descriptor.url));
  if (!response.ok) throw Error(`자료 HTTP ${response.status}: ${descriptor.url}`);
  const buffer=await response.arrayBuffer();
  if (descriptor.bytes!==undefined && buffer.byteLength!==descriptor.bytes) throw Error(`자료 크기 불일치: ${descriptor.url}`);
  let hash=null;
  if (globalThis.crypto?.subtle && descriptor.sha256) {
    hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',buffer)), n=>n.toString(16).padStart(2,'0')).join('');
    if (hash!==descriptor.sha256.toLowerCase()) throw Error(`자료 SHA256 불일치: ${descriptor.url}`);
  }
  return {buffer, hash, mime:response.headers.get('content-type') || 'application/octet-stream'};
}
function binary(descriptor) {
  const key=JSON.stringify(descriptor);
  if (!bufferCache.has(key)) bufferCache.set(key, fetchBuffer(descriptor).catch(error=>{bufferCache.delete(key); throw error;}));
  return bufferCache.get(key);
}
function clearObject(panel) {
  if (!panel.object) return;
  panel.scene.remove(panel.object); panel.object.geometry.dispose(); panel.object.material.dispose(); panel.object=null;
}
function placeholder(panel, title, detail='') {
  panel.empty.hidden=false; panel.empty.replaceChildren();
  const heading=document.createElement('strong'), text=document.createElement('small');
  heading.textContent=title; text.textContent=detail; panel.empty.append(heading,text);
}
function panelStatus(panel,status) {
  panel.status.textContent=statusLabels[status]; panel.status.dataset.status=status;
  qa.panels[panel.role]={...(qa.panels[panel.role] || {}),status};
}
function buildPanel(role) {
  const article=document.createElement('article'); article.className='geometry-panel'; article.dataset.panel=role;
  article.innerHTML='<div class="panel-head"><h2></h2><span class="status"></span></div><div class="viewport"><div class="empty"></div><span class="axis">Z ↑</span></div><div class="panel-meta"><p class="geometry-label"></p><p class="counts"></p><details><summary>출처와 표시 정보</summary><pre></pre></details></div>';
  article.querySelector('h2').textContent=titles[role]; $('geometry-panels').append(article);
  const host=article.querySelector('.viewport'), scene=new THREE.Scene(); scene.background=new THREE.Color('#172434');
  const camera=new THREE.OrthographicCamera(-1,1,1,-1,.01,10000); camera.up.set(0,0,1);
  const renderer=new THREE.WebGLRenderer({antialias:true, preserveDrawingBuffer:true});
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1,1.5)); renderer.outputColorSpace=THREE.SRGBColorSpace;
  renderer.domElement.tabIndex=0; renderer.domElement.setAttribute('aria-label',titles[role]+' 동기화 3D 화면'); host.prepend(renderer.domElement);
  const panel={role,article,host,scene,camera,renderer,object:null,token:0,status:article.querySelector('.status'),empty:article.querySelector('.empty')};
  panels.set(role,panel); bindCamera(panel); new ResizeObserver(scheduleRender).observe(host);
  renderer.domElement.addEventListener('webglcontextlost',event=>{event.preventDefault();panelStatus(panel,'error');placeholder(panel,'3D 연결이 끊겼습니다.','페이지를 새로고침해 주세요.');report('WebGL context lost',role);});
  placeholder(panel,'자료 준비 중');
  const render=document.createElement('article'); render.className='render-panel'; render.dataset.render=role;
  render.innerHTML='<div class="panel-head"><h3></h3><span class="status"></span></div><figure><figcaption><strong>실제 GS RGB</strong><span>동일 촬영 뷰</span></figcaption><div class="image-slot rgb"></div></figure><figure><figcaption><strong>실제 GS depth</strong><span>공통 색상 범위</span></figcaption><div class="image-slot depth"></div></figure><p class="render-meta"></p>';
  render.querySelector('h3').textContent=titles[role]; $('render-panels').append(render); panel.renderArticle=render;
}
function preset(name) {
  if (name==='top') {shared.yaw=-Math.PI/2; shared.pitch=Math.PI/2-.002;}
  else if (name==='side') {shared.yaw=-Math.PI/2; shared.pitch=.025;}
  else {shared.yaw=-.8; shared.pitch=.66;}
  document.querySelectorAll('[data-preset]').forEach(b=>b.classList.toggle('active',b.dataset.preset===name)); scheduleRender();
}
function resetCamera() {
  if (!region) return;
  const lo=new THREE.Vector3(...region.bounds.min), hi=new THREE.Vector3(...region.bounds.max), size=hi.clone().sub(lo);
  shared.target.copy(lo).add(hi).multiplyScalar(.5); shared.radius=Math.max(size.length()*1.8,10); shared.span=Math.max(size.x,size.y,size.z)*.65; shared.zoom=1; preset('oblique');
}
function pan(panel,dx,dy) {
  const scale=2*shared.span/shared.zoom/Math.max(panel.host.clientHeight,1);
  shared.target.addScaledVector(new THREE.Vector3(1,0,0).applyQuaternion(panel.camera.quaternion),-dx*scale).addScaledVector(new THREE.Vector3(0,1,0).applyQuaternion(panel.camera.quaternion),dy*scale);
}
function bindCamera(panel) {
  const canvas=panel.renderer.domElement, pointers=new Map();
  canvas.addEventListener('contextmenu',e=>e.preventDefault());
  canvas.addEventListener('pointerdown',e=>{if(e.button>2)return;canvas.focus({preventScroll:true});canvas.setPointerCapture(e.pointerId);pointers.set(e.pointerId,{x:e.clientX,y:e.clientY,pan:e.shiftKey||e.button!==0});});
  canvas.addEventListener('pointermove',e=>{
    const old=pointers.get(e.pointerId); if (!old) return;
    const dx=e.clientX-old.x, dy=e.clientY-old.y;
    if (pointers.size===2) {
      const other=[...pointers.entries()].find(([id])=>id!==e.pointerId)?.[1];
      if(other){const before=Math.hypot(old.x-other.x,old.y-other.y),after=Math.hypot(e.clientX-other.x,e.clientY-other.y);if(before>2&&after>2)shared.zoom=Math.max(.2,Math.min(12,shared.zoom*after/before));pan(panel,dx/2,dy/2);}
    } else if(old.pan||e.shiftKey) pan(panel,dx,dy);
    else {shared.yaw-=dx*.007;shared.pitch=Math.max(-1.54,Math.min(1.54,shared.pitch+dy*.007));document.querySelectorAll('[data-preset]').forEach(b=>b.classList.remove('active'));}
    pointers.set(e.pointerId,{...old,x:e.clientX,y:e.clientY});scheduleRender();
  });
  for (const name of ['pointerup','pointercancel','lostpointercapture']) canvas.addEventListener(name,e=>pointers.delete(e.pointerId));
  canvas.addEventListener('wheel',e=>{e.preventDefault();shared.zoom=Math.max(.2,Math.min(12,shared.zoom*Math.exp(-e.deltaY*.0015)));scheduleRender();},{passive:false});
  canvas.addEventListener('keydown',e=>{
    if (!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','+','=','-','0'].includes(e.key)) return;
    e.preventDefault(); if(e.key==='0'){resetCamera();return;}
    if(e.key==='+'||e.key==='=')shared.zoom=Math.min(12,shared.zoom*1.15);
    else if(e.key==='-')shared.zoom=Math.max(.2,shared.zoom/1.15);
    else {const dx=e.key==='ArrowLeft'?-14:e.key==='ArrowRight'?14:0,dy=e.key==='ArrowUp'?-14:e.key==='ArrowDown'?14:0;if(e.shiftKey)pan(panel,dx,dy);else{shared.yaw-=dx*.007;shared.pitch=Math.max(-1.54,Math.min(1.54,shared.pitch+dy*.007));}}
    scheduleRender();
  });
}
function scheduleRender() {
  if(renderQueued)return; renderQueued=true;
  requestAnimationFrame(()=>{
    renderQueued=false;
    const direction=new THREE.Vector3(Math.cos(shared.yaw)*Math.cos(shared.pitch),Math.sin(shared.yaw)*Math.cos(shared.pitch),Math.sin(shared.pitch));
    for(const [role,panel] of panels){
      const width=Math.max(1,panel.host.clientWidth),height=Math.max(1,panel.host.clientHeight),span=shared.span/shared.zoom;
      panel.renderer.setSize(width,height,false); Object.assign(panel.camera,{left:-span*width/height,right:span*width/height,top:span,bottom:-span,near:.01,far:shared.radius*20});
      panel.camera.position.copy(shared.target).addScaledVector(direction,shared.radius); panel.camera.lookAt(shared.target); panel.camera.updateProjectionMatrix(); panel.renderer.render(panel.scene,panel.camera);
      qa.cameras[role]={position:panel.camera.position.toArray(),target:shared.target.toArray(),span:shared.span,zoom:shared.zoom,yaw:shared.yaw,pitch:shared.pitch};
      if(qa.panels[role])Object.assign(qa.panels[role],{width,height,drawn:!!panel.object});
    }
    qa.frames++;
  });
}
async function loadGeometry(panel) {
  const token=++panel.token, mode=representation, condition=conditionFor(panel.role);
  const data=mode==='mesh'?condition?.mesh:condition?.centers?.[mode];
  clearObject(panel);
  qa.panels[panel.role]={region:region.id,condition:panel.role,representation:mode,point_size_px:mode==='mesh'?null:2,alpha_threshold:mode==='alpha01' ? 0.1 : null,drawn:false};
  panel.article.querySelector('.geometry-label').textContent=mode==='mesh'?'동일 추출 조건의 raw RGB mesh':mode==='all'?'전체 Gaussian 중심의 표시 표본 · SH 색상':'α ≥ 0.1 Gaussian 중심 표본 · SH 색상 · 진단 전용';
  panel.article.querySelector('.counts').textContent='';
  panel.article.querySelector('pre').textContent=JSON.stringify({condition:condition?.id,source:condition?.source,color:condition?.color,representation:mode,descriptor:data || null},null,2);
  if(!data||condition?.status==='failed'){
    panelStatus(panel,condition?.status==='failed'?'failed':'pending');
    placeholder(panel,mode==='mesh'?'Raw RGB mesh 준비 대기':'선택한 중심점 자료 준비 대기',displayReason(condition?.reason) || '이 표현의 실제 파일이 준비되면 표시합니다.');scheduleRender();return;
  }
  panelStatus(panel,'loading'); placeholder(panel,'같은 표현의 기하를 불러오는 중'); inflight++;
  let geometry=null,material=null;
  try {
    const records=await Promise.all([binary(data.xyz),binary(data.rgb),...(mode==='mesh'?[binary(data.indices)]:[])]);
    const xyz=new Float32Array(records[0].buffer), rgb=new Uint8Array(records[1].buffer), count=mode==='mesh'?data.vertex_count:data.count;
    if(!Number.isSafeInteger(count)||count<1||xyz.length!==count*3||rgb.length!==xyz.length)throw Error('표시 XYZ/RGB 개수가 일치하지 않습니다.');
    for(const n of xyz)if(!Number.isFinite(n))throw Error('유효하지 않은 기하 좌표입니다.');
    const colors=new Float32Array(rgb.length);for(let i=0;i<rgb.length;i++)colors[i]=linearRGB[rgb[i]];
    geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.BufferAttribute(xyz,3));geometry.setAttribute('color',new THREE.BufferAttribute(colors,3));
    let object;
    if(mode==='mesh'){
      const indices=new Uint32Array(records[2].buffer);
      if(!Number.isSafeInteger(data.triangle_count)||data.triangle_count<1||indices.length!==data.triangle_count*3)throw Error('삼각형 개수가 일치하지 않습니다.');
      for(const index of indices)if(index>=count)throw Error('삼각형 인덱스가 정점 범위를 벗어납니다.');
      geometry.setIndex(new THREE.BufferAttribute(indices,1));material=new THREE.MeshBasicMaterial({vertexColors:true,side:THREE.DoubleSide,toneMapped:false});object=new THREE.Mesh(geometry,material);
    }else{material=new THREE.PointsMaterial({size:2,sizeAttenuation:false,vertexColors:true,toneMapped:false});object=new THREE.Points(geometry,material);}
    if(token!==panel.token){geometry.dispose();material.dispose();return;}
    geometry.computeBoundingSphere();object.userData.records=records;panel.object=object;panel.scene.add(object);panel.empty.hidden=true;panelStatus(panel,'available');
    Object.assign(qa.panels[panel.role],{count,triangle_count:data.triangle_count || 0,integrity:globalThis.crypto?.subtle?'SHA256_AND_BYTES_VERIFIED':'BYTES_VERIFIED_SHA256_API_UNAVAILABLE',buffers:records.map((r,i)=>({bytes:r.buffer.byteLength,sha256:r.hash,expected_sha256:[data.xyz,data.rgb,data.indices][i].sha256})),rgb_min:[0,1,2].map(c=>{let v=255;for(let i=c;i<rgb.length;i+=3)v=Math.min(v,rgb[i]);return v;}),rgb_max:[0,1,2].map(c=>{let v=0;for(let i=c;i<rgb.length;i+=3)v=Math.max(v,rgb[i]);return v;})});
    panel.article.querySelector('.counts').textContent=mode==='mesh'?`${countLabel(count)} 정점 · ${countLabel(data.triangle_count)} 삼각형`:`${countLabel(count)} 중심점 · 고정 크기 2 px`;
  }catch(error){geometry?.dispose();material?.dispose();if(token===panel.token){panelStatus(panel,'error');placeholder(panel,'기하 표시 오류',error.message);report(error,panel.role);}}
  finally{inflight--;scheduleRender();}
}
function imagePlaceholder(slot,text) {slot.replaceChildren();const span=document.createElement('span');span.className='image-placeholder';span.textContent=text;slot.append(span);}
async function loadImage(slot,descriptor,key,alt,reason='출력 준비 대기') {
  const token=Number(slot.dataset.token || 0)+1;slot.dataset.token=String(token);
  if(slot.dataset.blob){URL.revokeObjectURL(slot.dataset.blob);delete slot.dataset.blob;}
  qa.images[key]={status:descriptor?'loading':'pending',view:$('photo-view').value};imagePlaceholder(slot,descriptor?'실제 영상 불러오는 중':displayReason(reason));
  if(!descriptor)return;
  inflight++;let objectURL=null;
  try {
    const record=await fetchBuffer(descriptor,false);
    if(Number(slot.dataset.token)!==token)return;
    objectURL=URL.createObjectURL(new Blob([record.buffer],{type:record.mime}));
    const image=new Image();image.alt=alt;image.src=objectURL;await image.decode();
    if(Number(slot.dataset.token)!==token){URL.revokeObjectURL(objectURL);return;}
    slot.dataset.blob=objectURL;slot.replaceChildren(image);
    const link=document.createElement('a');link.href=urlFor(descriptor.url);link.target='_blank';link.rel='noopener noreferrer';link.setAttribute('aria-label',alt+' 원본 크기로 열기');slot.append(link);
    qa.images[key]={status:'available',view:$('photo-view').value,url:descriptor.url,width:image.naturalWidth,height:image.naturalHeight,bytes:record.buffer.byteLength,sha256:record.hash};
  }catch(error){if(objectURL)URL.revokeObjectURL(objectURL);if(Number(slot.dataset.token)===token){imagePlaceholder(slot,'영상 표시 오류: '+error.message);qa.images[key]={status:'error',message:error.message};report(error,key);}}
  finally{inflight--;}
}
async function selectView(id) {
  const view=(region?.views || []).find(v=>v.id===id) || null;
  $('photo-view').value=view?.id || '';qa.selected_view=view?.id || null;
  $('photo-name').textContent=view?.image_name || '촬영 뷰 준비 대기';
  $('view-details').textContent=view?[view.label || view.image_name,view.split?`분할: ${view.split}`:'',view.roi_bbox?`공통 ROI: ${JSON.stringify(view.roi_bbox)}`:''].filter(Boolean).join(' · '):'같은 촬영 카메라의 렌더 결과를 준비하고 있습니다.';
  const range=view?.depth_range_m;
  $('depth-scale').textContent=Array.isArray(range)&&range.length===2?`세 조건 공통 depth 표시 범위: ${range[0]}–${range[1]} m`:'공통 depth 표시 범위 미제공';
  const requests=[loadImage($('original-slot'),view?.original,'original',`${region?.id} ${view?.image_name || ''} 원사진`)];
  if ($('weight-slot')) {
    const weights=view?.weights;
    $('weight-policy').textContent=region.weight_policy || '';
    $('weight-camera').textContent=view?.image_name || '';
    $('weight-note').textContent=weights?.applied
      ? '선택한 촬영 영상의 입력 native MVS와 실제 학습 마스크입니다. R1만 0·1·4로 변경하며 R2·R3는 1, R4·R5·R6와 결측은 0입니다. 그림을 누르면 확대됩니다.'
      : weights?.reason || '이 촬영 영상의 적용 가중치 자료가 없습니다.';
    $('weight-links').replaceChildren();
    for (const [key,label] of [['gallery_url','기준 영상 영역도'],['all_views_url','전체 학습뷰 영역도']]) {
      if (!weights?.[key]) continue;
      const link=document.createElement('a');link.href=urlFor(weights[key]);link.textContent=label+' ↗';link.target='_blank';link.rel='noopener';$('weight-links').append(link);
    }
    qa.weight={region:region.id,camera:view?.image_name,applied:!!weights?.applied,mask_sha256:weights?.mask_sha256 || null};
    requests.push(loadImage($('weight-slot'),weights?.figure,'weights',`${region.id} ${view?.image_name} 실제 depth 가중치 영역`,weights?.reason));
  }
  for(const role of roles){
    const entry=view?.conditions?.[role],panel=panels.get(role).renderArticle,status=entry?.status || 'pending';
    const pill=panel.querySelector('.status');pill.dataset.status=status;pill.textContent=statusLabels[status] || status;
    panel.querySelector('.render-meta').textContent=displayReason(entry?.reason) || (view?`${view.image_name} · ${roles.length}개 조건의 같은 촬영 카메라`:'동일 촬영 뷰의 실제 출력 준비 대기');
    for(const type of ['rgb','depth'])requests.push(loadImage(panel.querySelector('.'+type),status==='failed'?null:entry?.[type],`${role}.${type}`,`${region?.id} ${titles[role]} ${view?.image_name || ''} 실제 ${type}`,entry?.reason || '실제 렌더 출력 준비 대기'));
  }
  await Promise.all(requests);
}
async function selectRegion(id,preserve=false) {
  const next=manifest.regions.find(r=>r.id===id);if(!next)throw Error('알 수 없는 관찰 영역입니다.');
  const changed=region?.id!==id,oldView=$('photo-view').value;region=next;qa.region=id;
  for(const option of $('representation').options)option.disabled=option.value!=='mesh'&&!region.conditions.some(c=>c.centers?.[option.value]);
  if([...$('representation').options].find(option=>option.value===representation)?.disabled)representation='mesh';
  updateRepresentationUI();
  document.querySelectorAll('[data-region]').forEach(b=>{const active=b.dataset.region===(pageConfig.group_regions?id.split('_')[0]:id);b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));});
  if ($('region-scope')) $('region-scope').value=id.endsWith('_context')?'context':'roi';
  if(changed||!preserve)resetCamera();
  const selector=$('photo-view');selector.replaceChildren();
  for(const view of region.views || []){const option=document.createElement('option');option.value=view.id;option.textContent=view.label || view.image_name || view.id;selector.append(option);}
  selector.disabled=!region.views?.length;
  if(!region.views?.length){const option=document.createElement('option');option.textContent='촬영 뷰 준비 대기';option.value='';selector.append(option);}
  const selected=(region.views || []).some(v=>v.id===oldView)&&!changed?oldView:region.views?.[0]?.id;
  await Promise.all([...panels.values()].map(loadGeometry).concat(selectView(selected)));
}
async function setRepresentation(value) {
  if(!['mesh','all','alpha01'].includes(value))throw Error('알 수 없는 기하 표현입니다.');
  if([...$('representation').options].find(option=>option.value===value)?.disabled)throw Error('이 영역에는 선택한 중심점 자료가 없습니다.');
  representation=value;updateRepresentationUI();
  if(region)await Promise.all([...panels.values()].map(loadGeometry));
}
function updateRepresentationUI(){
  $('representation').value=representation;qa.representation=representation;
  $('representation-note').textContent=representation==='mesh'?`${roles.length}개 조건의 raw RGB mesh를 비교합니다. 파일이 없으면 해당 조건은 대기로 표시합니다.`:representation==='all'?'진단용: 전체 Gaussian 중심의 표시 표본을 2 px로 그립니다. 중심점은 추출 표면이나 실제 RGB 렌더가 아닙니다.':'진단용: α ≥ 0.1인 Gaussian 중심의 표시 표본을 2 px로 그립니다. 이 필터는 기하 정확도 판정이나 결과 보정을 의미하지 않습니다.';
}
async function refresh(skipUnchanged=false) {
  if(refreshBusy)return;refreshBusy=true;$('refresh').disabled=true;$('error').hidden=true;
  try {
    const response=await fetch(manifestURL,{cache:'no-store'});if(!response.ok)throw Error(`동일 조건 자료 HTTP ${response.status}; manifest 준비 여부를 확인해 주세요.`);
    const value=await response.json();validateManifest(value);
    if(skipUnchanged===true&&qa.ready&&manifest?.generated_at===value.generated_at)return;
    manifest=value;
    $('surface-contract').textContent=value.surface_contract?.label || [value.surface_contract?.surface || 'raw',value.surface_contract?.mesh_resolution?`TSDF ${value.surface_contract.mesh_resolution}`:''].filter(Boolean).join(' · ');
    $('freshness').textContent=[value.run_status?.label,value.generated_at?`자료 갱신: ${value.generated_at}`:'manifest에 기록된 실제 출력만 표시'].filter(Boolean).join(' · ');
    if ($('comparison-downloads')) {
      $('comparison-downloads').replaceChildren();
      for (const item of value.downloads || []) {const link=document.createElement('a');link.href=urlFor(item.url);link.textContent=item.label+' ↗';link.target='_blank';link.rel='noopener noreferrer';$('comparison-downloads').append(link,document.createTextNode(' · '));}
    }
    $('region-tabs').replaceChildren();
    for(const r of manifest.regions){
      if(pageConfig.group_regions&&r.id.endsWith('_context'))continue;
      const button=document.createElement('button');button.type='button';button.dataset.region=r.id;button.textContent=pageConfig.group_regions?r.id:r.label || r.id;
      button.addEventListener('click',()=>selectRegion(r.id+(pageConfig.group_regions&&$('region-scope')?.value==='context'?'_context':'')).catch(error=>report(error)));$('region-tabs').append(button);
    }
    const requested=region?.id || new URLSearchParams(location.search).get('region');
    await selectRegion(manifest.regions.some(r=>r.id===requested)?requested:manifest.regions[0].id,true);
    qa.ready=true;$('loading').hidden=true;
  }catch(error){$('loading').hidden=true;report(error);}
  finally{refreshBusy=false;$('refresh').disabled=false;}
}

roles.forEach(buildPanel);
document.querySelectorAll('[data-preset]').forEach(button=>button.addEventListener('click',()=>preset(button.dataset.preset)));
$('reset-camera').addEventListener('click',resetCamera);
$('representation').addEventListener('change',()=>setRepresentation($('representation').value).catch(error=>report(error)));
$('photo-view').addEventListener('change',()=>selectView($('photo-view').value).catch(error=>report(error)));
$('region-scope')?.addEventListener('change',()=>selectRegion(region.id.split('_')[0]+($('region-scope').value==='context'?'_context':'')).catch(error=>report(error)));
$('refresh').addEventListener('click',refresh);
Object.assign(qa,{setRegion:id=>selectRegion(id),setRepresentation,setView:selectView,setPreset:preset,refresh});
window.addEventListener('error',e=>{qa.errors.push({message:e.message,context:'window'});});
window.addEventListener('unhandledrejection',e=>report(e.reason,'unhandledrejection'));
refresh();
if (pageConfig.poll_seconds) setInterval(()=>refresh(true), Math.max(10, pageConfig.poll_seconds)*1000);
