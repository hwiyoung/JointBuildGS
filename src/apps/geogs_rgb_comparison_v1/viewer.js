import * as THREE from '/vendor/three.module.min.js';

const $ = id => document.getElementById(id);
const roles = ['prior', 'mvs', 'anchor', 'vanilla', 'geogs', 'mvs_geogs', 'gt'];
const titles = {prior:'Prior', mvs:'MVS', anchor:'Anchor-only · 8k', vanilla:'Vanilla GeoGS', geogs:'GeoGS 변형', mvs_geogs:'MVS GeoGS', gt:'Drone LiDAR · GT'};
const statusText = {available:'표시 가능', pending:'대기 중', failed:'실패', loading:'불러오는 중', error:'표시 오류'};
const panels = new Map();
const qa = window.__GEOGS_RGB_QA__ = {ready:false, errors:[], panels:{}, cameras:{}, selected:{}, frames:0, scientific_verdict:null};
Object.defineProperty(qa,'settled',{enumerable:true,get:()=>qa.ready && !refreshBusy && [...panels.values()].every(panel=>!qa.panels[panel.role]?.loading)});
const manifestURL = new URL('/data/manifest.json', location.href);
const linearRGB = new Float32Array(256);
for (let i=0;i<256;i++) { const value=i/255; linearRGB[i]=value<=.04045?value/12.92:((value+.055)/1.055)**2.4; }
let manifest=null, region=null, activeRegionID=null, representation='auto', pointSize=2, updateToken=0;
let shared={target:new THREE.Vector3(), yaw:-.8, pitch:.66, radius:100, span:30, zoom:1};
let renderRequested=false, refreshBusy=false, focused=null, restoreFocus=null;
const bufferCache = new Map();
const numeric = value => Number(value).toLocaleString('ko-KR');
const vectorValid = value => Array.isArray(value) && value.length===3 && value.every(Number.isFinite);

