import * as THREE from '/vendor/three.module.min.js';

const $ = id => document.getElementById(id);
const blue = '#267dbb', orange = '#d98a28', gray = '#afb7bf';
const color = {mvs: blue, als: orange, IMAGE: blue, PRIOR: orange, ABSTAIN: gray};
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number = n => n !== null && n !== undefined && Number.isFinite(Number(n));
const fmt = (n, digits = 3) => number(n) ? Number(n).toLocaleString('ko-KR', {minimumFractionDigits: digits, maximumFractionDigits: digits}) : '—';
const count = n => number(n) ? Number(n).toLocaleString('ko-KR') : '—';
const actionLabel = {IMAGE:'IMAGE · 현재 MVS 선택', PRIOR:'PRIOR · 과거 ALS 선택', ABSTAIN:'ABSTAIN · 판단 유보'};
const reasonLabels = {
  CANDIDATE_MISSING_OR_INVALID:'소스 후보가 없거나, 국소 평면을 안정적으로 만들 수 없습니다.',
  INSUFFICIENT_COMMON_PAIRS:'두 후보가 함께 평가되는 관측쌍이 부족합니다.',
  INSUFFICIENT_DISTINCT_VIEWS:'서로 다른 관측 영상 수가 부족합니다.',
  INSUFFICIENT_DISJOINT_PAIRS:'카메라를 공유하지 않는 관측쌍이 충분하지 않습니다.',
  SOURCES_NOT_DISTINGUISHABLE:'관측 비용 차이가 작아 두 소스를 구별하지 못했습니다.',
  BOTH_SOURCES_POOR_IMAGE_SUPPORT:'두 소스 모두 현재 영상에 대한 지지가 부족합니다.',
  PREFERRED_SOURCE_POOR_IMAGE_SUPPORT:'상대적으로 나은 소스도 관측 지지 기준을 충족하지 못했습니다.',
  INCONSISTENT_PAIRED_SOURCE_PREFERENCE:'관측쌍에 따라 더 잘 맞는 소스가 달라집니다.',
  PROFILE_INSUFFICIENT_COVERAGE:'기하 위치를 바꾼 대조 검사에 공통 관측이 부족합니다.',
  PROFILE_CONTROLS_MISSING:'양쪽 방향의 기하 대조 검사를 모두 확인할 수 없습니다.',
  PROFILE_REQUIRES_GEOMETRY_CORRECTION:'원래 기하보다 이동한 후보가 더 잘 맞아, 그대로 채택할 수 없습니다.',
  PROFILE_FLAT_OR_REMOTE_AMBIGUITY:'위치를 바꿔도 구별되지 않거나, 멀리 떨어진 대안도 잘 맞습니다.',
  PROFILE_MISSING:'기하 위치 대조 검사 결과가 없습니다.',
  PAIRED_OBSERVATION_AND_PROFILE_SUPPORTED_CONDITIONAL:'공통 관측쌍의 일관된 선호와 기하 위치 대조 검사를 통과했습니다.'
};
const reasonText = value => reasonLabels[value] || '원본 기록에 남은 판단 사유를 아래에서 확인할 수 있습니다.';
const state = window.sourceViewerState = {ready:false,loading:true,region:null,stage:1,cellId:null,error:null,pairId:null,anchorIndex:null,totalCells:0,acceptedCount:0,images:{},photos:{},scene:{},scientific_verdict:null};
let manifest, regionData, cellData, evidence, operation = 0, controller;
const regions = new Map(), cells = new Map(), regionalPoints = new Map();
let filteredCells = [], cloud;

async function getJSON(path, signal) {
  const response = await fetch(path, {signal});
  if (!response.ok) { let message = ''; try { const body = await response.json(); message = body.detail || body.error || body.message || ''; } catch {} throw new Error(`HTTP ${response.status} · ${path}${message ? ' · '+message : ''}`); }
  return response.json();
}
function begin() {
  operation++; controller?.abort(); controller = new AbortController();
  state.loading=true; state.ready=false; state.error=null;
  $('loading-indicator').hidden=false; $('error-banner').hidden=true;
  return {id:operation,signal:controller.signal};
}
function finish(id) {
  if (id !== operation) return;
  state.loading=false; state.ready=true; $('loading-indicator').hidden=true;
  document.documentElement.dataset.ready='true';
  window.dispatchEvent(new CustomEvent('source-viewer-ready',{detail:{...state}}));
}
function fail(error, id=operation) {
  if (id !== operation || error?.name === 'AbortError') return;
  state.loading=false; state.ready=false; state.error=String(error.message || error);
  $('loading-indicator').hidden=true; $('error-banner').hidden=false; $('error-message').textContent=state.error;
  document.documentElement.dataset.ready='false'; console.error(error);
}
function metric(label,value,unit='',sub='') { return `<div class="metric"><div class="label">${esc(label)}</div><strong>${esc(value)}</strong><span class="unit">${esc(unit)}</span>${sub?`<div class="sub">${esc(sub)}</div>`:''}</div>`; }
function detail(rows) { return `<dl class="detail-list">${rows.map(([a,b])=>`<div class="detail-row"><dt>${esc(a)}</dt><dd>${esc(b)}</dd></div>`).join('')}</dl>`; }
function setURL() { const url=new URL(location.href); url.searchParams.set('region',state.region);url.searchParams.set('stage',state.stage);url.searchParams.set('cell',state.cellId);history.replaceState(null,'',url); }
function stageUI() {
  document.querySelectorAll('[data-stage]').forEach(b=>b.setAttribute('aria-selected',Number(b.dataset.stage)===state.stage));
  for (let i=1;i<=3;i++) $('stage-'+i).hidden=i!==state.stage;
  document.querySelectorAll('[data-region]').forEach(b=>b.setAttribute('aria-selected',b.dataset.region===state.region));
}

