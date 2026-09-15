"""Publish a local, source-backed first-stage diagnostic page from fixed results."""
import hashlib
import html
import json
from pathlib import Path

assert Path('/.dockerenv').exists()
out=Path('/out');r=json.loads((out/'result.json').read_text())
assert r['status']=='PASS_FORWARD_ATTRIBUTION'
stereo=Path('/dense/stereo');config=stereo/'patch-match.cfg'
inventory=dict(geometric_depth_files=len(list((stereo/'depth_maps').glob('*.geometric.bin'))),
    consistency_graph_files=len(list((stereo/'consistency_graphs').glob('*'))),
    patch_match_cfg_sha256=hashlib.sha256(config.read_bytes()).hexdigest(),
    exact_original_filter_thresholds_bound=False,confidence_loaded_by_gs=False,
    note='Existing geometric depth is consumed directly. Empty consistency-graph directory is not evidence that geometric filtering was disabled. Patch-match.cfg is source-view selection, not the complete execution options.')
lines=config.read_text().splitlines();inventory['source_selection']={}
for name in ['DJI_20241217084553_0100_D.JPG','DJI_20241217084717_0142_D.JPG','DJI_20241217103041_0046_D.JPG']:
    i=lines.index(name);inventory['source_selection'][name]=lines[i+1]
