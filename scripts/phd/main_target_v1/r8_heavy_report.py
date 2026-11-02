"""Factual heavy-view readout report, no interpretation or scientific verdict."""
import shutil
from common import *
ROOT=OUT/'r8_recorded_continue';H=ROOT/'heavy';T=H/'tables'
def read(p):return json.loads(Path(p).read_text())
def build():
 assert read(H/'stats_verification.json')['status']=='PASS'
 assert read(H/'r8_receipt.json')['exit_code']==0 and read(H/'base_receipt.json')['exit_code']==0
 c=read(CFG/'r8_heavy.json');rows=read(T/'top_summary.json')['rows'];cam=c['heavy_camera'];s=[r for r in rows if r['camera']==cam];cross=read(T/'top_cells.json')['rows'];dist=read(T/'distributions.json')['rows'];gr=read(T/'pre_density_gradients.json')['rows'];growth=read(T/'growth_1000.json')['rows'];st=[r for r in s if r['state']=='r8_14031_stop'];base=[r for r in s if r['state']=='base_LoD2_30000']
 notes=['# r8 LoD2 중단 상태 — 무거운 영상과 저장 상태 원인 점검','',f'기록 시각: {stamp()}. `scientific_verdict: null`. 결론과 원인 해석은 쓰지 않고 저장 상태의 수치·그림만 제시한다.','',
 '11월 2일 후속 결정에 따라 추가 학습을 하지 않았다. 완료 반복은 14,030회이고 14,031회 forward 직전 상태를 읽었다. r8 항공 LiDAR는 완료 상태로 보존했고 나머지 여섯 판은 시작하지 않았다. 15,000·30,000회 r8 LoD2 결과는 없음.','',
 '## 셈과 저장 시점','',
 '- 상위 1%·10%의 분모는 각 상태의 **전체 가우시안 수**다. 겹침 0인 행을 포함하고 `ceil(비율 × 전체 수)`개를 고른다. 정렬은 겹침 내림차순, 동률은 저장 행 번호 오름차순이다. 표의 실제 선택 수·양의 겹침 수·마지막 순위 겹침도 JSON/CSV에 있다.',
 '- 겹침은 CUDA가 배정한 가우시안–타일 쌍 수다. 가려짐·알파 합성으로 실제 색에 기여했는지와는 별개의 정렬 작업량이다. 반지름은 같은 forward가 반환한 정수 pixel 반지름이다.',
 '- 카메라 거리는 중심 간 3차원 유클리드 거리, 긴 축은 `max(exp(scale_0),exp(scale_1))`(직경 아님), 불투명도는 `sigmoid(opacity)`다. 분포는 전체 선택 무리에 대해 계산했다.',
 '- 8,000~14,000회는 밀도 제어 **직전 PLY**와 **직후 완전 상태 PLY**를 따로 그렸다. 기울기 표는 직전 PLY와 같은 모집단이다.',
 '- 자리 칸은 기존 공통 기준 그대로다. 가로: 평가 상자 안 / 밖 50 m 안 / 50~200 m / 200 m 넘음. 높이(m): −43.640 아래 / −43.640~−10.180 / −10.180~0.476505482 / 0.476505482 위. 중간 높이는 쓰지 않았다.',
 '- `init_id`와 최초 `origin`을 씨앗 파일에 대조했다. 기준선은 SfM·사전 정보 출신, r8은 현재 배경·패치·풀림(100회 자손)·풀림(그 밖)을 사용했다. 처음 출신은 CSV에 별도 보존한다. 직접 부모 ID는 저장되지 않아 확인 불가다.',
 '- 모든 추가 GPU 실행은 저장 모델 렌더이며 최적화 0회다. 렌더용 여유량 95% 확인선은 Adam이 없는 읽기 전용 과정에만 적용했다. 학습의 절반 초과 멈춤값은 바꾸지 않았고 학습을 다시 시도하지 않았다.','',
 '## 무거운 영상과 기준선','',f'영상: `{cam}`. 중단 상태 {st[0]["population"]:,}개, 기준선 LoD2 30,000회 {base[0]["population"]:,}개.','',
 '| 상태 | 상위 무리 | 선택 수 | 겹침 수 | 전체 겹침 몫 | 처음 씨앗 수 |','|---|---:|---:|---:|---:|---:|']
 for r in st+base:notes.append(f'| {r["state"]} | {r["top_fraction"]*100:g}% | {r["selected"]:,} | {r["selected_overlap"]:,} | {r["overlap_share"]*100:.4f}% | {r["distinct_initial_seeds"]:,} |')
 notes+=['','분포의 0·1·5·25·50·75·95·99·100 백분위와 고정 구간 히스토그램은 `heavy_r8_lod2/tables/distributions.json`에 있다. 아래는 중앙값 / 95백분위다.','', '| 상태 | 상위 | 카메라 거리 m | 긴 축 m | 불투명도 | 반지름 pixel |','|---|---:|---:|---:|---:|---:|']
 for r in st+base:
  vals=[]
  for metric in ['camera_distance_m','longest_axis_m','opacity','radius_pixels']:
   dd=next(d for d in dist if d['state']==r['state'] and d['camera']==cam and d['top_fraction']==r['top_fraction'] and d['metric']==metric);v=dd['quantiles'];vals.append(f'{v["50"]:.4g} / {v["95"]:.4g}')
  notes.append(f'| {r["state"]} | {r["top_fraction"]*100:g}% | '+' | '.join(vals)+' |')
 notes+=['','| 상태 | 상위 | 출신 | 선택 수 | 전체 겹침 몫 |','|---|---:|---|---:|---:|']
 for rr in st+base:
  cc=[r for r in cross if r['state']==rr['state'] and r['camera']==cam and r['top_fraction']==rr['top_fraction']]
  for tag in sorted({r['tag'] for r in cc}):
   tt=[r for r in cc if r['tag']==tag];notes.append(f'| {rr["state"]} | {rr["top_fraction"]*100:g}% | {tt[0]["provenance"]} | {sum(r["count"] for r in tt):,} | {sum(r["overlap_fraction_of_all"] for r in tt)*100:.4f}% |')
 notes+=['','출신×가로×높이의 모든 칸은 `top_cells.csv/json`에 있다. 빈 칸도 0으로 기록했다. 각 칸의 긴 축·거리·불투명도·반지름 중앙값은 빈 칸일 때 null이다.','',
 '## 같은 영상의 반복별 기록','', '| 반복 | 저장 시점 | 전체 겹침 | 상위 1% 몫 | 상위 10% 몫 |','|---:|---|---:|---:|---:|']
 for r in s:
  if r['top_fraction']!=.01:continue
  q=next(t for t in s if t['state']==r['state'] and t['top_fraction']==.1);notes.append(f'| {r["iteration"]:,} | {r["stage"]} | {r["total_overlap"]:,} | {r["overlap_share"]*100:.4f}% | {q["overlap_share"]*100:.4f}% |')
 notes+=['','`fixed_initial_seed_cohorts.csv/json`은 중단 영상의 상위 무리와 **같은 처음 씨앗 ID를 공유하는 모든 자손**을 각 저장 상태에서 집계한다. 이는 중간 반복의 정확한 부모 경로를 복원한 값이 아니다. 매 상태에서 새로 뽑은 상위 무리와 구별한다.','',
 '## 다른 영상','', '중단 상태 203장 모두의 전체 forward와 개별 겹침을 확인했다. 아래 다섯 장은 재렌더한 개별 겹침 배열도 기존 203장 측정과 바이트 단위로 같았다.','', '| 순위 | 영상 | 전체 겹침 | 상위 1% 몫 | 상위 10% 몫 |','|---:|---|---:|---:|---:|']
 top5=read(ROOT/'stop_diagnostic/renders/summary.json')['top5']
 for i,v in enumerate(top5,1):
  one=next(r for r in rows if r['state']=='r8_14031_stop' and r['camera']==v['camera'] and r['top_fraction']==.01);ten=next(r for r in rows if r['state']=='r8_14031_stop' and r['camera']==v['camera'] and r['top_fraction']==.1);notes.append(f'| {i} | {v["camera"]} | {v["overlaps"]:,} | {one["overlap_share"]*100:.4f}% | {ten["overlap_share"]*100:.4f}% |')
 notes+=['','다섯 장 각각의 같은 분포·출신×자리 표, 개별 상위 가우시안과 처음 씨앗 목록을 함께 냈다. 203장 전체 표는 이어 학습 기록의 `recorded_r8_lod2/tables/render_views.csv`와 `render_cross.csv`에 있다.','',
 '## 밀도 제어 직전 기울기와 수 변화','', '| 반복 | 직전 가우시안 수 | 기울기 문턱 이상 수 | 비율 |','|---:|---:|---:|---:|']
 for it in range(8000,14001,1000):
  rr=[r for r in gr if r['iteration']==it];n=sum(r['count'] for r in rr);above=sum(r['above'] for r in rr);notes.append(f'| {it:,} | {n:,} | {above:,} | {100*above/n:.4f}% |')
 notes+=['','문턱은 0.0002이며 저장된 `accum/denom >= 문턱`을 사용했다. NaN은 원래 구현과 같이 0이다. 이는 기울기 조건을 넘은 수이며 복제·분할·삭제 결과 수와 동일한 항목이 아니다. 전체 7×64칸은 `pre_density_gradients.csv/json`에 있다.','',
 '| 1,000회 구간 | 시작 수 | 끝 수 | 순변화 |','|---|---:|---:|---:|']
 for it in range(8000,14001,1000):
  rr=[r for r in growth if r['end']==it];notes.append(f'| {it-1000:,} → {it:,} | {sum(r["start_count"] for r in rr):,} | {sum(r["end_count"] for r in rr):,} | {sum(r["net_change"] for r in rr):+,} |')
 notes+=['','1,000회 변화는 매 100회 **반복 후** 기록의 차이를 더해 양 끝 수와 일치함을 확인했다. 7,000회 시작은 원래 완전 상태다. 칸별 변화에는 칸 사이 이동·복제·분할·삭제가 함께 들어 있으므로 이를 각각의 원인 수로 읽지 않는다. 모든 칸은 `growth_1000.csv/json`에 있다.','',
 '## 그림과 개별 계보 자료','',
 '![반복별 겹침](heavy_r8_lod2/figures/heavy_iteration_curve.png)','',
 '![상위 1% 위치](heavy_r8_lod2/figures/top1_camera_overhead.png)','',
 '![상위 10% 위치](heavy_r8_lod2/figures/top10_camera_overhead.png)','',
 '![분포 비교](heavy_r8_lod2/figures/top_distributions.png)','',
 '- 위치 그림은 선택된 모든 중심을 그린다. 카메라 시점에는 원래 전체 RGB와 화면 안 중심을 겹쳤고, 가장 무거운 100개는 CUDA 반지름의 사각 범위를 추가했다. 중심이 화면 밖이어도 큰 가우시안은 화면 타일에 겹칠 수 있으므로 화면 밖/뒤 중심 수를 그림 JSON에 명시했다. 위에서 본 전체 범위와 평가 상자 주변 확대를 함께 낸다.',
 '- ZIP의 `heavy_selected_rows/*top10.csv.gz`: 상위 10% 모든 행, 상위 1% 표시, 겹침, 처음 씨앗 ID·출신, 현재 출신·자리·XYZ·거리·크기·불투명도·반지름. `*ancestors.csv.gz`: 두 상위 무리의 처음 씨앗별 자손 수·겹침 수. 별도 색상이나 행 표본으로 생략하지 않았다.',
 '- 각 그림에는 JSON이 있다. 체크포인트·PLY·전체 개별 겹침 NPZ는 외부 경로와 SHA-256으로 제공하며 ZIP에 중복하지 않는다. 패키지 무결성은 과학적 판정이 아니다.','']
 report=DOC/'중단상태_원인점검_r8_LoD2.md';report.write_text('\n'.join(notes));dest=DOC/'heavy_r8_lod2';dest.mkdir(exist_ok=False);shutil.copytree(H/'figures',dest/'figures');(dest/'tables').mkdir()
 for p in T.iterdir():
  if p.suffix in ['.json','.csv']:shutil.copy2(p,dest/'tables'/p.name)
 shutil.copy2(H/'stats_verification.json',dest/'stats_verification.json');return report,dest
if __name__=='__main__':build()