function mapColor(row) {
  const layer=$('map-layer').value;
  if (layer==='action') return color[row.decision?.action || 'ABSTAIN'];
  if (layer==='coverage') { const t=Math.min(1,(row.observation?.common_scored_pair_count || 0)/24);return `rgb(${Math.round(243-205*t)},${Math.round(247-122*t)},${Math.round(251-64*t)})`; }
  if (!number(row.height_difference_m)) return '#e5e9ee';
  const maximum=Math.max(1,...regionData.cells.map(r=>Math.abs(r.height_difference_m || 0))),t=Math.min(1,Math.abs(row.height_difference_m)/maximum);
  const base=row.height_difference_m>=0?[38,125,187]:[217,138,40];return `rgb(${base.map(v=>Math.round(250+(v-250)*t)).join(',')})`;
}
function renderMap() {
  if (!regionData) return;
  const domain=regionData.domain, xr=domain.x[1]-domain.x[0],yr=domain.y[1]-domain.y[0],scale=258/Math.max(xr,yr),ox=(300-xr*scale)/2,oy=(284-yr*scale)/2;
  const allowed=new Set(filteredCells.map(r=>r.cell_id));
  $('cell-map').innerHTML=`<title>${esc(state.region)} 고정 셀 지도</title><text x="15" y="15" fill="#738496" font-size="8">Y ↑</text>${regionData.cells.map(row=>{
    const [x0,y0,x1,y1]=row.bbox_xy,selected=row.cell_id===state.cellId;
    return `<rect data-cell-id="${row.cell_id}" data-testid="map-cell-${row.cell_id}" x="${ox+(x0-domain.x[0])*scale}" y="${oy+(domain.y[1]-y1)*scale}" width="${(x1-x0)*scale}" height="${(y1-y0)*scale}" fill="${mapColor(row)}" opacity="${allowed.has(row.cell_id)?1:.17}" stroke="${selected?'#102e46':'#ffffff'}" stroke-width="${selected?2.3:.28}" tabindex="${selected?0:-1}" role="button" aria-label="셀 ${row.cell_id}, ${esc(actionLabel[row.decision?.action || 'ABSTAIN'])}"><title>셀 ${row.cell_id} · ${esc(actionLabel[row.decision?.action || 'ABSTAIN'])} · 높이차 ${fmt(row.height_difference_m)} m</title></rect>`;
  }).join('')}<text x="17" y="296" fill="#738496" font-size="8">${domain.x[0]} m</text><text x="245" y="296" fill="#738496" font-size="8">X →</text>`;
  const layer=$('map-layer').value;
  $('map-legend').innerHTML=layer==='action'?'<span class="dot blue"></span> IMAGE <span class="dot orange"></span> PRIOR <span class="dot gray"></span> ABSTAIN':layer==='gap'?'<span class="dot orange"></span> ALS가 높음 <span class="dot blue"></span> MVS가 높음':'연함 0쌍 → 진함 24쌍';
  $('map-description').textContent=`${state.region} · EPSG:25832 계보의 장면 로컬 XY · 클릭하여 셀 선택`;
}
function updateFilter() {
  if(!regionData)return;
  const f=$('cell-filter').value;
  filteredCells=regionData.cells.filter(r=>f==='all'||r.decision?.action===f||(f==='large'&&number(r.height_difference_m)&&Math.abs(r.height_difference_m)>1)||(f==='valid'&&r.both_valid));
  $('cell-select').replaceChildren(...filteredCells.map(r=>{const o=new Option(`셀 ${r.cell_id} · ${r.decision?.action || 'ABSTAIN'}`,r.cell_id);return o;}));
  $('cell-select').value=String(state.cellId); $('cell-select').disabled=!filteredCells.length;
  $('filter-status').textContent=`필터 ${count(filteredCells.length)} / 전체 ${count(regionData.cells.length)} 셀`;
  $('cell-prev').disabled=!filteredCells.length;$('cell-next').disabled=!filteredCells.length;
  renderMap();
}
function recommendations() {
  const list=[],add=(id,label)=>{if(id!==undefined&&id!==null&&!list.some(x=>x.id===id))list.push({id,label});};
  const base=manifest.regions.find(r=>r.id===state.region);add(base?.default_cell_id,'기본 관측 사례');
  for(const action of ['IMAGE','PRIOR']) add(regionData.cells.find(r=>r.decision?.action===action)?.cell_id,action==='IMAGE'?'현재 MVS 선택 사례':'과거 ALS 선택 사례');
  add(regionData.cells.find(r=>r.decision?.action==='ABSTAIN'&&(r.observation?.common_scored_pair_count||0)>0)?.cell_id,'관측이 있어도 유보한 사례');
  const regrets=regionData.cells.filter(r=>r.decision?.accepted&&number(r.evaluation?.regret_m)).sort((a,b)=>b.evaluation.regret_m-a.evaluation.regret_m);
  add(regrets[0]?.cell_id,'참조 평가 뒤 확인한 최대 후회');
  $('recommended-cases').innerHTML=list.map(r=>`<button type="button" data-case="${r.id}" class="${r.id===state.cellId?'active':''}">셀 ${r.id} · ${esc(r.label)}</button>`).join('');
}
function renderRegion() {
  $('region-title').textContent=state.region+' 영역';
  state.totalCells=regionData.cells.length;state.acceptedCount=regionData.cells.filter(r=>r.decision?.accepted).length;
  updateFilter();recommendations();
}
function renderCell() {
  const c=cellData.candidate,d=cellData.decision,e=cellData.evaluation || {},o=cellData.observation;
  $('cell-title').textContent=`${state.region} · 셀 ${state.cellId}`;
  $('cell-location').textContent=`고정 2 m 셀 · X ${fmt(c.x,1)} / Y ${fmt(c.y,1)} m`;
  $('cell-search').value=state.cellId;$('cell-select').value=String(state.cellId);
  $('action-badge').textContent=actionLabel[d.action];$('action-badge').dataset.action=d.action;
  $('candidate-stats').innerHTML=metric('현재 MVS 원래 점',count(c.candidates.mvs.count),'점')+metric('과거 ALS 원래 점',count(c.candidates.als.count),'점')+metric('소스 높이차',fmt(c.height_difference_m),'m','MVS − ALS · 추정 up 방향')+metric('두 후보의 표현',c.both_valid?'모두 유효':'유효성 미충족','','유효성은 현재성을 뜻하지 않음');
  for(const s of ['mvs','als']){const v=c.candidates[s];$(s+'-candidate-detail').innerHTML=detail([['국소 평면 후보',v.valid?'유효':'부적합 / 부재'],['입력 점 수',count(v.count)],['인라이어 점 수',count(v.inlier_count)],['인라이어 비율',number(v.inlier_fraction)?fmt(v.inlier_fraction*100,1)+' %':'—'],['평면 적합 RMS',fmt(v.rms_m)+' m'],['상태 기록',v.reason || '—']]);}
  $('decision-card').dataset.action=d.action;
  $('decision-card').innerHTML=`<h3>${esc(actionLabel[d.action])}</h3><p>${esc(reasonText(d.reason))}</p><p class="micro">${d.accepted?'현재 관측에 대한 조건부 사용 지지입니다. 현재성 또는 참조 기하 정확도를 확정하지 않습니다.':'현재 기록에서 선택을 확정하지 않았습니다. 다른 소스가 자동으로 유효해지는 것은 아닙니다.'}</p><div class="decision-code">${esc(d.reason)}</div>`;
  $('decision-evidence').innerHTML=detail([['현재 MVS 비용',fmt(d.costs?.mvs)],['과거 ALS 비용',fmt(d.costs?.als)],['공통 관측쌍',count(d.common_pairs)],['서로 다른 영상',count(d.distinct_views)],['분리된 관측쌍',count(d.disjoint_pairs)],['관측쌍의 일관된 지지',number(d.support_fraction)?fmt(d.support_fraction*100,1)+' %':'—'],['승자 위치 대조 검사',d.winner_profile?.status || '검사까지 도달하지 않음']]);
  $('evaluation-metrics').innerHTML=detail([['평가 참조점',count(e.reference_count)],['MVS 오차',fmt(e.mvs_error_m)+' m'],['ALS 오차',fmt(e.als_error_m)+' m'],['선택한 소스의 오차',d.accepted?fmt(e.selected_error_m)+' m':'유보 · 선택값 없음'],['선택 후회 (오라클 대비)',d.accepted?fmt(e.regret_m)+' m':'유보 · 비교 대상 아님']]);
  $('region-summary-title').textContent=state.region+' 전체 셀에서의 적용 범위';
  const totals={IMAGE:0,PRIOR:0,ABSTAIN:0};regionData.cells.forEach(r=>totals[r.decision?.action || 'ABSTAIN']++);
  $('region-stats').innerHTML=metric('전체 고정 셀',count(state.totalCells),'셀')+metric('선택한 셀',count(state.acceptedCount),'셀')+metric('전체 대비 선택 범위',fmt(100*state.acceptedCount/state.totalCells,2),'%')+metric('판단을 유보한 셀',count(totals.ABSTAIN),'셀');
  $('coverage-bar').innerHTML=Object.entries(totals).map(([a,n])=>`<span style="width:${100*n/state.totalCells}%;background:${color[a]}" title="${a} ${n}"></span>`).join('');
  $('coverage-labels').innerHTML=Object.entries(totals).map(([a,n])=>`<span><i class="dot" style="background:${color[a]}"></i> ${a} ${count(n)}셀</span>`).join('');
  $('raw-record').textContent=JSON.stringify({candidate:c,decision:d,evaluation:e,observation_summary:o.shared},null,2);
  renderCharts();renderMap();recommendations();
}

