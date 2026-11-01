"""Initial uncapped MVS-background census and top ten positions for every prepared combination."""
import csv
import numpy as np
from common import *
from report_stage0 import plt,save,SITES

def main():
    cfg,lock=locked_r3();rows=[];top=[];paragraphs=[]
    for site,prior in [('B173nb_b10','ALS'),('B173nb_b10','LoD2'),('R1rep_b10','LoD2'),('B0_b10','LoD2')]:
        p=OUT/'r3/census'/f'{site}_{prior}/initial_background_sizes.json';d=json.loads(p.read_text())
        with np.load(p.with_suffix('.npz')) as z:xyz=z['xyz'];large=z['large'];scale=z['scale']
        row={k:d[k] for k in ['site','prior','background_count','count_gt_1m','max_scale_m']};rows.append(row)
        for rank,v in enumerate(d['top10'],1):
            x,y,z=v['xyz_local_m'];top.append(dict(site=site,prior=prior,rank=rank,init_id=v['init_id'],
                background_index=v['background_index'],x_local_m=x,y_local_m=y,z_local_m=z,scale_m=v['scale_m']))
        fig,axes=plt.subplots(1,2,figsize=(11,4.6));stride=max(1,len(xyz)//40000)
        axes[0].scatter(xyz[::stride,0],xyz[::stride,1],s=.4,color='#b7b7b7',alpha=.3,label='배경 표본')
        axes[0].scatter(xyz[large,0],xyz[large,1],s=2,color='#c96348',alpha=.65,label='처음 크기 >1 m')
        for rank,v in enumerate(d['top10'],1):
            x,y,z=v['xyz_local_m'];axes[0].plot(x,y,'k.',ms=2)
            axes[0].annotate(str(rank),xy=(x,y),xytext=((18 if rank%2 else -22),12+9*(rank%3)),
                textcoords='offset points',fontsize=8,color='black',ha='center',
                bbox=dict(boxstyle='round,pad=.12',fc='white',alpha=.8,ec='none'),
                arrowprops=dict(arrowstyle='-',lw=.6,color='black'))
        axes[0].set(xlabel='지역 동쪽 좌표 (m)',ylabel='지역 북쪽 좌표 (m)',title='큰 배경의 자리와 상위 열 개');axes[0].set_aspect('equal');axes[0].margins(.24)
        axes[1].hist(scale,bins=np.geomspace(max(.001,float(scale.min())),float(scale.max())*1.01,80),color='#478ac3')
        axes[1].set_xscale('log');axes[1].set_yscale('log');axes[1].axvline(1,color='#c96348',ls='--')
        axes[1].set(xlabel='초기 크기 (m)',ylabel='가우시안 수 (로그 눈금)',title='기준선 이웃 거리 규칙, 상한 없음')
        fig.subplots_adjust(top=.79,bottom=.22,wspace=.3);key=f'r3_background_{site}_{prior}'
        save(fig,key,f'{SITES[site]} {prior}: 1 m 초과 {d["count_gt_1m"]:,}개, 최대 {d["max_scale_m"]:.3f} m',d,
            '회색: 배경 표본 · 주황: 1 m 초과 · 크기 = 두 접선 축의 최댓값 · 지역 XYZ(m) · 멈춤 기준 아님')
        paragraphs +=[f'### {SITES[site]} {prior}','',f'![큰 배경](figures/{key}.png)','',
            '| 순위 | 처음 씨앗 번호 | X (m) | Y (m) | Z (m) | 크기 (m) |','|---|---:|---:|---:|---:|---:|']
        for rank,v in enumerate(d['top10'],1):
            x,y,z=v['xyz_local_m'];paragraphs.append(f'| {rank} | {v["init_id"]} | {x:.6f} | {y:.6f} | {z:.6f} | {v["scale_m"]:.6f} |')
        paragraphs +=['']
    for name,data in [('initial_background_summary_r3',rows),('initial_background_top10_r3',top)]:
        dump(DOC/'tables'/f'{name}.json',dict(rows=data,config_sha256=lock['config_sha256'],coordinates='source local training frame; see inherited camera/scene transforms',scientific_verdict=None))
        with (DOC/'tables'/f'{name}.csv').open('w',newline='') as f:
            w=csv.DictWriter(f,list(data[0]),lineterminator='\n');w.writeheader();w.writerows(data)
    text=['# r3 초기 배경 크기 기록','',
        '배경의 크기는 기준선의 이웃 거리 규칙 그대로이며 상한이나 외톨이 제거를 적용하지 않았다. 아래는 대표 자리 검사에 준비한 네 조합의 전수 집계다. 아직 배경을 준비하지 않은 네 조합의 값을 0으로 표시하지 않았다.','',
        '크기는 `exp(log(sqrt(clamp_min(distCUDA2(사전 목표 + 배경 XYZ), 1e-7))))`의 실제 float32 값이다. 두 접선 축이 같으므로 그 최댓값을 사용한다. 원반 지름이나 3σ 폭이 아니다. 배경 자체의 위치 자료만으로 계산하므로, 진행 중인 고리 불확실도를 임의로 채우지 않았다.','',
        '| 조합 | 배경 수 | 1 m 초과 수 | 가장 큰 크기 (m) |','|---|---:|---:|---:|']
    for r in rows:text.append(f'| {SITES[r["site"]]} {r["prior"]} | {r["background_count"]:,} | {r["count_gt_1m"]:,} | {r["max_scale_m"]:.6f} |')
    text +=['','좌표는 원본 학습 장면의 지역 XYZ(m)다. 측량 평면 좌표와 연결하는 XY 오프셋 출처는 `scripts/phd/main_axes71_v2/mvs_surface.py: OFFSET=[690953,5336071]`이다. EPSG:25832 평면 연결과 원본 카메라 좌표를 보존하며, Z를 검증하지 않은 절대 표고로 이름 붙이지 않는다.','',*paragraphs,
        '## 7,000회 기록 상태','',
        '3.5에서 중단하여 실제 자손의 잔존 수·크기·불투명도와 뜬 면 지도는 확인 불가다. 코드에는 처음 씨앗 번호를 통한 자손 추적, 목표 면에서의 법선·접선 이동, 배경 및 처음 1 m 초과 배경 출신의 렌더 기여를 추가했다. 이 진단은 새 멈춤 기준이 아니다.','',
        '실제 B173 항공 LiDAR 초기화에서 이전 위치·법선·정밀도·불투명도 배열이 모두 같고 난수 상태도 변하지 않음을 확인했다. 큰 배경 2,182개와 최대 크기가 별도 계산과 일치했다. 작은 예제의 복제·분할·제거 뒤 자손 수와 렌더 기여 합도 점검했다. 작은 예제는 실제 7,000회 결과가 아니다.','',
        '[검증 기록](tables/monitor_verification_r3.json) · `scientific_verdict: null`']
    (DOC/'초기배경_크기_r3.md').write_text('\n'.join(text)+'\n');print('BACKGROUND_REPORT_R3',flush=True)

if __name__=='__main__':main()
