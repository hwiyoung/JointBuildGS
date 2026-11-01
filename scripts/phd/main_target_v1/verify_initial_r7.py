"""Audit actual r7 seeds and report baseline-rule sizes and opacity, CPU only."""
import time
import numpy as np
from common import *
from report_stage0 import plt,save
from verify7000_r7 import loadz
def main():
    rows=[];text=['# r7 초기 씨앗 확인','', '목표에서 사라짐으로 옮긴 패치의 씨앗만 제외했다. 배경 위치와 마스크·솎기 범위는 r6와 같다. 처음 크기는 기준선의 이웃 거리 규칙이며 상한·외톨이 제거를 추가하지 않았다. 사전 씨앗을 뺀 데 따른 이웃 거리의 변화는 허용한 같은 규칙의 결과다.','']
    for prior in ['ALS','LoD2']:
        model=OUT/'r7/runs'/f'tg_B173nb_b10_{prior}_s0_r7/model'
        while not (model/'target_monitor/curve.jsonl').exists():time.sleep(2)
        s=loadz(model/'target_monitor/snapshot_0.npz');seeds=loadz(OUT/'r7/stage1'/f'B173nb_b10_{prior}/seeds.npz');t=loadz(OUT/'r7/targets'/f'B173nb_b10_{prior}.npz');old=loadz(OUT/'r6/runs'/f'tg_B173nb_b10_{prior}_s0_r6/model/target_monitor/snapshot_0.npz')
        assert np.array_equal(s['init_id'],np.arange(len(s['xyz']))) and np.array_equal(s['origin'],seeds['origin']);assert np.array_equal(s['xyz'],seeds['xyz'].astype('f4'))
        bg=s['origin']==0;patch=~bg;assert np.array_equal(s['xyz'][bg],old['xyz'][old['origin']==0]);assert np.array_equal(s['target_tag'],s['origin']);assert (s['target_released_at']==-1).all()
        assert not (t['region'][seeds['patch'][patch]]==5).any();assert np.max(abs(s['xyz'][patch]-t['target'][seeds['patch'][patch]]))<=1e-5
        for sel in [bg,patch]:assert np.all(s['opacity'][sel]==old['opacity'][0])
        large=bg&(s['scale'].max(1)>1);report=json.loads((model/'target_monitor/initial_large_background.json').read_text());assert report['count_gt_1m']==int(large.sum());order=np.flatnonzero(large);order=order[np.lexsort((order,-s['scale'][order].max(1)))][:10]
        assert [x['init_id'] for x in report['top10']]==order.tolist()
        for i,r in zip(order,report['top10']):assert r['max_scale_m']==float(s['scale'][i].max()) and np.array_equal(r['xyz_local_m'],s['xyz'][i])
        row=dict(prior=prior,status='PASS_R7_INITIALIZATION',seeds=len(bg),prior_seeds=int(patch.sum()),background_seeds=int(bg.sum()),prior_opacity=float(s['opacity'][patch][0]),background_opacity=float(s['opacity'][bg][0]),opacity_identical_to_r6_and_baseline_rule=True,background_positions_identical=True,initial_large=report,snapshot_sha256=sha(model/'target_monitor/snapshot_0.npz'));rows.append(row)
        text +=[f'## {prior}','',f'목표 씨앗 {int(patch.sum()):,}개, 배경 씨앗 {int(bg.sum()):,}개. 처음 불투명도는 각각 {row["prior_opacity"]:.8f}, {row["background_opacity"]:.8f}이며 기준선 기본값과 같다. 처음 1 m 초과 배경은 {int(large.sum()):,}개다.','', '| init_id | 동쪽(m) | 북쪽(m) | 높이(m) | 긴 축(m) |','|---:|---:|---:|---:|---:|']
        for r in report['top10']:text.append('| '+str(r['init_id'])+' | '+' | '.join(f'{v:.6f}' for v in r['xyz_local_m']+[r['max_scale_m']])+' |')
        fig,axes=plt.subplots(1,2,figsize=(11,4));axes[0].bar(range(len(order)),s['scale'][order].max(1),color='#61a8a7');axes[0].set(xticks=range(len(order)),xticklabels=list(range(1,len(order)+1)),xlabel='처음 배경 씨앗의 크기 순위',ylabel='긴 축 (m)');axes[0].tick_params(axis='x',rotation=45)
        axes[1].scatter(s['xyz'][bg,0][::20],s['xyz'][bg,1][::20],s=.1,c='#dddddd');axes[1].scatter(s['xyz'][order,0],s['xyz'][order,1],s=25,c='#61a8a7')
        for rank,i in enumerate(order,1):axes[1].annotate(str(rank),s['xyz'][i,:2],xytext=(4,3 if rank%2 else -7),textcoords='offset points',fontsize=7)
        axes[1].set(xlabel='지역 동쪽 (m)',ylabel='지역 북쪽 (m)',title='같은 열 개의 자리');axes[1].set_aspect('equal');fig.subplots_adjust(top=.8,bottom=.25,wspace=.3);save(fig,f'r7_{prior}_initial_large_background',f'{prior}: 처음 큰 배경 씨앗 열 개',row,'같은 이웃 거리 크기 규칙 · 상한 없음 · 위치는 지역 좌표, EPSG:25832 변환은 입력 메타데이터')
        text +=['',f'![초기 큰 배경](figures/r7_{prior}_initial_large_background.png)','']
    result=dict(at=stamp(),status='PASS_R7_INITIALIZATION',rows=rows,scientific_verdict=None);dump(OUT/'r7/verification/initial.json',result);dump(DOC/'tables/initial_r7.json',result);text+=['`scientific_verdict: null`'];(DOC/'초기배경_크기_r7.md').write_text('\n'.join(text)+'\n');print(result['status'],flush=True)
if __name__=='__main__':main()