function chart(host, series, xLabel, yLabel, zero=false) {
  const points=series.flatMap(s=>s.values.filter(p=>number(p[0])&&number(p[1])));
  if(!points.length){host.innerHTML='<div class="no-data">기록된 공통 측정이 없습니다.</div>';return;}
  let xmin=Math.min(...points.map(p=>p[0])),xmax=Math.max(...points.map(p=>p[0])),ymin=Math.min(0,...points.map(p=>p[1])),ymax=Math.max(.05,...points.map(p=>p[1]));
  if(xmin===xmax){xmin-=1;xmax+=1;}const pad=(ymax-ymin)*.13;ymin-=pad;ymax+=pad;
  const W=560,H=250,left=48,right=15,top=29,bottom=43,x=v=>left+(v-xmin)/(xmax-xmin)*(W-left-right),y=v=>H-bottom-(v-ymin)/(ymax-ymin)*(H-top-bottom);
  let svg=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(yLabel)}"><title>${esc(yLabel)}</title>`;
  for(let i=0;i<5;i++){const val=ymin+(ymax-ymin)*i/4;svg+=`<path d="M${left},${y(val)}H${W-right}" stroke="#e7ecf1"/><text x="${left-8}" y="${y(val)+3}" text-anchor="end" font-size="10" fill="#8492a0">${val.toFixed(2)}</text>`;}
  for(let i=0;i<5;i++){const val=xmin+(xmax-xmin)*i/4;svg+=`<text x="${x(val)}" y="${H-bottom+18}" text-anchor="middle" font-size="10" fill="#8492a0">${Number(val.toFixed(1))}</text>`;}
  if(zero)svg+=`<path d="M${left},${y(0)}H${W-right}" stroke="#62788a" stroke-dasharray="4 4"/>`;
  for(const [index,s] of series.entries()){
    let path='',open=false;for(const p of s.values){if(!number(p[1])){open=false;continue;}path+=`${open?'L':'M'}${x(p[0])},${y(p[1])}`;open=true;}
    svg+=`<path d="${path}" fill="none" stroke="${color[s.source]}" stroke-width="1.8" ${index?'stroke-dasharray="5 2"':''}/>`;
    for(const p of s.values.filter(p=>number(p[1])))svg+=index?`<path d="M${x(p[0])},${y(p[1])-3.5}l3.5,6h-7z" fill="${color[s.source]}"/>`:`<circle cx="${x(p[0])}" cy="${y(p[1])}" r="3" fill="${color[s.source]}"/>`;
    svg+=`<text x="${left+index*145}" y="15" fill="${color[s.source]}" font-size="11">${index?'▲ 과거 ALS':'● 현재 MVS'}</text>`;
  }
  svg+=`<text x="${W/2}" y="${H-7}" text-anchor="middle" font-size="10" fill="#778897">${esc(xLabel)}</text></svg>`;host.innerHTML=svg;
}
function renderCharts(){
  const obs=cellData.observation;
  chart($('pair-chart'),['mvs','als'].map(s=>({source:s,values:(obs.candidates?.[s]?.pairs||[]).map((p,i)=>[i+1,p.cost])})),'저장된 카메라쌍 순서','카메라쌍별 공통 비용');
  chart($('profile-chart'),['mvs','als'].map(s=>({source:s,values:(obs.candidates?.[s]?.profile||[]).map(p=>[p.offset_m,p.paired_delta_cost])})),'후보 법선 방향 이동 (m)','동일 마스크에서 이동 전후 비용 차이',true);
}

