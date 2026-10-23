/* Actual source XYZ, colored with unchanged patch statistics. CPU canvas only. */
'use strict';
window.MG=(()=>{
let A,S,$;
function enabled(){return !!S&&S.geometry==='source'}
function isMvs(side){if(!enabled())return false;const l=A.byId[S[side]],key=DV.key(l,S.data.meta.prior,S.v);return l.id==='missed'||typeof key==='string'&&key.startsWith('mvs_')}
function cloud(){return S.data.clouds[S.v]}
function mapping(){return cloud().mapping[S.data.meta.prior]}
function init(api){
  A=api;S=A.S;$=A.$;S.geometry='source';
  $('viewUnit').parentElement.insertAdjacentHTML('beforebegin','<label>표시 형상<select id="displayGeometry"><option value="source">MVS는 실제 점군</option><option value="legacy">공통 사전 면 / 패치</option></select></label>');
  $('displayGeometry').onchange=()=>{S.geometry=$('displayGeometry').value;S.faceFocus=null;S.patch=null;A.refresh(false,true)};
  for(const side of ['left','right'])document.querySelector('#map'+side).closest('.panel').querySelector('.panelhead').insertAdjacentHTML('afterend',`<div id="geometryLabel${side}" class="geometryLabel"></div>`);
  document.querySelector('.pairbar').insertAdjacentHTML('afterend','<p id="geometryNote" class="geometryNote"></p>');
  document.querySelector('.pairbar .small').textContent='MVS 값과 사전 정보 값을 각각 확인 · 같은 색 범위';
  document.title='불확실도 지도 · v1.2';document.querySelector('.versionbadge').textContent='v1.2';
  document.querySelector('footer span').textContent='PHD-MAIN-UNCERT-VIEW-v1.2 · MVS 실제 점군 · 원본 수치 유지';
}
function label(side){
  if(isMvs(side))return '형상: MVS 실제 점군 · 판 '+(S.v==='a'?'가':'나');
  if(S.unit==='face')return '형상: LoD2 면 / 격자'+(S.data.meta.prior==='ALS'?' · 항공 LiDAR 패치를 면별로 집계':'');
  return '형상: '+(S.data.meta.prior==='ALS'?'항공 LiDAR':'LoD2')+' 사전 패치';
}
function labels(){
  for(const side of ['left','right']){$('geometryLabel'+side).textContent=label(side)+' | 색: '+A.byId[S[side]].label;$('geometryLabel'+side).classList.toggle('mvsGeometry',isMvs(side))}
  $('geometryNote').textContent=enabled()?'MVS 형상은 실제 원본 점입니다. 색은 연결된 패치의 기존 값이며, 점마다 새로 계산한 오차가 아닙니다. 표시용 점만 솎았고 차트는 모든 유효 패치로 계산합니다.':'공통 사전 면 / 패치에 값을 비교하는 기존 보기입니다. 형상이 MVS 점군을 뜻하지 않습니다.';
}
function extendBounds(b){
  if(!enabled()||!S.data?.clouds)return b;
  const g=cloud(),key=S.data.meta.prior+':'+S.scope;
  g.bounds??={};if(!g.bounds[key]){
    const v={...b},xyz=g.xyz,ids=mapping();
    for(let j=0;j<g.n;j++){const i=ids[j];if(i<0||S.scope==='eval'&&!S.z.in_eval[i])continue;
      v.x0=Math.min(v.x0,xyz[j*3]-.25);v.x1=Math.max(v.x1,xyz[j*3]+.25);
      v.y0=Math.min(v.y0,xyz[j*3+1]-.25);v.y1=Math.max(v.y1,xyz[j*3+1]+.25);
      v.z0=Math.min(v.z0,xyz[j*3+2]);v.z1=Math.max(v.z1,xyz[j*3+2]);
    }g.bounds[key]=v;
  }return g.bounds[key];
}
function inScope(i){return i>=0&&(S.scope!=='eval'||S.z.in_eval[i])}
function pointPixel(paint,i){if(paint.flags[i]===1)return S.match[i]?A.packedColor('#b9c2c1'):A.packedColor('#eef1ef');return S.match[i]?paint.normal[i]:paint.faded[i]}
function buildMaps(){
  const start=performance.now();A.buildMaps(true);
  const {w,h,ppu,b}=S.raster,g=cloud(),ids=mapping(),xyz=g.xyz;
  for(const side of ['left','right']){
    A.maps[side].pick=S.pick;A.maps[side].facePick=S.unit==='face';
    if(!isMvs(side))continue;
    const image=new ImageData(w,h),pixels=new Uint32Array(image.data.buffer),depth=new Float32Array(w*h).fill(-Infinity),pick=new Int32Array(w*h).fill(-1);
    pixels.fill(A.packedColor('#f4f5f3'));const l=A.byId[S[side]],rg=A.range(l),paint=A.paints(l,rg);let rendered=0;
    for(let j=0;j<g.n;j++){
      const i=ids[j];if(!inScope(i))continue;
      const x=Math.floor((xyz[j*3]-b.x0)*ppu),y=Math.floor((b.y1-xyz[j*3+1])*ppu),z=xyz[j*3+2];
      if(x<0||y<0||x>=w||y>=h)continue;const pixel=paint.flags[i]===2&&j%11===0?A.packedColor('#172f39'):pointPixel(paint,i);rendered++;
      for(let yy=y;yy<Math.min(y+2,h);yy++)for(let xx=x;xx<Math.min(x+2,w);xx++){const k=yy*w+xx;if(z>=depth[k]){depth[k]=z;pixels[k]=pixel;pick[k]=i}}
    }
    const canvas=document.createElement('canvas');canvas.width=w;canvas.height=h;canvas.getContext('2d').putImageData(image,0,0);
    Object.assign(A.maps[side],{image:canvas,pick,facePick:false,displayedPoints:rendered});
    A.legend(side,l,rg,paint.inapp);const note=$('legend'+side).querySelector('.muted');if(note)note.textContent='회색: 값 없음 · 점무늬: 범위 밖';$('legend'+side).insertAdjacentHTML('beforeend','<span>실제 MVS 점 · 회색: 연결 패치의 값 없음</span>');
  }
  labels();
  if(isMvs('left')||isMvs('right')){
    const count=A.maps[isMvs('left')?'left':'right'].displayedPoints;
    $('pairNumbers').textContent='MVS 실제 점 '+A.int(count)+'개 표시 · 색은 패치 값 · 표시 점 수로 통계를 다시 세지 않음';
    $('faceCoverage').textContent='MVS의 불확실도·실제 오차는 MVS 점군에 표시합니다. 사전 정보 층은 위에 적힌 사전 형상에 표시합니다. 원래 패치 구역은 사전 정보에서 정의되었으며, 점과 값의 연결은 해당 MVS 안쪽 원·면 띠 조건을 따릅니다.';
  }
  S.lastMapMs=performance.now()-start;A.drawAll();
}
function anchor(side,i){
  if(!isMvs(side))return [S.z.centre[i*3],S.z.centre[i*3+1],S.z.centre[i*3+2]];
  const g=cloud(),prior=S.data.meta.prior;g.anchor??={};
  if(!g.anchor[prior]){const a=new Int32Array(S.data.n).fill(-1),ids=mapping();for(let j=0;j<g.n;j++)if(ids[j]>=0&&a[ids[j]]<0)a[ids[j]]=j;g.anchor[prior]=a}
  const j=g.anchor[prior][i];return j<0?null:[g.xyz[j*3],g.xyz[j*3+1],g.xyz[j*3+2]];
}
function selected(side,poly,inside){
  if(!isMvs(side))return null;const g=cloud(),ids=mapping(),found=new Set();
  for(let j=0;j<g.n;j++){const i=ids[j];if(inScope(i)&&S.match[i]&&inside([g.xyz[j*3],g.xyz[j*3+1]],poly))found.add(i)}
  return [...found].sort((a,b)=>a-b);
}
function drawOrbit(){
  const side=S.orbitSide||'left';if(!isMvs(side))return false;
  const canvas=$('oblique'),[w,h]=A.canvasSize(canvas),ctx=canvas.getContext('2d'),b=S.bounds,g=cloud(),ids=mapping(),xyz=g.xyz;
  const {yaw,tilt,zoom}=S.orbit,scale=Math.min((w-30)/(b.x1-b.x0),(h-30)/Math.max(b.y1-b.y0,b.z1-b.z0))*zoom;
  const cy=Math.cos(yaw),sy=Math.sin(yaw),ct=Math.cos(tilt),st=Math.sin(tilt),cx=(b.x0+b.x1)/2,yy=(b.y0+b.y1)/2,cz=(b.z0+b.z1)/2;
  const image=new ImageData(w,h),pixels=new Uint32Array(image.data.buffer),depth=new Float32Array(w*h).fill(Infinity),pick=new Int32Array(w*h).fill(-1);
  pixels.fill(A.packedColor('#f5f7f5'));const l=A.byId[S[side]],paint=A.paints(l,A.range(l));
  let rendered=0;
  for(let j=0;j<g.n;j++){
    const i=ids[j];if(!inScope(i)||$('wallonly').checked&&S.z.roof_like[i])continue;
    const x=xyz[j*3]-cx,y=xyz[j*3+1]-yy,z=xyz[j*3+2]-cz,rx=cy*x-sy*y,ry=sy*x+cy*y;
    const px=Math.round(w/2+rx*scale),py=Math.round(h/2-(ry*st+z*ct)*scale),d=ry*ct-z*st;
    if(px<0||px>=w||py<0||py>=h)continue;rendered++;const pixel=paint.flags[i]===2&&j%11===0?A.packedColor('#172f39'):pointPixel(paint,i);
    for(let y1=py;y1<Math.min(py+2,h);y1++)for(let x1=px;x1<Math.min(px+2,w);x1++){const k=y1*w+x1;if(d<=depth[k]){depth[k]=d;pixels[k]=pixel;pick[k]=i}}
  }
  ctx.putImageData(image,0,0);ctx.fillStyle='#315965';ctx.font='10px system-ui';ctx.fillText('MVS 실제 점군 · '+l.label+' · '+A.int(rendered)+'점',12,h-12);
  S.mvsOrbitPick={w,h,pick};S.orbitPoints=[];S.orbitTriangles=[];return true;
}
function pickOrbit(x,y){const o=S.mvsOrbitPick;if(!o)return -1;x=Math.round(x);y=Math.round(y);for(let d=0;d<=4;d++)for(let dy=-d;dy<=d;dy++)for(let dx=-d;dx<=d;dx++){const xx=x+dx,yy=y+dy;if(xx>=0&&xx<o.w&&yy>=0&&yy<o.h){const i=o.pick[yy*o.w+xx];if(i>=0)return i}}return -1}
return {init,enabled,isMvs,label,labels,extendBounds,buildMaps,anchor,selected,drawOrbit,pickOrbit};
})();