function artifactURL(value) {
  const url=new URL(value, manifestURL);
  if (!['http:','https:'].includes(url.protocol)) throw Error('허용되지 않은 자료 URL');
  return url.href;
}
function recordError(error, role=null) {
  const message=String(error?.message || error);
  qa.errors.push({message, panel:role, at:new Date().toISOString()});
  if (qa.errors.length>30) qa.errors.shift();
  if (!role) { $('error').hidden=false; $('error').textContent=message; }
  console.error(error);
}
function validateManifest(value) {
  if (value?.schema!=='geogs_rgb_comparison_v1' || value.scientific_verdict!==null || !value.regions?.length) throw Error('RGB 비교 manifest 형식 또는 판정 상태가 올바르지 않습니다.');
  const ids=new Set();
  for (const r of value.regions) {
    if (!r.id || ids.has(r.id) || !vectorValid(r.bounds?.min) || !vectorValid(r.bounds?.max) || !r.bounds.min.every((v,i)=>v<r.bounds.max[i])) throw Error('영역 ID 또는 공통 표시 범위를 확인할 수 없습니다.');
    ids.add(r.id);
    if (!Array.isArray(r.candidates) || new Set(r.candidates.map(c=>c.id)).size!==r.candidates.length) throw Error(`${r.id}: 후보 ID가 중복되거나 없습니다.`);
    for (const candidate of r.candidates) {
      if (!['available','pending','failed'].includes(candidate.status)) throw Error(`${r.id}/${candidate.id}: 알 수 없는 상태입니다.`);
      if (candidate.status==='available' && !candidate.points && !candidate.mesh && candidate.representation_policy!=='surface_only') throw Error(`${r.id}/${candidate.id}: 표시할 실제 기하 descriptor가 없습니다.`);
    }
  }
}
function candidatesFor(role) {
  if (!region) return [];
  return region.candidates.filter(candidate=> role==='geogs'
    ? ['geogs','vanilla'].includes(candidate.group) || candidate.groups?.some(group=>['geogs','vanilla'].includes(group))
    : candidate.group===role || candidate.groups?.includes(role));
}
function currentCandidate(role) {
  const id=qa.selected[role];
  return region?.candidates.find(candidate=>candidate.id===id) || null;
}
function descriptorMode(candidate) {
  if (candidate?.representation_policy==='surface_only') return 'mesh';
  return representation==='auto' ? (candidate?.mesh?'mesh':'points') : representation;
}
function geometryLabel(candidate, mode) {
  if (candidate?.representation_policy==='surface_only') return candidate.mesh?'실제 삼각형 표면 · RGB · 표면 전용':'RGB 표면 준비 대기';
  const kind=String(candidate?.geometry_kind || '');
  if (/gaussian.*cent|sh.?dc/i.test(kind)) return 'Gaussian 중심 · SH 색상 · 표시 전용';
  if (/COLMAP/.test(kind)) return 'COLMAP depth 역투영 표본 · 융합 전';
  if (mode==='mesh') return '실제 삼각형 표면 · RGB';
  if (/mesh|surface|triangle/i.test(kind)) return '표면에서 추출한 RGB 점';
  return '원본 좌표의 RGB 점';
}
function colorDescription(candidate) {
  if (!candidate) return '색상 출처 없음';
  return candidate.color?.label || candidate.color?.kind || '색상 출처 미기재';
}
function coverageText(candidate) {
  const coverage=candidate?.color?.coverage;
  if (Number.isFinite(coverage)) return `색상 지원 ${(coverage<=1?100*coverage:coverage).toFixed(1)}%`;
  return '';
}
function placeholder(panel, title, detail='') {
  panel.empty.hidden=false;
  panel.empty.replaceChildren();
  const strong=document.createElement('strong');strong.textContent=title;
  const small=document.createElement('small');small.textContent=detail;
  panel.empty.append(strong,small);
}
function clearGeometry(panel) {
  if (panel.object) { panel.scene.remove(panel.object);panel.object.geometry.dispose();panel.object.material.dispose();panel.object=null; }
}
async function bufferEvidence(object) {
  if(!object)return null;
  const records=[];
  for(const [kind,entry] of Object.entries(object.userData.rawBuffers)){
    const digest=globalThis.crypto?.subtle?new Uint8Array(await crypto.subtle.digest('SHA-256',entry.buffer)):null;
    const actual=digest?Array.from(digest,value=>value.toString(16).padStart(2,'0')).join(''):null;
    records.push({kind,url:entry.descriptor.url,bytes:entry.buffer.byteLength,expected_sha256:entry.descriptor.sha256,sha256:actual,matches:actual===null?null:actual===entry.descriptor.sha256.toLowerCase()});
  }
  const rgb=new Uint8Array(object.userData.rawBuffers.rgb.buffer),colors=object.geometry.getAttribute('color').array;
  const distinct=new Set(),minimum=[255,255,255],maximum=[0,0,0];
  const stride=Math.max(1,Math.floor(rgb.length/3/8192));
  let colorConversionMatches=true;
  for(let point=0;point<rgb.length/3;point+=stride){const i=point*3;distinct.add(`${rgb[i]},${rgb[i+1]},${rgb[i+2]}`);for(let channel=0;channel<3;channel++){minimum[channel]=Math.min(minimum[channel],rgb[i+channel]);maximum[channel]=Math.max(maximum[channel],rgb[i+channel]);if(colors[i+channel]!==linearRGB[rgb[i+channel]])colorConversionMatches=false;}}
  return {records,rgb_min:minimum,rgb_max:maximum,rgb_distinct_sampled:distinct.size,sample_stride:stride,color_conversion_matches:colorConversionMatches,vertex_color_space:'linear-sRGB',output_color_space:'sRGB',material:object.material.type};
}
function setPanelStatus(panel,status) {
  panel.status.textContent=statusText[status] || status;
  panel.status.dataset.status=status;
  qa.panels[panel.role]={...(qa.panels[panel.role] || {}),status,loading:status==='loading'};
}
function buildPanel(role,index) {
  const article=document.createElement('article');article.className='panel';article.dataset.panel=role;
  article.innerHTML='<div class="panel-header"><div class="panel-title"><span class="panel-index"></span><h2></h2></div><button type="button" class="panel-expand">확대 ↗</button></div><div class="panel-selection"><span class="candidate-label"></span><select hidden></select><span class="status-pill"></span></div><div class="viewport"><div class="empty-state"></div><span class="viewport-label"></span><span class="axis-note">Z ↑</span></div><div class="panel-meta"><div class="source-line"><i class="source-dot"></i><span class="source-name"></span></div><div class="geometry-note"></div><div class="color-note"></div><div class="panel-links"></div><details class="source-details"><summary>출처와 표시 정보</summary><pre></pre></details></div>';
  article.querySelector('.panel-index').textContent=String(index+1).padStart(2,'0');
  article.querySelector('h2').textContent=titles[role];
  article.querySelector('select').setAttribute('aria-label',titles[role]+' 조건');
  $('panels').append(article);
  const host=article.querySelector('.viewport'), scene=new THREE.Scene();scene.background=new THREE.Color('#14202d');
  const camera=new THREE.OrthographicCamera(-1,1,1,-1,.01,10000);camera.up.set(0,0,1);
  const renderer=new THREE.WebGLRenderer({antialias:true,alpha:false,preserveDrawingBuffer:true});
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1,1.5));
  if (THREE.SRGBColorSpace) renderer.outputColorSpace=THREE.SRGBColorSpace;
  renderer.domElement.tabIndex=0;renderer.domElement.setAttribute('aria-label',titles[role]+' 3D 화면. 드래그로 전체 카메라 회전.');
  host.prepend(renderer.domElement);
  const panel={role,article,host,scene,camera,renderer,object:null,token:0,signature:null,
    empty:article.querySelector('.empty-state'),status:article.querySelector('.status-pill'),select:article.querySelector('select')};
  panels.set(role,panel);
  panel.select.addEventListener('change',()=>{qa.selected[role]=panel.select.value;loadPanel(panel,true);});
  article.querySelector('.panel-expand').addEventListener('click',()=>toggleFocus(role));
  bindCameraControls(panel);
  new ResizeObserver(()=>scheduleRender()).observe(host);
  renderer.domElement.addEventListener('webglcontextlost',event=>{event.preventDefault();setPanelStatus(panel,'error');placeholder(panel,'3D 화면 연결이 끊겼습니다.','페이지를 새로고침하면 화면을 다시 만들 수 있습니다.');recordError('WebGL context lost',role);});
  placeholder(panel,'자료를 확인하고 있습니다.');
}
function setPreset(name) {
  if (name==='top') {shared.yaw=-Math.PI/2;shared.pitch=Math.PI/2-.002;}
  else if (name==='side') {shared.yaw=-Math.PI/2;shared.pitch=.025;}
  else {shared.yaw=-.8;shared.pitch=.66;}
  document.querySelectorAll('[data-preset]').forEach(button=>button.classList.toggle('active',button.dataset.preset===name));
  scheduleRender();
}
function resetCamera() {
  if (!region) return;
  const lower=new THREE.Vector3(...region.bounds.min),upper=new THREE.Vector3(...region.bounds.max),size=upper.clone().sub(lower);
  shared.target.copy(lower).add(upper).multiplyScalar(.5);
  shared.radius=Math.max(size.length()*1.8,10);shared.span=Math.max(size.x,size.y,size.z)*.65;shared.zoom=1;
  setPreset('oblique');
}
function panCamera(panel,dx,dy) {
  const scale=2*shared.span/shared.zoom/Math.max(panel.host.clientHeight,1);
  const right=new THREE.Vector3(1,0,0).applyQuaternion(panel.camera.quaternion);
  const up=new THREE.Vector3(0,1,0).applyQuaternion(panel.camera.quaternion);
  shared.target.addScaledVector(right,-dx*scale).addScaledVector(up,dy*scale);
}
function bindCameraControls(panel) {
  const canvas=panel.renderer.domElement,pointers=new Map();
  canvas.addEventListener('contextmenu',event=>event.preventDefault());
  canvas.addEventListener('pointerdown',event=>{if(event.button>2)return;canvas.focus({preventScroll:true});pointers.set(event.pointerId,{x:event.clientX,y:event.clientY,pan:event.shiftKey||event.button!==0});canvas.setPointerCapture(event.pointerId);});
  canvas.addEventListener('pointermove',event=>{
    const previous=pointers.get(event.pointerId);if(!previous)return;
    const dx=event.clientX-previous.x,dy=event.clientY-previous.y;
    if(pointers.size===2){const other=[...pointers.entries()].find(([id])=>id!==event.pointerId)?.[1];if(other){const before=Math.hypot(previous.x-other.x,previous.y-other.y),after=Math.hypot(event.clientX-other.x,event.clientY-other.y);if(before>2&&after>2)shared.zoom=Math.max(.2,Math.min(12,shared.zoom*after/before));panCamera(panel,dx/2,dy/2);}}
    else if(previous.pan||event.shiftKey)panCamera(panel,dx,dy);
    else{shared.yaw-=dx*.007;shared.pitch=Math.max(-Math.PI/2+.025,Math.min(Math.PI/2-.025,shared.pitch+dy*.007));document.querySelectorAll('[data-preset]').forEach(button=>button.classList.remove('active'));}
    pointers.set(event.pointerId,{...previous,x:event.clientX,y:event.clientY});scheduleRender();
  });
  for(const name of ['pointerup','pointercancel','lostpointercapture'])canvas.addEventListener(name,event=>pointers.delete(event.pointerId));
  canvas.addEventListener('wheel',event=>{event.preventDefault();shared.zoom=Math.max(.2,Math.min(12,shared.zoom*Math.exp(-event.deltaY*.0015)));scheduleRender();},{passive:false});
  canvas.addEventListener('keydown',event=>{
    if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','+','=','-','0'].includes(event.key))return;
    event.preventDefault();const dx=event.key==='ArrowLeft'?-14:event.key==='ArrowRight'?14:0,dy=event.key==='ArrowUp'?-14:event.key==='ArrowDown'?14:0;
    if(event.key==='0'){resetCamera();return;}
    if(event.key==='+'||event.key==='=')shared.zoom=Math.min(12,shared.zoom*1.15);
    else if(event.key==='-')shared.zoom=Math.max(.2,shared.zoom/1.15);
    else if(event.shiftKey)panCamera(panel,dx,dy);
    else{shared.yaw-=dx*.007;shared.pitch=Math.max(-1.54,Math.min(1.54,shared.pitch+dy*.007));}
    scheduleRender();
  });
}
function scheduleRender() {
  if(renderRequested)return;renderRequested=true;
  requestAnimationFrame(()=>{
    renderRequested=false;
    const direction=new THREE.Vector3(Math.cos(shared.yaw)*Math.cos(shared.pitch),Math.sin(shared.yaw)*Math.cos(shared.pitch),Math.sin(shared.pitch));
    for(const [role,panel] of panels){
      const width=Math.max(1,panel.host.clientWidth),height=Math.max(1,panel.host.clientHeight),aspect=width/height;
      panel.renderer.setSize(width,height,false);
      const span=shared.span/shared.zoom;
      Object.assign(panel.camera,{left:-span*aspect,right:span*aspect,top:span,bottom:-span,near:.01,far:shared.radius*20});
      panel.camera.position.copy(shared.target).addScaledVector(direction,shared.radius);panel.camera.lookAt(shared.target);panel.camera.updateProjectionMatrix();
      panel.renderer.render(panel.scene,panel.camera);
      qa.cameras[role]={position:panel.camera.position.toArray(),target:shared.target.toArray(),yaw:shared.yaw,pitch:shared.pitch,zoom:shared.zoom,span:shared.span};
      qa.panels[role]={...(qa.panels[role]||{}),hasCanvas:true,width,height,drawn:!!panel.object};
    }
    qa.frames++;
  });
}
async function binary(descriptor) {
  if(!descriptor || typeof descriptor.url!=='string' || !Number.isSafeInteger(descriptor.bytes) || descriptor.bytes<0 || !/^[a-f0-9]{64}$/i.test(descriptor.sha256 || ''))throw Error('바이너리 파일의 크기 또는 SHA256 정보가 없습니다.');
  const key=descriptor.url+'#'+descriptor.sha256;
  if(!bufferCache.has(key))bufferCache.set(key,(async()=>{
    const response=await fetch(artifactURL(descriptor.url));if(!response.ok)throw Error(`기하 파일 HTTP ${response.status}: ${descriptor.url}`);
    const buffer=await response.arrayBuffer();if(buffer.byteLength!==descriptor.bytes)throw Error(`기하 파일 크기가 일치하지 않습니다: ${descriptor.url}`);
    if(globalThis.crypto?.subtle){const bytes=new Uint8Array(await crypto.subtle.digest('SHA-256',buffer)),hex=Array.from(bytes,value=>value.toString(16).padStart(2,'0')).join('');if(hex!==descriptor.sha256.toLowerCase())throw Error(`기하 파일 SHA256이 일치하지 않습니다: ${descriptor.url}`);}
    return buffer;
  })().catch(error=>{bufferCache.delete(key);throw error;}));
  return bufferCache.get(key);
}
function validateXYZ(xyz,expected) {
  if(!Number.isSafeInteger(expected)||expected<1||xyz.length!==expected*3)throw Error('표시 점 또는 정점 개수가 일치하지 않습니다.');
  for(const value of xyz)if(!Number.isFinite(value))throw Error('유효하지 않은 XYZ 좌표가 포함되어 있습니다.');
}
async function loadObject(candidate,mode) {
  const data=candidate[mode];
  if(!data)return null;
  const buffers=await Promise.all([binary(data.xyz),binary(data.rgb),...(mode==='mesh'?[binary(data.indices)]:[])]);
  const xyz=new Float32Array(buffers[0]),rgb=new Uint8Array(buffers[1]),count=mode==='mesh'?data.vertex_count:data.count;
  validateXYZ(xyz,count);if(rgb.length!==xyz.length)throw Error('RGB와 XYZ 개수가 다릅니다.');
  const colors=new Float32Array(rgb.length);for(let i=0;i<rgb.length;i++)colors[i]=linearRGB[rgb[i]];
  const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.BufferAttribute(xyz,3));geometry.setAttribute('color',new THREE.BufferAttribute(colors,3));
  let object;
  if(mode==='mesh'){
    const indices=new Uint32Array(buffers[2]);
    if(!Number.isSafeInteger(data.triangle_count)||data.triangle_count<1||indices.length!==data.triangle_count*3){geometry.dispose();throw Error('삼각형 개수가 일치하지 않습니다.');}
    for(const index of indices)if(index>=count){geometry.dispose();throw Error('표면 인덱스가 정점 범위를 벗어났습니다.');}
    geometry.setIndex(new THREE.BufferAttribute(indices,1));
    object=new THREE.Mesh(geometry,new THREE.MeshBasicMaterial({vertexColors:true,side:THREE.DoubleSide,toneMapped:false}));
  }else object=new THREE.Points(geometry,new THREE.PointsMaterial({size:pointSize,sizeAttenuation:false,vertexColors:true,toneMapped:false}));
  object.userData.rawBuffers={xyz:{buffer:buffers[0],descriptor:data.xyz},rgb:{buffer:buffers[1],descriptor:data.rgb}};
  if(mode==='mesh')object.userData.rawBuffers.indices={buffer:buffers[2],descriptor:data.indices};
  geometry.computeBoundingSphere();return object;
}
function updatePanelMetadata(panel,candidate,mode) {
  const article=panel.article;
  article.querySelector('.candidate-label').textContent=candidate?.label || '자료 없음';
  article.querySelector('.candidate-label').title=candidate?.label || '';
  article.querySelector('.source-name').textContent=colorDescription(candidate);
  const note=article.querySelector('.geometry-note');note.textContent=candidate?geometryLabel(candidate,mode):'이 영역의 자료가 준비되지 않았습니다.';
  note.classList.toggle('display-only',candidate?.representation_policy!=='surface_only'&&/gaussian.*cent|sh.?dc/i.test(String(candidate?.geometry_kind||'')));
  const data=candidate?.[mode];
  const count=data ? mode==='mesh'?`${numeric(data.vertex_count)} 정점 · ${numeric(data.triangle_count)} 삼각형`:`${numeric(data.count)} 점` : '';
  article.querySelector('.color-note').textContent=[count,coverageText(candidate),candidate?.representation_policy==='surface_only'?candidate.stage:null].filter(Boolean).join(' · ');
  article.querySelector('.viewport-label').textContent=candidate?.representation_policy==='surface_only'&&!data?'표면 대기':candidate?.status==='available'?(mode==='mesh'?'RGB 표면':'RGB 점'):'기하 대기';
  article.querySelector('pre').textContent=JSON.stringify(candidate?{id:candidate.id,geometry_kind:candidate.geometry_kind,stage:candidate.stage,representation_policy:candidate.representation_policy,color:candidate.color,source:candidate.source,
    integrity:panel.object?(globalThis.crypto?.subtle?'SHA256_AND_BYTES_VERIFIED':'BYTES_VERIFIED_SHA256_API_UNAVAILABLE'):'NOT_LOADED'}:{status:'pending'},null,2);
  const links=article.querySelector('.panel-links');links.replaceChildren();
  for(const link of candidate?.links || []){try{const a=document.createElement('a');a.href=artifactURL(link.url);a.textContent=link.label;a.target='_blank';a.rel='noopener noreferrer';links.append(a);}catch(error){recordError(error,panel.role);}}
}
function updateOptions(panel) {
  const variant=panel.role==='mvs'||panel.role==='geogs'||panel.role==='mvs_geogs';
  panel.select.hidden=!variant;panel.article.querySelector('.candidate-label').hidden=variant;
  if(!variant)return;
  const options=candidatesFor(panel.role),selected=qa.selected[panel.role];
  panel.select.replaceChildren();
  for(const candidate of options){const option=document.createElement('option');option.value=candidate.id;option.textContent=candidate.label+(candidate.status==='available'?'':` · ${statusText[candidate.status]}`);panel.select.append(option);}
  if(!options.length){const option=document.createElement('option');option.textContent='조건 준비 중';option.value='';panel.select.append(option);}
  panel.select.value=selected || '';panel.select.disabled=options.length===0;
}
async function loadPanel(panel,force=false) {
  const candidate=currentCandidate(panel.role),mode=descriptorMode(candidate);
  const surfaceOnly=candidate?.representation_policy==='surface_only';
  const signature=JSON.stringify([region?.id,candidate?.id,candidate?.status,candidate?.[mode],mode,candidate?.representation_policy,surfaceOnly?[candidate.stage,candidate.reason]:null]);
  if(!force&&panel.signature===signature&&qa.panels[panel.role]?.status!=='error'){updatePanelMetadata(panel,candidate,mode);return;}
  panel.signature=signature;const token=++panel.token;clearGeometry(panel);
  updatePanelMetadata(panel,candidate,mode);
  qa.panels[panel.role]={candidate:candidate?.id || null,status:candidate?.status || 'pending',geometry_kind:candidate?.geometry_kind || null,
    representation:mode,representation_policy:candidate?.representation_policy || null,points:candidate?.points?.count || 0,triangles:candidate?.mesh?.triangle_count || 0,color:candidate?.color || null,integrity:'NOT_LOADED',loading:false,drawn:false};
  if(surfaceOnly&&candidate.status!=='failed'&&(candidate.status!=='available'||!candidate.mesh)){
    setPanelStatus(panel,'pending');
    placeholder(panel,candidate.stage || 'RGB 표면 추출 대기',candidate.reason || '실제 RGB 표면 파일이 준비되면 표시합니다.');scheduleRender();return;
  }
  if(!candidate||candidate.status!=='available'){
    setPanelStatus(panel,candidate?.status || 'pending');
    placeholder(panel,candidate?.status==='failed'?'실행 결과를 확인해 주세요.':'아직 표시할 결과가 없습니다.',candidate?.reason || '결과가 준비되면 자동으로 표시합니다. 다른 자료로 대신 채우지 않습니다.');scheduleRender();return;
  }
  if(!candidate[mode]){setPanelStatus(panel,'pending');placeholder(panel,mode==='mesh'?'실제 표면 파일이 없습니다.':'RGB 점 자료가 없습니다.',mode==='mesh'?'표현을 “자동” 또는 “RGB 점”으로 변경하면 제공된 점 자료를 볼 수 있습니다.':'이 후보에는 실제 표면만 제공되었습니다. “자동” 또는 “RGB 표면”을 선택하세요.');scheduleRender();return;}
  setPanelStatus(panel,'loading');placeholder(panel,'기하를 불러오고 있습니다.',candidate.label);scheduleRender();
  try{
    const object=await loadObject(candidate,mode);
    if(token!==panel.token){object?.geometry.dispose();object?.material.dispose();return;}
    panel.object=object;panel.scene.add(object);panel.empty.hidden=true;setPanelStatus(panel,'available');
    qa.panels[panel.role].integrity=globalThis.crypto?.subtle?'SHA256_AND_BYTES_VERIFIED':'BYTES_VERIFIED_SHA256_API_UNAVAILABLE';
    updatePanelMetadata(panel,candidate,mode);scheduleRender();
  }catch(error){if(token!==panel.token)return;setPanelStatus(panel,'error');placeholder(panel,'자료를 표시하지 못했습니다.',String(error.message || error));recordError(error,panel.role);}
}
function frameDescription(value) {
  if(typeof value==='string')return value;
  if(value && typeof value==='object')return [value.crs || value.working || value.name || '공통 지역 좌표',value.units || 'm'].join(' · ');
  return '영역 내 공통 지역 좌표 · m';
}
async function selectRegion(id,preserve=false) {
  if(!manifest)return;
  const next=manifest.regions.find(row=>row.id===id);if(!next)return;
  const changed=activeRegionID!==id;activeRegionID=id;region=next;const token=++updateToken;
  if(changed){for(const panel of panels.values()){panel.token++;clearGeometry(panel);panel.signature=null;}bufferCache.clear();qa.selected={};}
  for(const role of roles){
    if(!qa.selected[role]||!region.candidates.some(candidate=>candidate.id===qa.selected[role]))qa.selected[role]=region.default_candidates?.[role] || candidatesFor(role)[0]?.id || null;
    updateOptions(panels.get(role));
  }
  $('region-select').value=id;document.querySelectorAll('#region-tabs button').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.region===id)));
  qa.region=id;qa.frame=region.frame;qa.bounds=region.bounds;
  $('frame-label').textContent=`${id} · ${frameDescription(region.frame)} · 공통 프레임`;
  if(changed||!preserve)resetCamera();
  const available=region.candidates.filter(row=>row.status==='available').length;
  $('availability').textContent=`${id} 자료 ${available} / ${region.candidates.length} 표시 가능`;
  await Promise.all(roles.map(role=>loadPanel(panels.get(role))));
  if(token!==updateToken)return;
  qa.ready=true;$('loading').hidden=true;scheduleRender();
}
function updateHeader() {
  const run=manifest.run_status || {},completed=Number.isFinite(run.completed)?run.completed:0,total=Number.isFinite(run.total)?run.total:12;
  $('run-progress').textContent=`${completed} / ${total}`;$('progress-fill').style.width=`${Math.max(0,Math.min(100,100*completed/Math.max(total,1)))}%`;
  const state=String(run.queue_status || '상태 확인 중');
  const stateLabels={RUNNING:'학습 진행 중',TRAINING:'학습 진행 중',COMPLETE:'실험 및 후처리 완료',COMPLETED:'완료',FINALIZING:'결과 정리 중',FINALIZE:'결과 정리 중',FAILED:'실행 상태 확인 필요',FAIL:'실행 상태 확인 필요',PAUSED:'대기 중'};
  $('queue-status').textContent=stateLabels[state.toUpperCase()] || state;qa.run_status=run;
  const report=$('final-report');report.hidden=true;
  if(manifest.report){report.href=artifactURL(typeof manifest.report==='string'?manifest.report:manifest.report.url);report.hidden=false;}
  const tabs=$('region-tabs');tabs.replaceChildren();$('region-select').replaceChildren();
  for(const r of manifest.regions){const button=document.createElement('button');button.type='button';button.textContent=r.id;button.dataset.region=r.id;button.setAttribute('aria-pressed',String(r.id===activeRegionID));button.addEventListener('click',()=>selectRegion(r.id));tabs.append(button);const option=document.createElement('option');option.value=r.id;option.textContent=r.id;$('region-select').append(option);}
}
async function refresh() {
  if(refreshBusy)return;refreshBusy=true;$('refresh-now').disabled=true;
  try{
    const response=await fetch(manifestURL,{cache:'no-store'});if(!response.ok)throw Error(`결과 목록을 가져오지 못했습니다: HTTP ${response.status}`);
    const value=await response.json();validateManifest(value);manifest=value;updateHeader();
    const desired=manifest.regions.some(row=>row.id===activeRegionID)?activeRegionID:manifest.regions[0].id;
    await selectRegion(desired,activeRegionID===desired);
    $('error').hidden=true;const checked=new Date();$('refresh-status').textContent=`${checked.toLocaleTimeString('ko-KR',{hour:'2-digit',minute:'2-digit'})} 확인 · 60초마다 갱신`;
    qa.built_at=manifest.built_at;qa.last_refresh=checked.toISOString();
  }catch(error){if(!manifest){qa.ready=false;$('loading').hidden=true;}recordError(error);$('refresh-status').textContent='갱신 대기 · 기존 화면 유지';}
  finally{refreshBusy=false;$('refresh-now').disabled=false;}
}
function toggleFocus(role=null) {
  if(focused===role)role=null;
  if(focused){const old=panels.get(focused);old.article.classList.remove('is-focused');old.article.querySelector('.panel-expand').textContent='확대 ↗';}
  focused=role;qa.focused=role;$('focus-backdrop').hidden=!role;document.body.classList.toggle('focus-open',!!role);
  for(const panel of panels.values())panel.article.inert=!!role&&panel.role!==role;
  for(const id of ['toolbar','page-header','view-info','interpretation','page-footer'])$(id).inert=!!role;
  if(role){restoreFocus=document.activeElement;const panel=panels.get(role);panel.article.classList.add('is-focused');panel.article.querySelector('.panel-expand').textContent='돌아가기 ↙';panel.article.querySelector('.panel-expand').focus();}
  else restoreFocus?.focus?.({preventScroll:true});
  scheduleRender();
}