class Photo {
  constructor(key){this.key=key;this.canvas=$(key+'-canvas');this.img=$(key+'-image');this.context=this.canvas.getContext('2d');this.zoom=1;this.pan=[0,0];this.overlays={};this.loaded=false;this.drag=null;
    this.canvas.addEventListener('pointerdown',e=>{if(!this.loaded)return;this.drag=[e.clientX,e.clientY];this.canvas.setPointerCapture(e.pointerId);});
    this.canvas.addEventListener('pointermove',e=>{if(!this.drag)return;this.pan[0]+=e.clientX-this.drag[0];this.pan[1]+=e.clientY-this.drag[1];this.drag=[e.clientX,e.clientY];this.draw();});
    for(const name of ['pointerup','pointercancel','lostpointercapture'])this.canvas.addEventListener(name,()=>this.drag=null);
    this.canvas.addEventListener('wheel',e=>{if(!this.loaded)return;e.preventDefault();const r=this.canvas.getBoundingClientRect(),p=[e.clientX-r.left,e.clientY-r.top],next=Math.max(.02,Math.min(40,this.zoom*Math.exp(-e.deltaY*.0015))),ratio=next/this.zoom;this.pan=p.map((v,i)=>v-(v-this.pan[i])*ratio);this.zoom=next;this.draw();},{passive:false});
    this.canvas.addEventListener('dblclick',()=>this.focus());this.canvas.addEventListener('contextmenu',e=>e.preventDefault());
    new ResizeObserver(()=>{if(this.loaded)this.draw();else this.blank();}).observe(this.canvas.parentElement);
  }
  clear(){this.loaded=false;this.img.removeAttribute('src');this.overlays={};this.blank();this.canvas.parentElement.querySelector('.photo-empty')?.removeAttribute('hidden');if(this.key!=='lightbox'){state.images[this.key]={loaded:false,naturalWidth:0,naturalHeight:0};$(this.key+'-resolution').textContent='';$(this.key+'-caption').textContent='';$(this.key+'-zoom').textContent='';}}
  async load(info,overlays,id){this.loaded=false;this.overlays=overlays;this.img.src=info.url;await this.img.decode();if(id!==operation)return;this.loaded=true;this.info=info;this.canvas.parentElement.querySelector('.photo-empty')?.setAttribute('hidden','');if(this.key!=='lightbox'){state.images[this.key]={loaded:true,naturalWidth:this.img.naturalWidth,naturalHeight:this.img.naturalHeight,url:info.url};$(this.key+'-resolution').textContent=`${this.img.naturalWidth} × ${this.img.naturalHeight}`;$(this.key+'-caption').textContent=`영상 ${info.id} · ${info.name} · 휠 확대 / 드래그 이동`;}this.focus();}
  size(){return [this.canvas.clientWidth,this.canvas.clientHeight];}
  blank(){const [w,h]=this.size(),d=Math.min(devicePixelRatio||1,2);this.canvas.width=Math.max(1,Math.round(w*d));this.canvas.height=Math.max(1,Math.round(h*d));this.context.fillStyle='#16232d';this.context.fillRect(0,0,this.canvas.width,this.canvas.height);}
  fit(){if(!this.loaded)return;const [w,h]=this.size();this.zoom=Math.min(w/this.img.naturalWidth,h/this.img.naturalHeight);this.pan=[(w-this.img.naturalWidth*this.zoom)/2,(h-this.img.naturalHeight*this.zoom)/2];this.draw();}
  actual(){if(!this.loaded)return;const [w,h]=this.size(),center=[(w/2-this.pan[0])/this.zoom,(h/2-this.pan[1])/this.zoom];this.zoom=1;this.pan=[w/2-center[0],h/2-center[1]];this.draw();}
  focus(){if(!this.loaded)return;const p=Object.values(this.overlays).flat().filter(v=>Array.isArray(v)&&v.every(Number.isFinite));if(!p.length){this.fit();return;}const xs=p.map(v=>v[0]),ys=p.map(v=>v[1]),cx=(Math.min(...xs)+Math.max(...xs))/2+.5,cy=(Math.min(...ys)+Math.max(...ys))/2+.5,[w,h]=this.size();this.zoom=Math.min(w/Math.max(170,Math.max(...xs)-Math.min(...xs)+120),h/Math.max(170,Math.max(...ys)-Math.min(...ys)+120));this.pan=[w/2-cx*this.zoom,h/2-cy*this.zoom];this.draw();}
  draw(){if(!this.loaded)return;const [w,h]=this.size();if(!w||!h)return;const d=Math.min(devicePixelRatio||1,2),ctx=this.context;this.canvas.width=Math.round(w*d);this.canvas.height=Math.round(h*d);ctx.setTransform(d,0,0,d,0,0);ctx.fillStyle='#16232d';ctx.fillRect(0,0,w,h);ctx.imageSmoothingEnabled=this.zoom<1;ctx.drawImage(this.img,...this.pan,this.img.naturalWidth*this.zoom,this.img.naturalHeight*this.zoom);
    for(const [source,list] of Object.entries(this.overlays)){const p=list.filter(v=>Array.isArray(v)&&v.every(Number.isFinite));if(!p.length)continue;const xs=p.map(v=>v[0]),ys=p.map(v=>v[1]),lo=[Math.min(...xs),Math.min(...ys)],hi=[Math.max(...xs),Math.max(...ys)],center=p[Math.floor(p.length/2)];ctx.strokeStyle=source==='reference'?'#ffffff':color[source];ctx.lineWidth=2;ctx.setLineDash(source==='als'?[7,4]:[]);ctx.strokeRect(this.pan[0]+lo[0]*this.zoom,this.pan[1]+lo[1]*this.zoom,(hi[0]-lo[0]+1)*this.zoom,(hi[1]-lo[1]+1)*this.zoom);ctx.setLineDash([]);const x=this.pan[0]+(center[0]+.5)*this.zoom,y=this.pan[1]+(center[1]+.5)*this.zoom;ctx.beginPath();ctx.moveTo(x-5,y);ctx.lineTo(x+5,y);ctx.moveTo(x,y-5);ctx.lineTo(x,y+5);ctx.stroke();}
    if(this.key!=='lightbox'){state.photos[this.key]={zoom:this.zoom,pan:[...this.pan]};$(this.key+'-zoom').textContent=Math.round(this.zoom*100)+' %';}
  }
}
const photos={reference:new Photo('reference'),target:new Photo('target'),lightbox:new Photo('lightbox')};
function clearEvidence(){evidence=null;state.pairId=null;state.anchorIndex=null;photos.reference.clear();photos.target.clear();$('pair-select').replaceChildren();$('pair-select').disabled=true;$('anchor-select').replaceChildren();$('anchor-select').disabled=true;for(const k of ['reference','mvs','als','mask']){const c=$('patch-'+k);c.width=9;c.height=9;const ctx=c.getContext('2d');ctx.fillStyle='#e3e8ed';ctx.fillRect(0,0,9,9);}for(const id of ['mvs-patch-cost','als-patch-cost','common-pixel-count'])$(id).textContent='';if($('lightbox').open)$('lightbox').close();}
function pairRows(){const o=cellData.observation,by={};for(const s of ['mvs','als'])by[s]=new Map((o.candidates?.[s]?.pairs||[]).map(p=>[p.pair_id,p]));return (o.shared?.selected_pairs||[]).map(p=>({...p,mvs_cost:by.mvs.get(p.pair_id)?.cost,als_cost:by.als.get(p.pair_id)?.cost,scored:number(by.mvs.get(p.pair_id)?.cost)&&number(by.als.get(p.pair_id)?.cost)}));}
function renderPairSelect(rows, selected){$('pair-select').replaceChildren(...rows.map(p=>{const option=new Option(`${p.reference_id} → ${p.target_id}${p.scored===false?' · 공통 점수 없음':''}`,p.pair_id);option.disabled=p.scored===false;option.dataset.scored=String(p.scored!==false);return option;}));if(selected)$('pair-select').value=selected;$('pair-select').disabled=!rows.some(p=>p.scored!==false);}
function paintPatch(id, values, mask, width, maskOnly=false){const canvas=$(id);canvas.width=width;canvas.height=width;const ctx=canvas.getContext('2d'),pixels=ctx.createImageData(width,width);for(let i=0;i<width*width;i++){const v=maskOnly?(mask[i]?42:188):mask[i]?Math.max(0,Math.min(255,values[i])):188;pixels.data[i*4]=v;pixels.data[i*4+1]=maskOnly||mask[i]?v:193;pixels.data[i*4+2]=maskOnly||mask[i]?v:199;pixels.data[i*4+3]=255;}ctx.putImageData(pixels,0,0);}
async function fetchEvidence(ctx,pairId=null,anchor=null){
  const base=`/api/evidence/${encodeURIComponent(state.region)}/${state.cellId}`,query=new URLSearchParams();if(pairId)query.set('pair_id',pairId);if(anchor!==null)query.set('anchor',anchor);
  const value=await getJSON(base+(query.size?'?'+query:''),ctx.signal);if(ctx.id!==operation)return;evidence=value;
  const rows=value.pairs || pairRows();renderPairSelect(rows,value.pair_id);
  state.pairId=value.pair_id || null;state.anchorIndex=value.anchor ?? null;
  if(!value.available){photos.reference.clear();photos.target.clear();$('evidence-unavailable').hidden=false;$('evidence-unavailable').textContent=`공통 관측을 표시할 수 없습니다. ${reasonText(cellData.decision.reason)}${value.reason?' · '+value.reason:''}`;$('anchor-select').replaceChildren();$('anchor-select').disabled=true;$('patch-panel').hidden=true;$('observation-description').textContent='측정할 수 없는 상태를 그대로 표시합니다. 다른 영상이나 생성 영상으로 대체하지 않습니다.';return;}
  $('evidence-unavailable').hidden=true;$('patch-panel').hidden=false;
  const valid=new Set(value.anchor_indices_valid || Array.from({length:value.anchor_count},(_,i)=>i));
  $('anchor-select').replaceChildren(...Array.from({length:value.anchor_count},(_,i)=>{const option=new Option(`${i+1} / ${value.anchor_count}${valid.has(i)?'':' · 유효 픽셀 부족'}`,i);option.disabled=!valid.has(i);return option;}));$('anchor-select').value=String(value.anchor);$('anchor-select').disabled=false;
  const patch=value.patch,used=patch.mask.filter(Boolean).length;
  $('observation-description').textContent=`영상 ${value.reference.id} → ${value.target.id} · 같은 ${used}/${patch.width**2} 픽셀을 비교합니다. 두 원본 영상에서 위치를 확대해 확인하세요.`;
  $('patch-note').textContent=`${patch.width} × ${patch.width} 검사 격자 · 선택 패치 ${value.anchor+1}/${value.anchor_count} · 회색은 비교 제외. 여기의 비용은 이 패치 값이며, 셀 전체·관측쌍 중앙값과 다릅니다.`;
  for(const source of ['reference','mvs','als'])paintPatch('patch-'+source,patch[source],patch.mask,patch.width);
  paintPatch('patch-mask',[],patch.mask,patch.width,true);
  $('mvs-patch-cost').textContent='선택 패치 비용 '+fmt(patch.costs.mvs);$('als-patch-cost').textContent='선택 패치 비용 '+fmt(patch.costs.als);$('common-pixel-count').textContent=`${used} / ${patch.width**2}`;
  $('reproduction-badge').textContent=value.reproduced?'저장 점수 재현 확인':'재현 상태 확인 필요';
  await Promise.all([photos.reference.load(value.reference,{reference:value.reference.pixels},ctx.id),photos.target.load(value.target,value.target.pixels,ctx.id)]);
}

