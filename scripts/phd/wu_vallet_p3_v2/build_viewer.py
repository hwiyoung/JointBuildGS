"""Offline viewer of native-source Wu--Vallet point update artifacts, no GS.

Counts and downloads retain every native point. The browser uses an explicitly
declared deterministic DISPLAY_ONLY subset, always indexed into the exact input.
This script never changes labels, performs fusion, or infers a scientific verdict.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import time

import numpy as np


LABELS = ["consistent", "changed", "single", "unassessed"]


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write(path, data):
    with Path(path).open("x") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


HTML = r'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>P3 · Wu–Vallet 점군 갱신</title><link rel="icon" href="data:,"><style>
:root{--ink:#172d3d;--muted:#587080;--border:#dce4e9;--blue:#1876a0;--old:#b88742;--new:#268dc0;--changed:#d44952;--same:#26a68b;--single:#92a0aa;--unassessed:#5e5279}*{box-sizing:border-box}body{margin:0;color:var(--ink);background:#f0f4f6;font:15px/1.6 system-ui,-apple-system,"Noto Sans KR",sans-serif}main{max-width:1640px;padding:28px 24px 60px;margin:auto}h1{font-size:31px;letter-spacing:-1px;line-height:1.3;margin:9px 0 13px}h2{font-size:21px;margin:0 0 6px}h3{font-size:16px;margin:0}p{margin:8px 0}.eyebrow{font-size:12px;color:var(--blue);font-weight:750;letter-spacing:1px}.lead,.muted{color:var(--muted)}.notice{border-left:4px solid #c2933e;background:#fff7e5;padding:14px 18px;margin:20px 0}.notice p{margin:5px 0}.tag{display:inline-block;background:#e0ebf1;border-radius:20px;padding:3px 10px;font-size:12px;margin:4px 6px 0 0}.card{background:white;border:1px solid var(--border);border-radius:12px;padding:21px;margin:22px 0}.controls{display:flex;flex-wrap:wrap;align-items:center;gap:12px;margin:15px 0}.control{display:flex;gap:8px;align-items:center;min-width:0;max-width:100%}.control span{font-size:13px;font-weight:650;flex-shrink:0}button,select{font:inherit;border:1px solid #c6d3dd;background:#fff;color:var(--ink);border-radius:7px;padding:7px 10px;max-width:100%;min-width:0}button{cursor:pointer}button:hover{background:#eef5f8}a{color:var(--blue)}button:focus-visible,select:focus-visible,a:focus-visible{outline:3px solid #dba331;outline-offset:2px}.view-grid{display:grid;grid-template-columns:minmax(0,1fr) 270px;gap:18px}.viewport{position:relative;background:#eef3f6;border:1px solid var(--border);border-radius:9px;overflow:hidden;min-width:0;height:560px}.viewport canvas{display:block;width:100%;height:100%;touch-action:none}.viewport .corner{position:absolute;left:13px;top:10px;font-size:12px;pointer-events:none;color:#3c5768;background:#ffffffcf;border-radius:5px;padding:4px 7px}.stats{display:grid;grid-template-columns:1fr;gap:9px}.stat{background:#f4f7f9;border-radius:8px;padding:11px 14px}.stat b{font-size:21px;font-variant-numeric:tabular-nums;display:block;line-height:1.4}.stat span{font-size:12px;color:var(--muted)}.legend{display:flex;gap:12px;flex-wrap:wrap;font-size:12px;margin:12px 0}.swatch{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px}.small{font-size:12px}.two{display:grid;grid-template-columns:1fr 1fr;gap:20px}.plot{height:370px;min-width:0;border:1px solid var(--border);border-radius:8px;overflow:hidden;background:#fbfcfd}.plot canvas{display:block;width:100%;height:100%}.table-wrap{overflow:auto;max-width:100%;border:1px solid var(--border);border-radius:8px;margin-top:14px}table{width:100%;border-collapse:collapse;font-size:13px;white-space:nowrap;font-variant-numeric:tabular-nums;text-align:right}th,td{padding:10px 12px;border-bottom:1px solid var(--border)}th{background:#edf4f7;font-size:12px}th:first-child,td:first-child{text-align:left}tr.selected td{background:#e7f2f7}tr[data-arm]{cursor:pointer}tbody tr:last-child td{border:0}.mono{font:12px/1.55 ui-monospace,monospace;overflow-wrap:anywhere;white-space:pre-wrap}details{padding:12px 0;border-bottom:1px solid var(--border)}summary{cursor:pointer;font-weight:650}.links{display:flex;flex-wrap:wrap;gap:15px;margin:13px 0}.error{background:#ffe2e2;color:#921c26;padding:15px;border-radius:9px}footer{font-size:12px;color:var(--muted)}#loading{font-size:13px;color:var(--muted)}
@media(max-width:900px){main{padding:18px 12px 45px}.card{padding:16px}.view-grid{grid-template-columns:1fr}.stats{grid-template-columns:repeat(2,minmax(0,1fr))}.two{grid-template-columns:1fr}.viewport{height:420px}.plot{height:340px}h1{font-size:26px}.stat b{font-size:19px}.control{width:100%}.control select{flex:1}.controls button{flex:1} .mono{font-size:11px}}
</style></head><body><main><header><div class="eyebrow">JOINTBUILDGS · P3 · POINT CLOUD UPDATE</div><h1>Wu–Vallet은 어떤 점을 남기고 바꾸는가</h1><p class="lead">과거 ALS와 현재 영상 센서 점군을 비교하여, 유지·삭제·추가한 점과 최종 갱신 점군을 확인합니다. 동일 P3 범위에서 광선 방향과 거리 허용값의 영향을 나란히 봅니다.</p><span class="tag">원래 산출물: 갱신 점군</span><span class="tag">비확증 개발 실행</span><span class="tag">scientific_verdict: null</span></header>
<div class="notice"><strong>논문 기반 구현이며 저자 코드의 동일 재현은 아닙니다.</strong><p>과거 ALS 센서 위치를 추정한 조건과 현재 영상 광선만 사용한 조건을 구분합니다. 현재 영상 점군은 COLMAP 깊이를 사용하므로 논문의 PSMNet 입력 생성과도 다릅니다. 추정 위치의 오차와 입력 대체의 영향을 포함한 결과입니다.</p><p id="scope-detail" class="small"></p></div>
<div id="loading">점군과 실행 기록을 불러오는 중입니다.</div><div id="error" class="error" hidden></div>
<section class="card"><h2>원점과 갱신 결과</h2><p class="muted">드래그로 회전하고 휠로 확대합니다. 아래 3D와 지도는 같은 표시 점을 사용하며, 점의 색은 출처·판정입니다. 사진이나 Gaussian 렌더가 아닙니다.</p><div class="controls"><label class="control"><span>실행 조건</span><select id="arm-select" aria-label="실행 조건"></select></label><label class="control"><span>표시할 점</span><select id="mode-select" aria-label="표시할 점"><option value="updated">갱신 점군 · 출처 색</option><option value="inputs">두 입력 · 출처 색</option><option value="labels">두 입력 · 구현 판정 색</option><option value="removed">삭제된 과거 ALS</option><option value="added">추가된 현재 영상 점</option></select></label><button id="reset-view">3D 초기 시점</button><button id="top-view">위에서 보기</button></div><div class="view-grid"><div class="viewport" id="viewport"><div class="corner" id="view-caption"></div></div><aside><div class="stats" id="stats"></div><div class="legend" id="legend"></div><p class="small muted" id="display-count"></p><p class="small muted" id="direction-note"></p></aside></div></section>
<section class="card"><h2>같은 위치의 지도와 단면</h2><p class="muted">위에서 선택한 점을 XY 지도와 고정 단면에서 함께 봅니다. 단면 표본은 전체 원점에서 직접 선택하므로 3D 표시용 샘플링에 의해 사라지지 않습니다.</p><div class="controls"><label class="control"><span>단면 위치</span><select id="section-select"><option value="x">X = −40 m · Y–Z 단면</option><option value="y">Y = −15 m · X–Z 단면</option></select></label></div><div class="two"><div><h3>XY 출처·판정 지도</h3><div class="plot"><canvas id="map-canvas" aria-label="XY 지도"></canvas></div></div><div><h3 id="section-title">고정 단면</h3><div class="plot"><canvas id="section-canvas" aria-label="고정 단면"></canvas></div></div></div><p class="small muted" id="section-count"></p></section>
<section class="card"><h2>실행 조건별 유지·삭제·추가</h2><p class="muted">모든 수는 P3의 원래 점 전체에서 계산합니다. 점 수의 증가·감소 자체가 정확도나 개선을 뜻하지 않습니다. 행을 누르면 해당 조건으로 이동합니다.</p><div class="table-wrap"><table><thead><tr><th>실행 조건</th><th>광선 방향</th><th>허용 거리</th><th>소영역 문턱</th><th>유지 ALS</th><th>삭제 ALS</th><th>추가 영상 점</th><th>갱신 전체</th></tr></thead><tbody id="arm-table"></tbody></table></div><div id="evaluation-panel" hidden><h3 style="margin-top:20px">평가 기록</h3><p class="small muted">평가 전용 참조와의 비교입니다. 판정이나 매개변수 선택에 이 참조를 사용하지 않았으며, 좌표계·시점·밀도 차이의 제한을 함께 읽어야 합니다.</p><p class="small muted" id="evaluation-summary"></p><div class="table-wrap"><table><thead><tr><th>입력 / 갱신 조건</th><th>전체 점 수</th><th>점군 → UAS p90</th><th>UAS → 점군 p90</th><th>참조 셀의 점군 누락</th></tr></thead><tbody id="evaluation-table"></tbody></table></div><div class="links" id="evaluation-links"><a href="receipts/evaluation.json">전체 평가 JSON</a></div></div></section>
<section class="card"><h2>확인 범위와 원본 산출물</h2><p>일치한 점은 과거 ALS를 유지하고 현재 영상의 중복 점을 제외합니다. 변경으로 판정한 과거 점은 삭제하고 현재 점을 추가합니다. 단독 관측·가려진 부분에 남은 과거 점의 현재 적합성은 별도로 검증해야 합니다.</p><details open><summary>GPS time과 과거 센서 위치가 하는 일</summary><p class="muted">GPS time은 점의 취득 순서와 스캔 구조 복원에 쓰입니다. 센서 위치가 있으면 각 점까지 비어 있어야 하는 광선 구간을 검사할 수 있습니다. 현재 영상 광선만 사용하면 현재 관측 앞에 있는 낡은 ALS를 제거할 수 있지만, 신축 구조 뒤에 있는 과거 면은 같은 방식으로 배제할 수 없습니다. 추정 ALS 광선의 결과는 이 누락을 줄일 가능성과 추정 오차의 영향을 함께 포함합니다.</p></details><details><summary>표시와 원자료 출처</summary><pre class="mono" id="provenance"></pre></details><div class="links"><a href="viewer_manifest.json">뷰어 출처·해시</a><a href="receipts/update_receipt.json">전체 실행 기록</a><a href="downloads/common.npz">P3 두 입력 NPZ</a><a id="arm-json" href="#">선택 조건 실행 JSON</a><a id="arm-npz" href="#">선택 조건 갱신 NPZ</a><a id="arm-ply" href="#">선택 조건 갱신 PLY</a></div></section><footer>원점·분류·갱신 산출물은 보존됩니다. 이 화면은 Wu–Vallet 기반 점군 갱신의 개발 결과이며 방법 우위나 과학적 판정을 대신하지 않습니다.</footer>
<script id="evidence-data" type="application/json">__DATA__</script><script type="module">
import * as THREE from './three.module.min.js';
const d=JSON.parse(document.getElementById('evidence-data').textContent),$=id=>document.getElementById(id),count=x=>Number(x).toLocaleString('ko-KR'),colors={old:'#b88742',new:'#268dc0',consistent:'#26a68b',changed:'#d44952',single:'#92a0aa',unassessed:'#5e5279'},labelNames={old:'과거 ALS',new:'현재 영상',consistent:'일치',changed:'변경',single:'단독 관측',unassessed:'미판정'};
window.__WV_QA={ready:false,arm:null,mode:null,frames:0,errors:[],assets:[]};
async function binary(path,Type){const r=await fetch(path);if(!r.ok)throw Error(path+' HTTP '+r.status);const b=await r.arrayBuffer();window.__WV_QA.assets.push(path);return new Type(b);}
let current=d.arms.find(a=>a.name===d.default_arm)??d.arms[0],mode='updated',section='x',oldXYZ,newXYZ,oldSections={},newSections={},armCache=new Map(),active,selected={old:[],new:[]},scene,camera,renderer,group,azimuth=-.65,elevation=.72,zoom=1;
const center=d.bounds.min.map((v,i)=>(v+d.bounds.max[i])/2),span=Math.max(...d.bounds.max.map((v,i)=>v-d.bounds.min[i]));
function colorFor(side,label){return mode==='labels'?colors[d.labels[label]]:mode==='removed'?colors.changed:colors[side];}
function included(side,label,keep){if(mode==='inputs'||mode==='labels')return true;if(mode==='updated')return keep===1;if(mode==='removed')return side==='old'&&keep===0;return side==='new'&&keep===1;}
function setCamera(){const w=$('viewport').clientWidth,h=$('viewport').clientHeight,scale=span*.74/zoom*Math.max(1,h/w);camera.left=-scale*w/h;camera.right=scale*w/h;camera.top=scale;camera.bottom=-scale;camera.position.set(center[0]+span*3*Math.cos(azimuth)*Math.cos(elevation),center[1]+span*3*Math.sin(azimuth)*Math.cos(elevation),center[2]+span*3*Math.sin(elevation));camera.up.set(0,0,1);camera.lookAt(...center);camera.updateProjectionMatrix();renderer.setSize(w,h,false);draw();}
function draw(){renderer.render(scene,camera);window.__WV_QA.frames++;}
function rebuildCloud(){if(!active)return;for(const obj of [...group.children]){group.remove(obj);obj.geometry.dispose();obj.material.dispose();}selected={old:[],new:[]};for(const side of ['old','new']){const xyz=side==='old'?oldXYZ:newXYZ,pos=[],col=[],labels=active[side+'Labels'],keep=active[side+'Keep'];for(let i=0;i<labels.length;i++){if(!included(side,labels[i],keep[i]))continue;selected[side].push(i);pos.push(xyz[3*i],xyz[3*i+1],xyz[3*i+2]);const c=new THREE.Color(colorFor(side,labels[i]));col.push(c.r,c.g,c.b);}const geo=new THREE.BufferGeometry();geo.setAttribute('position',new THREE.Float32BufferAttribute(pos,3));geo.setAttribute('color',new THREE.Float32BufferAttribute(col,3));const material=new THREE.PointsMaterial({size:1.7,sizeAttenuation:false,vertexColors:true,transparent:false});group.add(new THREE.Points(geo,material));}draw();drawPlots();$('view-caption').textContent=current.name+' · '+$('mode-select').selectedOptions[0].textContent;$('display-count').textContent=`표시 ${count(selected.old.length+selected.new.length)}점. 입력 전체 ALS ${count(d.sources.old.native_count)}점 / 영상 ${count(d.sources.new.native_count)}점. 3D·지도만 소스당 최대 ${count(d.display_cap)}점을 결정적 순서로 표시합니다.`;window.__WV_QA.arm=current.name;window.__WV_QA.mode=mode;window.__WV_QA.visiblePoints={old:selected.old.length,new:selected.new.length};window.__WV_QA.ready=true;}
function setupCanvas(canvas){const rect=canvas.parentElement.getBoundingClientRect(),ratio=Math.min(devicePixelRatio,2);canvas.width=Math.round(rect.width*ratio);canvas.height=Math.round(rect.height*ratio);const ctx=canvas.getContext('2d');ctx.scale(ratio,ratio);ctx.fillStyle='#fbfcfd';ctx.fillRect(0,0,rect.width,rect.height);return {ctx,w:rect.width,h:rect.height};}
function axes(canvas,xb,yb,xlabel,ylabel){const {ctx,w,h}=setupCanvas(canvas),pad={l:54,r:17,t:20,b:43},sx=(w-pad.l-pad.r)/(xb[1]-xb[0]),sy=(h-pad.t-pad.b)/(yb[1]-yb[0]),fx=x=>pad.l+(x-xb[0])*sx,fy=y=>h-pad.b-(y-yb[0])*sy;ctx.font='11px system-ui';ctx.lineWidth=1;for(let i=0;i<=4;i++){const x=xb[0]+(xb[1]-xb[0])*i/4,y=yb[0]+(yb[1]-yb[0])*i/4;ctx.strokeStyle='#e5ebef';ctx.beginPath();ctx.moveTo(fx(x),pad.t);ctx.lineTo(fx(x),h-pad.b);ctx.moveTo(pad.l,fy(y));ctx.lineTo(w-pad.r,fy(y));ctx.stroke();ctx.fillStyle='#627684';ctx.textAlign='center';ctx.fillText(x.toFixed(1),fx(x),h-pad.b+17);ctx.textAlign='right';ctx.fillText(y.toFixed(1),pad.l-7,fy(y)+4);}ctx.fillStyle='#405c6c';ctx.textAlign='center';ctx.fillText(xlabel,w/2,h-6);ctx.save();ctx.translate(13,h/2);ctx.rotate(-Math.PI/2);ctx.fillText(ylabel,0,0);ctx.restore();return {ctx,fx,fy};}
function drawPlots(){if(!active)return;const map=axes($('map-canvas'),[d.bounds.min[0],d.bounds.max[0]],[d.bounds.min[1],d.bounds.max[1]],'X · scene-local m','Y · scene-local m');for(const side of ['old','new']){const xyz=side==='old'?oldXYZ:newXYZ;for(const i of selected[side]){map.ctx.fillStyle=colorFor(side,active[side+'Labels'][i]);map.ctx.fillRect(map.fx(xyz[3*i])-0.6,map.fy(xyz[3*i+1])-0.6,1.2,1.2);}}const axis=section==='x'?1:0,at=section==='x'?d.sections.x:d.sections.y;map.ctx.strokeStyle='#162f3f';map.ctx.lineWidth=1.6;map.ctx.setLineDash([5,4]);map.ctx.beginPath();if(section==='x'){map.ctx.moveTo(map.fx(at),map.fy(d.bounds.min[1]));map.ctx.lineTo(map.fx(at),map.fy(d.bounds.max[1]));}else{map.ctx.moveTo(map.fx(d.bounds.min[0]),map.fy(at));map.ctx.lineTo(map.fx(d.bounds.max[0]),map.fy(at));}map.ctx.stroke();const plot=axes($('section-canvas'),[d.bounds.min[axis],d.bounds.max[axis]],[d.bounds.min[2],d.bounds.max[2]],(axis===0?'X':'Y')+' · scene-local m','Z · scene-local m');let n=0;for(const side of ['old','new']){const xyz=(side==='old'?oldSections:newSections)[section],labels=active[side+'SectionLabels'][section],keep=active[side+'SectionKeep'][section];for(let i=0;i<labels.length;i++){if(!included(side,labels[i],keep[i]))continue;plot.ctx.fillStyle=colorFor(side,labels[i]);plot.ctx.fillRect(plot.fx(xyz[3*i+axis])-1,plot.fy(xyz[3*i+2])-1,2,2);n++;}}$('section-title').textContent=`${section.toUpperCase()} = ${at} m · 폭 ${d.sections.width} m`;$('section-count').textContent=`단면 표시 ${count(n)}점 · 전체 원점에서 |${section.toUpperCase()} − ${at}| ≤ ${d.sections.width/2} m로 선택. 좌표는 작업 원점 이동 후 미터 단위입니다.`;window.__WV_QA.section=section;window.__WV_QA.sectionPoints=n;}
function updateText(){const c=current.counts;$('stats').replaceChildren();for(const [name,value] of [['유지한 과거 ALS',c.retained_old],['삭제한 과거 ALS',c.removed_old],['추가한 현재 영상 점',c.admitted_new],['최종 갱신 점',c.updated]]){const el=document.createElement('div');el.className='stat';el.innerHTML='<span></span><b></b>';el.children[0].textContent=name;el.children[1].textContent=count(value);$('stats').append(el);}$('legend').replaceChildren();for(const key of (mode==='labels'?d.labels:mode==='removed'?['changed']:['old','new'])){const el=document.createElement('span'),swatch=document.createElement('i');swatch.className='swatch';swatch.style.background=colors[key];el.append(swatch,document.createTextNode(labelNames[key]));$('legend').append(el);}$('direction-note').textContent=current.direction_mode==='ONLY_CURRENT_IMAGE_RAYS'?'현재 영상 → ALS만 실행했습니다. 현재 관측 뒤쪽의 과거 면은 과거 광선 없이 배제할 수 없습니다.':'추정한 ALS 센서 위치와 현재 영상 위치에서 양방향 광선을 실행했습니다. ALS 광선의 근사는 별도 불확실성입니다.';$('direction-note').textContent+=` ALS ${count(c.old_labels.unassessed)}점은 메시 미지원으로 미판정 상태에서 보존했습니다.`;for(const row of $('arm-table').children)row.classList.toggle('selected',row.dataset.arm===current.name);for(const ext of ['json','npz','ply'])$('arm-'+ext).href=current.downloads[ext];}
async function switchArm(name){window.__WV_QA.ready=false;current=d.arms.find(a=>a.name===name);$('arm-select').value=name;if(!armCache.has(name)){const b=current.display,entry={};for(const side of ['old','new']){entry[side+'Labels']=await binary(b[side].labels,Uint8Array);entry[side+'Keep']=await binary(b[side].keep,Uint8Array);entry[side+'SectionLabels']={};entry[side+'SectionKeep']={};for(const s of ['x','y']){entry[side+'SectionLabels'][s]=await binary(b[side].sections[s].labels,Uint8Array);entry[side+'SectionKeep'][s]=await binary(b[side].sections[s].keep,Uint8Array);}}armCache.set(name,entry);}active=armCache.get(name);updateText();rebuildCloud();}
try{oldXYZ=await binary(d.sources.old.display_xyz,Float32Array);newXYZ=await binary(d.sources.new.display_xyz,Float32Array);for(const s of ['x','y']){oldSections[s]=await binary(d.sources.old.sections[s].xyz,Float32Array);newSections[s]=await binary(d.sources.new.sections[s].xyz,Float32Array);}scene=new THREE.Scene();scene.background=new THREE.Color('#eef3f6');camera=new THREE.OrthographicCamera(-1,1,1,-1,.01,span*100);renderer=new THREE.WebGLRenderer({antialias:true,preserveDrawingBuffer:true});renderer.setPixelRatio(Math.min(devicePixelRatio,1.5));$('viewport').append(renderer.domElement);group=new THREE.Group();scene.add(group);const axesHelper=new THREE.AxesHelper(span*.2);axesHelper.position.set(d.bounds.min[0],d.bounds.min[1],d.bounds.min[2]);scene.add(axesHelper);const grid=new THREE.GridHelper(span,10,'#c5d2db','#dbe4ea');grid.rotation.x=Math.PI/2;grid.position.set(center[0],center[1],d.bounds.min[2]);scene.add(grid);let drag=null;renderer.domElement.onpointerdown=e=>{drag=[e.clientX,e.clientY];renderer.domElement.setPointerCapture(e.pointerId);};renderer.domElement.onpointerup=()=>drag=null;renderer.domElement.onpointermove=e=>{if(!drag)return;azimuth-=(e.clientX-drag[0])*.006;elevation=Math.max(.02,Math.min(1.56,elevation+(e.clientY-drag[1])*.006));drag=[e.clientX,e.clientY];setCamera();};renderer.domElement.addEventListener('wheel',e=>{e.preventDefault();zoom=Math.max(.3,Math.min(8,zoom*Math.exp(-e.deltaY*.001)));setCamera();},{passive:false});for(const arm of d.arms){const option=document.createElement('option');option.value=arm.name;option.textContent=arm.name;$('arm-select').append(option);const row=document.createElement('tr');row.dataset.arm=arm.name;for(const value of [arm.name,arm.direction_mode==='ONLY_CURRENT_IMAGE_RAYS'?'현재 영상 → ALS':'추정 ALS ↔ 현재 영상',arm.tolerance_m+' m',arm.small_region_area_m2+' m²',...['retained_old','removed_old','admitted_new','updated'].map(k=>count(arm.counts[k]))]){const cell=document.createElement('td');cell.textContent=value;row.append(cell);}row.onclick=()=>switchArm(arm.name).catch(fail);$('arm-table').append(row);} $('arm-select').onchange=()=>switchArm($('arm-select').value).catch(fail);$('mode-select').onchange=()=>{mode=$('mode-select').value;updateText();rebuildCloud();};$('section-select').options[0].textContent=`X = ${d.sections.x} m · Y–Z 단면`;$('section-select').options[1].textContent=`Y = ${d.sections.y} m · X–Z 단면`;$('section-select').onchange=()=>{section=$('section-select').value;drawPlots();};$('reset-view').onclick=()=>{azimuth=-.65;elevation=.72;zoom=1;setCamera();};$('top-view').onclick=()=>{azimuth=-Math.PI/2;elevation=1.56;setCamera();};new ResizeObserver(()=>{setCamera();drawPlots();}).observe($('viewport'));window.addEventListener('resize',drawPlots);$('scope-detail').textContent=`${d.arms.length}개 실행 조건 · 현재 영상 ${d.image_id??'133'} · 원문 미기재 판정 문턱과 샘플링 규칙은 실행 JSON에 명시했습니다.`;$('provenance').textContent=JSON.stringify({source_paths:d.source_paths,display_rule:d.display_rule,coordinates:d.coordinates,scientific_verdict:null},null,2);if(d.evaluation){$('evaluation-panel').hidden=false;$('evaluation-summary').textContent='참조 헤더 EPSG:32632 / 작업 표기 EPSG:25832. 이번 평가는 재투영·정합 없이 기존 수치 좌표의 원점 이동만 사용했습니다. 거리값은 이에 조건부이며 절대 정확도 인증이 아닙니다.';for(const [name,value] of Object.entries(d.evaluation.methods??{})){const row=document.createElement('tr'),nn=value.native_3d_nearest_distances,grid=value.xy_height_grid;for(const item of [name==='native_als'?'원 ALS':name==='native_image'?'현재 영상 센서 점':name,count(value.point_count),nn.prediction_to_reference.p90_m.toFixed(3)+' m',nn.reference_to_prediction.p90_m.toFixed(3)+' m',count(grid.missing_prediction_on_reference_cells)+' / '+count(grid.reference_occupied_cells)]){const cell=document.createElement('td');cell.textContent=item;row.append(cell);}$('evaluation-table').append(row);}for(const [name,path] of Object.entries(d.evaluation_figures??{})){const link=document.createElement('a');link.href=path;link.textContent=name==='height_comparison.png'?'전체 점 높이 비교 그림':'전체 점 공통 단면 그림';$('evaluation-links').append(link);}}setCamera();await switchArm(current.name);$('loading').hidden=true;}
catch(error){fail(error);}function fail(error){window.__WV_QA.errors.push(String(error));$('error').hidden=false;$('error').textContent='표시 실패: '+String(error);console.error(error);}
</script></main></body></html>'''


def main(config, output):
    if not Path("/.dockerenv").exists():
        raise RuntimeError("Build this project artifact in Docker")
    started = time.monotonic()
    cfg = read(config)
    if cfg.get("scientific_verdict", "missing") is not None:
        raise ValueError("scientific_verdict must be null")
    run = Path(cfg["update_root"])
    receipt = read(run / "receipt.json")
    if receipt.get("scientific_verdict", "missing") is not None or not receipt.get("arms"):
        raise ValueError("Completed update receipt with arms and null verdict required")
    if output.exists():
        raise FileExistsError("New viewer output required")
    output.mkdir(parents=True, exist_ok=False)
    copied, derivatives, inputs = {}, {}, {}

    def copy(source, relative):
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        digest = sha(source)
        shutil.copy2(source, destination)
        if sha(destination) != digest:
            raise ValueError("Copied artifact hash mismatch")
        copied[relative] = {"source": str(source), "sha256": digest, "bytes": destination.stat().st_size}
        inputs[str(source)] = digest
        return relative

    def binary(array, relative, dtype):
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as handle:
            np.asarray(array, dtype=dtype).tofile(handle)
        derivatives[relative] = {"sha256": sha(destination), "bytes": destination.stat().st_size,
                                 "dtype": np.dtype(dtype).str, "shape": list(np.asarray(array).shape),
                                 "role": "DISPLAY_ONLY_never_used_for_classification_or_metrics"}
        return relative

    copy(run / "receipt.json", "receipts/update_receipt.json")
    copy(run / "common.npz", "downloads/common.npz")
    repo = Path(__file__).resolve().parents[3]
    copy(repo / "src/apps/gs3d_4way_viewer/build/three.module.min.js", "three.module.min.js")
    copy(config, "receipts/viewer_config.json")
    common = np.load(run / "common.npz", allow_pickle=False)
    xyz = {side: np.asarray(common[f"{side}_xyz"], dtype=np.float64) for side in ("old", "new")}
    for side, points in xyz.items():
        if points.ndim != 2 or points.shape[1] != 3 or not np.isfinite(points).all():
            raise ValueError(f"Invalid native {side} geometry")
    cap = int(cfg["maximum_display_points_per_source"])
    if cap < 1:
        raise ValueError("Positive display cap required")
    indices = {side: np.arange(len(points), dtype=np.int64)[::max(1, int(np.ceil(len(points) / cap)))] for side, points in xyz.items()}
    sections = {"x": float(cfg["section_x_m"]), "y": float(cfg["section_y_m"]), "width": float(cfg["section_full_width_m"])}
    sec_indices = {side: {key: np.flatnonzero(np.abs(points[:, axis] - sections[key]) <= sections["width"] / 2)
                          for key, axis in (("x", 0), ("y", 1))} for side, points in xyz.items()}
    sources = {}
    for side in ("old", "new"):
        sources[side] = {
            "native_count": len(xyz[side]), "display_count": len(indices[side]),
            "display_xyz": binary(xyz[side][indices[side]], f"display/{side}_xyz.bin", "<f4"),
            "display_indices": binary(indices[side], f"display/{side}_indices.bin", "<i8"),
            "sections": {key: {"native_count": len(ids),
                                "xyz": binary(xyz[side][ids], f"display/{side}_section_{key}_xyz.bin", "<f4"),
                                "indices": binary(ids, f"display/{side}_section_{key}_indices.bin", "<i8")}
                         for key, ids in sec_indices[side].items()},
        }
    arms = []
    for entry in receipt["arms"]:
        name = entry["name"]
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
            raise ValueError("Unsafe arm name")
        root = run / name
        result = read(root / "result.json")
        payload = np.load(root / "updated_points.npz", allow_pickle=False)
        counts, display = {}, {}
        expected_parts = []
        for side in ("old", "new"):
            labels, keep = payload[f"{side}_labels"], np.asarray(payload[f"{side}_keep_mask"], dtype=bool)
            if labels.shape != (len(xyz[side]),) or keep.shape != labels.shape or not np.isin(labels, LABELS).all():
                raise ValueError(f"Native label/membership mismatch: {name}/{side}")
            label_ids = np.array([LABELS.index(label) for label in labels], dtype=np.uint8)
            display[side] = {
                "labels": binary(label_ids[indices[side]], f"display/{name}/{side}_labels.bin", "u1"),
                "keep": binary(keep[indices[side]], f"display/{name}/{side}_keep.bin", "u1"),
                "sections": {key: {"labels": binary(label_ids[ids], f"display/{name}/{side}_section_{key}_labels.bin", "u1"),
                                    "keep": binary(keep[ids], f"display/{name}/{side}_section_{key}_keep.bin", "u1")}
                             for key, ids in sec_indices[side].items()},
            }
            counts[f"{side}_labels"] = {label: int(np.count_nonzero(labels == label)) for label in LABELS}
            counts["retained_old" if side == "old" else "admitted_new"] = int(keep.sum())
            if side == "old":
                counts["removed_old"] = int((~keep).sum())
            expected_parts.append(xyz[side][keep])
        expected = np.concatenate(expected_parts)
        actual = payload["updated_points"]
        if actual.shape != expected.shape or not np.allclose(actual, expected, rtol=0, atol=1e-7):
            raise ValueError(f"Updated XYZ does not match native-source membership: {name}")
        expected_source = np.r_[np.zeros(len(expected_parts[0]), dtype=np.int8), np.ones(len(expected_parts[1]), dtype=np.int8)]
        if not np.array_equal(payload["updated_source"], expected_source):
            raise ValueError(f"Updated source ordering mismatch: {name}")
        counts["updated"] = len(actual)
        downloads = {"json": copy(root / "result.json", f"receipts/{name}.json"),
                     "npz": copy(root / "updated_points.npz", f"downloads/{name}.npz"),
                     "ply": copy(root / "updated_points.ply", f"downloads/{name}.ply")}
        arms.append({"name": name, "direction_mode": entry.get("direction_mode", result.get("direction_mode")),
                     "tolerance_m": entry.get("tolerance_m", result.get("tolerance_m")),
                     "small_region_area_m2": entry.get("small_region_area_m2", result.get("small_region_area_m2", 0)),
                     "counts": counts, "display": display, "downloads": downloads})
    if len({arm["name"] for arm in arms}) != len(arms):
        raise ValueError("Duplicate arm names")
    merged = np.concatenate(list(xyz.values()))
    if not len(merged):
        raise ValueError("No native points")
    evaluation, evaluation_figures = None, {}
    epath = Path(cfg["evaluation_root"]) / "evaluation.json"
    if epath.is_file():
        evaluation = read(epath)
        if evaluation.get("scientific_verdict", "missing") is not None:
            raise ValueError("Evaluation scientific_verdict must be null")
        copy(epath, "receipts/evaluation.json")
        for name in ("height_comparison.png", "cross_sections.png"):
            source = epath.parent / name
            if source.is_file():
                if evaluation.get("outputs", {}).get(name) != sha(source):
                    raise ValueError(f"Evaluation figure hash differs: {name}")
                evaluation_figures[name] = copy(source, f"figures/{name}")
    data = {"schema": cfg["schema"], "task_id": cfg["task_id"], "generated_utc": datetime.now(timezone.utc).isoformat(),
            "scientific_verdict": None, "native_2026_reproduction": False, "arms": arms, "sources": sources,
            "labels": LABELS, "display_cap": cap, "sections": sections,
            "display_rule": "DISPLAY_ONLY_native_input_order_stride_ceil_N_over_cap_no_spatial_aggregation_no_scoring",
            "bounds": {"min": merged.min(axis=0).tolist(), "max": merged.max(axis=0).tolist()},
            "source_paths": {"update": str(run), "evaluation": str(epath) if evaluation else None},
            "coordinates": receipt.get("coordinates", {"working_crs": "EPSG:25832", "display": "scene_local_meters"}),
            "image_id": receipt.get("image_id", 133), "evaluation": evaluation,
            "evaluation_figures": evaluation_figures}
    data["default_arm"] = cfg.get("default_arm") if cfg.get("default_arm") in {arm["name"] for arm in arms} else arms[0]["name"]
    data["default_arm_policy"] = "configured_nominal_tolerance_and_no_region_filter_not_selected_from_performance"
    json_text = json.dumps(data, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c")
    (output / "index.html").write_text(HTML.replace("__DATA__", json_text))
    manifest = {"status": "WU_VALLET_POINT_UPDATE_VIEWER_COMPLETE", "task_id": cfg["task_id"],
                "scientific_verdict": None, "native_2026_reproduction": False,
                "source_receipt": str(run / "receipt.json"), "input_hashes": inputs,
                "copied_assets": copied, "display_derivatives": derivatives,
                "index_sha256": sha(output / "index.html"), "arm_count": len(arms),
                "native_source_counts": {side: len(points) for side, points in xyz.items()},
                "display_source_counts": {side: len(ids) for side, ids in indices.items()},
                "all_arm_native_membership_xyz_and_source_validation": "PASS",
                "evaluation_included": evaluation is not None,
                "runtime_seconds": time.monotonic() - started}
    write(output / "viewer_manifest.json", manifest)
    print(json.dumps({"status": manifest["status"], "arms": len(arms), "output": str(output)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        main(args.config, args.output)
    except Exception as exc:
        if args.output.exists() and not (args.output / "FAILED.json").exists():
            write(args.output / "FAILED.json", {"error": repr(exc), "scientific_verdict": None})
        raise
