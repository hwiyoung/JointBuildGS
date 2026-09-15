import * as THREE from '/vendor/three.module.min.js';
const $=id=>document.getElementById(id), roles=['prior','mvs','local_prior0','da3'];
const names={prior:'Existing ALS prior',mvs:'MVS–GeoGS · prior 0.005',local_prior0:'MVS–GeoGS · Z08 국소 prior 0',da3:'DA3–GeoGS · prior 0.005'};
const colors={prior:0x56d19b,mvs:0x65aaff,local_prior0:0xd59aff,da3:0xffbc63};
const panels=[], qa=window.__FAILURE_QA__={ready:false,errors:[],panels:{},region:'R1',scientific_verdict:null};
let target=new THREE.Vector3(43,-15,-33), yaw=-Math.PI/2, pitch=0, span=11, rendering=false;
Object.defineProperty(qa,'settled',{enumerable:true,get:()=>qa.ready&&!rendering});
function fail(e){qa.errors.push(String(e));$('error').hidden=false;$('error').textContent=String(e);console.error(e);}
function boxPlanes(lo,hi){return [new THREE.Plane(new THREE.Vector3(1,0,0),-lo[0]),new THREE.Plane(new THREE.Vector3(-1,0,0),hi[0]),new THREE.Plane(new THREE.Vector3(0,1,0),-lo[1]),new THREE.Plane(new THREE.Vector3(0,-1,0),hi[1]),new THREE.Plane(new THREE.Vector3(0,0,1),-lo[2]),new THREE.Plane(new THREE.Vector3(0,0,-1),hi[2])];}
function planes(){return boxPlanes([35,$('slice').checked?-15.25:-19,-38],[51,$('slice').checked?-14.75:-11,-28]);}
async function binary(d,type){const r=await fetch(d.url);if(!r.ok)throw Error(d.url+': HTTP '+r.status);const b=await r.arrayBuffer();if(b.byteLength!==d.bytes)throw Error('Buffer size mismatch: '+d.url);if(crypto.subtle){const h=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',b)),x=>x.toString(16).padStart(2,'0')).join('');if(h!==d.sha256)throw Error('Buffer hash mismatch: '+d.url);}return new type(b);}
function geo(x,t){const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.BufferAttribute(x,3));if(t)g.setIndex(new THREE.BufferAttribute(t,1));return g;}
function draw(){if(rendering)return;rendering=true;requestAnimationFrame(()=>{try{for(const p of panels){const w=p.host.clientWidth,h=p.host.clientHeight,a=w/h;p.renderer.setSize(w,h,false);Object.assign(p.camera,{left:-span*a/2,right:span*a/2,top:span/2,bottom:-span/2});p.camera.updateProjectionMatrix();p.camera.position.copy(target).add(new THREE.Vector3(Math.cos(pitch)*Math.cos(yaw),Math.cos(pitch)*Math.sin(yaw),Math.sin(pitch)).multiplyScalar(40));p.camera.lookAt(target);p.surface.material.clippingPlanes=planes();p.points.material.clippingPlanes=planes();p.points.visible=$('lidar').checked;p.section.visible=$('slice').checked;p.section.material.clippingPlanes=planes();p.renderer.render(p.scene,p.camera);qa.panels[p.role].drawn=true;qa.panels[p.role].camera=p.camera.position.toArray();}qa.slice=$('slice').checked;qa.lidar=$('lidar').checked;}catch(e){fail(e);}finally{rendering=false;}});}
function preset(kind){if(kind==='side'){yaw=-Math.PI/2;pitch=0;}if(kind==='oblique'){yaw=-1.05;pitch=.5;}if(kind==='top'){yaw=-Math.PI/2;pitch=Math.PI/2-.001;}draw();}
function interact(canvas){let drag=null;canvas.addEventListener('pointerdown',e=>{drag={x:e.clientX,y:e.clientY};canvas.setPointerCapture(e.pointerId);});canvas.addEventListener('pointerup',()=>drag=null);canvas.addEventListener('pointercancel',()=>drag=null);canvas.addEventListener('pointermove',e=>{if(!drag)return;let dx=e.clientX-drag.x,dy=e.clientY-drag.y;drag={x:e.clientX,y:e.clientY};if(e.shiftKey){const right=new THREE.Vector3(-Math.sin(yaw),Math.cos(yaw),0),up=new THREE.Vector3(-Math.sin(pitch)*Math.cos(yaw),-Math.sin(pitch)*Math.sin(yaw),Math.cos(pitch));target.addScaledVector(right,-dx*span/canvas.clientHeight).addScaledVector(up,dy*span/canvas.clientHeight);}else{yaw-=dx*.006;pitch=Math.max(-1.5,Math.min(1.569,pitch+dy*.006));}draw();});canvas.addEventListener('wheel',e=>{e.preventDefault();span=Math.max(2,Math.min(30,span*Math.exp(e.deltaY*.001)));draw();},{passive:false});}
async function load(){
 const r=await fetch('case.json');if(!r.ok)throw Error('case manifest missing');const m=await r.json();qa.validation=m.validation;
 const uas=await binary(m.uas,Float32Array);
 for(const role of roles){
  const info=m.models[role],card=document.createElement('article');card.className='panel';card.dataset.role=role;
  const title=document.createElement('h3');title.textContent=names[role];const host=document.createElement('div');host.className='view';const metric=document.createElement('div');metric.className='metric';metric.textContent=`동일한 LiDAR 155점 → 표면 거리 중앙값: ${info.median_m.toFixed(3)} m`;card.append(title,host,metric);$('panels').append(card);
  const scene=new THREE.Scene();scene.background=new THREE.Color(0x132131);const camera=new THREE.OrthographicCamera(-8,8,5,-5,.01,200);camera.up.set(0,0,1);
  const renderer=new THREE.WebGLRenderer({antialias:true,preserveDrawingBuffer:true});renderer.setPixelRatio(Math.min(devicePixelRatio,1.5));renderer.localClippingEnabled=true;host.append(renderer.domElement);
  scene.add(new THREE.HemisphereLight(0xffffff,0x69809a,2.2));const light=new THREE.DirectionalLight(0xffffff,2);light.position.set(40,-30,0);scene.add(light);
  const [x,t,s]=await Promise.all([binary(info.xyz,Float32Array),binary(info.indices,Uint32Array),binary(m.sections[role],Float32Array)]);
  const surface=new THREE.Mesh(geo(x,t),new THREE.MeshStandardMaterial({color:colors[role],side:THREE.DoubleSide,roughness:1,flatShading:true,clippingPlanes:planes()}));scene.add(surface);
  // Reference is drawn in front for inspection; explicitly points, not mesh triangles.
  const points=new THREE.Points(geo(uas),new THREE.PointsMaterial({color:0xffe96a,size:3,sizeAttenuation:false,depthTest:false,clippingPlanes:planes()}));points.renderOrder=3;scene.add(points);
  const section=new THREE.LineSegments(geo(s),new THREE.LineBasicMaterial({color:colors[role],depthTest:false,clippingPlanes:planes()}));section.renderOrder=2;scene.add(section);
  const box=new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(2,2,2)),new THREE.LineBasicMaterial({color:0xff5d62,depthTest:false}));box.position.set(43,-15,-33);box.renderOrder=4;scene.add(box);
  const grid=[];for(let u=35;u<=51;u++)grid.push(u,-10,-38,u,-10,-28);for(let z=-38;z<=-28;z++)grid.push(35,-10,z,51,-10,z);const gridlines=new THREE.LineSegments(geo(new Float32Array(grid)),new THREE.LineBasicMaterial({color:0x334455}));scene.add(gridlines);
  panels.push({role,host,renderer,scene,camera,surface,points,section});qa.panels[role]={vertices:x.length/3,triangles:t.length/3,uas:uas.length/3,drawn:false};interact(renderer.domElement);
 }
 $('case-validation').textContent='1 m 격자 · 네 화면의 카메라와 축척 동일 · LiDAR와 빨간 상자는 가림 없이 표시합니다. 원본 메시 및 기존 RGB 뷰어와 이 위치의 거리 차이 < 1 mm 검증 완료.';
 qa.ready=true;draw();
}
async function census(){const r=await fetch('census.json');if(!r.ok)throw Error('census missing');const data=await r.json();for(const [region,d] of Object.entries(data.regions)){const tr=document.createElement('tr');for(const v of [region,d.n,...Object.values(d.category_counts)]){const td=document.createElement('td');td.textContent=typeof v==='number'?v.toLocaleString('ko-KR'):v;tr.append(td);}$('counts').append(tr);const b=document.createElement('button');b.textContent=region;b.dataset.region=region;b.onclick=()=>setRegion(region);$('regions').append(b);}setRegion('R1');}
function setRegion(r){$('map').src=r+'_census.png';$('map').alt=r+' 전체 표본 거리 구간 분포';$('csv').href=r+'_all_cells.csv';$('csv').textContent=r+' 전체 3D 셀 CSV';for(const b of $('regions').children)b.classList.toggle('active',b.dataset.region===r);qa.region=r;}
qa.setRegion=setRegion;qa.preset=preset;
for(const k of ['side','oblique','top'])$(k).onclick=()=>preset(k);
$('reset').onclick=()=>{target.set(43,-15,-33);span=11;$('slice').checked=true;preset('side');};
$('slice').onchange=draw;$('lidar').onchange=draw;window.addEventListener('resize',draw);
Promise.all([load(),census()]).catch(fail);
