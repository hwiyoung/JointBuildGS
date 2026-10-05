"""Step 8 (jointbuildgs:dev): single-file viewer.html (pure JS + canvas, no libraries, no server)
with tables/faces/points embedded as JSON; PNG layers and per-view pixel readout sidecars are read
by relative path from out/.  Also writes viewer_README.md and the top-view figure PNGs.
"""
import json

import numpy as np

import common as cm

rc = cm.Receipt("viewer")
R = json.loads((cm.OUT / "results.json").read_text())

# ----------------------------------------------------------------------------- figures (matplotlib)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection, PolyCollection

fig_dir = cm.OUT / "figures"
fig_dir.mkdir(exist_ok=True)
faces = R["faces"]
bb = np.array(faces["crop_local_xy"])
for key, rows in faces["attributes"].items():
    prior, cond = key.split("|")
    fig, ax = plt.subplots(figsize=(7, 8), dpi=110)
    polys_roof, cols_roof, segs, cols_wall = [], [], [], []
    cmap = plt.get_cmap("Reds")
    for p, a in zip(faces["target"], rows):
        v = a["conflict_frac"]
        col = (0.75, 0.75, 0.75, 1.0) if v is None else cmap(min(max(v, 0), 1))
        ring = np.array(p["ring_local_xy"])
        if p["region"] == "wall":
            segs.append(ring[[0, len(ring) // 2]] if len(ring) > 2 else ring)
            cols_wall.append(col)
        elif p["region"] == "roof":
            polys_roof.append(ring)
            cols_roof.append(col)
    for p in faces["context"]:
        ax.add_patch(plt.Polygon(np.array(p["ring_local_xy"]), closed=True, fc=(0.93, 0.93, 0.93), ec=(0.7, 0.7, 0.7), lw=0.5))
    ax.add_collection(PolyCollection(polys_roof, facecolors=cols_roof, edgecolors="k", linewidths=0.6))
    ax.add_collection(LineCollection(segs, colors=cols_wall, linewidths=5))
    for p, a in zip(faces["target"], rows):
        ring = np.array(p["ring_local_xy"])
        c = ring.mean(0)
        lab = "" if a["conflict_frac"] is None else f"{a['conflict_frac']:.2f}"
        ax.text(c[0], c[1], f"{p['poly_index']}\n{lab}", fontsize=6, ha="center", va="center")
    ax.set_xlim(bb[0][0], bb[1][0])
    ax.set_ylim(bb[0][1], bb[1][1])
    ax.set_aspect("equal")
    ax.set_title(f"conflict_frac per LoD2 face — prior {prior}, {cond} (scale 0..1 fixed)")
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(0, 1))
    fig.colorbar(sm, ax=ax, fraction=0.04, label="conflict_frac")
    ax.set_xlabel("x local (m)")
    ax.set_ylabel("y local (m)")
    fig.tight_layout()
    fig.savefig(fig_dir / f"faces_{prior}_{cond}_conflict.png")
    plt.close(fig)
for cond, pts in R["als_points"].items():
    fig, ax = plt.subplots(figsize=(7, 8), dpi=110)
    x, y = np.array(pts["x"]), np.array(pts["y"])
    c = np.array([np.nan if v is None else v for v in pts["conflict"]])
    ok = np.isfinite(c)
    ax.scatter(x[~ok], y[~ok], s=1, c="#bbbbbb", label="no confident view")
    sc = ax.scatter(x[ok], y[ok], s=1.5, c=c[ok], cmap="Reds", vmin=0, vmax=1)
    for p in faces["target"]:
        if p["region"] == "roof":
            ax.add_patch(plt.Polygon(np.array(p["ring_local_xy"]), closed=True, fill=False, ec="k", lw=0.5))
    ax.set_xlim(bb[0][0], bb[1][0])
    ax.set_ylim(bb[0][1], bb[1][1])
    ax.set_aspect("equal")
    ax.set_title(f"ALS points: conflict fraction — {cond} (scale 0..1 fixed)")
    fig.colorbar(sc, ax=ax, fraction=0.04, label="conflict")
    fig.tight_layout()
    fig.savefig(fig_dir / f"als_points_{cond}_conflict.png")
    plt.close(fig)

# ----------------------------------------------------------------------------- viewer data
stage2 = {p: json.loads((cm.OUT / f"stage2_config_{p}.json").read_text()) for p in cm.PRIORS}
data = {k: R[k] for k in ["task_id", "generated_at", "views", "tolerance", "checks", "facts", "diagN", "compare_rows", "hist", "hist_meta", "faces", "als_points"]}
data["stage2"] = stage2
data["overall"] = {"stats": [r for r in R["stats_rows"] if r[2] == "ALL"], "coverage": [r for r in R["coverage_rows"] if r[2] == "ALL"],
                   "conflict": [r for r in R["conflict_rows"] if r[2] == "ALL"]}
data["per_view"] = {"coverage": [r for r in R["coverage_rows"] if r[2] != "ALL" and r[3] in ("roof", "wall")],
                    "conflict": [r for r in R["conflict_rows"] if r[2] != "ALL" and r[3] in ("roof", "wall")],
                    "stats": [r for r in R["stats_rows"] if r[2] != "ALL" and r[3] == "roof"]}
data["constants"] = R["config"]["constants"]
data["priors"] = R["config"]["priors"]
json_blob = json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=lambda o: None)

HTML = r"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8"><title>첫 단계 뷰어 — 신뢰도·허용 오차·충돌 (L vs M)</title>
<style>
:root{--bg:#fafafa;--fg:#222;--muted:#666;--line:#ddd;--acc:#1f5fbf;--warn:#c62828;--ok:#2e7d32}
body{margin:0;font:14px/1.45 system-ui,"Noto Sans KR",sans-serif;color:var(--fg);background:var(--bg)}
header{position:sticky;top:0;background:#fff;border-bottom:1px solid var(--line);padding:8px 16px;z-index:5;display:flex;flex-wrap:wrap;gap:12px;align-items:center}
header h1{font-size:16px;margin:0 12px 0 0}
.ctl{display:flex;gap:6px;align-items:center;flex-wrap:wrap}
.ctl label{color:var(--muted)}
section{padding:14px 16px;border-bottom:1px solid var(--line)}
h2{font-size:15px;margin:0 0 6px}
.why{background:#fff;border:1px solid var(--line);border-radius:6px;padding:8px 10px;margin:6px 0 10px;font-size:13px}
.why b{display:inline-block;width:64px;color:var(--acc)}
table{border-collapse:collapse;background:#fff;font-size:12.5px}
th,td{border:1px solid var(--line);padding:3px 7px;text-align:right;white-space:nowrap}
th:first-child,td:first-child{text-align:left}
.ok{color:var(--ok);font-weight:600}.bad{color:var(--warn);font-weight:600}.na{color:var(--muted)}
canvas{background:#111;border:1px solid var(--line);max-width:100%}
.row{display:flex;gap:12px;flex-wrap:wrap;align-items:flex-start}
.legend{display:flex;gap:10px;flex-wrap:wrap;font-size:12px;margin:4px 0}
.sw{display:inline-block;width:14px;height:12px;vertical-align:middle;border:1px solid #999;margin-right:3px}
.bar{display:inline-block;width:120px;height:12px;vertical-align:middle;border:1px solid #999}
pre{background:#fff;border:1px solid var(--line);padding:8px;font-size:12px;overflow:auto;max-height:420px}
textarea{width:100%;min-height:60px;font:13px system-ui}
#readout{font-family:ui-monospace,monospace;font-size:12.5px;background:#fff;border:1px solid var(--line);padding:6px 8px;min-width:280px}
.small{font-size:12px;color:var(--muted)}
button{font:13px system-ui;padding:3px 8px}
#tip{position:fixed;pointer-events:none;background:#fff;border:1px solid #999;padding:4px 6px;font-size:12px;display:none;z-index:9}
</style></head><body>
<header>
<h1>첫 단계 뷰어 — 신뢰도·허용 오차·충돌</h1>
<div class="ctl"><label>prior</label><select id="prior"><option value="L">L (ALS)</option><option value="M">M (LoD2)</option></select>
<label>조건</label><select id="cond"><option value="nominal">정상</option><option value="biased">편향 +1.0 m</option></select>
<label>시점</label><select id="view"></select>
<label>비교</label><select id="cmp"><option value="off">없음</option><option value="prior">좌 L / 우 M</option><option value="cond">좌 정상 / 우 편향</option></select></div>
<div class="ctl"><label>레이어</label>
<label><input type="checkbox" class="layer" value="image" checked>영상</label>
<label><input type="checkbox" class="layer" value="conf">신뢰도</label>
<label><input type="checkbox" class="layer" value="res" checked>잔차</label>
<label><input type="checkbox" class="layer" value="conflict">충돌</label>
<label><input type="checkbox" class="layer" value="region">지붕/벽면</label>
<label><input type="checkbox" class="layer" value="prior">prior 깊이</label>
<label><input type="checkbox" class="layer" value="mvs">MVS 깊이</label>
<label>투명도 <input type="range" id="alpha" min="0" max="100" value="70"></label>
<a href="#p1">1</a> <a href="#p2">2</a> <a href="#p3">3</a> <a href="#p4">4</a> <a href="#p5">5</a> <a href="#p6">6</a></div>
</header>
<div id="tip"></div>

<section id="p1"><h2>패널 1 · 개요</h2>
<div class="why"><b>무엇</b> 네 조건의 허용 오차와 편차와 커버리지.<br><b>왜</b> τ는 둘째 단계 손실의 허용 구간이 되고, m은 정합 상태를, 커버리지는 방법이 이 건물에서 심판할 수 있는 범위를 말한다.<br><b>기대</b> 정상 조건 |m| &lt; s. 편향 조건 연직 잔차 m ≈ +1.0 m. τ_data가 τ_spec 근처. ALS의 s와 τ가 LoD2보다 작다.<br><b>이상 신호</b> 정상에서 |m| ≥ s면 정합 미완. 편향에서 m이 1.0 m에서 0.2 m 넘게 벗어나면 편향 적용이나 스케일 문제. 두 prior의 커버리지가 크게 다르면 마스크 정렬 문제(커버리지는 prior와 무관해야 한다).</div>
<div id="overview"></div></section>

<section id="p2"><h2>패널 2 · 시점</h2>
<div class="why"><b>무엇</b> 신뢰도 구멍의 위치, 잔차의 공간 패턴, 충돌의 위치.<br><b>왜</b> 신뢰도 구멍이 무텍스처·그림자·식생과 겹치면 신뢰도 지도가 뜻대로 만들어진 것이다. 잔차가 면 안에서 일정하면 표현 오차, 에지에서만 크면 에지 효과, 전면에 걸쳐 한 방향이면 정합 편차다. 충돌은 둘째 단계에서 보정될 자리의 미리보기다.<br><b>기대</b> 정상 조건 충돌은 도머·굴뚝·처마 같은 LoD2 단순화 부위와 에지에만. 편향 조건 충돌은 신뢰도가 있는 지붕 전체에, 벽면에는 거의 없음(연직 편향은 벽면을 벽면 방향으로 밀어 광선 깊이에 잘 안 보인다).<br><b>이상 신호</b> 정상 조건에서 지붕 한복판이 넓게 충돌이면 정합·스케일·면 혼합 의심. 편향 조건에서 신뢰도 있는 지붕이 충돌 아님이면 편향 파일 오류.</div>
<div class="legend"><span><span class="sw" style="background:#fff"></span>신뢰도 1</span><span><span class="sw" style="background:#000"></span>신뢰도 0</span>
<span><span class="bar" style="background:linear-gradient(90deg,#2166d9,#fff,#cc1a1a)"></span> 잔차 −1.5 … +1.5 m (MVS − prior, 카메라 Z; 회색 = 없음)</span>
<span><span class="sw" style="background:#dc1e1e"></span>충돌</span><span><span class="sw" style="background:#fff"></span>신뢰도 있음</span><span><span class="sw" style="background:#969696"></span>신뢰도 없음</span><span><span class="sw" style="background:#464646"></span>집계 밖(다른 건물·비대상)</span>
<span><span class="sw" style="background:#e6781e"></span>지붕</span><span><span class="sw" style="background:#3c82dc"></span>벽면</span><span><span class="sw" style="background:#5aaa5a"></span>지면(L)</span><span><span class="sw" style="background:#969696"></span>다른 건물</span>
<span><span class="bar" style="background:linear-gradient(90deg,#9e0142,#f46d43,#ffffbf,#66c2a5,#5e4fa2)"></span> 깊이 30 … 130 m</span></div>
<div class="row"><div><div id="capL" class="small"></div><canvas id="cvL" width="1200" height="868"></canvas></div><div id="rightWrap" style="display:none"><div id="capR" class="small"></div><canvas id="cvR" width="1200" height="868"></canvas></div>
<div id="readout">픽셀을 클릭하면 잔차·신뢰도·두 깊이를 표시</div></div></section>

<section id="p3"><h2>패널 3 · 지도</h2>
<div class="why"><b>무엇</b> 면 단위로 본 신뢰도·충돌·잔차와 두 prior의 차이.<br><b>왜</b> 이 지도가 둘째 단계의 "보정될 자리"이고, L과 M의 차이가 prior 종류에 따라 결과가 달라지는지의 답이다.<br><b>기대</b> 편향 조건에서 신뢰도 비율이 높은 지붕 면일수록 충돌 비율이 높다. ALS는 s가 작아 같은 잔차에서 충돌이 더 예민하게 켜진다.<br><b>이상 신호</b> 신뢰도 비율은 높은데 충돌 비율이 0인 편향 지붕 면, 또는 그 반대.</div>
<div class="ctl"><label>속성</label><select id="mapAttr"><option value="conf_frac">신뢰도 비율</option><option value="conflict_frac" selected>충돌 비율</option><option value="res_median">잔차 중앙값 (m)</option></select>
<label><input type="checkbox" id="mapDiff">L−M 차이 모드</label> <label><input type="checkbox" id="mapAls">ALS 점 겹치기(선택 조건)</label> <span class="small">prior·조건은 상단 선택을 따른다. 색 눈금 고정: 비율 0…1, 잔차 −1.5…+1.5 m, 차이 −1…+1.</span></div>
<div class="legend"><span><span class="bar" style="background:linear-gradient(90deg,#fff5f0,#cb181d)"></span> 비율 0 … 1</span><span><span class="bar" style="background:linear-gradient(90deg,#2166d9,#fff,#cc1a1a)"></span> 잔차/차이 (발산)</span><span><span class="sw" style="background:#bbb"></span> 값 없음</span></div>
<canvas id="map" width="760" height="900"></canvas><div id="mapInfo" class="small"></div></section>

<section id="p4"><h2>패널 4 · 분포</h2>
<div class="why"><b>무엇</b> 잔차 분포의 모양과 이동, 두 prior의 면별 일치.<br><b>왜</b> 정상 조건은 좁은 봉우리 하나에 단순화 부위의 꼬리가 붙은 모양이어야 하고, 편향 조건은 그 봉우리가 +1.0 m로 옮겨 가야 한다. 산점이 대각선 근처면 두 prior가 같은 자리를 가리키는 것이고, 벗어난 면이 prior 종류가 결과를 바꾸는 자리다.<br><b>이상 신호</b> 봉우리가 둘이면 정합·스케일·면 혼합. 편향 조건에서 봉우리가 안 옮겨 가면 편향 미적용.</div>
<div class="ctl"><label>잔차 종류</label><select id="histKind"><option value="ray_depth_camZ">광선(카메라 Z) 잔차</option><option value="vertical">연직 잔차(지붕만)</option></select> <span class="small">실선 = 정상, 점선 = 편향; 세로선: m2(가는 선), ±τ(굵은 선, 정상 조건). 가로축 −3 … +3 m, 0.02 m 구간, 각 조건은 자기 픽셀 수로 정규화.</span></div>
<div class="row"><div><div class="small">지붕 — prior L</div><canvas id="hLroof" width="560" height="220"></canvas></div><div><div class="small">지붕 — prior M</div><canvas id="hMroof" width="560" height="220"></canvas></div></div>
<div class="row"><div><div class="small">벽면 — prior L (참고값)</div><canvas id="hLwall" width="560" height="220"></canvas></div><div><div class="small">벽면 — prior M</div><canvas id="hMwall" width="560" height="220"></canvas></div></div>
<div class="row"><div><div class="small">면별 충돌 비율 산점 — 가로 L, 세로 M (선택 조건; ● 지붕, ▲ 벽면)</div><canvas id="scat" width="420" height="420"></canvas></div><div id="scatInfo" class="small"></div></div></section>

<section id="p5"><h2>패널 5 · 점검 목록</h2>
<div id="checks"></div>
<h3 style="font-size:14px">사람 메모 (브라우저에 저장됨)</h3>
<div class="small">신뢰도 구멍이 실제 무텍스처·그림자와 겹치는지</div><textarea id="memo1"></textarea>
<div class="small">정상 충돌이 단순화 부위(도머·굴뚝·처마)인지</div><textarea id="memo2"></textarea>
<div class="small">L과 M이 갈리는 면이 어떤 면인지</div><textarea id="memo3"></textarea>
<button id="memoExport">메모 JSON 내려받기</button></section>

<section id="p6"><h2>패널 6 · 둘째 단계 연결</h2>
<div class="why"><b>무엇</b> 둘째 단계에 들어갈 파일과 숫자, 그리고 둘째 단계 결과를 판정할 때 쓸 기대치.<br><b>왜</b> 이 패널이 둘째 단계 설정의 근거이고, 학습 뒤 판독 결과가 여기 적힌 기대치와 맞는지가 방법이 약속대로 움직였는지의 첫 검증이다.<br><b>기대</b> 진행 규칙 등이 모두 초록. 편향 조건에서 "보정 기대 면"(충돌 비율 높은 지붕 면)이 뚜렷하고, 정상 조건에서는 "다듬기 기대 면"만 소수.<br><b>이상 신호</b> 빨간 등이 하나라도 있으면 둘째 단계 착수 전 원인 해결.</div>
<div id="link"></div>
<div class="row"><div><div class="small">stage2_config_L.json</div><pre id="cfgL"></pre></div><div><div class="small">stage2_config_M.json</div><pre id="cfgM"></pre></div></div></section>

<script id="data" type="application/json">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('data').textContent);
const $=s=>document.querySelector(s);
const KO={nominal:'정상',biased:'편향+1.0',L:'L(ALS)',M:'M(LoD2)',roof:'지붕',wall:'벽면',ground:'지면',all:'전체'};
const f=(x,d=3)=>x==null?'<span class="na">NA</span>':(typeof x==='boolean'?(x?'<span class="ok">예</span>':'<span class="bad">아니오</span>'):(typeof x==='number'?x.toFixed(d):x));
const pct=x=>x==null?'<span class="na">NA</span>':(100*x).toFixed(1)+'%';
const PC=[['L','nominal'],['L','biased'],['M','nominal'],['M','biased']];
const ov=(kind,p,c,reg)=>{const r=D.overall[kind].find(r=>r[0]===p&&r[1]===c&&r[3]===reg);return r?r[6]:null};
const st=(p,c,reg,kind)=>D.overall.stats.find(r=>r[0]===p&&r[1]===c&&r[3]===reg&&r[4]===kind);
// ---------------- panel 1
(function(){let h='<table><tr><th>항목</th>'+PC.map(([p,c])=>`<th>${KO[p]} ${KO[c]}</th>`).join('')+'</tr>';
const T=D.tolerance;const rows=[['τ_data (m)','tau_data'],['τ_spec (m)','tau_spec'],['τ (m)','tau'],['τ 출처','tau_source'],['τ_n (°)','tau_n'],['m 지붕 1차 (m)','m'],['s 지붕 1차 (m)','s'],['m2 지붕 2차 (m)','m2'],['s2 지붕 2차 (m)','s2'],['연직 m2 지붕 (m)','m2_v'],['이상치 비율','out_frac'],['지붕 픽셀 수','n']];
for(const [n,k] of rows)h+=`<tr><td>${n}</td>`+PC.map(([p,c])=>`<td>${k==='n'?T[p][c][k].toLocaleString():f(T[p][c][k],k==='out_frac'?4:3)}</td>`).join('')+'</tr>';
for(const reg of ['roof','wall','ground','all'])h+=`<tr><td>커버리지 ${KO[reg]}</td>`+PC.map(([p,c])=>`<td>${pct(ov('coverage',p,c,reg))}</td>`).join('')+'</tr>';
for(const reg of ['roof','wall','ground','all'])h+=`<tr><td>충돌 비율 ${KO[reg]}</td>`+PC.map(([p,c])=>`<td>${pct(ov('conflict',p,c,reg))}</td>`).join('')+'</tr>';
h+='</table>';
const C=D.checks;h+='<p class="small">자동 점검: '+['L','M'].map(p=>`${KO[p]} R1 ${f(C.per_prior[p].R1_registration_ok)} · R2 ${f(C.per_prior[p].R2_bias_verified)} · R6 ${f(C.per_prior[p].R6_conflict_sane)}`).join(' | ')+` | R5 run_both_priors ${f(C.cross_prior.R5_run_both_priors)} | 모두 초록 ${f(C.all_green)}</p>`;
h+=`<p class="small">진단 N(GeoGS 출력 vs GT) 지붕 부호 오차: 중앙값 ${D.diagN.roof_median_m.toFixed(3)} m, NMAD ${D.diagN.roof_nmad_m.toFixed(3)} m (다른 양, 참고).</p>`;
$('#overview').innerHTML=h;})();
// ---------------- panel 2
const views=D.views;const vs=$('#view');views.forEach((v,i)=>{const o=document.createElement('option');o.value=i;o.textContent=v.stem;vs.appendChild(o)});
const imgCache={};function img(src){if(imgCache[src])return imgCache[src];const im=new Image();im.src=src;imgCache[src]=im;im.onload=()=>drawAll();im.onerror=()=>{console.warn('png load failed',src)};return im}
function layers(){return [...document.querySelectorAll('.layer')].filter(x=>x.checked).map(x=>x.value)}
function srcFor(layer,v,p,c){switch(layer){case 'image':return `viewer_png/views/${v.stem}_image.png`;case 'conf':return `viewer_png/views/${v.stem}_conf.png`;case 'mvs':return `viewer_png/views/${v.stem}_mvs.png`;case 'region':return `viewer_png/${p}/${v.stem}_region.png`;case 'res':return `viewer_png/${p}/${c}/${v.stem}_res.png`;case 'conflict':return `viewer_png/${p}/${c}/${v.stem}_conflict.png`;case 'prior':return `viewer_png/${p}/${c}/${v.stem}_prior.png`}}
function drawOne(cv,v,p,c){const ctx=cv.getContext('2d');cv.width=v.vw;cv.height=v.vh;ctx.clearRect(0,0,cv.width,cv.height);const ls=layers();const a=+$('#alpha').value/100;let first=true;
for(const l of ls){const im=img(srcFor(l,v,p,c));if(!im.complete||!im.naturalWidth)continue;ctx.globalAlpha=first?1:a;ctx.drawImage(im,0,0,cv.width,cv.height);first=false}ctx.globalAlpha=1}
function sel(){return {v:views[+$('#view').value],p:$('#prior').value,c:$('#cond').value,cmp:$('#cmp').value}}
function drawAll(){const s=sel();drawOne($('#cvL'),s.v,s.p,s.c);$('#capL').textContent=`${s.v.stem} — prior ${s.p}, ${KO[s.c]}`;
const rw=$('#rightWrap');if(s.cmp==='off'){rw.style.display='none'}else{rw.style.display='';const p2=s.cmp==='prior'?(s.p==='L'?'M':'L'):s.p;const c2=s.cmp==='cond'?(s.c==='nominal'?'biased':'nominal'):s.c;drawOne($('#cvR'),s.v,p2,c2);$('#capR').textContent=`${s.v.stem} — prior ${p2}, ${KO[c2]}`}}
// pixel readout via sidecar scripts (loaded on demand)
window.JBGS_PIX=window.JBGS_PIX||{};const loading={};
function loadSide(key,file,cb){if(window.JBGS_PIX[key])return cb(window.JBGS_PIX[key]);if(loading[key])return;loading[key]=true;const s=document.createElement('script');s.src=file;s.onload=()=>{loading[key]=false;cb(window.JBGS_PIX[key])};s.onerror=()=>{loading[key]=false;$('#readout').textContent='readout 데이터 없음: '+file};document.head.appendChild(s)}
function dec(b64,Type){const bin=atob(b64);const u8=new Uint8Array(bin.length);for(let i=0;i<bin.length;i++)u8[i]=bin.charCodeAt(i);return new Type(u8.buffer)}
const decoded={};function get(key,field,Type){const k=key+'|'+field;if(!decoded[k])decoded[k]=dec(window.JBGS_PIX[key][field],Type);return decoded[k]}
function readout(ev,cv,p,c){const s=sel();const v=s.v;const r=cv.getBoundingClientRect();const x=(ev.clientX-r.left)/r.width,y=(ev.clientY-r.top)/r.height;const kc=`${v.stem}|common`,kp=`${v.stem}|${p}|${c}`;
loadSide(kc,`viewer_data/${v.stem}_common.js`,()=>loadSide(kp,`viewer_data/${v.stem}_${p}_${c}.js`,()=>{const P=window.JBGS_PIX[kc];const i=Math.min(P.w-1,Math.floor(x*P.w)),j=Math.min(P.h-1,Math.floor(y*P.h)),k=j*P.w+i;
const conf=get(kc,'conf',Uint8Array)[k],mvs=get(kc,'mvs',Uint16Array)[k],pr=get(kp,'prior',Uint16Array)[k],rs=get(kp,'res',Int16Array)[k],code=get(kp,'code',Uint8Array)[k];const reg=['없음','지붕','벽면','지면','다른 건물'][code&15];const cf=(code>>4)&1;
$('#readout').innerHTML=`시점 ${v.stem}<br>prior ${p} · ${KO[c]} · 픽셀(전체 해상도 약) u=${Math.round(x*v.W)}, v=${Math.round(y*v.H)}<br>신뢰도 conf = ${conf}<br>MVS 깊이 = ${mvs?(mvs/100).toFixed(2)+' m':'없음'}<br>prior 깊이 = ${pr?(pr/100).toFixed(2)+' m':'없음'}<br>잔차 r = ${rs===-32768?'없음':(rs/100).toFixed(2)+' m'}<br>구분 = ${reg} · 충돌 = ${cf}`;}))}
$('#cvL').addEventListener('click',e=>{const s=sel();readout(e,$('#cvL'),s.p,s.c)});
$('#cvR').addEventListener('click',e=>{const s=sel();const p2=s.cmp==='prior'?(s.p==='L'?'M':'L'):s.p;const c2=s.cmp==='cond'?(s.c==='nominal'?'biased':'nominal'):s.c;readout(e,$('#cvR'),p2,c2)});
['#prior','#cond','#view','#cmp','#alpha'].forEach(q=>$(q).addEventListener('input',()=>{drawAll();drawMap();drawScatter()}));
document.querySelectorAll('.layer').forEach(x=>x.addEventListener('change',drawAll));
// ---------------- panel 3 map
const F=D.faces;const bb=F.crop_local_xy;const mapCv=$('#map');const M=mapCv.getContext('2d');const pad=30;
function mx(x){return pad+(x-bb[0][0])/(bb[1][0]-bb[0][0])*(mapCv.width-2*pad)}function my(y){return mapCv.height-pad-(y-bb[0][1])/(bb[1][1]-bb[0][1])*(mapCv.height-2*pad)}
function reds(t){t=Math.max(0,Math.min(1,t));const a=[255,245,240],b=[203,24,29];return `rgb(${a.map((v,i)=>Math.round(v+(b[i]-v)*t)).join(',')})`}
function div(t){t=Math.max(-1,Math.min(1,t));const lo=[33,102,217],mid=[255,255,255],hi=[204,26,26];const c=t<0?lo.map((v,i)=>v+(mid[i]-v)*(t+1)):mid.map((v,i)=>v+(hi[i]-v)*t);return `rgb(${c.map(Math.round).join(',')})`}
function attrOf(p,c,i,a){const r=F.attributes[`${p}|${c}`][i];return r?r[a]:null}
function faceColor(i,a,s){const diff=$('#mapDiff').checked;if(diff){const l=attrOf('L',s.c,i,a),m=attrOf('M',s.c,i,a);if(l==null||m==null)return '#bbb';const d=l-m;return div(a==='res_median'?d/1.5:d)}
const v=attrOf(s.p,s.c,i,a);if(v==null)return '#bbb';return a==='res_median'?div(v/1.5):reds(v)}
let mapShapes=[];
function drawMap(){const s=sel();const a=$('#mapAttr').value;M.fillStyle='#fff';M.fillRect(0,0,mapCv.width,mapCv.height);mapShapes=[];
for(const p of F.context){M.beginPath();p.ring_local_xy.forEach(([x,y],k)=>k?M.lineTo(mx(x),my(y)):M.moveTo(mx(x),my(y)));M.closePath();M.fillStyle='#eee';M.fill();M.strokeStyle='#bbb';M.lineWidth=0.5;M.stroke()}
if($('#mapAls').checked&&D.als_points[s.c]){const P=D.als_points[s.c];for(let i=0;i<P.x.length;i++){const v=P.conflict[i];M.fillStyle=v==null?'#ccc':reds(v);M.fillRect(mx(P.x[i])-1,my(P.y[i])-1,2,2)}}
F.target.forEach((p,i)=>{if(p.region==='roof'){M.beginPath();p.ring_local_xy.forEach(([x,y],k)=>k?M.lineTo(mx(x),my(y)):M.moveTo(mx(x),my(y)));M.closePath();M.fillStyle=faceColor(i,a,s);M.fill();M.strokeStyle='#000';M.lineWidth=0.8;M.stroke();mapShapes.push({i,type:'poly',pts:p.ring_local_xy.map(([x,y])=>[mx(x),my(y)])})}});
F.target.forEach((p,i)=>{if(p.region==='wall'){const r=p.ring_local_xy;const A=r[0],B=r[Math.floor(r.length/2)];M.beginPath();M.moveTo(mx(A[0]),my(A[1]));M.lineTo(mx(B[0]),my(B[1]));M.strokeStyle=faceColor(i,a,s);M.lineWidth=6;M.stroke();mapShapes.push({i,type:'seg',a:[mx(A[0]),my(A[1])],b:[mx(B[0]),my(B[1])]})}});
F.target.forEach((p,i)=>{const c=p.ring_local_xy.reduce((q,[x,y])=>[q[0]+x/p.ring_local_xy.length,q[1]+y/p.ring_local_xy.length],[0,0]);M.fillStyle='#000';M.font='10px system-ui';M.fillText(p.poly_index,mx(c[0])-6,my(c[1])+3)});
M.fillStyle='#333';M.font='11px system-ui';M.fillText(`${$('#mapDiff').checked?'L−M 차이':'prior '+s.p} · ${KO[s.c]} · ${a}   (x,y = 장면 지역 좌표 m; 회색 = 이웃 건물 지붕)`,pad,16)}
function inPoly(pt,pts){let c=false;for(let i=0,j=pts.length-1;i<pts.length;j=i++){const [xi,yi]=pts[i],[xj,yj]=pts[j];if(((yi>pt[1])!==(yj>pt[1]))&&(pt[0]<(xj-xi)*(pt[1]-yi)/(yj-yi)+xi))c=!c}return c}
function dseg(p,a,b){const dx=b[0]-a[0],dy=b[1]-a[1];const t=Math.max(0,Math.min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/(dx*dx+dy*dy||1)));return Math.hypot(p[0]-a[0]-t*dx,p[1]-a[1]-t*dy)}
mapCv.addEventListener('mousemove',e=>{const r=mapCv.getBoundingClientRect();const pt=[(e.clientX-r.left)*mapCv.width/r.width,(e.clientY-r.top)*mapCv.height/r.height];let hit=null;for(const sh of mapShapes){if(sh.type==='seg'&&dseg(pt,sh.a,sh.b)<5)hit=sh.i;}for(const sh of mapShapes){if(sh.type==='poly'&&inPoly(pt,sh.pts))hit=sh.i}
const tip=$('#tip');if(hit==null){tip.style.display='none';return}const p=F.target[hit];const s=sel();const row=x=>{const r=F.attributes[x][hit];return `conf ${f(r.conf_frac)} · 충돌 ${f(r.conflict_frac)} · 잔차 중앙값 ${f(r.res_median)} m`};
tip.innerHTML=`<b>면 ${p.poly_index}</b> ${p.citygml_type} → ${KO[p.region]} · 면적 ${p.area_m2.toFixed(1)} m²<br>L 정상: ${row('L|nominal')}<br>L 편향: ${row('L|biased')}<br>M 정상: ${row('M|nominal')}<br>M 편향: ${row('M|biased')}`;tip.style.display='block';tip.style.left=(e.clientX+12)+'px';tip.style.top=(e.clientY+12)+'px'});
mapCv.addEventListener('mouseleave',()=>$('#tip').style.display='none');
['#mapAttr','#mapDiff','#mapAls'].forEach(q=>$(q).addEventListener('input',drawMap));
// ---------------- panel 4
function drawHist(id,p,reg){const cv=$(id);const g=cv.getContext('2d');g.fillStyle='#fff';g.fillRect(0,0,cv.width,cv.height);const kind=$('#histKind').value;const hm=D.hist_meta;const L=40,B=24,W=cv.width-L-10,H=cv.height-B-10;
let ymax=0;const series=[];for(const c of ['nominal','biased']){const h=D.hist[`${p}|${c}|${reg}|${kind}`];if(!h)continue;const n=h.counts.reduce((a,b)=>a+b,0)+h.under+h.over;const y=h.counts.map(v=>v/(n||1));ymax=Math.max(ymax,...y);series.push({c,y,h})}
if(!series.length){g.fillStyle='#666';g.fillText('데이터 없음',L,H/2);return}
const X=v=>L+(v-hm.range[0])/(hm.range[1]-hm.range[0])*W,Y=v=>10+H-v/ymax*H;
g.strokeStyle='#999';g.beginPath();g.moveTo(L,10+H);g.lineTo(L+W,10+H);g.stroke();for(let t=-3;t<=3;t++){g.fillStyle='#333';g.font='10px system-ui';g.fillText(t+' m',X(t)-8,cv.height-8);g.strokeStyle='#eee';g.beginPath();g.moveTo(X(t),10);g.lineTo(X(t),10+H);g.stroke()}
for(const s of series){g.strokeStyle=s.c==='nominal'?'#1f5fbf':'#c62828';g.setLineDash(s.c==='nominal'?[]:[4,3]);g.lineWidth=1.5;g.beginPath();s.y.forEach((v,i)=>{const x=X(hm.range[0]+(i+0.5)*hm.bin);i?g.lineTo(x,Y(v)):g.moveTo(x,Y(v))});g.stroke();g.setLineDash([]);
const T=D.tolerance[p][s.c];const m=kind==='vertical'?T.m2_v:(reg==='roof'?T.m2:(st(p,s.c,reg,'ray_depth_camZ')||{})[8]);if(m!=null){g.strokeStyle=g.strokeStyle;g.lineWidth=1;g.beginPath();g.moveTo(X(m),10);g.lineTo(X(m),10+H);g.stroke()}
g.fillStyle=s.c==='nominal'?'#1f5fbf':'#c62828';g.fillText(`${KO[s.c]}: n=${(s.h.counts.reduce((a,b)=>a+b,0)+s.h.under+s.h.over).toLocaleString()} (범위 밖 ${s.h.under+s.h.over}) p50=${s.h.quantiles.p50==null?'NA':s.h.quantiles.p50.toFixed(3)}`,L+6,s.c==='nominal'?20:34)}
const tau=D.tolerance[p].nominal.tau;if(tau!=null){g.strokeStyle='#444';g.lineWidth=2.5;for(const t of [-tau,tau]){g.beginPath();g.moveTo(X(t),10);g.lineTo(X(t),10+H);g.stroke()}g.fillStyle='#444';g.fillText('±τ='+tau.toFixed(3),X(tau)+3,48)}}
function drawHists(){drawHist('#hLroof','L','roof');drawHist('#hMroof','M','roof');drawHist('#hLwall','L','wall');drawHist('#hMwall','M','wall')}
$('#histKind').addEventListener('input',drawHists);
function drawScatter(){const cv=$('#scat');const g=cv.getContext('2d');g.fillStyle='#fff';g.fillRect(0,0,cv.width,cv.height);const s=sel();const P=40,W=cv.width-P-10;const X=v=>P+v*W,Y=v=>10+W-v*W;g.strokeStyle='#999';g.strokeRect(P,10,W,W);g.strokeStyle='#ccc';g.beginPath();g.moveTo(X(0),Y(0));g.lineTo(X(1),Y(1));g.stroke();
g.fillStyle='#333';g.font='10px system-ui';for(const t of [0,0.5,1]){g.fillText(t,X(t)-4,cv.height-14);g.fillText(t,P-22,Y(t)+3)}g.fillText('L 충돌 비율',X(0.4),cv.height-2);let n=0,out=[];
F.target.forEach((p,i)=>{const l=attrOf('L',s.c,i,'conflict_frac'),m=attrOf('M',s.c,i,'conflict_frac');if(l==null||m==null)return;n++;g.fillStyle=p.region==='roof'?'#e6781e':'#3c82dc';g.beginPath();if(p.region==='roof')g.arc(X(l),Y(m),4,0,7);else{g.moveTo(X(l),Y(m)-5);g.lineTo(X(l)-5,Y(m)+4);g.lineTo(X(l)+5,Y(m)+4);g.closePath()}g.fill();g.fillStyle='#000';g.fillText(p.poly_index,X(l)+5,Y(m)-3);if(Math.abs(l-m)>0.2)out.push(`${p.poly_index}(${KO[p.region]}: L ${l.toFixed(2)} / M ${m.toFixed(2)})`)});
$('#scatInfo').innerHTML=`${KO[s.c]} 조건, 면 ${n}개 표시. 대각선에서 0.2 넘게 벗어난 면: ${out.length?out.join(', '):'없음'}`}
// ---------------- panel 5
(function(){const C=D.checks;const li=[];const row=(t,ok,detail)=>li.push(`<tr><td>${t}</td><td>${ok==null?'<span class="na">NA</span>':(ok?'<span class="ok">● 초록</span>':'<span class="bad">● 빨강</span>')}</td><td>${detail}</td></tr>`);
for(const p of ['L','M']){const q=C.per_prior[p];row(`${KO[p]} 정상 |m| &lt; s (R1)`,q.R1_registration_ok,`|m2|=${f(Math.abs(q.R1_values.m2_roof))} m, s2=${f(q.R1_values.s2_roof)} m`);
row(`${KO[p]} 편향 연직 m 0.8~1.2 m (R2)`,q.R2_bias_verified,`m2_v=${f(q.R2_values.m2_v_biased)} m (정상 ${f(q.R2_values.m2_v_nominal)}, 차 ${f(q.R2_values.delta_m2_v)})`);
row(`${KO[p]} τ 출처 (R3)`,true,`${q.R3_tolerance_source} · τ_data&gt;2τ_spec: ${f(q.R3_tau_data_gt_2x_spec)}${q.R3_note?' — '+q.R3_note:''}`);
row(`${KO[p]} 편향 지붕 충돌 &gt; 정상 지붕 충돌 (R6)`,q.R6_conflict_sane,`${pct(q.R6_values.roof_conflict_biased)} vs ${pct(q.R6_values.roof_conflict_nominal)}`);
row(`${KO[p]} 벽면 충돌 비율 편향 ≈ 정상 (|Δ| ≤ 0.10)`,q.wall_conflict_similar,`${pct(q.wall_conflict_values.nominal)} → ${pct(q.wall_conflict_values.biased)}`);
row(`${KO[p]} 지붕 커버리지 (R4)`,null,`${pct(q.R4_roof_coverage)} → 미판정 기대 상한 ${pct(q.R4_undetermined_upper)}`)}
const x=C.cross_prior;row('s_L &lt; s_M',x.s_L_lt_s_M,`${f(x.s_values.s2_L)} vs ${f(x.s_values.s2_M)} m`);row('두 prior 지붕 커버리지 차 5%p 이내',x.coverage_within_5pp,`L ${pct(x.coverage_values.roof_L)} / M ${pct(x.coverage_values.roof_M)}`);row('R5 run_both_priors',null,`${f(x.R5_run_both_priors)} (τ 상대차 ${pct(x.R5_values.rel_diff_tau)}, 지붕 충돌 상대차 정상 ${pct(x.R5_values.rel_diff_roof_conflict.nominal)} · 편향 ${pct(x.R5_values.rel_diff_roof_conflict.biased)})`);
$('#checks').innerHTML='<table><tr><th>항목</th><th>등</th><th>값</th></tr>'+li.join('')+'</table>';
for(const k of ['memo1','memo2','memo3']){const el=$('#'+k);try{el.value=localStorage.getItem('jbgs_stage1_'+k)||''}catch(e){}el.addEventListener('input',()=>{try{localStorage.setItem('jbgs_stage1_'+k,el.value)}catch(e){}})}
$('#memoExport').addEventListener('click',()=>{const o={memo1:$('#memo1').value,memo2:$('#memo2').value,memo3:$('#memo3').value,at:new Date().toISOString()};const a=document.createElement('a');a.href='data:application/json;charset=utf-8,'+encodeURIComponent(JSON.stringify(o,null,2));a.download='viewer_memo.json';a.click()})})();
// ---------------- panel 6
(function(){const T=D.tolerance,C=D.checks,S=D.stage2;const cf=(p,c,r)=>pct(ov('conflict',p,c,r));const tl=T.L.nominal,tm=T.M.nominal;
const rows=[['conf.npy(시점별)','손실의 픽셀 가중','out/conf/{view}_conf.npy ×15 (공통). prior 가중 = (1−conf)×prior 마스크, MVS 가중 = conf×MVS 마스크'],
['conf.npy','원반 신뢰도 E','8000회에 원반 중심을 각 시점에 투영해 conf 평균, 500회마다 갱신'],
['E','기울기 배율과 불투명도 하한','prior 출신 E&lt;0.5: 배율 0.01, 불투명도 하한 0.5; E≥0.5: 배율 1'],
['E','밀집화·가지치기','prior 출신 E&lt;0.5 동결; prior 출신 가지치기 기록'],
['tolerance.json의 τ','허용 구간과 절단',`τ = L ${f(tl.tau)} / M ${f(tm.tau)} m; 4τ = ${f(4*tl.tau)} / ${f(4*tm.tau)}; 상수 3τ = ${f(3*tl.tau)} / ${f(3*tm.tau)}`],
['τ','초기화의 관측 점 선택',`prior 표면 거리 &gt; ${f(tl.tau)} / ${f(tm.tau)} m인 MVS 점만 시드`],
['τ','판독 문턱','이동량 &lt; τ 보존, ≥ τ 보정'],
['τ_n','prior 법선 항 허용 각도',`${f(tl.tau_n,1)}° / ${f(tm.tau_n,1)}° (출처 ${tl.tau_n_source} / ${tm.tau_n_source})`],
['coverage.csv','판독 기대치',`지붕 커버리지 ${pct(C.per_prior.L.R4_roof_coverage)} / ${pct(C.per_prior.M.R4_roof_coverage)} → 미판정 상한 ${pct(C.per_prior.L.R4_undetermined_upper)} / ${pct(C.per_prior.M.R4_undetermined_upper)}`],
['면별 충돌 비율(편향)','판독 검증 기준',`지붕 충돌 ${cf('L','biased','roof')} / ${cf('M','biased','roof')} — 면별 값은 패널 3·lod2_faces_*_biased.csv`],
['면별 충돌 비율(정상)','다듬기 기대 자리',`지붕 충돌 ${cf('L','nominal','roof')} / ${cf('M','nominal','roof')} — lod2_faces_*_nominal.csv`],
['stats의 연직 m(편향)','보정 이동량 기대치',`m2_v = ${f(T.L.biased.m2_v)} / ${f(T.M.biased.m2_v)} m`],
['compare_L_vs_M','arm 구성',`run_both_priors = ${f(C.cross_prior.R5_run_both_priors)} (τ 상대차 ${pct(C.cross_prior.R5_values.rel_diff_tau)})`],
['정합 경고','착수 조건',`경고 L ${f(C.per_prior.L.registration_warning)} / M ${f(C.per_prior.M.registration_warning)}`]];
let h='<table><tr><th>첫 단계 산출</th><th>둘째 단계의 자리</th><th>실제 값 (L / M)</th></tr>'+rows.map(r=>`<tr><td>${r[0]}</td><td>${r[1]}</td><td style="white-space:normal;text-align:left">${r[2]}</td></tr>`).join('')+'</table>';
h+='<p>진행 규칙: '+['L','M'].map(p=>{const q=C.per_prior[p];return `${KO[p]} R1 ${f(q.R1_registration_ok)} · R2 ${f(q.R2_bias_verified)} · R3 ${q.R3_tolerance_source} · R4 ${pct(q.R4_roof_coverage)} · R6 ${f(q.R6_conflict_sane)}`}).join(' | ')+` | R5 ${f(C.cross_prior.R5_run_both_priors)} | 모두 초록 ${f(C.all_green)}</p>`;
$('#link').innerHTML=h;$('#cfgL').textContent=JSON.stringify(S.L,null,2);$('#cfgM').textContent=JSON.stringify(S.M,null,2)})();
drawAll();drawMap();drawHists();drawScatter();
// ---------------- self-test (open viewer.html?selftest=1): loads every PNG layer and readout sidecar of all
// views x priors x conditions, exercises every panel drawing, and reports to console + #selftest.
if(location.search.indexOf('selftest=1')>=0){(async()=>{const errs=[];window.addEventListener('error',e=>errs.push(String(e.message||e)));
const loadImg=src=>new Promise(res=>{const im=new Image();im.onload=()=>res({src,ok:im.naturalWidth>0});im.onerror=()=>res({src,ok:false});im.src=src});
const loadJs=src=>new Promise(res=>{const sc=document.createElement('script');sc.onload=()=>res({src,ok:true});sc.onerror=()=>res({src,ok:false});sc.src=src;document.head.appendChild(sc)});
const pngs=[],sides=[];let switches=0;
for(let vi=0;vi<views.length;vi++){const v=views[vi];$('#view').value=vi;for(const l of ['image','conf','mvs'])pngs.push(await loadImg(srcFor(l,v)));sides.push(await loadJs(`viewer_data/${v.stem}_common.js`));
for(const p of ['L','M']){pngs.push(await loadImg(srcFor('region',v,p)));for(const c of ['nominal','biased']){$('#prior').value=p;$('#cond').value=c;for(const l of ['res','conflict','prior'])pngs.push(await loadImg(srcFor(l,v,p,c)));sides.push(await loadJs(`viewer_data/${v.stem}_${p}_${c}.js`));
document.querySelectorAll('.layer').forEach(x=>x.checked=true);drawAll();drawMap();drawHists();drawScatter();switches++;}}}
for(const m of ['off','prior','cond']){$('#cmp').value=m;drawAll()}$('#mapDiff').checked=true;drawMap();$('#mapAls').checked=true;drawMap();$('#histKind').value='vertical';drawHists();
const keys=Object.keys(window.JBGS_PIX||{});const rep={ok:errs.length===0&&pngs.every(x=>x.ok)&&sides.every(x=>x.ok),views:views.length,condition_switches:switches,pngs_total:pngs.length,pngs_failed:pngs.filter(x=>!x.ok).map(x=>x.src),sidecars_total:sides.length,sidecars_failed:sides.filter(x=>!x.ok).map(x=>x.src),sidecar_keys:keys.length,js_errors:errs};
console.log('JBGS_SELFTEST '+JSON.stringify(rep));const pre=document.createElement('pre');pre.id='selftest';pre.textContent=JSON.stringify(rep);document.body.appendChild(pre);document.title=(rep.ok?'SELFTEST PASS ':'SELFTEST FAIL ')+document.title;})()}
</script></body></html>
"""
(cm.OUT / "viewer.html").write_text(HTML.replace("__DATA__", json_blob.replace("</script", "<\\/script")), encoding="utf-8")
README = f"""# viewer_README — {R['task_id']}

`out/viewer.html`은 외부 라이브러리·서버 없이 순수 JS와 canvas로 만든 단일 HTML이다. 인터넷 없이
더블클릭으로 열린다(Chrome·Firefox·Edge 확인 대상).

- 표·면 속성·면 다각형·ALS 점(4점마다 1점 부표본)은 HTML 안에 JSON으로 들어 있다.
- 그림은 `out/viewer_png/`(긴 변 {R['config']['constants']['viewer_long_side_px']} px 축소 사본)를 **out/ 기준 상대 경로**로 읽고,
  클릭 픽셀 판독 숫자는 `out/viewer_data/*.js`(긴 변 {R['config']['constants']['readout_long_side_px']} px 격자, base64)를
  시점·조건별로 필요할 때 읽는다. **viewer.html을 out/ 밖으로 옮기면 그림과 판독이 안 보인다.**
- 조작: prior(L/M), 조건(정상/편향), 시점, 레이어 토글, 투명도 슬라이더, 나란히 비교(좌 L 우 M 또는 좌 정상 우 편향).
  모든 색 눈금은 고정이고 범례는 항상 보인다. 패널 3은 마우스 오버로 면 id와 네 조건 값을, L−M 차이 모드와 ALS 점 겹치기를 제공한다.
- 패널 5의 사람 메모는 브라우저 localStorage에 저장되고 JSON으로 내려받을 수 있다.
- 색은 시각화 전용이며 숫자의 정본은 `out/*.npy|csv|ply|json`이다.
- 화소 판독 격자는 표시 png의 1/2 해상도이므로 경계 픽셀에서는 표시색과 판독값이 다를 수 있다.
"""
(cm.OUT / "viewer_README.md").write_text(README, encoding="utf-8")
print("viewer bytes", (cm.OUT / "viewer.html").stat().st_size)
rc.write()
