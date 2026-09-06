import * as T from './three.module.min.js';

const $=id=>document.getElementById(id), cache=new Map();
let data, arm, angle=-1.1, elevation=1.0, zoom=1, section=false, generation=0;
const panels=['initial','final'].map(id=>{
  const element=$(id), scene=new T.Scene(), camera=new T.OrthographicCamera(-1,1,1,-1,.01,2000);
  scene.background=new T.Color('#202a26');camera.up.set(0,0,1);
  const renderer=new T.WebGLRenderer({antialias:true,preserveDrawingBuffer:true});
  renderer.setPixelRatio(Math.min(devicePixelRatio,2));element.appendChild(renderer.domElement);
  return {id,element,scene,camera,renderer,object:null,block:null};
});

async function block(descriptor){
  if(!descriptor)return null;
  if(!cache.has(descriptor.url))cache.set(descriptor.url,fetch(descriptor.url).then(r=>{if(!r.ok)throw Error(descriptor.url+': '+r.status);return r.json()}));
  return cache.get(descriptor.url);
}
function clear(panel){
  if(panel.object){panel.scene.remove(panel.object);panel.object.geometry.dispose();panel.object.material.dispose();panel.object=null}
}
function selectedRows(b){
  const rows=[];for(let i=0;i<b.count;i++)if(!section||Math.abs(b.xyz[3*i+1]-data.center[1])<=1)rows.push(i);return rows;
}
function makePoints(panel,b){
  const rows=selectedRows(b),p=[],colors=[];
  for(const i of rows){p.push(...b.xyz.slice(i*3,i*3+3).map((x,k)=>x-data.center[k]));colors.push(...(b.rgb?.slice(i*3,i*3+3)||[.65,.8,.7]))}
  const geo=new T.BufferGeometry();geo.setAttribute('position',new T.Float32BufferAttribute(p,3));geo.setAttribute('color',new T.Float32BufferAttribute(colors,3));
  panel.object=new T.Points(geo,new T.PointsMaterial({size:2,sizeAttenuation:false,vertexColors:true}));panel.scene.add(panel.object);
}
function makeGaussians(panel,b){
  const rows=selectedRows(b),positions=new Float32Array(rows.length*18),uv=new Float32Array(rows.length*12),rgb=new Float32Array(rows.length*18),opacity=new Float32Array(rows.length*6);
  const corners=[[-3,-3],[3,-3],[3,3],[-3,-3],[3,3],[-3,3]];
  for(let j=0;j<rows.length;j++){
    const i=rows[j],q=b.quats.slice(4*i,4*i+4),norm=Math.hypot(...q),[w,x,y,z]=q.map(v=>v/norm);
    const u=[1-2*(y*y+z*z),2*(x*y+w*z),2*(x*z-w*y)],v=[2*(x*y-w*z),1-2*(x*x+z*z),2*(y*z+w*x)];
    for(let k=0;k<6;k++){
      const [a,c]=corners[k],vertex=j*6+k;uv[2*vertex]=a;uv[2*vertex+1]=c;opacity[vertex]=b.opacity[i];
      for(let axis=0;axis<3;axis++){
        positions[3*vertex+axis]=b.xyz[3*i+axis]-data.center[axis]+a*b.scales[3*i]*u[axis]+c*b.scales[3*i+1]*v[axis];
        rgb[3*vertex+axis]=b.rgb[3*i+axis];
      }
    }
  }
  const geo=new T.BufferGeometry();geo.setAttribute('position',new T.BufferAttribute(positions,3));geo.setAttribute('uv',new T.BufferAttribute(uv,2));geo.setAttribute('aColor',new T.BufferAttribute(rgb,3));geo.setAttribute('aOpacity',new T.BufferAttribute(opacity,1));
  const mat=new T.ShaderMaterial({transparent:true,depthWrite:false,depthTest:false,side:T.DoubleSide,
    vertexShader:'attribute vec3 aColor;attribute float aOpacity;varying vec2 vKernel;varying vec3 vColor;varying float vOpacity;void main(){vKernel=uv;vColor=aColor;vOpacity=aOpacity;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}',
    fragmentShader:'varying vec2 vKernel;varying vec3 vColor;varying float vOpacity;void main(){float r=dot(vKernel,vKernel);if(r>9.0)discard;float a=min(.99,vOpacity*exp(-.5*r));if(a<.003)discard;gl_FragColor=vec4(vColor,a);}' });
  panel.object=new T.Mesh(geo,mat);panel.object.userData.rows=rows;panel.scene.add(panel.object);
}
function draw(){
  if(!data)return;
  const d=[Math.cos(elevation)*Math.cos(angle),Math.cos(elevation)*Math.sin(angle),Math.sin(elevation)],span=Math.max(data.span,...panels.map(p=>p.fitSpan||0))/zoom;
  for(const p of panels){
    const width=p.element.clientWidth,height=p.element.clientHeight,aspect=width/height;
    const verticalSpan=span*Math.max(1,1/aspect);
    p.renderer.setSize(width,height,false);Object.assign(p.camera,{left:-verticalSpan*aspect/2,right:verticalSpan*aspect/2,top:verticalSpan/2,bottom:-verticalSpan/2});
    p.camera.position.set(...d.map(x=>x*500));p.camera.lookAt(0,0,0);p.camera.updateProjectionMatrix();
    if(p.object?.isMesh){
      const rows=p.object.userData.rows,xyz=p.block.xyz,order=rows.map((i,j)=>[j,d[0]*xyz[3*i]+d[1]*xyz[3*i+1]+d[2]*xyz[3*i+2]]).sort((a,b)=>a[1]-b[1]);
      const indices=new Uint32Array(rows.length*6);for(let j=0;j<order.length;j++)for(let k=0;k<6;k++)indices[6*j+k]=6*order[j][0]+k;
      p.object.geometry.setIndex(new T.BufferAttribute(indices,1));
    }
    p.renderer.render(p.scene,p.camera);
  }
  window.P2_GAUSSIAN_VIEWER_STATE={arm:arm.id,mode:$('mode').value,section,counts:panels.map(p=>p.block?.count||0),meshCounts:panels.map(p=>p.object?.isMesh?p.object.geometry.attributes.position.count/6:0)};
}
async function refresh(){
  const token=++generation;arm=data.arms[Number($('arm').value)];$('error').textContent='';
  try{
    const blocks=await Promise.all(panels.map(p=>block($('mode').value==='source'?arm.source:arm[p.id])));
    if(token!==generation)return;
    for(let k=0;k<panels.length;k++){
      const p=panels[k],b=blocks[k];clear(p);p.block=b;p.fitSpan=0;
      if(b){
        if($('mode').value==='gaussian')makeGaussians(p,b);else makePoints(p,b);
        const geometry=p.object.geometry;geometry.computeBoundingSphere();
        if(geometry.attributes.position.count){
          const sphere=geometry.boundingSphere;
          p.fitSpan=2*(sphere.radius+sphere.center.length())*1.04;
        }
      }
    }
    $('counts').textContent=`${arm.label} · 초기 ${blocks[0]?.count.toLocaleString()||0}개 / 최종 ${blocks[1]?.count.toLocaleString()||0}개 · ${section?'단면 표시':'전체 표시'}`;
    $('metrics').textContent=JSON.stringify(arm.metrics,null,2);
    $('view').replaceChildren(...(arm.images||[]).map((v,i)=>new Option(String(v.image_id),i)));
    photos();draw();window.P2_GAUSSIAN_VIEWER_READY=true;
  }catch(e){$('error').textContent=String(e);throw e}
}
function photos(){
  const view=arm.images?.[Number($('view').value)];$('photos').replaceChildren();
  for(const [key,label] of [['target','현재 사진'],['initial','초기 gsplat 렌더'],['final','학습 후 gsplat 렌더']]){
    if(!view?.[key])continue;const figure=document.createElement('figure'),img=document.createElement('img'),caption=document.createElement('figcaption');img.src=view[key];img.alt=label+' '+view.image_id;caption.textContent=label;figure.append(img,caption);$('photos').append(figure);
  }
}
for(const p of panels){
  let previous;p.element.addEventListener('pointerdown',e=>{previous=[e.clientX,e.clientY];p.element.setPointerCapture(e.pointerId)});
  p.element.addEventListener('pointerup',()=>previous=null);
  p.element.addEventListener('pointermove',e=>{if(!previous)return;angle-=(e.clientX-previous[0])*.008;elevation=Math.max(-1.55,Math.min(1.5707,elevation+(e.clientY-previous[1])*.008));previous=[e.clientX,e.clientY];draw()});
  p.element.addEventListener('wheel',e=>{e.preventDefault();zoom=Math.max(.3,Math.min(50,zoom*Math.exp(-e.deltaY*.001)));draw()},{passive:false});
}
$('arm').addEventListener('change',refresh);$('mode').addEventListener('change',refresh);$('view').addEventListener('change',photos);
$('oblique').onclick=()=>{elevation=1;angle=-1.1;section=false;refresh()};$('top').onclick=()=>{elevation=1.5707;section=false;refresh()};$('section').onclick=()=>{elevation=0;angle=-Math.PI/2;section=true;refresh()};$('reset').onclick=()=>{zoom=1;section=false;refresh()};window.addEventListener('resize',draw);
try{const response=await fetch('inspection.json');if(!response.ok)throw Error('inspection.json '+response.status);data=await response.json();$('arm').replaceChildren(...data.arms.map((a,i)=>new Option(a.label,i)));$('status').textContent=data.description;await refresh()}catch(e){$('error').textContent=String(e)}