class Cloud {
  constructor(){this.host=$('cloud-host');this.canvas=$('cloud-canvas');this.renderer=new THREE.WebGLRenderer({canvas:this.canvas,antialias:true,preserveDrawingBuffer:true});this.renderer.setPixelRatio(Math.min(devicePixelRatio,1.7));this.scene=new THREE.Scene();this.scene.background=new THREE.Color('#13222d');this.camera=new THREE.OrthographicCamera(-1,1,1,-1,.01,10000);this.camera.up.set(0,0,1);this.objects={};this.data={};this.zoom=1;this.pan=[0,0,0];this.azimuth=-.8;this.elevation=.65;this.view='iso';this.center=[0,0,0];this.span=3;this.drag=null;
    this.canvas.addEventListener('contextmenu',e=>e.preventDefault());this.canvas.addEventListener('pointerdown',e=>{this.drag={x:e.clientX,y:e.clientY,pan:e.shiftKey||e.button===2};this.canvas.setPointerCapture(e.pointerId);});
    this.canvas.addEventListener('pointermove',e=>{if(!this.drag)return;const dx=e.clientX-this.drag.x,dy=e.clientY-this.drag.y;if(this.drag.pan){const scale=(this.camera.top-this.camera.bottom)/this.host.clientHeight,right=new THREE.Vector3().setFromMatrixColumn(this.camera.matrixWorld,0),up=new THREE.Vector3().setFromMatrixColumn(this.camera.matrixWorld,1);for(let i=0;i<3;i++)this.pan[i]+=(-dx*right.getComponent(i)+dy*up.getComponent(i))*scale;}else{this.azimuth-=dx*.007;this.elevation=Math.max(-1.56,Math.min(1.56,this.elevation+dy*.007));}this.drag.x=e.clientX;this.drag.y=e.clientY;this.draw();});
    for(const name of ['pointerup','pointercancel','lostpointercapture'])this.canvas.addEventListener(name,()=>this.drag=null);
    this.canvas.addEventListener('wheel',e=>{e.preventDefault();this.zoom=Math.max(.15,Math.min(60,this.zoom*Math.exp(-e.deltaY*.001)));this.draw();},{passive:false});new ResizeObserver(()=>this.draw()).observe(this.host);
  }
  setData(data){this.data=data;for(const object of Object.values(this.objects)){this.scene.remove(object);object.geometry.dispose();object.material.dispose();}this.objects={};this.renderer.renderLists?.dispose();const min=[Infinity,Infinity,Infinity],max=[-Infinity,-Infinity,-Infinity];let total=0;
    for(const s of ['mvs','als']){const item=data[s],p=item?.positions || [];if(!p.length)continue;total+=p.length/3;for(let i=0;i<p.length;i++){const k=i%3;min[k]=Math.min(min[k],p[i]);max[k]=Math.max(max[k],p[i]);}const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(p,3));const material=new THREE.PointsMaterial({size:2.6,sizeAttenuation:false,color:color[s],transparent:false});const points=new THREE.Points(geometry,material);this.scene.add(points);this.objects[s]=points;}
    if(total){this.center=min.map((v,i)=>(v+max[i])/2);this.span=Math.max(.5,...max.map((v,i)=>v-min[i]));}else{this.center=[0,0,0];this.span=3;}$('cloud-empty').hidden=total>0;this.updateColors();this.reset();this.counts();
  }
  updateColors(){for(const [s,object] of Object.entries(this.objects)){const raw=this.data[s];if(s==='mvs'&&$('point-color').value==='rgb'&&raw.colors?.length===raw.positions.length){const rgb=new Float32Array(raw.colors.length);for(let i=0;i<rgb.length;i++){const c=raw.colors[i]/255;rgb[i]=c<=.04045?c/12.92:((c+.055)/1.055)**2.4;}object.geometry.setAttribute('color',new THREE.BufferAttribute(rgb,3));object.material.vertexColors=true;object.material.color.set('#ffffff');}else{object.material.vertexColors=false;object.material.color.set(color[s]);}object.material.needsUpdate=true;}this.draw();}
  counts(){$('cloud-counts').innerHTML=['mvs','als'].map(s=>{const item=this.data[s];return `${s==='mvs'?'현재 MVS':'과거 ALS'} · 원래 ${count(item?.native_count ?? 0)} / 표시 ${count(item?.display_count ?? (item?.positions?.length||0)/3)}점`;}).join('<br>');}
  reset(){this.zoom=1;this.pan=[0,0,0];this.setView('iso');}
  setView(value){this.view=value;if(value==='top'){this.azimuth=-Math.PI/2;this.elevation=Math.PI/2-.0001;}else if(value==='side'){this.azimuth=-Math.PI/2;this.elevation=0;}else{this.azimuth=-.8;this.elevation=.65;}document.querySelectorAll('[data-view]').forEach(b=>b.setAttribute('aria-pressed',b.dataset.view===value));this.draw();}
  draw(){const w=this.host.clientWidth,h=this.host.clientHeight;if(!w||!h)return;const span=this.span,scale=span*.65/this.zoom*Math.max(1,h/w),center=this.center.map((v,i)=>v+this.pan[i]);this.camera.left=-scale*w/h;this.camera.right=scale*w/h;this.camera.top=scale;this.camera.bottom=-scale;this.camera.near=.001;this.camera.far=span*100+100;this.camera.position.set(center[0]+3*span*Math.cos(this.azimuth)*Math.cos(this.elevation),center[1]+3*span*Math.sin(this.azimuth)*Math.cos(this.elevation),center[2]+3*span*Math.sin(this.elevation));this.camera.lookAt(...center);this.camera.updateProjectionMatrix();this.camera.updateMatrixWorld();for(const [s,obj]of Object.entries(this.objects))obj.visible=$('source-'+s).checked;this.renderer.setSize(w,h,false);this.renderer.render(this.scene,this.camera);state.scene={visibility:{mvs:$('source-mvs').checked,als:$('source-als').checked},view:this.view,scope:$('view-scope').value,zoom:this.zoom,pan:[...this.pan],camera:this.camera.position.toArray(),renderedPoints:this.renderer.info.render.points};}
}

