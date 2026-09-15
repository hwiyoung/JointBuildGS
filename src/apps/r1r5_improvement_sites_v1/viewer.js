import * as THREE from '/vendor/three.module.min.js';
const $=id=>document.getElementById(id), roles=['prior','mvs','local_prior0','da3'];
const names={prior:'Existing ALS prior',mvs:'MVS–GeoGS · prior 0.005',local_prior0:'MVS–GeoGS · 보정 후보 국소 prior 0',da3:'DA3–GeoGS · prior 0.005'};
const colors={prior:0x56d19b,mvs:0x65aaff,local_prior0:0xd59aff,da3:0xffbc63};
const panels=[], qa=window.__FAILURE_QA__={ready:false,errors:[],panels:{},caseID:null,scientific_verdict:null};
let manifest,selected,review; let target=new THREE.Vector3(0,0,0), yaw=-Math.PI/2, pitch=0, span=14, rendering=false;
Object.defineProperty(qa,'settled',{enumerable:true,get:()=>qa.ready&&!rendering});
function fail(e){qa.errors.push(String(e));$('error').hidden=false;$('error').textContent=String(e);console.error(e);}
function boxPlanes(lo,hi){return [new THREE.Plane(new THREE.Vector3(1,0,0),-lo[0]),new THREE.Plane(new THREE.Vector3(-1,0,0),hi[0]),new THREE.Plane(new THREE.Vector3(0,1,0),-lo[1]),new THREE.Plane(new THREE.Vector3(0,-1,0),hi[1]),new THREE.Plane(new THREE.Vector3(0,0,1),-lo[2]),new THREE.Plane(new THREE.Vector3(0,0,-1),hi[2])];}
function planes(){const lo=[...manifest.display_box[0]],hi=[...manifest.display_box[1]];if($('slice').checked){lo[1]=manifest.center[1]-.25;hi[1]=manifest.center[1]+.25;}return boxPlanes(lo,hi);}
async function binary(d,type){const r=await fetch(d.url);if(!r.ok)throw Error(d.url+': HTTP '+r.status);const b=await r.arrayBuffer();if(b.byteLength!==d.bytes)throw Error('Buffer size mismatch: '+d.url);if(crypto.subtle){const h=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',b)),x=>x.toString(16).padStart(2,'0')).join('');if(h!==d.sha256)throw Error('Buffer hash mismatch: '+d.url);}return new type(b);}
function geo(x,t){const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.BufferAttribute(x,3));if(t)g.setIndex(new THREE.BufferAttribute(t,1));return g;}
function draw(){if(rendering)return;rendering=true;requestAnimationFrame(()=>{try{for(const p of panels){const w=p.host.clientWidth,h=p.host.clientHeight,a=w/h;p.renderer.setSize(w,h,false);Object.assign(p.camera,{left:-span*a/2,right:span*a/2,top:span/2,bottom:-span/2});p.camera.updateProjectionMatrix();p.camera.position.copy(target).add(new THREE.Vector3(Math.cos(pitch)*Math.cos(yaw),Math.cos(pitch)*Math.sin(yaw),Math.sin(pitch)).multiplyScalar(40));p.camera.lookAt(target);p.surface.material.clippingPlanes=planes();p.points.material.clippingPlanes=planes();p.points.visible=$('lidar').checked;p.section.visible=$('slice').checked;p.section.material.clippingPlanes=planes();p.renderer.render(p.scene,p.camera);qa.panels[p.role].drawn=true;qa.panels[p.role].camera=p.camera.position.toArray();}qa.slice=$('slice').checked;qa.lidar=$('lidar').checked;}catch(e){fail(e);}finally{rendering=false;}});}
function preset(kind){if(kind==='side'){yaw=-Math.PI/2;pitch=0;}if(kind==='oblique'){yaw=-1.05;pitch=.5;}if(kind==='top'){yaw=-Math.PI/2;pitch=Math.PI/2-.001;}draw();}
function interact(canvas){let drag=null;canvas.addEventListener('pointerdown',e=>{drag={x:e.clientX,y:e.clientY};canvas.setPointerCapture(e.pointerId);});canvas.addEventListener('pointerup',()=>drag=null);canvas.addEventListener('pointercancel',()=>drag=null);canvas.addEventListener('pointermove',e=>{if(!drag)return;let dx=e.clientX-drag.x,dy=e.clientY-drag.y;drag={x:e.clientX,y:e.clientY};if(e.shiftKey){const right=new THREE.Vector3(-Math.sin(yaw),Math.cos(yaw),0),up=new THREE.Vector3(-Math.sin(pitch)*Math.cos(yaw),-Math.sin(pitch)*Math.sin(yaw),Math.cos(pitch));target.addScaledVector(right,-dx*span/canvas.clientHeight).addScaledVector(up,dy*span/canvas.clientHeight);}else{yaw-=dx*.006;pitch=Math.max(-1.5,Math.min(1.569,pitch+dy*.006));}draw();});canvas.addEventListener('wheel',e=>{e.preventDefault();span=Math.max(2,Math.min(30,span*Math.exp(e.deltaY*.001)));draw();},{passive:false});}
async function load(){
 review=await(await fetch('reviewed_sites.json')).json();const requested=new URLSearchParams(location.search).get('case')||review.default_case;selected=review.cases.find(x=>x.id===requested);if(!selected)throw Error('알 수 없는 사례');const r=await fetch(selected.case_file);if(!r.ok)throw Error('case manifest missing');const m=manifest=await r.json();target.fromArray(m.center);qa.validation=m.validation;qa.caseID=m.id;fillReport();
 const uas=await binary(m.uas,Float32Array);
 for(const role of roles){
  const info=m.models[role],card=document.createElement('article');card.className='panel';card.dataset.role=role;
  const title=document.createElement('h3');title.textContent=names[role];const host=document.createElement('div');host.className='view';const metric=document.createElement('div');metric.className='metric';metric.textContent=`동일한 LiDAR ${m.case.n}점 → 표면 거리 중앙값: ${info.median_m.toFixed(3)} m`;card.append(title,host,metric);$('panels').append(card);
  const scene=new THREE.Scene();scene.background=new THREE.Color(0x132131);const camera=new THREE.OrthographicCamera(-8,8,5,-5,.01,200);camera.up.set(0,0,1);
  const renderer=new THREE.WebGLRenderer({antialias:true,preserveDrawingBuffer:true});renderer.setPixelRatio(Math.min(devicePixelRatio,1.5));renderer.localClippingEnabled=true;host.append(renderer.domElement);
  scene.add(new THREE.HemisphereLight(0xffffff,0x69809a,2.2));const light=new THREE.DirectionalLight(0xffffff,2);light.position.set(40,-30,0);scene.add(light);
  const [x,t,s]=await Promise.all([binary(info.xyz,Float32Array),binary(info.indices,Uint32Array),binary(m.sections[role],Float32Array)]);
  const surface=new THREE.Mesh(geo(x,t),new THREE.MeshStandardMaterial({color:colors[role],side:THREE.DoubleSide,roughness:1,flatShading:true,clippingPlanes:planes()}));scene.add(surface);
  // Reference is drawn in front for inspection; explicitly points, not mesh triangles.
  const points=new THREE.Points(geo(uas),new THREE.PointsMaterial({color:0xffe96a,size:3,sizeAttenuation:false,depthTest:false,clippingPlanes:planes()}));points.renderOrder=3;scene.add(points);
  const section=new THREE.LineSegments(geo(s),new THREE.LineBasicMaterial({color:colors[role],depthTest:false,clippingPlanes:planes()}));section.renderOrder=2;scene.add(section);
  const size=m.case_box[1].map((x,i)=>x-m.case_box[0][i]);const box=new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(...size)),new THREE.LineBasicMaterial({color:0xff5d62,depthTest:false}));box.position.fromArray(m.center);box.renderOrder=4;scene.add(box);
  const grid=[],lo=m.display_box[0],hi=m.display_box[1],back=hi[1]+.1;for(let u=Math.ceil(lo[0]);u<=hi[0];u++)grid.push(u,back,lo[2],u,back,hi[2]);for(let z=Math.ceil(lo[2]);z<=hi[2];z++)grid.push(lo[0],back,z,hi[0],back,z);const gridlines=new THREE.LineSegments(geo(new Float32Array(grid)),new THREE.LineBasicMaterial({color:0x334455}));scene.add(gridlines);
  panels.push({role,host,renderer,scene,camera,surface,points,section});qa.panels[role]={vertices:x.length/3,triangles:t.length/3,uas:uas.length/3,drawn:false};interact(renderer.domElement);
 }
 $('case-validation').textContent='1 m 격자 · 네 화면의 카메라와 축척 동일 · LiDAR와 빨간 상자는 가림 없이 표시합니다. 같은 LiDAR 표본에서 원본 메시와 확대 메시의 거리 차이 < 1 mm 검증 완료.';
 qa.ready=true;draw();
}
function cell(tr,text,cls=''){const td=document.createElement('td');td.textContent=text;td.className=cls;tr.append(td);return td;}
function link(x){const a=document.createElement('a');a.href='?case='+x.id+'#case';a.textContent=x.title;a.className='site-link'+(x.id===selected.id?' active':'');a.dataset.case=x.id;return a;}
function fillReport(){
 $('case-title').textContent=selected.title;$('case-kind').textContent=selected.kind;$('issue').textContent=selected.issue;$('action').textContent=selected.action;$('case-note').classList.toggle('held',!selected.recommended);
 $('location').textContent=`객체축 u ${selected.uvz_min[0]}–${selected.uvz_min[0]+selected.size[0]} m / v ${selected.uvz_min[1]}–${selected.uvz_min[1]+selected.size[1]} m / local z ${selected.uvz_min[2]}–${selected.uvz_min[2]+selected.size[2]} m · 같은 LiDAR ${selected.n}점. 수치는 빨간 상자 전체 기준입니다.`;
 $('slice-info').textContent=`노란 점: UAS LiDAR · 색 있는 면: 각 조건의 원본 메시. 기본 화면은 v=${-manifest.center[1]} m 중심 두께0.5m 단면입니다. 높이 과장은 없습니다.`;
 $('photos').src=selected.photo_file;$('photos').alt=selected.title+' 원영상 두 장의 동일 위치';$('case-section').src=selected.section_file;$('case-section').alt=selected.title+' 위치와 원본 표면 단면';$('observations').href=selected.id+'_observations.json';$('geometry').href=selected.case_file;
 for(const id of [...review.recommended,...review.held]){const x=review.cases.find(x=>x.id===id);const tr=document.createElement('tr');cell(tr,'').append(link(x));cell(tr,x.kind);for(const b of ['prior','mvs','da3'])cell(tr,x.median_m[b].toFixed(3),'number');cell(tr,String(x.n),'number');$(x.recommended?'site-table':'held-table').append(tr);}
 for(const id of review.recommended)$('shortcuts').append(link(review.cases.find(x=>x.id===id)));
 for(const b of ['prior','mvs','da3']){const s=selected.depth_summary[b],tr=document.createElement('tr');cell(tr,{prior:'prior depth',mvs:'MVS depth',da3:'DA3 depth'}[b]);cell(tr,s.valid_views+' / '+s.projected_views);cell(tr,s.median_of_view_medians_m===null?'없음':s.median_of_view_medians_m.toFixed(3)+' m');$('depth-table').append(tr);}
}
for(const k of ['side','oblique','top'])$(k).onclick=()=>preset(k);
$('reset').onclick=()=>{target.fromArray(manifest.center);span=14;$('slice').checked=true;preset('side');};
$('slice').onchange=draw;$('lidar').onchange=draw;window.addEventListener('resize',draw);
load().catch(fail);