try{
  roles.forEach(buildPanel);
  $('region-select').addEventListener('change',event=>selectRegion(event.target.value));
  $('representation-select').addEventListener('change',event=>{representation=event.target.value;roles.forEach(role=>loadPanel(panels.get(role),true));});
  $('point-size').addEventListener('input',event=>{pointSize=Number(event.target.value);$('point-size-value').textContent=`${pointSize} px`;for(const panel of panels.values())if(panel.object?.isPoints)panel.object.material.size=pointSize;scheduleRender();});
  document.querySelectorAll('[data-preset]').forEach(button=>button.addEventListener('click',()=>setPreset(button.dataset.preset)));
  $('reset-view').addEventListener('click',resetCamera);$('refresh-now').addEventListener('click',refresh);
  $('focus-backdrop').addEventListener('click',()=>toggleFocus());document.addEventListener('keydown',event=>{if(event.key==='Escape'&&focused)toggleFocus();});
  window.addEventListener('resize',scheduleRender);document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
  qa.refresh=refresh;qa.setRegion=id=>selectRegion(id);qa.resetCamera=resetCamera;qa.verifyBuffers=role=>bufferEvidence(panels.get(role)?.object);
  refresh();setInterval(refresh,60000);
}catch(error){recordError(error);$('loading').hidden=true;}