async function loadCloud(ctx){let data=cellData.points;if($('view-scope').value==='region'){const region=state.region;if(!regionalPoints.has(region)){const values=await Promise.all(['mvs','als'].map(s=>getJSON(`/api/points/${region}/${s}`,ctx.signal)));if(ctx.id!==operation)return;regionalPoints.set(region,{mvs:values[0],als:values[1]});}data=regionalPoints.get(region);}if(ctx.id!==operation)return;cloud.setData(data);}
async function navigate({region=state.region,cell=state.cellId,stage=state.stage,force=false}={}){
  const ctx=begin(),changedRegion=region!==state.region,changedCell=changedRegion||Number(cell)!==state.cellId;clearEvidence();
  try{
    state.region=region;state.stage=Number(stage);stageUI();
    if(force){regions.delete(region);cells.clear();regionalPoints.delete(region);}
    if(!regions.has(region)){const data=await getJSON(`/api/region/${encodeURIComponent(region)}`,ctx.signal);if(ctx.id!==operation)return;regions.set(region,data);}
    regionData=regions.get(region);if(changedRegion)$('cell-filter').value='all';
    if(!regionData.cells.some(r=>r.cell_id===Number(cell)))cell=manifest.regions.find(r=>r.id===region)?.default_cell_id ?? regionData.cells[0]?.cell_id;
    state.cellId=Number(cell);const key=`${region}/${state.cellId}`;
    if(!cells.has(key)){const data=await getJSON(`/api/cell/${key}`,ctx.signal);if(ctx.id!==operation)return;cells.set(key,data);}
    cellData=cells.get(key);renderRegion();renderCell();stageUI();setURL();
    if(state.stage===1)await loadCloud(ctx);else if(state.stage===2)await fetchEvidence(ctx);
    if(changedCell&&state.stage!==2){$('evidence-unavailable').hidden=true;$('patch-panel').hidden=false;}
    finish(ctx.id);
  }catch(error){fail(error,ctx.id);}
}
async function changeEvidence(pair,anchor){const ctx=begin();try{await fetchEvidence(ctx,pair,anchor);finish(ctx.id);}catch(error){fail(error,ctx.id);}}

