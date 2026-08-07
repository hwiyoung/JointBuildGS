import * as THREE from 'three';

const manifest = await (await fetch('./viewer_manifest.json', {cache:'no-store'})).json();
const summary = document.getElementById('summary');
summary.textContent = `후보 ${manifest.candidate_count} · train ${manifest.local_train_count} · validation ${manifest.local_validation_count} (기존 ${manifest.global_heldout_count} + 추가 ${manifest.added_local_validation_count}) · sparse ${manifest.seed.sparse_count.toLocaleString()} · MVS 비교 ${manifest.seed.mvs_count.toLocaleString()}`;

const viewSelect = document.getElementById('viewSelect');
const roleFilter = document.getElementById('roleFilter');
const table = document.getElementById('table');
let filtered = manifest.views;
let selectedMarker = null;
let selectedArrow = null;

function roleLabel(role){return role==='GLOBAL_HELDOUT_PROTECTED'?'기존 validation':role==='LOCAL_VAL_ADDED'?'추가 validation':'train'}
function refreshOptions(){
  filtered = manifest.views.filter(v => roleFilter.value==='ALL' || v.local_role===roleFilter.value);
  viewSelect.innerHTML = filtered.map(v=>`<option value="${v.index}">${String(v.index).padStart(2,'0')} · ${roleLabel(v.local_role)} · ${v.view_name}</option>`).join('');
  table.innerHTML = filtered.map(v=>`<div data-index="${v.index}"><span>${String(v.index).padStart(2,'0')}</span><span>${v.view_name}</span><span>${roleLabel(v.local_role)}</span><span>az ${v.azimuth_deg.toFixed(1)}°</span><span>nadir ${v.nadir_deg.toFixed(1)}°</span></div>`).join('');
  table.querySelectorAll('[data-index]').forEach(row=>row.onclick=()=>selectView(row.dataset.index));
  if(filtered.length)selectView(filtered[0].index);
}
function selectView(index){
  const value=String(index); const option=[...viewSelect.options].find(item=>item.value===value);
  if(!option){roleFilter.value='ALL';refreshOptions();}
  viewSelect.value=value; showView(); updateSelectedCamera();
}
function showView(){
  const view=manifest.views.find(v=>String(v.index)===String(viewSelect.value)); if(!view)return;
  for(const kind of ['original','sparse','mvs']) document.getElementById(kind).src=view[kind];
  const badge=document.getElementById('roleBadge'); badge.textContent=roleLabel(view.local_role); badge.className=`badge ${view.local_role==='GLOBAL_HELDOUT_PROTECTED'?'eval':view.local_role==='LOCAL_VAL_ADDED'?'added':''}`;
  document.getElementById('meta').textContent=`${view.view_name}\ncrop ${view.crop_xyxy.join(', ')} · coverage ${(100*view.projection_coverage).toFixed(1)}% · area ${(100*view.projected_area_fraction).toFixed(2)}%\nazimuth ${view.azimuth_deg.toFixed(1)}° · nadir ${view.nadir_deg.toFixed(1)}°\nsparse projected ${view.sparse_projected_count.toLocaleString()} · MVS projected ${view.mvs_projected_count.toLocaleString()}`;
}
roleFilter.onchange=refreshOptions; viewSelect.onchange=()=>selectView(viewSelect.value);
document.getElementById('sheets').innerHTML=manifest.contact_sheets.map((path,i)=>`<a href="${path}" target="_blank">contact sheet ${i+1}</a>`).join('');
refreshOptions();

