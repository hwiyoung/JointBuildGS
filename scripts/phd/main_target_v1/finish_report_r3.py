"""Promote the current r3 result while retaining r1/r2 reports as historical evidence."""
import re
from common import *
from report_stage0 import SITES

def main():
    cfg,lock=locked_r3();base=(DOC/'영역별목표학습_보고_r2.md').read_text()
    parts=re.split(r'^## [1-8]\. [^\n]+\n',base,flags=re.M);assert len(parts)==9
    gate=json.loads((DOC/'tables/initial_render_gate_r3.json').read_text())['rows']
    bg=json.loads((DOC/'tables/initial_background_summary_r3.json').read_text())['rows']
    full={(r['site'],r['prior']):r for r in json.loads((DOC/'tables/r2_stage1_initial_render.json').read_text())}
    reps=json.loads((CFG/'representatives_v1.json').read_text())['rows']
    text=['# 영역별 목표 학습 보고 v1 · r3','',
        '판단 정확도: r2 그대로다. 항공 LiDAR 지붕의 틀린 넓이 비율은 개발용 24.88%, 확인용 28.92%이며, LoD2·실험 지역·대체 패치 비교는 단계 0 표에 있다.',
        '7,000회 점검: 미실행. 배경을 제외한 r3 3.5에서 LoD2 세 조합이 5 cm를 넘어 최적화 0회로 중단했다.',
        '8판의 네 값: 학습·결과 메시가 없어 계산하지 않았다.',
        'GS와 목표로 바로 만든 메시 비교: 미실행.',
        '확인 불가: 학습 효과, 실제 자손 잔존·뜬 면, 최종 메시·채점. scientific_verdict: null.','',
        '## 1. 현재 상태','',
        '10/31·11/1 결정에 따른 단계 0 r2 계산은 통과했다. 이번 r3는 사용자 재중단 결정 1~5를 적용한 학습 전 재검사다. 배경 크기는 기준선 이웃 거리 규칙 그대로이며 상한·외톨이 제거를 적용하지 않았다. 판단·목표·지도와 정밀도, 사전 씨앗 수·크기는 r2와 같다.','',
        '3.5 통과 기준의 렌더에서 배경만 제외했다. 사전 목표 가우시안끼리 겹치는 효과는 남아 있다. 현재 재개 조건은 충족되지 않았으며, 후속 결정 전 학습하지 않는다.','',
        '## 2. 단계 0: 판단과 목표',parts[2],
        '## 3. 단계 1: 구현과 r3 재검사','',
        '| 조합 | 영상 수 | r3 배경 제외 오차 (cm) | 깊이 없음 (%) | 5 cm | r2 배경 포함 전체 목표 오차 (m), 참고 | r2 배경 포함 사전 목표만 오차 (m), 참고 |',
        '|---|---:|---:|---:|---|---:|---:|']
    comparison=[]
    for r in gate:
        f=full[(r['site'],r['prior'])]
        text.append(f'| {SITES[r["site"]]} {r["prior"]} | {r["views"]} | {r["median_m"]*100:.4f} | {r["missing_fraction"]*100:.5f} | {"통과" if r["status"]=="PASS" else "미충족"} | {f["pooled_median_m"]:.6f} | {f["prior_pooled_median_m"]:.6f} |')
        comparison.append(dict(r,full_all_target_median_m=f['pooled_median_m'],full_prior_target_median_m=f['prior_pooled_median_m']))
    dump(DOC/'tables/full_vs_prior_only_r3.json',dict(rows=comparison,note='full and prior-only valid-pixel denominators differ; fixed-view common-pixel decomposition in r2 diagnosis',scientific_verdict=None))
    text+=['','r3는 모든 학습 영상의 사전 목표 화소 중 양의 유한 렌더 깊이가 있는 화소를 합친 중앙값이다. 깊이 없음은 별도로 적고 성공으로 세지 않는다. 배경 포함 수치는 통과 기준에 쓰지 않는다. 두 렌더의 유효 깊이 분모는 다르며, 같은 화소 비교는 별도 r2 분해 표에 있다.','',
        '![r3 깊이 검사](figures/r3_initial_depth_gate.png)','',
        '### 씨앗 위치와 합성 깊이의 구분','',
        '대표 자리의 목표 지도 940,805개 원반 화소는 높이 복원 중앙값 1 cm 안으로 맞았다. 묶기와 실제 복제·분할·제거의 부모 목표 상속도 통과했다. 사전 씨앗 크기는 기준선 텐서와 같고, 배경 크기는 새 결합 점군에 기준선 이웃 거리 규칙을 적용했다.','',
        'LoD2 씨앗 위치와 목표의 최대 차이는 약 0.008 mm였다. 고정 영상 네 곳에서 각 화소가 속한 패치만 그린 96개 진단 표본의 최대 오차는 0.035 mm 이내였다. 반면 여러 사전 가우시안을 함께 그리면 투명도에 따른 기대 깊이에 앞뒤 면이 섞인다. 목표 지도는 가장 가까운 패치 원반의 깊이다. 이 차이를 [r3 재검사와 원인 확인](단계1_r3_재점검.md)에 기록했다. 개별 패치 검사·지붕/벽 분리·중앙 깊이를 새 통과 기준으로 적용하지 않았다.','',
        'B173 날개 고정 영상의 LoD2 오차는 4.26 cm지만 전체 203장의 중앙값은 13.61 cm다. 고정 영상만으로 통과를 선언하지 않았다. 항공 LiDAR는 유효 깊이 오차를 통과했으나, 사전 목표 화소의 약 43.44%에는 깊이가 없었다. 이를 숨기거나 새 멈춤 기준으로 바꾸지 않았다.','',
        '### 초기 큰 배경과 자손 기록','',
        '| 조합 | 배경 수 | 초기 크기 1 m 초과 | 최대 크기 (m) |','|---|---:|---:|---:|']
    for r in bg:text.append(f'| {SITES[r["site"]]} {r["prior"]} | {r["background_count"]:,} | {r["count_gt_1m"]:,} | {r["max_scale_m"]:.6f} |')
    text+=['','각 조합의 가장 큰 열 개의 XYZ와 크기, 위치 지도는 [초기 배경 크기 보고서](초기배경_크기_r3.md)에 있다. 크기는 활성화한 두 접선 축 중 큰 값이며 지름이 아니다. 아직 준비하지 않은 나머지 네 조합의 값은 확인 불가다.','',
        '처음 1 m 초과 배경의 자손을 처음 씨앗 번호로 추적하고, 남은 수·크기·불투명도·목표 면에 대한 법선/접선 이동과 배경 출신 렌더 기여를 저장하도록 구현했다. 이 항목은 멈춤 기준이 아니다. 실제 초기화 배열과 난수 상태가 r2와 같고, 합성 예제의 자손 추적과 렌더 기여 합이 맞음을 확인했다. 실제 7,000회 자손·뜬 면 지도는 학습 전 중단으로 확인 불가다.','',
        '[기록 코드 점검](tables/monitor_verification_r3.json) · [기본 끔 경로 점검](tables/runtime_verification_r3.json) · [변경 파일과 줄](tables/r19_changes_r3.json)','',
        '### 기준선과 차이','',
        '| 항목 | 기준선 | 이번 작업 |','|---|---|',
        '| 배경 씨앗 자료 | SfM 희소점 | 신뢰도 마스크를 통과한 자체 MVS A 점 |',
        '| 배경 위치·법선·폭 | 기존 규칙 | MVS 위치, MVS 법선 없으면 연직 위, 자체 σM 폭 |',
        '| 배경 크기 | 이웃 거리, 상한 없음 | 같은 규칙, 상한·외톨이 제거 없음 |',
        '| 사전 씨앗 | 기존 수·크기 | 같은 수·크기, r2 목표 위치·법선·σ |',
        '| 밀도 제어·불투명도 재설정·학습률 | 기존 일정 | 동일 |','',
        '## 4. 단계 2: 본 학습과 채점',parts[4],
        '## 5. 비교 방법',parts[5],
        '## 6. 대표 자리 그림','',
        '대표 자리·카메라는 첫 계산 전에 고정한 값을 유지한다. r2 목표와 0회 단면에 r3 배경 제외 렌더를 나란히 연결한다. 7,000·30,000회 중심, 결과 메시, 메시 다각도는 없다.','']
    for rep in reps:
        for prior in rep['priors']:
            for prefix,suffix in [('r2_stage1','target'),('r2_stage1','section'),('r3','initial')]:
                key=f'{prefix}_rep{rep["id"]}_{prior}_{suffix}'
                text +=[f'![{rep["name"]} {prior}](figures/{key}.png)','']
    text+=['## 7. 미리 정한 물음과 현재 증거',parts[7],
        '## 8. 변경·출처·확인 불가·시간','',
        'r3 설정 sha256: `'+lock['config_sha256']+'`. 15:39:20 설정, 15:43:30 검사 코드 잠금 뒤 처음 계산했다. 사용자의 11/1 재중단 결정 원문과 이전 r2 설정·코드를 보존했다. 큰 배경 기록만 추가한 실행 코드도 별도 잠금과 기본 끔 경로 검증을 남겼다.','',
        'LoD2 σP 출처: '+cfg['lod2_sigma_provenance']['statement'],'',
        '원본 고리 불확실도, 원통 제외, 대체 규칙은 r2를 유지한다. 원반 없는 목표 지도 화소의 σ는 같은 단위의 지붕 패치 중앙값 대체이며 지도 인덱스에 표시했다. 배경 씨앗의 자체 고리 불확실도와 동일한 자료로 간주하지 않았다.','',
        '별도 재계산 검사기 첫 실행은 유효 화소가 0인 영상의 null 중앙값을 허용하지 않아 멈췄다. 검사기만 고치고 실패 기록을 보존했다. 원래 검사 값과 설정은 바꾸지 않았다.','',
        '과학적 결론과 사용자 그림 승인은 내려진 것이 아니다. 확인용 상세 패치는 외부 holdout/r2에 유지한다. ZIP에는 수·넓이·비율만 공개하고 패치 상세는 넣지 않는다. 재계산에는 기존 외부 입력과 잠긴 Docker 이미지가 필요하다.','',
        f'이 보고서 작성 시각: {stamp()}. 계산별 시간은 r2/r3 명령 영수증과 [진행 기록](progress.md)에 남긴다. 이후 학습은 3.5 비교 방식에 관한 후속 결정이 필요하다.','']
    body='\n'.join(text);assert len(body)<22000 and len(re.findall(r'^## [1-8]\. ',body,re.M))==8
    for link in re.findall(r'!\[[^\]]*\]\(([^)]+)\)',body):assert (DOC/link).exists(),link
    (DOC/'영역별목표학습_보고_r3.md').write_text(body);(DOC/'영역별목표학습_보고_v1.md').write_text(body)
    print('R3_FINAL_REPORT',len(body),flush=True)

if __name__=='__main__':main()
