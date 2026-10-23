'use strict';
window.V11=(()=>{
let A,S,$,timer,token=0,lastSignature='',lastFacesKey='';
const finite=Number.isFinite, colors={mvs:'#168b91',prior:'#c17b36'};
const name=s=>s==='mvs'?'MVS':'사전 정보';
function filters(){return {v:S.v,r:S.r,scope:S.scope,cell:$('cell').value,shape:$('shape').value,roof:$('roof').value,status:$('status').value,flag:$('flag').value,left:S.left,range:$('enableRange').checked?[Number($('filterlow').value),Number($('filterhigh').value)]:null}}
function init(api){
  A=api;S=A.S;$=A.$;S.unit='face';S.pair='mvs';S.left='mvs_u';S.right='mvs_e';S.orbitSide='left';
  document.title='불확실도 지도 · v1.1';document.querySelector('h1').insertAdjacentHTML('beforeend',' <span class="versionbadge">v1.1</span>');
  $('scope').parentElement.insertAdjacentHTML('afterend','<label>보는 단위<select id="viewUnit"><option value="patch">패치</option><option value="face" selected>면</option></select></label>');
  document.querySelector('.maptools').insertAdjacentHTML('beforebegin',`<section id="judgement" class="panel judgement"><div class="panelhead"><h2>판정 그림</h2><span class="recount">참값 점검용</span><span class="recount">화면에서 다시 셈</span></div><div class="judgecontrols"><div class="segmented"><button id="judgeCurrent" class="active">지금 경우</button><button id="judgePool">세 지역 합</button></div><label class="check"><input type="checkbox" id="judgeExclude">크게 틀린 곳 빼기</label><label id="judgeDetailWrap" hidden><input type="checkbox" id="judgeDetail">지역 · 지붕 형태마다</label><button id="chartReset" class="textbtn" hidden>점 선택 해제</button></div><p id="judgeScope" class="small muted"></p><div class="judgeplots"><article><h3>불확실도 구간별 실제 오차 <span class="small muted">기존 보정 그림</span></h3><div id="calibration"></div></article><article><h3>불확실도가 큰 곳을 뺀 뒤의 오차 <span class="small muted">희소화 곡선</span></h3><div id="sparsification"></div></article></div><p id="judgeWarning" class="small warning" hidden></p><p id="judgeSelection" class="small"></p><details id="calibrationDetails"><summary>보정 그림 표 · 화면에서 다시 셈</summary><div id="calibrationTable" class="tableScroll"></div></details></section><section class="pairbar"><div class="segmented">${U11.C.pairs.map(p=>`<button data-pair="${p.id}" class="${p.id==='mvs'?'active':''}">${p.label}</button>`).join('')}</div><span class="small muted">면으로 보기 · 색 범위 함께 변경</span></section>`);
  document.querySelector('.maps').insertAdjacentHTML('afterend','<div id="pairNumbers" class="pairnumbers"></div><div id="faceCoverage" class="small muted"></div>');
  document.querySelector('.oblique .panelhead').insertAdjacentHTML('beforeend','<label>층<select id="orbitSide"><option value="left">왼쪽 칸</option><option value="right">오른쪽 칸</option></select></label>');
  document.querySelector('.oblique > p').textContent='끌어서 회전 · 휠로 확대 · 눌러 확인';
  $('viewUnit').onchange=()=>{S.unit=$('viewUnit').value;A.buildMaps();A.drawOrbit();if(S.unit==='patch')$('card').innerHTML='<p class="small">패치를 누르면 원래 값을 확인합니다.</p>'};
  $('orbitSide').onchange=()=>{S.orbitSide=$('orbitSide').value;A.drawOrbit()};
  document.querySelectorAll('[data-pair]').forEach(b=>b.onclick=()=>setPair(b.dataset.pair));
  $('judgeCurrent').onclick=()=>{S.judgePool=false;S.chartGate=null;A.refresh();schedule(true)};
  $('judgePool').onclick=()=>{S.judgePool=true;S.chartGate=null;A.refresh();schedule(true)};
  $('judgeExclude').onchange=()=>{S.judgeExclude=$('judgeExclude').checked;schedule(true)};
  $('judgeDetail').onchange=()=>{S.judgeDetail=$('judgeDetail').checked;schedule(true)};
  $('chartReset').onclick=()=>{S.chartGate=null;$('judgeSelection').textContent='';$('chartReset').hidden=true;A.refresh()};
  new ResizeObserver(()=>{if(S.judgement)renderJudgement(S.judgement)}).observe($('judgement'));
}
function setPair(id){const p=U11.C.pairs.find(p=>p.id===id);S.pair=id;S.unit='face';S.left=p.left;S.right=p.right;S.ranges[p.left]=[0,50];S.ranges[p.right]=[0,50];$('viewUnit').value='face';$('layerleft').value=p.left;$('layerright').value=p.right;A.clearQuestion();S.q=0;S.chartGate=null;A.resetRangeFilter();A.refresh();document.querySelectorAll('[data-pair]').forEach(b=>b.classList.toggle('active',b.dataset.pair===id))}
function prepareFaces(){
  if(!S.data?.faces)return;
  S.faceRows=U11.faceValues(S.data,S.z,S.match,A.byId[S.left],A.byId[S.right],S.v);
  S.faceByIndex=new Map(S.faceRows.map(f=>[f.index,f]));S.faceStats=U11.pairStats(S.faceRows);
  const p=S.faceStats;
  $('pairNumbers').innerHTML=`<span class="recount">화면에서 다시 셈</span> 면 ${A.int(p.n)}개 · 순위 상관 ${p.rho===null?'없음':A.fmt(p.rho,3)} · 오른쪽 ÷ 왼쪽 중앙값 ${p.median_right_over_left===null?'없음':A.fmt(p.median_right_over_left,3)} <span class="small muted">두 층 표본이 충분한 LoD2 면 · 격자 제외</span>`;
  const ids=Array.from(S.match,(v,i)=>v?i:-1).filter(i=>i>=0),grid=ids.filter(i=>S.data.faces.items[S.data.faces.assignment[i]].grid).length;
  $('faceCoverage').textContent=`화면에서 다시 셈 · 지금 범위의 면 연결 ${A.int(ids.length-grid)} / ${A.int(ids.length)} 패치 (${A.fmt(ids.length?100*(ids.length-grid)/ids.length:0)} %) · 격자 ${A.int(grid)} 패치 · 표본 부족 면 ${S.faceRows.filter(f=>!f.face.grid&&(f.left.insufficient||f.right.insufficient)).length}개. 판정 그림은 항상 패치로 셈.`;
  document.querySelectorAll('[data-pair]').forEach(b=>b.classList.toggle('active',b.dataset.pair===S.pair));
}
function faceLayer(layer){return layer.id==='missed'?{...layer,kind:'continuous',unit:'%',range:[0,100]}:layer}
function faceStyle(f,side){const l=faceLayer(A.byId[S[side]]),v=f[side].value,rg=A.range(l);return {l,rg,fill:v===null?'#edf0ee':A.color(l,v,rg),hatch:f[side].insufficient}}
function path(ctx,triangles,project){ctx.beginPath();for(const t of triangles){t.forEach((v,i)=>{const p=project(v);i?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1])});ctx.closePath()}}
function hatch(ctx,w,h){ctx.save();ctx.clip();ctx.strokeStyle='#485f7775';ctx.lineWidth=1;ctx.beginPath();for(let x=-h;x<w;x+=9){ctx.moveTo(x,0);ctx.lineTo(x+h,h)}ctx.stroke();ctx.restore()}
function buildMaps(){
  const started=performance.now(),b=A.bounds();S.bounds=b;
  const ppu=Math.min(12,2800/Math.max(b.x1-b.x0,b.y1-b.y0)),w=Math.ceil((b.x1-b.x0)*ppu),h=Math.ceil((b.y1-b.y0)*ppu);S.raster={w,h,ppu,b};
  const project=v=>[(v[0]-b.x0)*ppu,(b.y1-v[1])*ppu];
  const rows=S.faceRows.slice().sort((a,b)=>meanZ(a.face)-meanZ(b.face));
  const pick=document.createElement('canvas');pick.width=w;pick.height=h;const pc=pick.getContext('2d',{willReadFrequently:true});
  for(const side of ['left','right']){
    const c=document.createElement('canvas');c.width=w;c.height=h;const ctx=c.getContext('2d');ctx.fillStyle='#f4f5f3';ctx.fillRect(0,0,w,h);
    for(const f of rows){const sty=faceStyle(f,side);path(ctx,f.face.triangles,project);ctx.fillStyle=sty.fill;ctx.fill();if(sty.hatch)hatch(ctx,w,h);
      // Surface boundaries, without the internal triangulation edges.
      ctx.beginPath();for(const e of edges(f.face)){const a=project(e[0]),b=project(e[1]);ctx.moveTo(...a);ctx.lineTo(...b)}ctx.strokeStyle='#183b4545';ctx.lineWidth=.6;ctx.stroke();
      if(side==='left'){path(pc,f.face.triangles,project);const n=f.index+1;pc.fillStyle=`rgb(${n&255},${n>>8&255},${n>>16&255})`;pc.fill()}
    }
    A.maps[side].image=c;const l=faceLayer(A.byId[S[side]]);A.legend(side,l,A.range(l),false);$('legend'+side).insertAdjacentHTML('beforeend','<span>빗금: 표본 부족</span>');
  }
  const pixels=pc.getImageData(0,0,w,h).data;S.pick=new Int32Array(w*h).fill(-1);for(let j=0;j<S.pick.length;j++){const fi=(pixels[j*4]|pixels[j*4+1]<<8|pixels[j*4+2]<<16)-1;if(pixels[j*4+3]===255&&S.faceByIndex.has(fi))S.pick[j]=S.faceByIndex.get(fi).ids[0]}
  S.rasterKey=null;S.lastMapMs=performance.now()-started;A.drawAll();
}
function meanZ(f){if(f._z!==undefined)return f._z;return f._z=f.triangles.flat().reduce((s,p)=>s+p[2],0)/(f.triangles.length*3)}
function edges(f){if(f._edges)return f._edges;const m=new Map();for(const t of f.triangles)for(let i=0;i<3;i++){const a=t[i],b=t[(i+1)%3],key=[a.join(','),b.join(',')].sort().join('|');if(m.has(key))m.delete(key);else m.set(key,[a,b])}return f._edges=[...m.values()]}
function faceText(f){
  const fields=['left','right'].map(side=>{const x=f[side],l=A.byId[S[side]];return `<div><b>${l.group==='참값 점검용'?'참값 점검용: ':''}${A.esc(l.label)}</b><br>${l.kind==='category'&&l.id!=='missed'?(x.value===null?'없음':A.esc(A.category(l,x.value)))+' · 가장 많은 것 '+A.fmt(x.majority_share*100)+' %':(l.id==='missed'?'넓이 비율 ':'중앙값 ')+A.fmt(x.value)+' '+(l.id==='missed'?'%':l.unit)}${l.kind!=='category'?'<br>25·75 %: '+A.fmt(x.p25)+' · '+A.fmt(x.p75)+' '+l.unit:''}<br>값 있음 ${A.int(x.n)} / ${A.int(x.total)} (${A.fmt(x.valid_fraction*100)} %) ${x.insufficient?'· 표본 부족':''}</div>`}).join('');
  const shape=f.face.grid?'격자':f.face.kind===1?'지붕꼴':'벽꼴',rt=f.face.roof_type;
  return `<h3>${f.face.grid?'2 m 격자':'LoD2 면'} ${A.esc(f.face.id)}</h3><p>${A.int(f.ids.length)} 패치 · 패치 넓이 ${A.fmt(f.left.area_m2)} m²<br>면 넓이 ${A.fmt(f.face.area_m2)} m² · ${shape}<br>지붕 형태 ${rt?A.esc(rt+' '+(DV.M.roof_types[rt]||'')):'없음'}</p><span class="recount">화면에서 다시 셈</span>${fields}`;
}
function tooltip(i,e){const f=S.faceByIndex.get(S.data.faces.assignment[i]);if(!f)return;$('tooltip').innerHTML=faceText(f);$('tooltip').style.cssText=`display:block;left:${Math.min(innerWidth-340,e.clientX+15)}px;top:${Math.max(8,Math.min(innerHeight-370,e.clientY+15))}px`}
function showFace(index){const f=S.faceByIndex.get(index);if(!f)return;S.faceFocus=index;S.patch=null;S.section=null;$('sectionbox').hidden=true;$('card').innerHTML='<div class="facecard">'+faceText(f)+'<button id="faceToPatch">이 면의 패치 보기</button><p class="small muted">유리 채광창처럼 면보다 작은 곳은 패치로 확인합니다.</p></div>';$('faceToPatch').onclick=()=>{S.unit='patch';$('viewUnit').value='patch';S.selected=f.ids;S.place=f.ids;A.buildMaps();zoomIds(f.ids);A.recount();A.drawOrbit();A.choose(f.ids[0])};A.drawAll()}
function zoomIds(ids){let lo=[Infinity,Infinity],hi=[-Infinity,-Infinity];for(const i of ids)for(let k=0;k<2;k++){const x=S.z.centre[i*3+k];lo[k]=Math.min(lo[k],x);hi[k]=Math.max(hi[k],x)}const [w,h]=A.canvasSize(A.maps.left.canvas);S.camera={x:(lo[0]+hi[0])/2,y:(lo[1]+hi[1])/2,scale:Math.min((w-60)/Math.max(2,hi[0]-lo[0]),(h-60)/Math.max(2,hi[1]-lo[1]))};A.drawAll()}
function overlays(ctx,canvas){
  const wanted=['glass_strip','glass_dome','flat_roof','b173_wing','r1_step_roof'];
  ctx.font='11px system-ui';ctx.lineWidth=1.5;
  for(const place of S.data.places){if(!wanted.includes(place.id)||!place.indices.length)continue;if(!place.box){const xs=place.indices.map(i=>S.z.centre[i*3]),ys=place.indices.map(i=>S.z.centre[i*3+1]);place.box=[Math.min(...xs),Math.min(...ys),Math.max(...xs),Math.max(...ys)]}
    const [x0,y0,x1,y1]=place.box,a=A.screen(x0,y1,canvas),b=A.screen(x1,y0,canvas);if(b[0]<0||a[0]>canvas.width||b[1]<0||a[1]>canvas.height)continue;
    ctx.strokeStyle='#f8b83a';ctx.setLineDash([5,3]);ctx.strokeRect(a[0]-2,a[1]-2,b[0]-a[0]+4,b[1]-a[1]+4);ctx.setLineDash([]);const label=place.label.replace('B173 주변 ','');const x=Math.max(3,Math.min(canvas.width-110,a[0])),y=Math.max(17,Math.min(canvas.height-8,a[1]-5));ctx.fillStyle='#fffffff0';ctx.fillRect(x-2,y-12,ctx.measureText(label).width+7,16);ctx.fillStyle='#513a14';ctx.fillText(label,x,y);
  }
  if(S.unit==='face'&&S.faceFocus!==null&&!window.MG?.isMvs(canvas.id==='mapright'?'right':'left')){const f=S.faceByIndex.get(S.faceFocus);if(f){path(ctx,f.face.triangles,p=>A.screen(p[0],p[1],canvas));ctx.strokeStyle='#e05c32';ctx.lineWidth=2;ctx.stroke()}}
}
function drawOrbit(){
  const canvas=$('oblique'),[w,h]=A.canvasSize(canvas),ctx=canvas.getContext('2d'),b=S.bounds,side=S.orbitSide||'left';ctx.fillStyle='#f5f7f5';ctx.fillRect(0,0,w,h);
  const {yaw,tilt,zoom}=S.orbit,scale=Math.min((w-30)/(b.x1-b.x0),(h-30)/Math.max(b.y1-b.y0,b.z1-b.z0))*zoom;
  const proj=p=>{const x=p[0]-(b.x0+b.x1)/2,y=p[1]-(b.y0+b.y1)/2,z=p[2]-(b.z0+b.z1)/2,rx=Math.cos(yaw)*x-Math.sin(yaw)*y,ry=Math.sin(yaw)*x+Math.cos(yaw)*y;return [w/2+rx*scale,h/2-(ry*Math.sin(tilt)+z*Math.cos(tilt))*scale,ry*Math.cos(tilt)-z*Math.sin(tilt)]};
  const tris=[];S.orbitPoints=[];
  for(const f of S.faceRows){if($('wallonly').checked&&f.face.kind!==2)continue;for(const t of f.face.triangles){const p=t.map(proj);tris.push({f,p,depth:p.reduce((s,p)=>s+p[2],0)/3})}const i=f.ids[0],p=proj([S.z.centre[i*3],S.z.centre[i*3+1],S.z.centre[i*3+2]]);S.orbitPoints.push([i,...p,scale])}
  tris.sort((a,b)=>b.depth-a.depth);S.orbitTriangles=tris;
  for(const t of tris){const sty=faceStyle(t.f,side);path(ctx,[t.p],p=>p);ctx.fillStyle=sty.fill;ctx.fill();if(sty.hatch){hatch(ctx,w,h);path(ctx,[t.p],p=>p)}ctx.strokeStyle='#29434d30';ctx.lineWidth=.3;ctx.stroke()}
  ctx.fillStyle='#46606a';ctx.font='11px system-ui';ctx.fillText((side==='left'?'왼쪽':'오른쪽')+' · '+A.byId[S[side]].label+' · LoD2 면 / 격자',12,h-12);
}
function pickOrbit(x,y){for(let k=(S.orbitTriangles?.length||0)-1;k>=0;k--){const t=S.orbitTriangles[k],p=t.p;let positive=false,negative=false;for(let j=0;j<3;j++){const a=p[j],b=p[(j+1)%3],cross=(b[0]-a[0])*(y-a[1])-(b[1]-a[1])*(x-a[0]);positive||=cross>0;negative||=cross<0}if(!(positive&&negative))return t.f.index}return null}
function updated(){window.MG?.labels();if(S.faceFocus!==null&&S.unit==='face'&&S.faceByIndex?.has(S.faceFocus))showFace(S.faceFocus);if(!S.chartGate){$('chartReset').hidden=true;$('judgeSelection').textContent=''}schedule()}
function schedule(force=false){if(!S.ready)return;const signature=JSON.stringify([S.data.meta.id,filters(),!!S.judgePool,!!S.judgeExclude,!!S.judgeDetail]);if(!force&&signature===lastSignature)return;lastSignature=signature;clearTimeout(timer);const my=++token;S.judgeBusy=true;$('judgeScope').textContent='패치 값으로 다시 세는 중…';timer=setTimeout(()=>calculate(my),80)}
async function calculate(my){try{
  const f=filters(),pooled=!!S.judgePool,exclude=!!S.judgeExclude,detail=!!S.judgeDetail;
  const datasets=pooled?await Promise.all(DV.M.cases.filter(c=>c.prior===S.data.meta.prior).map(c=>DV.load(c.id))):[S.data];
  if(my!==token)return;const started=performance.now(),r=U11.calculate(datasets,f,pooled,exclude,detail);if(my!==token)return;S.judgement=r;S.judgeMs=performance.now()-started;renderJudgement(r);
}catch(e){S.error=e.stack;$('judgeScope').textContent='확인 불가: '+e.message;console.error(e)}finally{if(my===token)S.judgeBusy=false}}
const svg=(w,h,content,label)=>`<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="${label}">${content}</svg>`;
const txt=(x,y,s,extra='')=>`<text x="${x}" y="${y}" ${extra}>${s}</text>`;
function calibrationPlot(r){
  const w=520,h=330,l=62,right=412,top=24,bottom=283,log=v=>Math.log10(Math.max(.5,Math.min(100,v))),lo=Math.log10(.5),span=Math.log10(100)-lo;
  const x=v=>l+(log(v)-lo)/span*(right-l),y=v=>bottom-(log(v)-lo)/span*(bottom-top);
  let s='';for(const tick of [.5,1,2,5,10,20,50,100]){s+=`<path d="M${x(tick)},${top}V${bottom}M${l},${y(tick)}H${right}" class="gridline"/>`+txt(x(tick),bottom+18,tick,'text-anchor="middle"')+txt(l-9,y(tick)+4,tick,'text-anchor="end"')}
  s+=`<path d="M${x(.5)},${y(.5)}L${x(100)},${y(100)}" stroke="#829493" stroke-dasharray="5 4"/>`+txt((l+right)/2,h-9,'불확실도 (cm) · 로그 눈금','text-anchor="middle"')+txt(6,14,'실제 오차 (cm) · 로그 눈금');
  for(const source of ['mvs','prior']){const rows=r.calibration.map((v,i)=>({...v,index:i})).filter(p=>p.source===source&&p.draw);const col=colors[source];
    if(!(source==='prior'&&r.prior==='LoD2'))s+=`<path d="${rows.map((p,j)=>(j?'L':'M')+x(p.u_median_cm)+','+y(p.e_median_cm)).join('')}" fill="none" stroke="${col}" stroke-width="1.6"/>`;
    rows.forEach((p,j)=>{const xx=x(p.u_median_cm),yy=y(p.e_median_cm),tooltip=`${name(source)} ${p.label} · ${p.n} 패치 · 불확실도 ${A.fmt(p.u_median_cm,3)} cm · 실제 오차 ${A.fmt(p.e_median_cm,3)} cm · 25·75 % ${A.fmt(p.e_p25_cm,3)}·${A.fmt(p.e_p75_cm,3)} cm · 화면에서 다시 셈`;
      s+=`<g data-cal="${p.index}" tabindex="0" role="button" aria-label="${A.esc(tooltip)}" class="calpoint"><title>${A.esc(tooltip)}</title><path d="M${xx},${y(p.e_p25_cm)}V${y(p.e_p75_cm)}M${xx-4},${y(p.e_p25_cm)}h8M${xx-4},${y(p.e_p75_cm)}h8" stroke="${col}" stroke-width="1.6"/><circle cx="${xx}" cy="${yy}" r="5" fill="${col}" stroke="white"/>`;
      const max=Math.max(p.e_median_cm,p.e_p75_cm);if(max>100)s+=`<path d="M${xx},${top-4}l-5,8h10z" fill="${col}"/>`+txt(xx+8,top+12+(j%3)*12,A.fmt(max,1),'fill="'+col+'"');
      if(p.u_median_cm>100)s+=`<path d="M${right+4},${yy}l-8,-5v10z" fill="${col}"/>`+txt(right+8,yy+4,A.fmt(p.u_median_cm,1));
      if(p.e_median_cm<.5||p.e_p25_cm<.5)s+=`<path d="M${xx},${bottom+4}l-5,-8h10z" fill="${col}"/>`;
      if(source==='prior'&&r.prior==='LoD2'){const ly=top+20+j*22;s+=`<path d="M${xx+6},${yy}L${right+8},${ly-4}" fill="none" stroke="${col}" opacity=".45"/>`+txt(right+10,ly,p.label.replace('B173nb_b10','B173').replace('B0_b10','B0').replace('R1rep_b10','R1'),'class="pointlabel"')+txt(right+10,ly+11,A.int(p.n)+'개','class="pointlabel"')}
      s+='</g>';
    });
  }
  s+=txt(l+9,top+15,'● MVS','fill="'+colors.mvs+'"')+txt(l+85,top+15,'● 사전 정보','fill="'+colors.prior+'"');
  return svg(w,h,s,'보정 그림 · 화면에서 다시 셈');
}
function sparsePlot(result,source){
  if(!result.available)return `<div class="sparseEmpty"><b>${name(source)}</b><p>${A.esc(result.reason)}</p><span class="small">화면에서 다시 셈 · ${A.int(result.n)} 패치</span></div>`;
  const w=430,h=194,l=43,right=410,top=27,bottom=148,max=Math.max(1.1,...result.rows.map(r=>r.curve))*1.05,x=p=>l+p/90*(right-l),y=v=>bottom-v/max*(bottom-top);let s='';
  for(const n of [0,.5,1])s+=`<path d="M${l},${y(n)}H${right}" class="gridline"/>`+txt(l-7,y(n)+4,n,'text-anchor="end"');
  if(max>1.5)s+=txt(l-7,top+4,A.fmt(max,1),'text-anchor="end"');
  s+=`<path d="M${l},${y(1)}H${right}" stroke="#89949b" stroke-dasharray="4 3"/>`;
  for(const [field,col]of [['ideal','#8b6999'],['curve',colors[source]]])s+=`<path d="${result.rows.map((r,i)=>(i?'L':'M')+x(r.percent)+','+y(r[field])).join('')}" fill="none" stroke="${col}" stroke-width="2"/>`;
  for(const row of result.rows){const tip=`${name(source)}: 불확실도 상위 ${row.percent}% (${A.int(row.removed)}패치)를 평가에서 제외. 남은 ${A.int(row.remaining)}패치 평균 오차 ${A.fmt(row.mean_cm,2)} cm / 처음 ${A.fmt(result.base_mean_cm,2)} cm = ${A.fmt(row.curve,3)}. 실제 오차 순으로 뺐다면 ${A.fmt(row.ideal_mean_cm,2)} cm.`;s+=`<circle cx="${x(row.percent)}" cy="${y(row.curve)}" r="3" fill="${colors[source]}" tabindex="0" aria-label="${A.esc(tip)}"><title>${A.esc(tip)}</title></circle>`}
  for(const n of [0,30,60,90])s+=txt(x(n),bottom+16,n+' %','text-anchor="middle"');
  s+=txt(l,15,name(source)+' · '+A.int(result.n)+' 패치','font-weight="600"')+txt(right,15,'실제 오차 평균 ÷ 처음 평균','text-anchor="end"')+txt((l+right)/2,h-6,'큰 쪽부터 뺀 비율','text-anchor="middle"');
  return svg(w,h,s,name(source)+' 희소화 곡선 · 화면에서 다시 셈')+`<div class="sparseAreas">화면에서 다시 셈 · 곡선−이상적 넓이 <b>${A.fmt(result.area_curve_ideal,4)}</b> · 무작위−이상적 넓이 <b>${A.fmt(result.area_random_ideal,4)}</b></div>`;
}
function renderJudgement(r){
  $('judgeCurrent').classList.toggle('active',!r.pooled);$('judgePool').classList.toggle('active',r.pooled);$('judgeDetailWrap').hidden=!(r.pooled&&r.prior==='LoD2');
  $('judgeScope').textContent=`${r.pooled?'세 지역 합 · B0 1 m / B173 주변·R1 1.5 m':S.data.meta.label+' · 고리 '+DV.radius(S.data,S.r).toFixed(1)+' m'} · MVS 판 ${r.filters.v==='a'?'가':'나'} · ${r.filters.scope==='eval'?'평가 범위만':'둘레 10 m 띠까지'} · 왼쪽 걸러 보기 적용 · 항상 패치로 셈`;
  $('judgeWarning').hidden=!r.exclude;$('judgeWarning').textContent=U11.C.population.exclusion_warning;
  const overflow=r.calibration.filter(p=>p.draw&&[p.u_median_cm,p.e_median_cm,p.e_p25_cm,p.e_p75_cm].some(v=>v>100)).map(p=>name(p.source)+' '+A.esc(p.label)+': '+[['u_median_cm','불확실도'],['e_median_cm','실제 오차 중앙값'],['e_p25_cm','25 %'],['e_p75_cm','75 %']].filter(([k])=>p[k]>100).map(([k,label])=>label+' '+A.fmt(p[k],2)+' cm').join(' · '));
  $('calibration').innerHTML=calibrationPlot(r)+'<p class="small muted">점: 중앙값 · 막대: 25~75 % · 30 패치 미만은 표에만 표시 · 세모: 축 범위 밖</p>'+(overflow.length?'<div class="overflowValues">100 cm 초과 · 화면에서 다시 셈<br>'+overflow.join('<br>')+'</div>':'');
  $('sparsification').innerHTML=sparsePlot(r.sparse.mvs,'mvs')+sparsePlot(r.sparse.prior,'prior')+'<p class="small muted">색 선: 불확실도 순 · 보라: 실제 오차 순 · 회색 점선: 무작위</p>';
  $('calibration').insertAdjacentHTML('beforeend','<details class="chartExplanation"><summary>왜 구간과 중앙값으로 보나요?</summary><p>비슷한 불확실도를 가진 패치끼리 묶어 실제 오차의 대표값과 분포를 봅니다. 구간 0~2·2~5·5~10·10~20·20~40·40 cm 이상은 기존 발주문 6.1의 고정 요약 구간이며, 각 경계의 별도 통계적 근거는 문서에 없습니다. 품질 등급이나 합격 기준이 아닙니다.</p><p>점은 구간별 중앙값, 막대는 오차의 가운데 50%입니다. 중앙값은 소수의 큰 실패를 가릴 수 있습니다. 대각선은 대표적인 크기의 일치를 보는 참고선이며 확률적 보정을 증명하지 않습니다.</p></details>');
  $('sparsification').insertAdjacentHTML('beforeend','<details class="chartExplanation" open><summary>희소화 곡선 읽는 법</summary><p>불확실도가 큰 패치부터 평가에서 빼고, 남은 패치의 실제 오차 평균을 봅니다. 원본 삭제나 재학습은 없습니다. 예: 처음 평균 10 cm → 상위 20% 제외 뒤 4 cm이면 가로 20%, 세로 0.4입니다.</p><p>색 선은 불확실도 순, 보라 선은 실제 오차를 미리 알고 큰 순서로 뺀 최선의 기준입니다. 회색 1은 무작위 제외의 기대값입니다. 색 선이 보라 선에 가까울수록 큰 오차를 먼저 찾아냅니다. 1보다 높아지면 남은 곳의 평균 오차가 오히려 커진 것입니다.</p><p>각 점에 마우스를 올리면 제외·잔여 패치 수와 실제 cm를 볼 수 있습니다. 이 곡선은 순서 평가입니다. 불확실도에 모두 10을 곱해도 순서와 곡선은 같으므로 크기의 정확성까지 보장하지 않습니다.</p></details>');
  $('calibrationTable').innerHTML='<table><thead><tr><th>자료 · 구간 / 면</th><th>패치 수</th><th>불확실도 중앙값 cm</th><th>실제 오차 중앙값 cm</th><th>25 % cm</th><th>75 % cm</th><th>오차 ÷ 불확실도</th></tr></thead><tbody>'+r.calibration.map((p,i)=>`<tr data-cal="${i}" tabindex="0"><td>${name(p.source)} · ${A.esc(p.label)}${p.draw?'':' · 표본 부족'}</td><td>${A.int(p.n)}</td><td>${A.fmt(p.u_median_cm,3)}</td><td>${A.fmt(p.e_median_cm,3)}</td><td>${A.fmt(p.e_p25_cm,3)}</td><td>${A.fmt(p.e_p75_cm,3)}</td><td>${A.fmt(p.median_e_over_u,3)}</td></tr>`).join('')+'</tbody></table>';
  document.querySelectorAll('[data-cal]').forEach(el=>{el.onclick=()=>selectCalibration(Number(el.dataset.cal));el.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();el.click()}}});
}
async function selectCalibration(index){const r=S.judgement,p=r.calibration[index];if(!p)return;
  if(p.select.site&&p.select.site!==S.data.meta.site){await A.changeCase(p.select.site+'__'+r.prior,true);for(const key of ['cell','shape','roof','status','flag'])$(key).value=r.filters[key];$('enableRange').checked=!!r.filters.range;if(r.filters.range){$('filterlow').value=r.filters.range[0];$('filterhigh').value=r.filters.range[1]}}
  S.q=0;A.clearQuestion();S.unit='patch';$('viewUnit').value='patch';
  S.chartGate={select:p.select,exclude:r.exclude,pooled:r.pooled};A.refresh();$('chartReset').hidden=false;$('judgeSelection').textContent=`${name(p.source)} · ${p.label}의 패치만 지도에 표시 · 화면에서 다시 셈. ${r.pooled?'지도는 현재 지역, 그림은 세 지역 합입니다. 구간 선택은 지역마다 고른 고리 값입니다.':''}`;
}
return {init,filters,setPair,prepareFaces,buildMaps,tooltip,showFace,overlays,drawOrbit,pickOrbit,updated,schedule,selectCalibration,zoomIds};
})();
