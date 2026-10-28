"""Early population and force measurements accompanying the formation strip."""
import numpy as np
import matplotlib.pyplot as plt
from common import *
from build_visuals import save_figure
rows=[]
for res in ['fd_dynnow_ALS_s0','fd_current_ALS_s0_record_only']:
    rows+=json.loads((DOC/'tables'/f'formation_gaussians_R1rep_b10_{res}.json').read_text())['rows']
for case in ['R1-뜬면-1','R1-뜬면-2']:
    fig,axs=plt.subplots(2,3,figsize=(15,8));selected=[r for r in rows if r['case']==case]
    metrics=[('count','가우시안 수'),('opacity_median','불투명도 중앙값'),('max_axis_median_m','가장 긴 축 중앙값 (m)'),
        ('densified_opacity_fraction','밀도 제어 생성 · 불투명도 비율'),('birth_iteration_q25_q50_q75_q90','생긴 반복 중앙값'),('patches','렌더 높이로 구분한 패치 수')]
    for ax,(key,label) in zip(axs.flat,metrics):
        for res,col,name in [('fd_current_ALS_s0_record_only','#888888','기존 손실·기록 전용'),('fd_dynnow_ALS_s0','#7a3fb0','판 4')]:
            for kind,style,klab in [('floating','-','뜬 면'),('roof','--','지붕')]:
                rr=sorted([r for r in selected if r['result']==res and r['kind']==kind],key=lambda r:r['iteration'])
                vv=[r[key][1] if key.startswith('birth_') and r[key] else r[key] for r in rr]
                ax.plot([r['iteration'] for r in rr],[v if v is not None else np.nan for v in vv],style,color=col,label=name+' '+klab)
        ax.axvline(3000,color='#999',ls=':',lw=.7);ax.set(xlabel='저장 반복',ylabel=label);ax.grid(alpha=.15)
    axs[0,0].legend(fontsize=8);fig.suptitle(case+' · 생성 과정의 가우시안과 계보',fontsize=17);fig.tight_layout()
    save_figure(fig,case+'_formation_population_A2',dict(case=case,rows=selected,definition='same saved-iteration Gaussian population rules; opacity>=0.1; original STOP run remains separately tabulated'))
print('two formation population figures PASS')