(out/'mvs_inventory.json').write_text(json.dumps(inventory,indent=2))
names={'anchor':'공통 시작 8k','global_0005':'전역 · prior 0.0005','regional_005':'영역별 · prior 0.005 · R1=4','regional_0005':'영역별 · prior 0.0005 · R1=4'}
rows=''.join('<tr><th>'+names[x['id']]+'</th>'+''.join('<td>'+v+'</td>' for v in [f"{100*x['contribution_fraction']['tracked_old_roof']:.2f}%",f"{100*x['contribution_fraction']['mvs_near_centers']:.2f}%",f"{100*x['contribution_fraction']['all_unprotected']:.2f}%",f"{100*x['mvs_depth_abs_error']['mean']:.2f} cm"] )+'</tr>' for x in r['rows'])
latest=r['rows'][-1];counter=latest['counterfactual_tracked_opacity_zero']
page='''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>1단계 · P1 렌더 기여 진단</title>
<style>*{box-sizing:border-box}body{margin:0;background:#f4f6fa;color:#1d2939;font:16px/1.65 system-ui,sans-serif}main{max-width:1250px;margin:auto;padding:30px 22px}h1{font-size:30px;line-height:1.3}h2{font-size:22px;margin-top:0}section{background:white;border:1px solid #dae1ec;border-radius:12px;padding:24px;margin:22px 0}.eyebrow{color:#3455a4;font-weight:700}.muted,small{color:#526278}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.card{padding:18px;background:#edf4ff;border-radius:10px}.card strong{display:block;font-size:28px;color:#16447b}img{max-width:100%;display:block;margin:auto}a{color:#1e55a5}table{width:100%;border-collapse:collapse;font-size:14px}td,th{padding:12px;text-align:right;border-bottom:1px solid #dce2eb}th:first-child{text-align:left}.table{overflow:auto}nav{display:flex;gap:18px;flex-wrap:wrap}.note{border-left:4px solid #d19a35;padding:12px 16px;background:#fffaed}.controls{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:16px 0}select{padding:8px;font:inherit}#detail-canvas{width:100%;height:auto}li{margin:8px 0}@media(max-width:700px){main{padding:18px 12px}section{padding:16px}.cards{grid-template-columns:1fr}h1{font-size:25px}}</style>
<main><div class="eyebrow">단계별 검토 · 1 / 기존 결과의 작동 경로</div><h1>P1의 과거 지붕은 어떻게 덜 보이게 됐는가?</h1>
<p>0100_D · 동일한 최종 checkpoint 재렌더 · 추가 학습 없음. 집단별 색만 바꿔 <b>전체 장면의 가림과 합성 순서</b>를 유지했습니다.</p>
<nav><a href="/app/weights.html?comparison=prior">기존 3D 비교</a><a href="/data/prior_verification_v1/verification.jCU13Dtc/report.html">P1/P2/P3 GT 검증</a><a href="result.json">원본 집계 JSON</a></nav>
<section><h2>이번에 확인한 내용</h2><div class="cards"><div class="card">추적한 과거 지붕 집단의 현재 기여<strong>0.34%</strong>동일 보정 ROI의 누적 alpha 중 비율</div><div class="card">그 집단을 일시적으로 끈 영향<strong>0.52 cm</strong>예상 depth 변화의 평균 절대값</div><div class="card">비보호 Gaussian의 현재 기여<strong>99.66%</strong>기존/신규의 출생 이력은 미분리</div></div>
<p>보호 집단은 삭제되지 않고 남아 있지만, 이 시점·영역에서는 렌더 기여가 작습니다. 해당 집단의 추가 제거만으로 크게 개선될 여지는 작다는 진단입니다.</p>
<p class="note">전역 .0005와 영역별 .0005의 추적 집단 불투명도 중앙값은 모두 약 .0013이지만 실제 기여는 16.46%와 0.34%로 다릅니다. <b>불투명도만으로 표면 제거를 판정할 수 없습니다.</b> 다른 Gaussian의 가림·형상·겹침도 영향을 줍니다.</p></section>
<section><h2>1. 어디를 측정했는가?</h2><a href="inputs.png" target="_blank"><img src="inputs.png" alt="P1 현재 사진, 과거 prior depth, prior와 MVS 차이 및 고정 진단 영역"></a>
<p>기존 R1 중 prior와 MVS가 모두 유효하고 MVS가 prior보다 2m 이상 뒤에 있는 113,102픽셀입니다. 학습 마스크를 바꾸지 않았습니다. GT는 이 진단에 사용하지 않았습니다.</p>
<p>추적 집단은 시작 상태의 보호 Gaussian 중 중심이 이 영역에 투영되고 prior depth와 1m 이내인 4,455개입니다. 이전 4,557개 집계에 표면 근접 조건을 추가한 부분집합입니다.</p></section>
<section><h2>2. 조건별 기여 지도</h2><p>밝을수록 해당 집단의 기여가 큽니다. 청록 경계가 고정 진단 ROI입니다. 각 지도는 0–1의 같은 색상 범위를 사용합니다.</p>
<div class="controls"><label for="state">확대할 조건</label><select id="state"><option value="3">영역별 prior .0005 / R1=4</option><option value="2">영역별 prior .005 / R1=4</option><option value="1">전역 prior .0005</option><option value="0">공통 시작 8k</option></select><a href="attribution.png" target="_blank">전체 비교 그림 열기</a></div><canvas id="detail-canvas" width="1900" height="520" aria-label="선택한 조건의 렌더와 집단 기여 지도"></canvas>
<details><summary>네 조건을 한 번에 보기</summary><img src="attribution.png" alt="네 조건의 RGB, 시작 지붕 집단 기여, 현재 MVS 근처 중심 집단 기여, 과거 prior 근처 중심 집단 기여 비교"></details>
<p>왼쪽부터 RGB / <b>시작 지붕 집단</b> / <b>현재 MVS 근처 중심 집단</b> / <b>과거 prior 근처 중심 집단</b>입니다. 뒤의 두 집단은 해당 depth와 중심 camera-Z가 0.5m 이내인 Gaussian입니다.</p>
<p class="note">중심 기준의 집단 분류이므로 면 전체의 정확한 귀속은 아닙니다. 큰 Gaussian은 중심과 다른 위치의 픽셀에도 기여합니다. 세 집단은 서로 배타적이지 않으며 합이 100%가 될 필요가 없습니다.</p></section>
<section><h2>3. 동일 ROI 집계</h2><div class="table"><table><thead><tr><th>조건</th><th>시작 지붕 집단 기여</th><th>MVS 근처 중심 집단 기여</th><th>비보호 집단 기여</th><th>MVS depth 평균 절대차</th></tr></thead><tbody>ROWS</tbody></table></div>
<p>기여율은 ROI에서 집단의 합성 가중치 합 / 전체 누적 alpha 합입니다. MVS 일치도는 독립적인 정확도 평가가 아닙니다.</p>
<p>최종 결과에서 추적 집단의 불투명도만 메모리상 0으로 바꿨을 때 MVS 평균 절대차는 3.96→4.27cm, depth 변화는 평균 0.52cm였습니다. 이 일시적 조작은 원 checkpoint에 저장하지 않았고 복원 후 원 렌더와 일치함을 확인했습니다.</p></section>
<section><h2>4. 결과에 따라 이어질 실험</h2><div class="table"><table><thead><tr><th>진단 결과</th><th>다음에 분리할 요인</th></tr></thead><tbody><tr><th>과거 집단의 기여가 남고, 껐을 때 보정이 좋아짐</th><td>해당 표면의 prior 손실 약화와 보호 완화를 각각 비교</td></tr><tr><th>과거 집단 기여는 작지만 현재 표면도 부족함</th><td>현재 관측의 신뢰도·관측 범위·표현할 Gaussian 공급</td></tr><tr><th>과거 집단 기여가 작고 현재 표면을 다른 집단이 표현함</th><td>보정–보존을 함께 평가하는 국소 감독 배분부터 비교</td></tr><tr><th>렌더는 맞지만 추출 표면에 잔여층이 있음</th><td>동일 checkpoint의 추출 설정과 이중층을 별도 진단</td></tr></tbody></table></div>
<p>현재 P1의 이 시점은 세 번째 해석을 지지합니다. 모든 시점에서 잔여층이 없어졌다는 결론은 아닙니다.</p></section>
<section><h2>5. 이미 MVS인 depth를 다시 평가하는 이유</h2><p>다시점 검사를 통과했다는 것은 선별 조건을 만족했다는 뜻이며, 남은 픽셀의 예상 오차가 모두 같다는 뜻은 아닙니다. 다만 동일한 이진 필터를 반복하는 것만으로는 새 근거가 생기지 않습니다.</p>
<ul><li>현재 GS 입력은 geometric depth이며, 원 depth 값과 유효성만 읽습니다. confidence 가중치는 사용하지 않습니다.</li><li>원 workspace의 consistency_graphs는 0개입니다. 일치 영상 목록이 저장되지 않았다는 뜻이며, 검사를 안 했다는 뜻은 아닙니다.</li><li>확인한 대표 영상의 patch-match.cfg는 __auto__, 20입니다. 이는 후보 영상 선택 설정이며 픽셀마다 20개 관측이 지지한다는 뜻은 아닙니다.</li><li>원 실행의 정확한 필터 임계값은 이번 진단에 결박하지 못했습니다. 현재 설치 버전의 기본값으로 대신하지 않습니다.</li></ul>
<p>다음 단계에서는 기존 depth에서 복원한 잔차·관측각·관측 지지를 먼저 각각 표시합니다. 아직 이를 정확도 확률이나 최종 자동 가중치라고 부르지 않습니다. 추가 점수가 오차를 구분하지 못한다면 confidence 재가중의 효과를 주장하지 않습니다.</p><a href="mvs_inventory.json">MVS 입력 조사 JSON</a> · <a href="https://colmap.github.io/format.html#consistency-graphs">COLMAP 자료 형식</a></section>
<section><h2>검증 및 남은 범위</h2><ul><li>최종 세 조건의 재렌더 depth는 저장된 depth와 최대 차이 0입니다.</li><li>보호·비보호 기여의 합은 전체 alpha와 최대 약 0.0000011 이내에서 일치합니다.</li><li>원본 입력·checkpoint는 읽기 전용이며, 변경은 신규 진단 산출물에 한정했습니다.</li><li>단일 시점, 중심 기반 집단, 저장된 끝점 진단입니다. 모든 표면의 제거·생성 이력·독립 정확도·일반화 결론은 미확인입니다.</li><li>기술 검증 PASS / 기제 해석 PARTIAL / scientific_verdict: null.</li></ul></section>
<p class="muted">다음 검토 단계: P1/P2/P3 자동 근거 지도 → MVS 신뢰도만 적용 → 국소 prior 조절 추가. 각 단계의 그림과 측정 결과를 확인한 뒤 이어갑니다.</p></main>
<script>const image=new Image();image.src='attribution.png';const canvas=document.getElementById('detail-canvas'),ctx=canvas.getContext('2d');function draw(){const row=Number(document.getElementById('state').value);ctx.clearRect(0,0,canvas.width,canvas.height);ctx.drawImage(image,0,row*image.height/4,image.width*.915,image.height/4,0,0,canvas.width,canvas.height)}image.onload=()=>{draw();window.__ATTRIBUTION_READY__=true};document.getElementById('state').addEventListener('change',draw);</script></html>'''
page=page.replace('ROWS',rows)
(out/'report.html').write_text(page)
(out/'report_receipt.json').write_text(json.dumps(dict(status='PASS_REPORT_BUILD',source_result_sha256=hashlib.sha256((out/'result.json').read_bytes()).hexdigest(),script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),scientific_verdict=None),indent=2))
print('report.html written')
