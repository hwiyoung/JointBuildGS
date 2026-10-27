"""Compact factual report from current receipts, paired tables and frozen preparation."""
import json
from pathlib import Path
from inputs import OUT,save
from side_tables import VARS

DOC=Path('/docs');TAB=DOC/'tables'
def load(path,default=None):return json.loads(path.read_text()) if path.exists() else default
def fmt(x,n=4):return '확인 불가' if x is None else f'{x:.{n}f}'

def main():
    rt=load(TAB/'runtime.json');c=rt['counts'];scores=load(TAB/'patch_scores_all.json')['rows']
    gates=load(TAB/'direct_stage1_gates.json');selection=load(OUT/'checks/lambda_selection.json')
    lines=['# 손실 학습 시험 v1','',
        f"완료 학습: 짧은 학습 {c['calibration_complete']}/4, 본 학습 {c['required_complete']}/24, 선택 {c['optional_complete']}/6. 핵심 패치 채점 {c.get('core_patch_scored',0)}판, 추가 후처리까지 완료 {c['post_complete']}판, 추가 지표까지 채점 완료 {c['measurements_complete']}판. 기준 중단 {c.get('training_health_stopped',0)}판. 상태 {rt['status']}.",
        f"고른 λ: {selection['selected_lambda']}. 최초 규칙으로 골랐고 이후 바꾸지 않았다.",
        '확인 불가: 미완료 판의 결과 면·채점·최종 학습 비교. 오류나 중단을 완료 결과로 세지 않는다. scientific_verdict: null.','',
        f"기록 시각: {rt['at']}. 새로 계산한 표·그림은 [이 발주에서 냄]. 이 문서는 사실과 측정값만 적는다.",'',
        '## 단계 가: 구현과 확인','',
        'r16에서 r17을 만들고 깊이 두 항을 선택하는 스위치를 추가했다. 기본 동작의 실제 초기화·15,000회 체크포인트 확인은 6/6, 새 손실 화소 확인은 6/6 통과했다. CPU 손실·미분 검사 240건이 통과했다. 초기화·사진 손실·보호·밀도 제어 소스는 유지했다. 이후 관측 코드를 추가하면서 두 파일(jbgs_judgment.py, train.py)만 달라진 것을 새로 빌드해 확인했다.','',
        '10월 26일 17시 수정 지시에 따라 UNCERT 고리 1.5 m·MVS 판 가의 값을 같은 순서의 1단계 패치에서 읽어 직접 규칙을 적용했다. 5 cm·18 cm 연결은 기록으로만 남겼다. 참값 없는 패치는 사정 평균값을 쓰고 채점에서 뺀다. MVS가 없는 패치는 MVS 항을 쓰지 않는다. 중앙값으로 대체한 항공 LiDAR 패치도 채점에서 뺀다.','',
        '| 단위 | 사전 | 평가 패치 N | 평가 넓이 m² | 직접 규칙 넓이 % |',
        '|---|---|---:|---:|---:|']
    for r in gates['rows']:lines.append(f"| {r['site']} | {r['prior']} | {r['eval_patches']} | {fmt(r['eval_area_m2'])} | {fmt(100*r['area_coverage'])} |")
    lines+=['','넓이 95% 기준은 6/6 통과했다. LoD2 중심 1 cm 쌍 점검의 전체 일치율은 B0 99.0830%, B173 주변 99.3798%, R1 94.6727%로 모두 90% 이상이다. 지붕·벽별 분모, 다른 쌍의 두 거리와 이유, 대체 패치·넓이·화소 비율은 [준비 보고](준비보고_v1.md)와 직접 규칙 표에 있다.','',
        f"짧은 학습 4회에서 기본 λ의 전체 학습 영상 PSNR 하락은 {fmt(selection['psnr_drop_db'],9)} dB였다. 0을 포함한 전체 가우시안 중심 미분의 중앙값은 사진·깊이 모두 0이므로 비율 0/0은 확인 불가다. 미리 고정한 엄격 비교 0 < 0은 거짓이고 PSNR 하락도 1 dB 이하라 λ=0.0025를 유지했다. 이 중앙값으로 깊이 항의 세기가 충분하다고 단정하지 않는다. [세기 표](tables/calibration.md), [미분 기록](tables/calibration_gradient_audit.md).",'',
        'B173 타일 6911_53361의 두 항공 LiDAR 면 차이는 입력에 적용한 Z 이동량 차이로 점검했다. 대응하는 원자료 점을 비교했을 때 Z 이동량을 제외한 높이 차 중앙값은 0.0193642014 m, 95% 값은 0.0359128353 m였다. 이는 두 준비 자료의 차이를 설명하는 기록이며 참값 판정은 아니다.','',
        '## 8.1 1단계 패치의 결과 면','',
        '같은 평가 범위·참값·허용 오차로 센다. 바깥에서 처음 만난 면을 읽고 면 없음은 τ 밖으로 센다. 100패치 미만은 표본 부족이다. 아래는 채점이 있는 학습 결과이며, 미완료 판은 전체 표에서 확인 불가다.','',
        '| 단위 | 사전 | 판 | 범위 | N | 학습 없음 % | 학습 τ 안 % | 면 없음 m² | 면 없음 % |',
        '|---|---|---|---|---:|---:|---:|---:|---:|']
    actual=[r for r in scores if r['variant'].startswith('lt_')]
    for r in actual:
        if r['subset'] not in ['all_0_3','unexplained','cell_2']:continue
        label=dict(all_0_3='전체 0~3',unexplained='차가 설명 안 됨',cell_2='보존')[r['subset']]
        label+=('·표본 부족' if r['minimum_sample']=='INSUFFICIENT' else '')
        lines.append(f"| {r['site']} | {r['prior']} | {r['variant']} | {label} | {r['patches']} | {fmt(r['analytic_within_tau_percent'])} | {fmt(r['within_tau_percent'])} | {fmt(r['no_surface_area_m2'])} | {fmt(r['no_surface_percent'])} |")
    if not actual:lines.append('| 학습 채점 미완료 | — | — | 확인 불가 | — | — | — | — | — |')
    lines+=['','여섯 단위와 세 단위 합, 모든 칸과 면 없음 넓이, 기존 nojudge·본 방법 두 씨앗·MVS·사전 정보: [전체 패치 표](tables/patch_scores_all.md). 학습 없는 도착점과 학습을 나란히 두었으며, 모든 표의 반올림 전 값·분모·출처는 같은 이름 JSON·CSV에 있다. 다듬기 거리 중앙값은 면을 만난 패치에서 구하고 그 N을 별도로 적었다.','',
        '## 8.2 쪽 교차표와 8.3 두 축 지표','',
        '사전 정보 쪽·MVS 쪽·그 밖·면 없음을 같은 규칙으로 분류했다. [넓이 교차표](tables/sides_all.md)는 전체 설명 안 되는 곳, 보정, 보존을 따로 보인다. [두 축 지표](tables/axes_metrics.md)는 AXES71-v2의 같은 함수로 구한 열두 칸·의도별 합·전체 값이다. 기존 nojudge 여섯 단위는 a9에서 옮겼고, 독립 재계산 세 건은 모든 값이 1e-7 이내로 같았다.','',
        '8.4의 기준은 같은 지표에 존재하는 모은 흔들림 폭, 해당 단위 두 씨앗 폭, 비율 지표의 300/N 중 최댓값이다. 다른 정의의 흔들림 폭을 가져오지 않는다. 값과 수치 구간은 tables/noise_thresholds.json 및 numerical_changes.json에 남기고 과학적 판단을 붙이지 않았다.','',
        '## 8.5 심긴 점, 8.6 사진, 8.7 기대','',
        '[심긴 점의 운명](tables/fates_all.md)은 초기 점과 후손을 한 묶음으로 세어 지워짐·옛 자리·지금 면·둘 다 아님을 칸 1·3과 0·2에서 나눴고 칸 0과 칸 2도 별도로 적었다. [사진 표](tables/photo.md)는 같은 평가 영상의 PSNR·SSIM과 전체 학습 영상의 PSNR이다. 아래 추가 감시의 다섯 영상 PSNR과 구분한다. 기대 가~사는 tables/expectations.json·CSV에 측정값과 기준을 나란히 두며 판정하지 않는다.','',
        '## 추가 불투명도·PSNR 기록','',
        '사전 출신 불투명도는 모든 새 판에서 기록만 한다. 실제 정기 초기화 뒤 100회부터 전체 가우시안 불투명도 중앙값이 0.05 미만이면 멈춘다. PSNR은 기존 nojudge가 있는 7,000·15,000·30,000회에 같은 다섯 영상·같은 계산에서 3 dB 초과 낮을 때만 멈춘다. NaN과 실행 오류도 멈춘다.','',
        '새 판은 초기화 직전·+100회·+500회·매 1,000회에 출신별 수·불투명도 중앙값, 사전 계보의 초기 참값 칸별 값, 다섯 영상 PSNR을 남긴다. 새 생성 표식은 초기 사전·초기 영상·밀도 제어 생성의 세 집단을 겹치지 않게 나눈다. 참값 칸은 CPU 진단에서만 읽으며 손실이나 중단 결정에 쓰지 않는다.','',
        'nojudge는 다시 학습하지 않는다. 15,000·30,000회 모델의 통계를 새 판과 나란히 읽는다. 다른 시점은 새 판끼리만 비교하고 nojudge 칸은 기록 없음이다. 과거 모델에는 생성 표식이 없어 세 출신 분리는 기록 없음이며, origin/init_id로 읽을 수 있는 계보별·참값 칸별 값은 보인다. 이미 실행 중인 판 1의 누락도 남은 기록에서만 복구한다. [전체 관측 표](tables/monitor_v2_observations.md).','',
        '## 그림과 중간 보고','']
    figures=[]
    for p in sorted((DOC/'figures').glob('*.png')):
        if p.stem.startswith(('section_','map_','side_map_','render_','fates_')):
            meta=load(p.with_suffix('.json'),{});figures.append(dict(file=p.name,visual_review=meta.get('visual_review')))
            lines.append(f"- [{p.stem}](figures/{p.name}) — 그림 점검 {meta.get('visual_review','확인 불가')}")
    if not figures:lines.append('새 학습 결과 그림은 확인 불가: 새 메시의 후처리·채점이 아직 완료되지 않았다. 고정한 단면·사진 시점은 바꾸지 않았다.')
    lines+=['','[B173 중간 보고](중간보고_v1.md)는 보존 칸·면 없음 넓이·쪽 교차표·심긴 점·단면을 함께 보인다. 과거 9,100회 중단 진단 그림은 figures/opacity_grace_stop.png에 보존했다.','',
        '## 바꾼 것·오류·시간','',
        '사용자가 승인한 변경: 패치 연결 대신 1단계 직접 규칙, 초기화 직후 1~99회 유예, 이후 사전 불투명도를 기록 전용으로 바꾸고 전체 붕괴·세 시점 PSNR만 감시, 과거 기록 없음과 판 1 누락의 명시. 모두 앞 기록과 설정 해시를 남겼다. 손실 식·채점·밀도 제어는 변경하지 않았다.','',
        '3,001회 중단 두 건과 9,100회 사전 불투명도 중단을 보존했다. 새 판 2 attempt_2는 추가 기록의 카메라 목록이 기존 손실 카메라 사전을 덮어 첫 손실 계산에서 오류가 났다(최적화 0회). 이름을 분리하고 기존 속성 보존·실제 손실 순전파/역전파·모델 값/난수 상태 검사를 통과했다. 사용자 승인으로 attempt_3을 씨앗 0부터 시작했다. 이후 같은 조건의 검증된 기록 코드 수리는 자동 재실행하고 보고한다. 손실 식·채점·판을 바꾸거나 같은 판의 학습이 두 번 넘게 멈추면 문의한다. 이후 승인으로 자원 부족에 따른 후처리 중단은 학습 중단 횟수에서 제외했다. [오류 보고](중단보고_진단코드_v2.md).','',
        '판 1의 실행 중 소스를 바꾼 것은 이미 읽힌 함수에 영향을 주지 않는다. 시작 때 읽은 77d97761 소스·설정 해시는 별도 고정했고 완료 시 파일 해시와 구분한다. 기존 모델 사진 기록의 Docker 이름 충돌은 계산 시작 전 거절로 남겼고 GPU별 대기로 고쳤다. 기록 범위·표 모양·비교 시점의 세부 선택은 사용자 지시에 따라 이 절에 기록했다.','',
        '판 1과 판 2는 30,000회 학습을 완료했다. 판 1의 TSDF 후처리는 첫 시도와 같은 명령·48 GiB 제한의 재시도 모두 호스트 전체 메모리 부족으로 종료됐다(exit 137). Docker 사건과 커널의 해당 프로세스 기록으로 확인했다. 처음에는 가용 메모리 56 GiB를 기다렸고, 큰 CPU 채점을 TSDF와 직렬로 묶은 뒤 52 GiB(48 GiB 제한+4 GiB 여유)로 시작 대기선만 조정했다. 앞 대기와 두 실패 기록도 보존했다. 이후 사용자 승인으로 후처리 자원 중단을 학습 중단에서 분리했다. 새 실행 조건은 가용 RAM 64 GiB 이상이 60초 유지될 때 시작, 48 GiB 컨테이너 한도 유지, 동일 조건에서 최초 실패 뒤 최대 두 번 재시도다. 완료한 판 1·2는 저장 모델만 후처리한다. 판 3·4와 나머지 20회 학습은 채점 대기와 독립적으로 두 GPU에 이어 배정한다. 사진 확인 작업의 잔여 프로세스·RAM 임시 캐시는 없어 삭제 없이 확인만 마쳤다. 심긴 점 운명은 기존 점별 분류를 유지한 채 칸 0과 칸 2도 따로 낸다. 학습 설정·TSDF·채점은 바꾸지 않았다. 이전 실행기가 공용 중단 파일을 덮은 사건도 별도 보존하고, 승인 해시와 일치하는 원래 9,100회 중단 사본을 복원했다. [후처리 중단 보고](중단보고_후처리메모리_v1.md).','',
        'B0·LoD2 고정·참값 판은 30,000회에 같은 다섯 영상 PSNR 20.677782 dB, nojudge 24.250185 dB로 3.572403 dB 낮아 원래 중단 문턱에 걸렸다. 이 판은 정상 완료로 세지 않고 중단 기록·15,000회 모델을 보존한다. 손실·채점·판·중단 기준을 바꾸지 않은 채 이미 승인된 다른 독립 학습과 완료 모델 후처리를 이어간다. [PSNR 중단 기록](중단기록_B0_LoD2_PSNR_v1.md).','',
        '판 3의 첫 시도는 14,717회 사진 SSIM 계산의 CUDA 메모리 부족으로 중단됐다. 새 대기열 실행기에 빠진 원 발주의 동일 설정 1회 재시도를 복원하고 검증했다. 앞 중단은 그대로 보존하고 판 3을 같은 GPU·씨앗·학습 설정으로 처음부터 한 번 재시도한다. 완료한 판 1·2·4는 재학습하지 않는다. [GPU 중단 기록](중단기록_GPU메모리_v1.md).','',
        '중간 보고에는 B173 항공 LiDAR의 8.1 지표 21행에 대해 모은 폭·단위 폭·300/N·최댓값과 기존 두 씨앗 값·N·출처를 추가했다. 같은 패치별 결과 배열에서 다시 계산한 값 차이는 0이다. 모은 폭이 없는 지표와 거리에 적용하지 않는 300/N을 구분해 표시했다.','',
        '실행·후처리 소요 시간과 TSDF 대기는 각 영수증 및 tables/runtime.json에 있다. 기록되지 않은 과거 GPU 대기는 확인 불가다. GPU 메모리는 해당 GPU 전체 관측값이므로 다른 프로세스 사용량도 포함할 수 있다. TSDF는 한 번에 하나씩 실행한다.','',
        '필수 24판 완료 전이며 선택 판의 실행 조건도 충족되지 않았다. 중단 후 없는 결과·누락 영상·없는 생성 표식을 추정으로 채우지 않았다.']
    if (OUT/'checks/post_memory_56_40_v1/authorization.json').exists():
        lines += ['', '2026-10-27 16:57 사용자 지시로 위의 과거 64/48 GiB 자원 조건을 56/40 GiB로 변경했다. '
                  '60초 확인과 직렬 후처리, 손실·채점·판·기하 설정은 유지한다. B173+B0 항공 LiDAR 8판 전달을 먼저 완료한 뒤 R1 항공 LiDAR를 더한 12판 비교를 우선한다. '
                  '[변경 승인과 재개 기록](후처리_입장조건_변경승인_v1.md).']
    if (DOC/'중간보고_항공LiDAR_8판_v1.md').exists():
        lines += ['', '[항공 LiDAR 두 지역 8판 중간 보고](중간보고_항공LiDAR_8판_v1.md)에 보존 면적·면 없음·날개 단면·칸별 값·42행 문턱·칸 0과 2의 점 운명을 모았다.']
    report='\n'.join(lines)+'\n';assert len(report)<=20000,len(report)
    (DOC/'손실학습시험_보고_v1.md').write_text(report)
    save(TAB/'report_status.json',dict(status=rt['status'],counts=c,characters=len(report),figures=figures,scientific_verdict=None))
    print('report chars',len(report),'status',rt['status'],flush=True)

if __name__=='__main__':main()
