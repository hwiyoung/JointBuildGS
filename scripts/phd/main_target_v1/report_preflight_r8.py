"""Locked r8 implementation and input report, no causal/scientific interpretation."""
import numpy as np
from common import *
from report_stage0 import plt,save
def read(p):return json.loads(p.read_text())
def main():
    lock=read(CFG/'target_v1.r8.lock.json');L=['# r8 구현·학습 전 점검 [이 발주에서 냄]','',f"설정 잠금: {lock['at']}. SHA-256 `{lock['config_sha256']}`.",'','r21 파일을 보존하고 r22를 만들었다. 변경 파일·줄은 `tables/r22_changes_r8.json`과 `.patch`에 있다. 단계 0 판단·목표는 r7 파일을 그대로 사용한다. 패치 씨앗, 전체 목표 깊이·σ·소유 패치 배열, 패치 화소 무게는 r7과 바이트 단위로 같다. 유효한 배경 화소 무게는 모두 1이고 σ_ref는 r7의 모든 목표 화소 중앙값 그대로다.','',
    '기준선 `model/input.ply`와 장면 `points3D.ply`의 SHA-256이 같다. 그 점 순서의 `origin.npy == 0`으로 SfM을 골랐다. 사전 정보 점은 제외하고 기존 원통 제외 코드와 원통 배열을 그대로 적용했다. 기준선 SfM에는 추가 솎기를 하지 않았다. 배경은 기준선 RGB·불투명도 0.1·원래 무작위 회전을 보존하고, 현재 초기 점 집합에서 기준선 이웃 거리 크기 규칙을 적용했다. 패치·배경 처음 불투명도는 모두 0.1이며 기준선과 같다. 크기 상한은 없다. 배경 이동 진단의 법선은 이 초기 회전의 z축이며 묶기에는 쓰지 않는다. 배경 씨앗 σ는 같은 단위·사전 정보의 기존 배경 지도 대체값을 진단용으로만 보존한다.','',
    '| 사전 정보 | 판 | 입력 배경 후보 | 원통 제외 | 최종 배경 씨앗 | 초기 크기 1 m 초과 |','|---|---|---:|---:|---:|---:|'];rows=[];top=[]
    for prior in ['ALS','LoD2']:
        stem=f'B173nb_b10_{prior}';r=read(OUT/'r8/stage1'/stem/'seed_receipt.json');old=read(OUT/'r2/background/B173nb_b10'/prior/'receipt.json');v=read(OUT/'r8/verification/initial'/prior/'result.json')
        for rev,a,b,c,n in [('r7',old['raw_points'],old['excluded'],r['r7_background_kept'],v['initial_large_background_r7']['count_gt_1m']),('r8',r['sfm_candidates'],r['cylinder_excluded'],r['background_kept'],v['initial_large_background_r8']['count_gt_1m'])]:
            L.append(f'| {prior} | {rev} | {a:,} | {b:,} | {c:,} | {n:,} |');rows.append(dict(prior=prior,revision=rev,candidates=a,excluded=b,background=c,large=n))
        top +=['',f'### {prior} r8 큰 배경 상위 열 개','','| 초기 ID | 동쪽(m) | 북쪽(m) | 높이(m) | 긴 축(m) |','|---|---:|---:|---:|---:|']
        for x in v['initial_large_background_r8']['top10']:top.append('| '+str(x['init_id'])+' | '+' | '.join(f'{z:.6f}' for z in x['xyz_local_m']+[x['max_scale_m']])+' |')
        fig,ax=plt.subplots(figsize=(8,4));items=v['initial_large_background_r8']['top10'];ax.bar([str(x['init_id']) for x in items],[x['max_scale_m'] for x in items]);ax.set(xlabel='초기 배경 ID',ylabel='긴 축 (m)');ax.tick_params(axis='x',rotation=35);fig.subplots_adjust(top=.8,bottom=.25);save(fig,f'r8_{prior}_initial_top10',f'{prior}: 초기 크기 상위 배경',v['initial_large_background_r8'],'기준선 이웃 거리 규칙 · 상한 없음 · 좌표는 학습 지역 좌표, EPSG:25832 이동량은 입력 메타데이터')
    L +=top
    L +=['','r7은 원통 제외 뒤 0.25 m 복셀 솎기를 했다. 위 표의 원통 제외 수와 최종 씨앗 수 사이에는 그 솎기가 포함되어 있다. r8은 기준선 SfM 집합에 원통 제외만 적용했다.','',
    '실제 초기화 점검에서 패치의 위치·크기·불투명도·회전은 r7 초기 저장 배열과 바이트 단위로 같았다. 배경 RGB·불투명도·회전은 기준선 초기 배열과 같고 크기는 기준선 이웃 거리 연산과 일치했다. σ=1 m 법선 0.8 m 유지, 접선 0.6 m 풀림, 복제·분할·지우기, Adam·난수·영상 순서·목표 상태를 포함한 재개 점검을 통과했다. 9,000회 모의 관측에서 불투명도 유예 중에도 수 3배 중단과 메모리 기록이 작동함을 확인했다.','',
    '## r7 배경 화소 무게 기록','','배경 화소의 σ는 화소마다 측정한 값이 아니라 같은 단위·사전 정보의 유효한 원 지붕 u 중앙값에서 구한 대체값이다. 대체 비율 100%, 화소별 측정 비율 0%. 학습 화소와 배경 씨앗의 불확실도 출처는 다르다.','',
    '| 사전 정보 | [0.1,0.5) | [0.5,1) | [1,2) | [2,5) | [5,10] | 끝 0.1 | 끝 10 |','|---|---:|---:|---:|---:|---:|---:|---:|']
    ver=read(DOC/'tables/r8_input_verification.json')
    for r in ver['rows']:L.append('| '+r['prior']+' | '+' | '.join(f'{x*100:.6f}%' for x in r['bin_fractions']+r['clipped_endpoint_fractions'])+' |')
    for prior in ['ALS','LoD2']:L +=['',f'![r7 배경 무게](figures/r8_r7_background_weights_{prior}.png)',f'![큰 배경](figures/r8_{prior}_initial_top10.png)']
    fig,axes=plt.subplots(1,2,figsize=(10,4));xx=np.arange(2)
    for dx,rev,col in [(-.18,'r7','#999999'),(.18,'r8','#438bb6')]:
        rr=[r for r in rows if r['revision']==rev]
        for ax,k in zip(axes,['background','large']):ax.bar(xx+dx,[r[k] for r in rr],width=.36,label=rev,color=col)
    for ax,lab in zip(axes,['최종 배경 씨앗 수','초기 긴 축 1 m 초과 수']):ax.set(xticks=xx,xticklabels=['ALS','LoD2'],ylabel=lab);ax.legend()
    fig.subplots_adjust(top=.8,bottom=.2,wspace=.3);save(fig,'r8_initial_background_counts','r7·r8 초기 배경',rows,'원통 제외 뒤 사용된 씨앗 · 초기 크기와 개수 기록')
    L +=['','![배경 개수](figures/r8_initial_background_counts.png)','','학습·채점 상태는 시점별 보고서에 별도로 적는다. r7 LoD2는 참고용 계속, r7 ALS는 다시 잇지 않음, 나머지 여섯 판 미시작.','', 'scientific_verdict: null.']
    (DOC/'구현과_초기점검_r8.md').write_text('\n'.join(L)+'\n');dump(DOC/'tables/r8_initial_background_counts.json',dict(rows=rows,scientific_verdict=None))
    print('R8_PREFLIGHT_REPORT_COMPLETE',flush=True)
if __name__=='__main__':main()
