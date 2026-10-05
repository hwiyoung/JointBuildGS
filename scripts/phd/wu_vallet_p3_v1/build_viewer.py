"""Build an offline P3 evidence gallery from completed B and evaluation receipts.

Copies actual saved render images and evaluation figures; it does not render,
train, score, select sources, or create replacement images. Docker-only driver.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import time

import cv2
import numpy as np


LABELS = {
    "mvs_color": "MVS · 현재 색",
    "als_color": "ALS · 현재 색",
    "union_color": "MVS + ALS · 현재 색",
    "als_bounded_normal": "ALS · 현재 색과 제한된 기하 수정",
}


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    with Path(path).open("x") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


HTML = r'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>P3 · 입력과 재구성 결과</title><link rel="icon" href="data:,">
<style>
:root{color-scheme:light;--ink:#172b3a;--muted:#556979;--line:#dce4e9;--blue:#176b94;--pale:#eef5f8;--gold:#986111}
*{box-sizing:border-box}body{margin:0;background:#f3f6f8;color:var(--ink);font:15px/1.65 system-ui,-apple-system,"Noto Sans KR",sans-serif}button,select,input{font:inherit}button,select{border:1px solid #bfcdd6;border-radius:8px;background:white;color:var(--ink);padding:7px 12px}button{cursor:pointer}button:hover{background:var(--pale)}button:focus-visible,select:focus-visible,a:focus-visible{outline:3px solid #e1a439;outline-offset:3px}a{color:var(--blue)}.wrap{max-width:1680px;margin:auto;padding:28px 24px 64px}header{display:flex;align-items:flex-start;justify-content:space-between;gap:30px;margin:8px 0 24px}h1{font-size:30px;letter-spacing:-1px;line-height:1.25;margin:10px 0 12px}h2{font-size:22px;letter-spacing:-.5px;line-height:1.4;margin:0 0 8px}h3{font-size:16px;margin:0}p{margin:8px 0}.eyebrow{font-size:12px;letter-spacing:1.2px;font-weight:750;color:var(--blue)}.lead{max-width:940px;color:var(--muted)}.badges{display:flex;flex-wrap:wrap;gap:7px;margin-top:14px}.badge{font-size:12px;padding:3px 10px;border-radius:20px;background:#e3edf3}.badge.amber{background:#f7ead3;color:#795016}.receipt{text-align:right;font-size:12px;white-space:nowrap;color:var(--muted)}.notice{border-left:4px solid #ca9336;background:#fff8e9;padding:13px 18px;margin-bottom:28px}.notice strong{font-weight:700}.section{padding:24px;background:#fff;border:1px solid var(--line);border-radius:14px;margin-top:22px}.sub{color:var(--muted);font-size:14px}.controls{display:flex;flex-wrap:wrap;align-items:center;gap:14px;padding:14px 0 18px}.control{display:flex;align-items:center;gap:8px}.control>span{font-size:13px;font-weight:650}.push{margin-left:auto}.radio-group{display:flex;gap:4px;background:var(--pale);padding:4px;border-radius:10px}.radio-group button{border:0;background:transparent}.radio-group button[aria-pressed=true]{background:#fff;box-shadow:0 1px 4px #0002;color:var(--blue);font-weight:700}.rail{display:grid;grid-template-columns:repeat(5,minmax(235px,1fr));gap:12px;overflow-x:auto;padding-bottom:8px}.card{border:1px solid var(--line);border-radius:10px;overflow:hidden;min-width:0;background:#fafcfd}.card-head{padding:11px 12px;min-height:72px;display:flex;flex-direction:column;justify-content:center}.card-head small{color:var(--muted);font-size:12px}.photo-button{display:block;width:100%;padding:0;border:0;border-radius:0;background:#111b22;position:relative;line-height:0}.photo-button:hover{background:#111b22}.photo{display:block;width:100%;height:auto;aspect-ratio:1.382;object-fit:contain}.mask{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;opacity:.46;mix-blend-mode:screen;pointer-events:none}.mask[hidden]{display:none}.card-foot{font-size:12px;padding:10px 12px;color:var(--muted);min-height:61px}.gallery-hint{font-size:12px;color:var(--muted);margin-top:10px}.table-wrap{overflow-x:auto;border:1px solid var(--line);border-radius:9px;margin-top:14px}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums;white-space:nowrap;text-align:right;font-size:13px}th,td{padding:11px 13px;border-bottom:1px solid #e6ebef}thead{background:var(--pale)}th{font-size:12px;font-weight:700}th:first-child,td:first-child{text-align:left}tbody tr:last-child td{border-bottom:0}.quiet{color:var(--muted)}.figure-tabs{display:flex;flex-wrap:wrap;gap:7px;margin:18px 0 12px}.figure-tabs button[aria-pressed=true]{background:var(--blue);color:white;border-color:var(--blue)}.figure-main{display:block;width:100%;max-height:780px;object-fit:contain;background:white}.figure-button{width:100%;padding:0;border:1px solid var(--line);line-height:0;overflow:hidden}.figure-caption{font-size:13px;color:var(--muted);margin:12px 0}.two-col{display:grid;grid-template-columns:1fr 1fr;gap:24px}.fact{padding:12px 0;border-bottom:1px solid var(--line)}.fact:last-child{border:0}.fact strong{display:block;font-size:13px}.fact span{font-size:13px;color:var(--muted)}details{border-top:1px solid var(--line);padding:16px 0}summary{font-weight:650;cursor:pointer}.links{display:flex;gap:18px;flex-wrap:wrap;margin-top:12px}.mono{font-family:ui-monospace,monospace;font-size:12px;word-break:break-all}.error{padding:10px;background:#ffe4e4;color:#8a1515}dialog{max-width:96vw;max-height:96vh;width:1400px;border:0;border-radius:12px;padding:14px;background:#f6f8fa;color:var(--ink)}dialog::backdrop{background:#111d2bc9}.dialog-head{display:flex;justify-content:space-between;align-items:center;gap:20px;margin-bottom:10px}.dialog-head h3{line-height:1.4}.zoom-wrap{overflow:auto;max-height:82vh;text-align:center}.zoom-wrap img{max-width:100%;height:auto}.dialog-meta{font-size:12px;color:var(--muted);margin-top:8px}footer{font-size:12px;color:var(--muted);padding-top:24px}
.control{min-width:0;max-width:100%}.control select{min-width:0;max-width:100%;flex:1}.control>span{flex-shrink:0}
.receipt{white-space:pre-line;overflow-wrap:anywhere;max-width:100%}
@media(max-width:850px){.wrap{padding:18px 12px 40px}header{display:block}.receipt{text-align:left;margin-top:15px}.section{padding:17px}.two-col{grid-template-columns:1fr;gap:0}.push{margin-left:0}.rail{grid-template-columns:repeat(5,255px)}h1{font-size:25px}.figure-main{max-height:620px}}
</style></head><body><main class="wrap">
<header><div><div class="eyebrow">JOINTBUILDGS · P3 DEVELOPMENT</div><h1>입력부터 실제 재구성까지</h1><p class="lead">현재 영상에서 얻은 MVS와 과거 ALS를 각각 사용했을 때, 현재 사진의 색과 재구성 표면이 어떻게 달라지는지 확인합니다. P3의 지붕과 주변을 같은 범위에서 비교합니다.</p><div class="badges"><span class="badge">비확증 개발 실험</span><span class="badge">소스별 사용을 가정한 비교</span><span class="badge amber">Wu–Vallet 원방법 전체 미재현</span></div></div><div class="receipt" id="receipt"></div></header>
<div class="notice"><strong>이 화면은 사용 판단을 이미 해결한 결과가 아닙니다.</strong> ALS의 정확도나 현재 적합성을 전제하지 않습니다. Wu–Vallet의 원래 갱신 점군과 전체 방법의 우열은 아직 이 실험으로 확인하지 않았습니다. <span class="mono">scientific_verdict: null</span></div>
<section class="section" aria-labelledby="render-title"><h2 id="render-title">현재 사진과 실제 렌더</h2><p class="sub">각 결과는 저장된 Gaussian 렌더입니다. 같은 사진, 같은 평가영역으로 비교하며 검은 배경은 출력이 없는 부분입니다. 기본 화면은 초기 입력의 표면이 있는 범위를 모든 조건에서 똑같이 잘라 보여줍니다. 수치의 분모는 바뀌지 않습니다.</p><div class="controls"><label class="control"><span>평가 사진</span><select id="view-select" aria-label="평가 사진 선택"></select></label><label class="control"><span>표시 범위</span><select id="display-select"><option value="crop">P3 공통 영역 확대</option><option value="full">전체 사진</option></select></label><div class="control"><span>상태</span><div class="radio-group" id="phase-controls"><button data-phase="initial" aria-pressed="false">초기</button><button data-phase="final" aria-pressed="true">학습 후</button></div></div><label class="control"><span>평가영역</span><select id="mask-select"><option value="union">어느 입력이든 표면이 있는 영역</option><option value="intersection">모든 입력에 표면이 있는 영역</option></select></label><label class="control push"><input id="overlay-toggle" type="checkbox"><span>평가영역 덧보기</span></label></div><div class="rail" id="gallery"></div><p class="gallery-hint" id="gallery-hint"></p><div id="image-error" class="error" hidden></div></section>
<section class="section" aria-labelledby="metric-title"><h2 id="metric-title">같은 분모에서 보는 변화</h2><p class="sub" id="metric-sub"></p><div class="table-wrap"><table><thead><tr><th>입력과 처리</th><th>초기 표현 수</th><th>영상 MAE ↓</th><th>표면 없음 / 평가 픽셀</th><th>표면 → UAS p90 ↓</th><th>참조점 중 0.5 m 이내 비율</th><th>참조가 있는 셀의 피복</th></tr></thead><tbody id="metrics-body"></tbody></table></div><p class="sub">UAS는 학습 이후 평가에만 사용했습니다. 참조 원자료는 EPSG:32632, 프로젝트 작업 표기는 EPSG:25832이며 이번 비교에서는 재투영 없이 원점 이동만 적용했습니다. Datum·epoch 연결과 절대 정확도를 새로 보정하지 않았으므로 기존 수치 좌표 연결에 조건부인 거리입니다. 0.5 m 이내 비율은 가까운 출력 표본이 있는 참조점 비율이며, 정확한 구조 복원이 인증됐다는 뜻은 아닙니다. 점 밀도와 시점에 따른 표면 표본 수가 달라 거리 한 값만으로 우열을 정하지 않습니다.</p></section>
<section class="section" aria-labelledby="geometry-title"><h2 id="geometry-title">원소스, 표면 지도, 단면</h2><p class="sub">출처 지도는 데이터가 존재하는 위치를 표시합니다. 색이 어느 소스의 현재 적합성이나 신뢰도를 뜻하지는 않습니다. 재구성 표면은 각 광선에서 여러 Gaussian 평면 교점의 가중 평균 깊이로 추출한 표본입니다. 겹치는 면 사이에 평균값이 생길 수 있어 원래 면의 정확한 복원으로 간주하지 않습니다. 아래 지도와 산점도는 기하 진단이며 위의 실제 카메라 렌더와 구분합니다.</p><div class="figure-tabs" id="figure-tabs"></div><label class="control" id="section-control" hidden><span>조건별 초기·학습 후 단면</span><select id="section-select"></select></label><p class="figure-caption" id="figure-caption"></p><button class="figure-button" id="figure-button" aria-label="기하 그림 크게 보기"><img class="figure-main" id="figure-image" alt=""></button></section>
<section class="section" aria-labelledby="scope-title"><h2 id="scope-title">확인 범위와 출처</h2><div class="two-col"><div><div class="fact"><strong>판단과 재구성</strong><span>이 B 실험은 MVS, ALS, 단순 합집합을 각각 사용한다고 가정합니다. A의 실제 선택 결과를 전달한 전체 방법 실행은 아닙니다.</span></div><div class="fact"><strong>평가 사진</strong><span id="roles"></span></div><div class="fact"><strong>가림과 외관</strong><span>각 소스가 만드는 가시성에 조건부인 비교입니다. 주변 물체의 가림과 반사면의 외관 모호성이 남아 있습니다. 사진 오차 감소만으로 현재 기하 복원을 선언하지 않습니다.</span></div></div><div><div class="fact"><strong>기하 수정의 범위</strong><span id="geometry-limit"></span></div><div class="fact"><strong>좌표와 고정 영역</strong><span id="coordinates"></span></div><div class="fact"><strong>과학적 판정</strong><span>개발 실측을 제공하며 성공·우월성의 과학적 판정은 내리지 않았습니다.</span></div></div></div><details><summary>재현 기록과 원본 수치</summary><p class="sub">이 갤러리는 완료된 산출물을 복사해 보여줍니다. 새 학습·기하 평가나 소스 선택을 수행하지 않습니다.</p><div class="links"><a href="receipts/b_result.json">B 실행 기록</a><a href="receipts/evaluation.json">기하 평가 수치</a><a href="receipts/b_config.json">B 설정</a><a href="receipts/views.json">평가 사진과 카메라</a><a href="viewer_manifest.json">갤러리 출처·해시</a></div><p class="mono" id="source-info"></p></details></section>
<footer>오프라인 파일로 열 수 있습니다. 외부 폰트·스크립트·서비스를 불러오지 않습니다. 그림을 클릭하면 크게 볼 수 있습니다.</footer></main>
<dialog id="zoom"><div class="dialog-head"><h3 id="zoom-title"></h3><button id="zoom-close">닫기</button></div><div class="zoom-wrap"><img id="zoom-image" alt=""></div><p class="dialog-meta" id="zoom-meta"></p></dialog>
<script id="evidence-data" type="application/json">__EVIDENCE_JSON__</script>
<script>
'use strict';
const data=JSON.parse(document.getElementById('evidence-data').textContent),$=id=>document.getElementById(id);
let currentView=data.defaultViewId,phase='final',maskType='union',displayExtent='crop',figureKind='source',sectionArm=data.arms[0];
const fmt=(x,d=3)=>x===null||x===undefined||!Number.isFinite(Number(x))?'—':Number(x).toLocaleString('ko-KR',{maximumFractionDigits:d,minimumFractionDigits:d});
const count=x=>Number(x).toLocaleString('ko-KR');
const label=arm=>data.labels[arm]||arm;
function text(el,value){el.textContent=value;return el;}
function option(value,name){const o=document.createElement('option');o.value=value;o.textContent=name;return o;}
function zoom(src,title,meta){$('zoom-image').src=src;$('zoom-image').alt=title;$('zoom-title').textContent=title;$('zoom-meta').textContent=meta||'';$('zoom').showModal();}
$('zoom-close').onclick=()=>$('zoom').close();$('zoom').onclick=e=>{if(e.target===$('zoom'))$('zoom').close();};
function registerImage(img){img.addEventListener('error',()=>{$('image-error').hidden=false;$('image-error').textContent='그림 파일을 읽지 못했습니다: '+img.getAttribute('src');});}
function activeImages(){const base=data.images[String(currentView)];return displayExtent==='crop'?base.crop:base;}
function card(title,subtitle,path,footer,isTarget){const card=document.createElement('article');card.className='card';const head=document.createElement('div');head.className='card-head';head.append(text(document.createElement('h3'),title),text(document.createElement('small'),subtitle));const button=document.createElement('button');button.className='photo-button';button.setAttribute('aria-label',title+' 크게 보기');const img=document.createElement('img');img.className='photo';img.src=path;img.alt=title;registerImage(img);const overlay=document.createElement('img');overlay.className='mask';overlay.src=activeImages().masks[maskType];overlay.alt='고정 평가영역';overlay.hidden=!$('overlay-toggle').checked;button.append(img,overlay);button.onclick=()=>zoom(path,title,footer);const foot=document.createElement('div');foot.className='card-foot';foot.textContent=footer;card.append(head,button,foot);return card;}
function renderGallery(){const base=data.images[String(currentView)],imageSet=activeImages(),gallery=$('gallery');gallery.replaceChildren();gallery.append(card('현재 사진',base.name,imageSet.target,'2024-12-17 촬영 · 같은 사진을 모든 조건과 비교',true));for(const arm of data.arms){const result=data.b.arms.find(a=>a.arm===arm),entry=result[phase].views.find(v=>v.image_id===currentView),metric=entry.masks[maskType];gallery.append(card(label(arm),phase==='initial'?'초기 Gaussian 렌더':'학습 후 Gaussian 렌더',imageSet.arms[arm][phase],`이 사진의 MAE ${fmt(metric.mae)} · 표면 없음 ${count(metric.geometry_missing_pixels)} / ${count(metric.pixels)} px`));}const bbox=base.display_crop.bbox_xyxy;$('gallery-hint').textContent=`${data.viewIds.indexOf(currentView)+1} / ${data.viewIds.length} 평가 사진 · ${displayExtent==='crop'?`공통 표시 crop [${bbox.join(', ')}] px. 확대용 자르기만 적용했습니다.`:'전체 프레임을 표시합니다.'} ${$('overlay-toggle').checked?'덧보기의 흰 영역이 고정 평가 분모입니다.':'카드를 클릭하면 크게 볼 수 있습니다.'} 기본 사진은 학습 전 표면 지지 픽셀이 가장 많은 시점입니다.`;}
function renderMetrics(){const body=$('metrics-body');body.replaceChildren();for(const arm of data.arms){const b=data.b.arms.find(a=>a.arm===arm),a=b[phase].aggregate[maskType],g=data.evaluation.methods[phase==='initial'?arm+'__initial':arm],nn=g.native_3d_nearest_distances,hit=nn.within_distance.find(t=>t.threshold_m===.5);const values=[label(arm),count(b.seed_count),fmt(a.mae),`${count(a.geometry_missing_pixels)} / ${count(a.pixels)}`,fmt(nn.prediction_to_reference.p90_m)+' m',hit.reference_denominator?fmt(100*hit.reference_numerator/hit.reference_denominator,1)+' %':'—',fmt(100*g.xy_height_grid.prediction_coverage_reference_cells,1)+' %'];const row=document.createElement('tr');for(const value of values)row.append(text(document.createElement('td'),value));body.append(row);}$('metric-sub').textContent=`${phase==='initial'?'초기':'학습 후'} 결과 · 전체 ${data.viewIds.length}개 평가 사진의 합계 · ${maskType==='union'?'어느 초기 입력이든 표면을 지지하는 영역':'모든 초기 입력이 표면을 지지하는 공통 영역'}. 영상 MAE는 0–1 RGB의 평균 절대오차입니다.`;}
const figureDefs=[['source','원소스 존재 지도','source_occupancy.png','MVS만 있음 / ALS만 있음 / 둘 다 있음 / 둘 다 없음. 고정 0.5 m XY 셀의 존재 여부이며 소스 권위나 현재성 판단이 아닙니다.'],['native','3D 점과 표면','native_3d.png','원소스와 초기·학습 후 추출 표면입니다. 그림만 표시 점수를 줄였으며 정량 평가는 고정 영역의 모든 점을 사용합니다.'],['height','초기·학습 후 높이','median_heights.png','같은 XY 셀의 전체 점 Z 중앙값입니다. 벽·중첩 표면을 단일 높이로 요약하는 한계가 있습니다.'],['difference','참조와의 높이 차이','height_differences.png','UAS와 양쪽 모두 존재하는 셀의 높이 차이입니다. 빈 셀은 성공이 아니며 피복·누락 수를 별도로 기록합니다.'],['sections','공통 단면','cross_sections.png','X = −40 m, Y = −15 m, 폭 0.5 m의 고정 단면입니다. 원소스, 최종 표면, 평가 전용 UAS를 함께 표시합니다.'],['arm-section','조건별 초기·학습 후 단면',null,'동일 조건의 초기와 학습 후 표면을 원소스·UAS와 함께 비교합니다. 단면은 사전에 정한 위치이며 오차로 선택하지 않았습니다.']];
function renderFigure(){const def=figureDefs.find(d=>d[0]===figureKind);let filename=def[2],title=def[1];$('section-control').hidden=figureKind!=='arm-section';if(figureKind==='arm-section'){filename='cross_sections_'+sectionArm+'.png';title=label(sectionArm)+' · 초기와 학습 후';}const path=data.figures[filename];$('figure-image').src=path;$('figure-image').alt=title;$('figure-caption').textContent=def[3];$('figure-button').onclick=()=>zoom(path,title,def[3]);for(const button of $('figure-tabs').children)button.setAttribute('aria-pressed',String(button.dataset.kind===figureKind));}
for(const id of data.viewIds){const row=data.images[String(id)];$('view-select').append(option(id,`${id} · ${row.name}`));}
$('view-select').value=String(currentView);$('view-select').onchange=()=>{currentView=Number($('view-select').value);renderGallery();};$('display-select').onchange=()=>{displayExtent=$('display-select').value;renderGallery();};$('mask-select').onchange=()=>{maskType=$('mask-select').value;renderGallery();renderMetrics();};$('overlay-toggle').onchange=renderGallery;
for(const button of $('phase-controls').children)button.onclick=()=>{phase=button.dataset.phase;for(const b of $('phase-controls').children)b.setAttribute('aria-pressed',String(b===button));renderGallery();renderMetrics();};
for(const def of figureDefs){const button=document.createElement('button');button.textContent=def[1];button.dataset.kind=def[0];button.setAttribute('aria-pressed','false');button.onclick=()=>{figureKind=def[0];renderFigure();};$('figure-tabs').append(button);}
for(const arm of data.arms)$('section-select').append(option(arm,label(arm)));$('section-select').onchange=()=>{sectionArm=$('section-select').value;renderFigure();};
$('receipt').textContent=`${data.b.task_id}\n${data.generatedUtc.slice(0,10)} · ${data.b.arms[0].runtime_seconds!==undefined?'완료 기록 기반':''}`;
$('roles').textContent=`학습 ${data.trainCount}뷰와 평가 ${data.viewIds.length}뷰의 역할을 분리했습니다. 사진과 공통 MVS는 이전 개발에 사용되었으므로 독립 확증 자료가 아닙니다.`;
$('geometry-limit').textContent=`ALS의 법선 방향 이동만 최대 ${fmt(data.config.normal_limit_m,2)} m로 제한했습니다. 이 값은 정확도 인증이 아니라 개발 실험의 이동 한도입니다. 각 조건은 동일한 ${count(data.config.steps)}회 학습 예산을 사용합니다.`;
const crop=data.evaluation.crop;$('coordinates').textContent=`작업 표기 ${data.evaluation.coordinates.horizontal_crs}, UAS 원자료 EPSG:32632. 이번 평가는 재투영 없이 원점 이동만 적용했습니다. Scene-local X [${crop.x.join(', ')}), Y [${crop.y.join(', ')}), Z [${crop.z.join(', ')}) m. Datum·epoch 연결은 미보정 상태입니다.`;
$('source-info').textContent=`B: ${data.sourcePaths.b}\n평가: ${data.sourcePaths.evaluation}\n과학적 판정: null`;
registerImage($('figure-image'));renderGallery();renderMetrics();renderFigure();
</script></body></html>'''


def main(b_root, evaluation_root, output):
    if not Path("/.dockerenv").exists():
        raise RuntimeError("Build this project artifact in Docker")
    started = time.monotonic()
    b_path, e_path = b_root / "result.json", evaluation_root / "evaluation.json"
    b, evaluation = read(b_path), read(e_path)
    if b.get("status") != "COMPLETED_SOURCE_CONDITIONED_DEVELOPMENT":
        raise ValueError("Completed source-conditioned B receipt required")
    if evaluation.get("status") != "REFERENCE_ONLY_DEVELOPMENT_EVALUATION_COMPLETE":
        raise ValueError("Completed reference-only evaluation receipt required")
    if b.get("scientific_verdict", "missing") is not None or evaluation.get("scientific_verdict", "missing") is not None:
        raise ValueError("Scientific verdict must remain null")
    if b.get("wu_vallet_original_reproduced") is not False or b.get("actual_A_decision_consumed") is not False:
        raise ValueError("Gallery interpretation does not match the declared source-conditioned B contract")
    bound = evaluation.get("input_hashes", {})
    if str(b_path) not in bound or bound[str(b_path)] != sha(b_path):
        raise ValueError("Evaluation does not bind these exact completed B bytes")
    arms = [row["arm"] for row in b["arms"]]
    if len(arms) != 4 or set(arms) != set(LABELS):
        raise ValueError("Exactly the four declared P3 development arms are required")
    config_path, views_path = b_root / "config.json", b_root / "views.json"
    cfg, view_doc = read(config_path), read(views_path)
    by_id = {row["image_id"]: row for row in view_doc["views"]}
    view_ids = [row["image_id"] for row in b["arms"][0]["final"]["views"]]
    if len(view_ids) != 8 or len(set(view_ids)) != 8:
        raise ValueError("Exactly eight completed evaluation views required")
    for arm in b["arms"]:
        for phase in ["initial", "final"]:
            if [row["image_id"] for row in arm[phase]["views"]] != view_ids:
                raise ValueError("Arm phase view membership/order differs")
    if output.exists():
        raise FileExistsError("New output directory required")
    output.mkdir(parents=True, exist_ok=False)
    write(output / "STARTED.json", dict(scientific_verdict=None, generated_utc=datetime.now(timezone.utc).isoformat()))
    inputs, copies, derivatives = {}, {}, {}

    def copy(source, relative):
        source = Path(source)
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        source_hash = sha(source)
        shutil.copy2(source, destination)
        if sha(destination) != source_hash:
            raise ValueError(f"Copied file differs: {source}")
        inputs[str(source)] = source_hash
        copies[str(relative)] = dict(source=str(source), sha256=source_hash, bytes=source.stat().st_size)
        return str(relative)

    def crop_asset(relative, bbox):
        source = output / relative
        array = cv2.imread(str(source), cv2.IMREAD_UNCHANGED)
        if array is None:
            raise ValueError(f"Cannot decode copied image: {relative}")
        x0, y0, x1, y1 = bbox
        cropped = array[y0:y1, x0:x1]
        if cropped.size == 0 or cropped.shape[:2] != (y1-y0, x1-x0):
            raise ValueError("Shared display crop exceeds an image")
        destination_relative = Path("display_crop") / relative
        destination = output / destination_relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(destination), cropped):
            raise ValueError(f"Cannot write display crop: {destination}")
        restored = cv2.imread(str(destination), cv2.IMREAD_UNCHANGED)
        if not np.array_equal(restored, cropped):
            raise ValueError("Display crop pixel verification failed")
        derivatives[str(destination_relative)] = dict(source=str(relative), source_sha256=sha(source),
            sha256=sha(destination), bytes=destination.stat().st_size, bbox_xyxy=bbox,
            original_shape_hw=list(array.shape[:2]), crop_shape_hw=list(cropped.shape[:2]),
            role="DISPLAY_ONLY_EXACT_PIXEL_CROP_NO_RESIZE", metric_denominator_changed=False)
        return str(destination_relative)

    try:
        for source, name in [(b_path, "b_result.json"), (e_path, "evaluation.json"), (config_path, "b_config.json"), (views_path, "views.json")]:
            copy(source, Path("receipts") / name)
        images = {}
        for iid in view_ids:
            target = b_root / arms[0] / "initial" / f"target_{iid}.png"
            target_hash = sha(target)
            for arm in arms:
                for phase in ["initial", "final"]:
                    if sha(b_root / arm / phase / f"target_{iid}.png") != target_hash:
                        raise ValueError("Target RGB differs across arm/phase")
            item = dict(name=by_id[iid]["name"], target=copy(target, Path("images") / str(iid) / "target.png"), arms={}, masks={})
            for arm in arms:
                item["arms"][arm] = {phase: copy(b_root / arm / phase / f"rgb_{iid}.png", Path("images") / str(iid) / arm / f"{phase}.png") for phase in ["initial", "final"]}
            for kind in ["union", "intersection"]:
                item["masks"][kind] = copy(b_root / f"{kind}_support_{iid}.png", Path("images") / str(iid) / f"{kind}_support.png")
            support = cv2.imread(str(output / item["masks"]["union"]), cv2.IMREAD_GRAYSCALE)
            if support is None:
                raise ValueError("Frozen union support image cannot be read")
            yy, xx = np.where(support > 0)
            if len(xx) == 0:
                raise ValueError("No frozen P3 support for display crop")
            height, width = support.shape
            bbox = [max(0, int(xx.min())-10), max(0, int(yy.min())-10),
                    min(width, int(xx.max())+11), min(height, int(yy.max())+11)]
            item["display_crop"] = dict(bbox_xyxy=bbox, padding_px=10, original_shape_hw=[height, width],
                frozen_union_support_pixels=len(xx), criterion="Bounding rectangle of frozen initial union support plus 10 px; common to target, all arms and both phases; no result-based selection")
            item["crop"] = dict(target=crop_asset(item["target"], bbox),
                arms={arm: {phase: crop_asset(item["arms"][arm][phase], bbox) for phase in ["initial", "final"]} for arm in arms},
                masks={kind: crop_asset(item["masks"][kind], bbox) for kind in ["union", "intersection"]})
            images[str(iid)] = item
        figures = {}
        for name in ["source_occupancy.png", "native_3d.png", "median_heights.png", "height_differences.png", "cross_sections.png"] + [f"cross_sections_{arm}.png" for arm in arms]:
            figures[name] = copy(evaluation_root / name, Path("figures") / name)
        default_view = max(view_ids, key=lambda iid: images[str(iid)]["display_crop"]["frozen_union_support_pixels"])
        payload = dict(b=b, evaluation=evaluation, config=cfg, arms=arms, labels=LABELS, viewIds=view_ids, defaultViewId=default_view,
                       trainCount=sum(row["role"] == "train" for row in view_doc["views"]), images=images, figures=figures,
                       generatedUtc=datetime.now(timezone.utc).isoformat(), sourcePaths=dict(b=str(b_path), evaluation=str(e_path)))
        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
        (output / "index.html").write_text(HTML.replace("__EVIDENCE_JSON__", encoded))
        if any(sha(path) != digest for path, digest in inputs.items()):
            raise ValueError("Source inputs changed while building gallery")
        manifest = dict(status="OFFLINE_EVIDENCE_GALLERY_BUILT", scientific_verdict=None,
                        source_driver=dict(path=str(Path(__file__)), sha256=sha(__file__)),
                        input_hashes=inputs, copied_assets=copies, display_derivatives=derivatives, view_ids=view_ids, arms=arms,
                        default_view_id=default_view, default_selection="Maximum frozen initial union support pixels, first frozen view on ties; no trained performance selection",
                        display_crops={iid: item["display_crop"] for iid, item in images.items()},
                        html_sha256=sha(output / "index.html"), elapsed_seconds=time.monotonic() - started,
                        operations=dict(training=0, rendering=0, reference_evaluation=0, source_decisions=0),
                        qa=dict(source_binding="PASS", targets_identical_across_arms_and_phases="PASS", copied_asset_hashes="PASS", browser="NOT_RUN"),
                        offline=True, network_dependencies=[], original_wu_vallet_reproduced=False)
        write(output / "viewer_manifest.json", manifest)
        print(json.dumps(dict(status=manifest["status"], output=str(output), views=len(view_ids), copied_files=len(copies))), flush=True)
    except Exception as error:
        write(output / "FAILED.json", dict(status="FAILED", error=repr(error), scientific_verdict=None))
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--b-root", type=Path, required=True)
    parser.add_argument("--evaluation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    main(args.b_root, args.evaluation, args.output)
