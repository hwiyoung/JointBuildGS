"""Recorded time points only; never infer unsaved trajectory or mesh scores."""
import json
import numpy as np
import matplotlib.pyplot as plt
from common import *
from build_visuals import save_figure,NAMES
from build_a2 import depth_range,image
from recount import load_eval

def main():
    site='R1rep_b10';e,_=load_eval(site,'ALS');cases=[c for c in json.loads((CFG/f'cases_ALS.json').read_text())['cases'] if c['id'] in ['R1-뜬면-1','R1-뜬면-2']]
    rows=[];sources=[]
    for p in sorted((DOC/'tables').glob('formation_pixels_*.json')):
        rows+=json.loads(p.read_text())['rows'];sources.append(str(p))
    assert all(any(r['result']==res for r in rows) for res in ['fd_dynnow_ALS_s0','fd_current_ALS_s0_record_only'])
    distances=json.loads((DOC/'tables/formation_target_distances.json').read_text())['rows']
    for case in cases:
        fig,axs=plt.subplots(1,2,figsize=(13,4.5));selected=[r for r in rows if r['case']==case['id']]
        for res,col,label in [('fd_current_ALS_s0_record_only','#888888','기존 손실·불투명도 기록 전용'),('fd_dynnow_ALS_s0','#7a3fb0','판 4·원래 건강 기준')]:
            rr=sorted([r for r in selected if r['result']==res],key=lambda r:r['iteration'])
            axs[0].plot([r['iteration'] for r in rr],[100*r['floating_fraction'] for r in rr],'o-',color=col,label=label)
        for res,col in zip(RESULTS,config()['colours']['results']):
            rr=sorted([r for r in selected if r['result']==res],key=lambda r:r['iteration'])
            axs[1].plot([r['iteration'] for r in rr],[100*r['floating_fraction'] for r in rr],'o-',color=col,label=NAMES[res])
        for ax in axs:ax.set(xlabel='반복',ylabel='주 시점 뜬 면 화소 (%)');ax.legend(fontsize=9);ax.grid(alpha=.2)
        axs[0].axvline(3000,color='#999',ls=':',lw=1);axs[0].set_title('500회 간격 · 첫 불투명도 초기화 3,000회')
        axs[1].set_title('기존 저장본 15,000회·30,000회')
        fig.suptitle(case['id']+' · 렌더 깊이로 본 생기는 과정',fontsize=16)
        fig.tight_layout();save_figure(fig,case['id']+'_formation_A2',dict(case=case['id'],rows=selected,sources=sources,
            note='Samples are saved iterations. Lines only connect observed points. Render-depth pixel fractions are not TSDF mesh-area scores. Short replay need not reproduce the 30000-step trajectory.'))
        meta=json.loads((DOC/'figures'/(case['id']+'_plate_A1.json')).read_text());photo=meta['photo'];assert photo
        crop=photo['crop_xyxy'];name=photo['view'];dr=depth_range(case,e,photo)
        fig,axs=plt.subplots(2,5,figsize=(17,6.4),squeeze=False)
        for i,res in enumerate(['fd_current_ALS_s0_record_only','fd_dynnow_ALS_s0']):
            for j,it in enumerate([1000,3000,3500,5000,7000]):
                p=OUT/'formation'/site/res/f'iteration_{it}'/(name+'.npz');arr=None
                if p.exists():
                    with np.load(p) as f:arr=f['depth']
                image(axs[i,j],arr,f'{it:,}회',crop,cmap='turbo_r',vmin=dr[0],vmax=dr[1])
                if j==0:axs[i,j].set_ylabel('기존 손실\n불투명도 기록 전용' if i==0 else '판 4')
        fig.suptitle(case['id']+' · 같은 시점·같은 깊이 색 범위',fontsize=17,x=.02,ha='left')
        fig.text(.02,.01,f'깊이 {dr[0]:.2f}~{dr[1]:.2f} m. 저장되지 않은 반복은 확인 불가. 채점용 결과가 아닌 발생 과정 관찰이다.',fontsize=11)
        fig.tight_layout(rect=[0,.05,1,.94]);save_figure(fig,case['id']+'_formation_depth_A2',dict(case=case['id'],view=name,iterations=[1000,3000,3500,5000,7000],depth_range_m=dr,sources=sources))
    # Save a discrete-time onset record; no scientific verdict about expectation.
    onsets=[]
    for c in cases:
        for res in ['fd_current_ALS_s0','fd_dynnow_ALS_s0','fd_current_ALS_s0_record_only']:
            rr=sorted([r for r in rows if r['case']==c['id'] and r['result']==res],key=lambda r:r['iteration'])
            positive=next((r for r in rr if r['floating_pixels']>0),None)
            target=[d for d in distances if positive and d['case']==c['id'] and d['result']==res and d['iteration']==positive['iteration']]
            onsets.append(dict(case=c['id'],result=res,earliest_observed_nonzero_iteration=positive['iteration'] if positive else None,
                first_saved_iteration=rr[0]['iteration'] if rr else None,last_saved_iteration=rr[-1]['iteration'] if rr else None,
                earliest_observed_fraction=positive['floating_fraction'] if positive else None,target_distances=target,
                note='earliest saved nonzero; onset before that time or between saves is not determined',scientific_verdict=None))
    from reduce_diagnostics import table
    table(DOC/'tables/formation_onsets',onsets,'처음 관찰된 뜬 면 화소 · 저장 반복 기준')

if __name__=='__main__':main()
