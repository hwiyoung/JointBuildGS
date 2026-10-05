"""Rebuild Korean deliverables from measured CSVs; no training or method changes."""
import csv,json
from pathlib import Path

def read(p):
 with p.open(newline='',encoding='utf-8-sig') as f:return list(csv.DictReader(f))
def number(x,d=4):return '미측정' if x in ('',None) else f'{float(x):.{d}f}'
def pct(x):return '미측정' if x in ('',None) else f'{float(x)*100:.1f}%'
def md(headers,rows):return '\n'.join(['| '+' | '.join(headers)+' |','|'+'|'.join(['---']*len(headers))+'|']+['| '+' | '.join(map(str,r))+' |' for r in rows])
def write_korean(T):
 A=read(T/'tables/table_A.csv');B=read(T/'tables/table_B.csv');C=read(T/'tables/table_C.csv');D=read(T/'tables/table_D.csv');P=read(T/'tables/prior_roof_error.csv')
 roof={r['condition']:r for r in B if r['surface']=='roof'};prior={r['condition']:r for r in P}
 headers={'condition':'조건','status':'측정상태','measurement_status':'측정상태','PSNR_dB':'PSNR_dB','SSIM':'SSIM','LPIPS_native_vgg':'LPIPS_공식VGG','global_M3C2_mean_abs_m':'전역M3C2_절대평균_m','global_M3C2_signed_median_m':'전역M3C2_부호중앙값_m','global_M3C2_valid_n':'전역M3C2_유효점수','F1_at_0_2':'F1_0.2m','F1_at_0_5':'F1_0.5m','global_M3C2_rmse_m':'전역M3C2_RMSE_m','global_M3C2_signed_mean_m':'전역M3C2_부호평균_m','surface':'표면','n':'표본수','median_m':'부호오차_중앙값_m','nmad_m':'NMAD_m','abs_gt_0_2_fraction':'절대오차_0.2m초과_비율','gt_n':'GT_점수','prediction_n':'재구성_표본수','protected_n_8000':'8000회_보호판정수','matched_n_30000':'30000회_추적성공수','opacity_median':'추적집합_불투명도중앙값','opacity_gt_0_5_fraction':'추적집합_불투명도0.5초과비율','opacity_lt_0_01_fraction':'추적집합_불투명도0.01미만비율','movement_median_m':'추적집합_이동량중앙값_m','movement_p95_m':'추적집합_이동량95분위_m','distance_failed':'추적_거리초과실패수','collision_failed':'추적_중복대상실패수','unmatched_total':'추적_총실패수','matched_native_protected_fraction':'추적성공중_실제보호비율','roof_unprotected_n':'지붕_비보호원반수','roof_unprotected_opacity_median':'지붕_비보호불투명도중앙값','actual_protected_n':'실제보호원반수','actual_protected_opacity_median':'실제보호_불투명도중앙값','actual_opacity_gt_0_5_fraction':'실제보호_불투명도0.5초과비율','actual_opacity_lt_0_01_fraction':'실제보호_불투명도0.01미만비율','roof_actual_protected_n':'지붕_실제보호원반수','roof_actual_protected_opacity_median':'지붕_실제보호불투명도중앙값','roof_actual_protected_opacity_gt_0_5_fraction':'지붕_실제보호不透明度0.5초과비율','roof_actual_protected_opacity_lt_0_01_fraction':'지붕_실제보호불투명도0.01미만비율','nonfinite_xyz_30000':'30000회_비정상좌표수','nonfinite_xyz_native_protected':'실제보호_비정상좌표수','nonfinite_xyz_native_unprotected':'비보호_비정상좌표수','actual_opacity_nonfinite_n':'실제보호_비정상불투명도수','actual_opacity_valid_n':'실제보호_유효불투명도표본수','event':'학습상태','added':'누적추가수','removed':'누적제거수','clone_added':'복제추가수','split_added':'분할자식추가수','split_parents_removed':'분할부모제거수','culled':'불투명도크기_가지치기수'}
 headers['roof_actual_protected_opacity_gt_0_5_fraction']='지붕_실제보호불투명도0.5초과비율'
 values={'MEASURED':'측정완료','MEASURED_WITH_NONFINITE_EXCLUSIONS':'비정상값제외후_측정완료','COMPLETE_TRAINING':'학습완료','completed':'완료','roof':'지붕','wall':'벽면'}
 for tag,rows in zip('ABCD',[A,B,C,D]):
  assert set(rows[0])<=headers.keys(),set(rows[0])-headers.keys()
  with (T/f'tables/표_{tag}.csv').open('w',newline='',encoding='utf-8-sig') as f:
   w=csv.DictWriter(f,fieldnames=[headers[k] for k in rows[0]]);w.writeheader();w.writerows([{headers[k]:values.get(v,v) for k,v in row.items()} for row in rows])
 paper=[['N',16.654,.527,.266,.378,.469,.788],['B+0.25',16.617,.521,.382,.384,.447,.787],['B+0.5',16.312,.519,.385,.387,.448,.785],['B+1.0',15.866,.510,.395,.387,.451,.787]]
 with (T/'tables/논문표7_높이편향.csv').open('w',newline='',encoding='utf-8-sig') as f:
  w=csv.writer(f);w.writerow(['조건','PSNR_dB','SSIM','LPIPS','M3C2_m','F1_0.2m','F1_0.5m']);w.writerows(paper)
 rows=[]
 for p in paper:
  a=next(x for x in A if x['condition']==p[0]);rows.append([p[0],'논문 표7']+[number(v,3) for v in p[1:]])
  rows.append([p[0],'이번 단일건물']+[number(a[k],3) for k in ['PSNR_dB','SSIM','LPIPS_native_vgg','global_M3C2_mean_abs_m','F1_at_0_2','F1_at_0_5']])
 comparison=md(['조건','출처','PSNR','SSIM','LPIPS','M3C2(m)','F1@0.2','F1@0.5'],rows)
 failure_rates=[float(c['unmatched_total'])/float(c['protected_n_8000']) for c in C]
 lines=['# GeoGS 지붕 편향 진단 결과','',
'작업: GEOGS-ROOF-BIAS-20260921. 5조건의 학습과 계측을 완료했다. B−1.0 체크포인트의 비정상 값 때문에 실행 품질 상태는 PARTIAL로 유지한다. scientific_verdict: null. H1/H2/H3 판정은 하지 않는다.','',
'## 실험 의도를 충족했는가','',
'**단일 건물에서 지붕에 남은 부호 오차와 보호 가우시안의 불투명도를 분리해서 관찰하려는 계측 목적은 달성했다.** 두 값이 함께 확보되어 전역 기하 지표만으로 보이지 않는 내부 표현의 차이를 확인할 수 있다. 다만 표 7 동일 조건 재현, 편향만의 인과 효과, 비보호 가우시안이 실제 렌더 지붕을 형성했다는 증명은 달성한 것으로 볼 수 없다. 이는 가설 판정이 아니라 확보한 증거의 범위에 대한 평가다.','',
'최종 지붕 부호 오차 중앙값은 모든 조건에서 약 +0.225~+0.246 m다. 명목상 ±1 m를 입력했다고 최종 지붕 중앙값에 ±1 m가 그대로 나타난 것은 아니다. 그렇다고 최종 지붕 오차가 0인 것도 아니다. B+1.0의 실제 보호 원반은 불투명도 중앙값 0.00431, 0.01 미만 비율 52.4%다. 지붕으로 귀속된 실제 보호 원반만 보면 0.01 미만 비율은 64.4%다.','',
'## 원래 요청한 산출물','',
'- [표 A: 영상·전역 기하 지표](tables/표_A.csv) / [기계 판독용 원본](tables/table_A.csv)\n- [표 B: 지붕·벽면 부호 오차](tables/표_B.csv) / [원본](tables/table_B.csv)\n- [표 C: 보호 원반·불투명도·이동·추적 실패](tables/표_C.csv) / [원본](tables/table_C.csv)\n- [표 D: 밀집화·가지치기 누적 수](tables/표_D.csv) / [원본](tables/table_D.csv)\n- 그림 1~4는 아래에 제시한다. 명령·환경·로그는 provenance/, logs/, conditions/에, 재현 스크립트는 scripts/에 있다.\n- 조건별 8000·30000 PLY 10개는 conditions/조건/model/point_cloud/iteration_반복수/point_cloud.ply에 보존했다.','',
'## 지붕 부호 오차: 입력 prior와 최종 결과','',
md(['조건','prior 오차 중앙값(m)','최종 지붕 중앙값(m)','NMAD(m)','|오차|>0.2m'],[[a['condition'],number(prior[a['condition']]['median_m'],3),number(roof[a['condition']]['median_m'],3),number(roof[a['condition']]['nmad_m'],3),pct(roof[a['condition']]['abs_gt_0_2_fraction'])] for a in A]),'',
'prior 오차는 원본 복원 메시의 지붕 면에서 면적 비례로 추출한 동일 20만 점을 각 Δz만큼 이동해 계산했다. GT 지붕과의 최근접 거리에 원본 지붕 법선 방향으로 부호를 부여했다. N의 prior 수치는 복원 메시의 0 m 대체값이며, 저자가 실제 N 초기화에 사용한 메시를 측정한 값은 아니다. [추가 계측 CSV](tables/prior_roof_error.csv), [계측 정의](provenance/prior_roof_measurement.json).','',
'B+0.25는 prior 중앙값 +0.043 m에서 최종 +0.227 m로 GT 대비 오차가 커졌고, B+0.5는 +0.248 m에서 +0.243 m로 유사했다. B+1.0은 +0.695 m에서 +0.246 m, B−1.0은 −1.049 m에서 +0.225 m로 달라졌다. 각 분포를 비교한 관측이며 개별 점의 교정량이나 모든 지붕의 개선을 뜻하지 않는다.','',
'B+0.25에서 B+1.0까지 최종 지붕 중앙값의 차이는 약 0.019 m다. 명목 편향 간격 0.75 m보다 작지만, 이는 조건별 분포 중앙값 차이이며 같은 표면점을 추적한 이동량이나 보정률이 아니다. GT 대비 양의 잔여 오차는 계속 관측된다.','',
'![그림 1: 지붕 부호 오차 지도](figures/figure_1_roof_error.png)','그림 1. GT의 최근접 점 XY에 오차를 표시했다. 색 범위는 모든 조건에서 −1.5~+1.5 m로 고정했다. 0.2 m 표시 셀마다 결정론적으로 한 측정점을 선택했으며 보간하지 않았다.','',
'## 보호 가우시안의 불투명도','',
md(['조건','실제 보호 수','불투명도 중앙값','>0.5','<0.01','지붕 보호 <0.01'],[[c['condition'],c['actual_protected_n'],number(c['actual_protected_opacity_median'],5),pct(c['actual_opacity_gt_0_5_fraction']),pct(c['actual_opacity_lt_0_01_fraction']),pct(c['roof_actual_protected_opacity_lt_0_01_fraction'])] for c in C]),'',
'위 표는 공식 학습 중 기록한 실제 최종 보호 마스크 기준이다. B−1.0의 전체 보호 수는 66,431개이며, 불투명도 비율·중앙값의 유효 분모는 비정상 3개를 제외한 66,428개다. 지붕 귀속은 최종 중심에서 가장 가까운 원본 LoD2 면을 사용한다. 편향으로 중심이 다른 면에 귀속될 수 있어 지붕 하위집합은 조건 간 동일 원반 집합이 아니다.','',
md(['조건','8000 보호 판정','5cm 추적 성공','추적 실패','추적 불투명도 중앙값','이동 중앙값(mm)','이동95분위(mm)'],[[c['condition'],c['protected_n_8000'],c['matched_n_30000'],c['unmatched_total'],number(c['opacity_median'],5),number(float(c['movement_median_m'])*1000,2),number(float(c['movement_p95_m'])*1000,2)] for c in C]),'',
f'발주서의 8000→30000 최근접 5 cm 추적에서는 {min(failure_rates)*100:.1f}~{max(failure_rates)*100:.1f}%가 거리 또는 중복 대상 때문에 실패했다. 추적 통계는 성공한 원반만의 통계다. 8000 PLY는 그 반복의 밀집화·보호 등록 전에 저장되므로 실제 보호 마스크와 완전히 같지 않다. 추적 성공 집합에도 최종 비보호 원반과의 근접 매칭이 포함될 수 있다. 따라서 실제 보호 마스크 통계를 함께 제시하며 두 분모를 혼용하지 않는다.','',
'![그림 2: 보호 원반 불투명도](figures/figure_2_opacity.png)','그림 2. 발주서의 5 cm 추적 성공 집합을 사용한 N과 B+1.0 히스토그램. 두 집합의 크기가 달라 구간별 비율로 정규화했다. 실제 최종 보호 집합 전체의 비율과는 분모가 다르다.','',
'![그림 3: 지붕 마루 단면](figures/figure_3_section.png)','그림 3. 모든 조건에서 같은 마루 횡단면과 0.5 m 폭을 사용했다. 주황 점선은 복원한 편향 prior, 파랑은 최종 메시 표본, 회색은 GT, 색 점은 실제 보호 원반이다. N의 주황선도 제공된 원본 메시가 아닌 복원 대체 메시다. 이 단면에서는 ±1 m prior와 분리된 최종 지붕 및 prior 부근의 낮은 불투명도 원반을 관찰할 수 있다. 단면 한 장은 지붕 전체에 대한 증거를 대신하지 않는다.','',
'## GeoGS 표 7과의 비교','',
'기존 첨부 출판 PDF의 인쇄 199쪽(PDF 16쪽) 표 7과 §5.5를 이번에 직접 추출하고 페이지 이미지로 확인했다. 앞선 보고서의 “웹 403 때문에 표 7 수치 미확인” 상태를 갱신한다. [검증한 표 7 페이지](provenance/paper_page16.png), [추출 텍스트](provenance/paper_page16.txt), [높이 편향 4행 CSV](tables/논문표7_높이편향.csv), [논문 DOI](https://doi.org/10.1016/j.isprsjprs.2026.07.011). 원문 PDF SHA256: 21342911a9f5db6aba9be155a1e06cb4d36d7a2e27780235acb111f8e91c28c4.','',
'논문은 Region 1, K=13 조건이다. 이번 실험은 저자 제공 단일 건물 example_scene의 13 학습·2 시험 시점이며, 정확한 평가 범위·영상 구성의 동등성이 확보되지 않았다. 아래 숫자는 범위를 명시한 병렬 제시이며 성능 우열 또는 재현 성공 판정에 사용하지 않는다. −1 m는 논문 표 7에 없는 추가 조건이다.','',comparison,'',
'논문 N→+1 m는 M3C2가 0.378→0.387 m(+0.009 m), F1@0.5가 0.788→0.787로 변화한다. 이번 N→+1 m는 M3C2가 0.41875→0.42618 m(+0.00742 m), F1@0.5가 0.66642→0.66429로 변화한다. 전역 기하 지표의 변화가 작은 양상은 양쪽에 나타난다. 이는 지붕이 정확하거나 오류 prior가 수정됐다는 증명이 아니다.','',
'영상 지표는 같은 양상으로 재현되지 않았다. 논문 N→+1 m에서 LPIPS는 0.266→0.395, PSNR은 16.654→15.866 dB다. 이번 실험은 LPIPS 0.38670→0.38806, PSNR 16.004→16.522 dB다. 이번 N부터 LPIPS가 높고 PSNR 변화 방향도 다르다. 편향 조건끼리 +0.25→+1 m의 LPIPS는 0.38014→0.38806으로 증가하지만 논문의 N 대비 큰 격차와 동일시할 수 없다.','',
'표 7에는 지붕만의 부호 오차나 보호 가우시안의 불투명도 열이 없다. 이번 결과의 추가 가치는 전역 M3C2 변화가 작아도 지붕에 약 +0.23 m 잔여 오차가 있고, 낮은 불투명도의 보호 원반이 상당수 존재한다는 두 사실을 따로 측정했다는 것이다. 이를 H1/H2/H3 중 하나로 판정하지 않는다.','',
'![그림 4: 동일 시험 시점 렌더](figures/figure_4_test_render.png)','그림 4. 모든 조건의 같은 첫 번째 시험 카메라. 제목의 LPIPS는 해당 한 장의 점수가 아니라 공식 metrics.py가 계산한 시험 2장 평균이다.','',
'## 재현 조건과 남은 한계','',
'- 공식 GeoGS 커밋 db40c95c657ec03ff21c83cb99cf39f4e90247a6. 원본 방법 코드 diff는 비어 있다. 계측은 observe_train.py의 로그·덤프와 체크포인트 후처리다.\n- 시드 0, 30,000회, 단계 전환 8,000회, τ=0.2 m, 보호 학습률 배율 0.01, mesh_res=1024. 조건당 1회, 새 N·추가 조건·튜닝 없음. DA3와 카메라 포즈는 공유했다.\n- 원본 example OBJ가 없어 TUM2TWIN CityGML에서 DEBY_LOD2_4959323을 복원했다. 제공 보호 점군과 복원 표면의 최근접 거리 중앙값은 약 0.089 m다. N은 제공 초기화·깊이, B들은 복원 메시 재생성을 사용하므로 N 대비 변화의 인과 해석이 제한된다.\n- +Z 연직은 OPF 프레임과 15개 대응 카메라로 검증했다. CityGML은 EPSG:25832이며 OPF의 EPSG:32632 표기와 수평 기준계 연결은 독립 검정하지 않았다. 입력 좌표 계보는 provenance/에 기록했다.\n- 지붕은 지면이 아닌 원본 면 중 |법선 연직성분|>0.2로 정의했다. 최근접 원본 면으로 GT·재구성 표본을 귀속하고 지붕은 위가 +, 벽면은 원본 면 법선 방향을 부호 기준으로 삼았다. NMAD=1.4826×중앙절대편차다. 이 값은 순수 수직 높이차가 아니라 부호 있는 최근접 유클리드 거리다.\n- 전역 평가는 원본 건물 XY 경계의 고정 사각형으로 메시를 먼저 자른 뒤 공식 mesh2pcd를 실행했다. 사각형 내부의 주변 기하가 포함될 수 있다. 모든 조건에 같은 영역을 사용했다.\n- 실제 보호 불투명도는 렌더 기여도와 같지 않다. 지붕 비보호 원반 수·불투명도도 실제 표면 형성의 증거를 대신하지 않는다. 전체 집합의 낮은 불투명도만으로 H2를 확정할 수 없다.\n- B−1.0 최종 PLY의 73개 원반(보호 3·비보호 70)에 비정상 좌표·불투명도가 있다. 원본 PLY는 그대로 보존했다. 후처리는 공간 검색에서 비정상 좌표를 제외하고 유효 분모를 기록했다. 발생 원인은 미확인이다. 원본 체크포인트로 생성된 렌더·메시 지표에도 이 품질 예외가 적용된다.\n- N의 M3C2 최초 실패는 읽기 전용 소스 폴더의 로그 쓰기 때문이었다. 작업 경로만 변경한 재평가는 성공했다. 초기 실패 로그도 보존했다.\n- 표 7과 동일 범위가 아니므로 ±10% 기준 성능 통과 판정은 하지 않는다. 제공 example의 공식 수치 기대값도 없었다.\n- Docker 환경은 Python 3.10.20, Torch 2.1.2+cu121이며 CUDA 컴파일러 12.1.105와 Matplotlib 3.9.2를 사용했다. 저자 시험 CUDA 12.4와 차이가 있다. 설치 기록·이미지 ID·명령·소요 시간은 provenance/ 및 조건별 receipt에 있다.','',
'## 재생성','',
'저장된 데이터에서 `measure_prior_roof.py`로 prior 지붕 오차를, `export.py`로 표 A~D·한글 CSV·그림 1~4·이 보고서를 재생성한다. `write_korean.py`는 CSV 값을 읽어 한국어 보고서를 작성한다. 모든 계산은 기록된 Docker 이미지에서 실행한다. `seal_delivery.py`가 산출물·스크립트·체크포인트 해시를 기록한다. 단계별 원명령은 조건별 receipt와 provenance/에 보존했다.','',
'<!-- END GEOGS-ROOF-BIAS-20260921 KO -->']
 (T/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
 (T/'report_ko.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
if __name__=='__main__':write_korean(Path('/task'))