$('region-tabs').addEventListener('click',e=>{const b=e.target.closest('[data-region]');if(b)navigate({region:b.dataset.region,cell:manifest.regions.find(r=>r.id===b.dataset.region)?.default_cell_id});});
document.querySelector('.stage-tabs').addEventListener('click',e=>{const b=e.target.closest('[data-stage]');if(b)navigate({stage:Number(b.dataset.stage)});});
$('cell-filter').addEventListener('change',updateFilter);$('map-layer').addEventListener('change',renderMap);
$('cell-select').addEventListener('change',()=>navigate({cell:Number($('cell-select').value)}));
function jump(){const id=Number($('cell-search').value);if(!regionData?.cells.some(r=>r.cell_id===id)){$('filter-status').textContent=`셀 ${id}는 이 영역에 없습니다.`;return;}navigate({cell:id});}
$('cell-jump').addEventListener('click',jump);$('cell-search').addEventListener('keydown',e=>{if(e.key==='Enter')jump();});
for(const [id,direction]of [['cell-prev',-1],['cell-next',1]])$(id).addEventListener('click',()=>{if(!filteredCells.length)return;let index=filteredCells.findIndex(r=>r.cell_id===state.cellId);if(index<0)index=direction===1?-1:0;const next=(index+direction+filteredCells.length)%filteredCells.length;navigate({cell:filteredCells[next].cell_id});});
function mapClick(e){const r=e.target.closest('[data-cell-id]');if(r)navigate({cell:Number(r.dataset.cellId)});}
$('cell-map').addEventListener('click',mapClick);$('cell-map').addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();mapClick(e);}});
$('recommended-cases').addEventListener('click',e=>{const b=e.target.closest('[data-case]');if(b)navigate({cell:Number(b.dataset.case)});});
$('pair-select').addEventListener('change',()=>changeEvidence($('pair-select').value,null));$('anchor-select').addEventListener('change',()=>changeEvidence($('pair-select').value,Number($('anchor-select').value)));
document.querySelectorAll('[data-photo-action]').forEach(b=>b.addEventListener('click',async()=>{const p=photos[b.dataset.photo],action=b.dataset.photoAction;if(!p.loaded)return;if(action==='full'){const dialog=$('lightbox');$('lightbox-title').textContent=(b.dataset.photo==='reference'?'현재 원본 영상 A':'현재 원본 영상 B')+' · '+p.info.name;dialog.showModal();try{await photos.lightbox.load(p.info,p.overlays,operation);}catch(e){if(e.name!=='AbortError')fail(e);}}else p[action==='actual'?'actual':action]();}));
$('lightbox-close').addEventListener('click',()=>$('lightbox').close());$('lightbox-fit').addEventListener('click',()=>photos.lightbox.fit());$('lightbox-actual').addEventListener('click',()=>photos.lightbox.actual());$('lightbox-focus').addEventListener('click',()=>photos.lightbox.focus());$('lightbox-fullscreen').addEventListener('click',async()=>{try{if(document.fullscreenElement)await document.exitFullscreen();else await $('lightbox').requestFullscreen();photos.lightbox.draw();}catch(error){$('lightbox-title').textContent='전체 화면을 사용할 수 없습니다. 확대 창에서 계속 확인하세요.';}});
$('cloud-reset').addEventListener('click',()=>cloud.reset());for(const s of ['mvs','als'])$('source-'+s).addEventListener('change',()=>cloud.draw());document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>cloud.setView(b.dataset.view)));$('point-color').addEventListener('change',()=>cloud.updateColors());$('view-scope').addEventListener('change',async()=>{const ctx=begin();try{await loadCloud(ctx);finish(ctx.id);}catch(error){fail(error,ctx.id);}});
$('retry').addEventListener('click',()=>navigate({force:true}));
window.addEventListener('popstate',()=>{const q=new URLSearchParams(location.search);navigate({region:q.get('region')||state.region,cell:Number(q.get('cell')),stage:Number(q.get('stage'))||1});});
async function start(){const ctx=begin();try{cloud=new Cloud();manifest=await getJSON('/api/manifest',ctx.signal);if(!Array.isArray(manifest.regions)||!manifest.regions.length)throw new Error('표시할 실험 영역이 없습니다.');$('task-label').textContent=manifest.task_id;$('seal-label').textContent='동결 '+String(manifest.method_seal_sha256||'').slice(0,10);$('region-tabs').innerHTML=manifest.regions.map(r=>`<button type="button" data-region="${esc(r.id)}" data-testid="region-${esc(r.id)}" aria-selected="false">${esc(r.id)}</button>`).join('');const query=new URLSearchParams(location.search),region=manifest.regions.find(r=>r.id===query.get('region'))||manifest.regions[0],stage=[1,2,3].includes(Number(query.get('stage')))?Number(query.get('stage')):1,cell=query.has('cell')?Number(query.get('cell')):region.default_cell_id;await navigate({region:region.id,cell,stage});}catch(error){fail(error);}}
start();