const root=document.getElementById('scene'); const renderer=new THREE.WebGLRenderer({antialias:true}); renderer.setPixelRatio(Math.min(devicePixelRatio,1.5)); root.appendChild(renderer.domElement);
const scene=new THREE.Scene(); scene.background=new THREE.Color(0x03060a); scene.add(new THREE.HemisphereLight(0xffffff,0x243044,1.5));
const camera=new THREE.PerspectiveCamera(45,1,.1,2500); const orbit={target:new THREE.Vector3(0,0,0),distance:150,yaw:-.8,pitch:.7};
function applyCamera(){const c=Math.cos(orbit.pitch);camera.position.set(orbit.target.x+orbit.distance*c*Math.cos(orbit.yaw),orbit.target.y+orbit.distance*c*Math.sin(orbit.yaw),orbit.target.z+orbit.distance*Math.sin(orbit.pitch));camera.up.set(0,0,1);camera.lookAt(orbit.target);camera.updateMatrixWorld();}
async function points(xyzPath,rgbPath,color,size){const xyz=new Float32Array(await(await fetch(xyzPath)).arrayBuffer());const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.BufferAttribute(xyz,3));let material;if(rgbPath){const rgb=new Uint8Array(await(await fetch(rgbPath)).arrayBuffer());g.setAttribute('color',new THREE.BufferAttribute(rgb,3,true));material=new THREE.PointsMaterial({size,sizeAttenuation:false,vertexColors:true});}else material=new THREE.PointsMaterial({color,size,sizeAttenuation:false,transparent:true,opacity:.72});return new THREE.Points(g,material);}
const sparse=await points(manifest.seed.sparse_xyz,manifest.seed.sparse_rgb,'#7dd3fc',1.6);scene.add(sparse);const mvs=await points(manifest.seed.mvs_xyz,null,'#fb923c',1.2);mvs.visible=false;scene.add(mvs);
const linePositions=[];for(const ring of manifest.footprint_rings)for(let i=0;i+1<ring.length;i++)linePositions.push(...ring[i],...ring[i+1]);const fg=new THREE.BufferGeometry();fg.setAttribute('position',new THREE.Float32BufferAttribute(linePositions,3));scene.add(new THREE.LineSegments(fg,new THREE.LineBasicMaterial({color:'#ffe000'})));
const cameraGroup=new THREE.Group();scene.add(cameraGroup);
const cameraPositions=[];const cameraColors=[];const roleColor={GLOBAL_HELDOUT_PROTECTED:new THREE.Color('#f59e0b'),LOCAL_VAL_ADDED:new THREE.Color('#22c55e'),LOCAL_TRAIN:new THREE.Color('#94a3b8')};
for(const v of manifest.views){cameraPositions.push(...v.camera_center);const c=roleColor[v.local_role];cameraColors.push(c.r,c.g,c.b)}
const markerGeometry=new THREE.BufferGeometry();markerGeometry.setAttribute('position',new THREE.Float32BufferAttribute(cameraPositions,3));markerGeometry.setAttribute('color',new THREE.Float32BufferAttribute(cameraColors,3));
const cameraMarkers=new THREE.Points(markerGeometry,new THREE.PointsMaterial({size:8,sizeAttenuation:false,vertexColors:true}));cameraGroup.add(cameraMarkers);
const cameraLines=[];for(const v of manifest.views){const p=new THREE.Vector3(...v.camera_center),f=new THREE.Vector3(...v.camera_forward).normalize(),length=Math.min(16,Math.max(5,p.length()*.07));cameraLines.push(...p.toArray(),...p.clone().addScaledVector(f,length).toArray())}const cg=new THREE.BufferGeometry();cg.setAttribute('position',new THREE.Float32BufferAttribute(cameraLines,3));cameraGroup.add(new THREE.LineSegments(cg,new THREE.LineBasicMaterial({color:'#64748b',transparent:true,opacity:.62})));
selectedMarker=new THREE.Mesh(new THREE.SphereGeometry(2.5,16,10),new THREE.MeshBasicMaterial({color:'#ffe000'}));cameraGroup.add(selectedMarker);
function updateSelectedCamera(){if(!selectedMarker||!viewSelect.value)return;const v=manifest.views.find(row=>String(row.index)===String(viewSelect.value));if(!v)return;selectedMarker.position.set(...v.camera_center);if(selectedArrow)cameraGroup.remove(selectedArrow);const direction=new THREE.Vector3(...v.camera_forward).normalize();selectedArrow=new THREE.ArrowHelper(direction,new THREE.Vector3(...v.camera_center),Math.min(28,Math.max(10,new THREE.Vector3(...v.camera_center).length()*.12)),0xffe000,4,2.5);cameraGroup.add(selectedArrow)}
updateSelectedCamera();
const raycaster=new THREE.Raycaster();raycaster.params.Points.threshold=4;const pointer=new THREE.Vector2();
function pickCamera(event){const rect=renderer.domElement.getBoundingClientRect();pointer.x=((event.clientX-rect.left)/rect.width)*2-1;pointer.y=-((event.clientY-rect.top)/rect.height)*2+1;raycaster.setFromCamera(pointer,camera);const hit=raycaster.intersectObject(cameraMarkers,false)[0];if(hit&&Number.isInteger(hit.index))selectView(manifest.views[hit.index].index)}
let drag=null;renderer.domElement.oncontextmenu=e=>e.preventDefault();renderer.domElement.onpointerdown=e=>{drag={x:e.clientX,y:e.clientY,startX:e.clientX,startY:e.clientY,pan:e.button===2||e.shiftKey};renderer.domElement.setPointerCapture(e.pointerId)};renderer.domElement.onpointermove=e=>{if(!drag)return;const dx=e.clientX-drag.x,dy=e.clientY-drag.y;if(drag.pan){applyCamera();const right=new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld,0),up=new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld,1),scale=orbit.distance*.0016;orbit.target.addScaledVector(right,-dx*scale);orbit.target.addScaledVector(up,dy*scale)}else{orbit.yaw-=dx*.006;orbit.pitch=Math.max(.05,Math.min(1.5,orbit.pitch+dy*.006))}drag.x=e.clientX;drag.y=e.clientY};renderer.domElement.onpointerup=e=>{if(drag&&Math.hypot(e.clientX-drag.startX,e.clientY-drag.startY)<4)pickCamera(e);drag=null};renderer.domElement.onwheel=e=>{e.preventDefault();orbit.distance=Math.max(5,Math.min(1200,orbit.distance*Math.exp(e.deltaY*.001))) };
function resize(){const w=root.clientWidth,h=root.clientHeight;if(renderer.domElement.width!==w||renderer.domElement.height!==h){renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix()}}function animate(){resize();applyCamera();renderer.render(scene,camera);requestAnimationFrame(animate)}animate();
document.getElementById('toggleSparse').onclick=e=>{sparse.visible=!sparse.visible;e.target.textContent=`Sparse ${sparse.visible?'ON':'OFF'}`};document.getElementById('toggleMvs').onclick=e=>{mvs.visible=!mvs.visible;e.target.textContent=`MVS ${mvs.visible?'ON':'OFF'}`};document.getElementById('toggleCameras').onclick=e=>{cameraGroup.visible=!cameraGroup.visible;e.target.textContent=`카메라 ${cameraGroup.visible?'ON':'OFF'}`};document.getElementById('resetView').onclick=()=>Object.assign(orbit,{target:new THREE.Vector3(0,0,0),distance:150,yaw:-.8,pitch:.7});
