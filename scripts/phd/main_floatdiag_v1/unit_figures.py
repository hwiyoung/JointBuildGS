"""All-cell composition, actual residual distributions and centre gradients."""
import argparse
import json
import numpy as np
import matplotlib.pyplot as plt
from common import *
from build_visuals import save_figure,NAMES
from recount import LABELS

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--site',required=True);ap.add_argument('--prior',default='ALS',choices=['ALS','LoD2']);a=ap.parse_args();suffix='' if PRIOR=='ALS' else '_'+PRIOR
    rows=[r for r in json.loads((DOC/f'tables/recount_{PRIOR}.json').read_text())['rows'] if r['site']==a.site]
    results=list(dict.fromkeys(r['result'] for r in rows));fig,axs=plt.subplots(2,3,figsize=(16,11),squeeze=False)
    cols=config()['colours']['classes'];fields=['within_tau_pct','floating_pct','mvs_pct','prior_pct','other_missing_pct']
    # Field names come from the original five-way recount, with no reinterpretation.
    for k,ax in enumerate(axs.flat):
        rr=[next((r for r in rows if r['result']==res and r['cell']==str(k)),None) for res in results]
        left=np.zeros(len(results))
        for field,col in zip(fields,cols):
            values=[(r[field] or 0.) if r else 0. for r in rr]
            ax.barh(np.arange(len(results)),values,left=left,color=col,height=.7);left+=values
        labels=[]
        for r in results:
            base=r.removesuffix(f'_{PRIOR}_s0');labels.append(LABELS.get(base,NAMES.get(r,base)))
        ax.set(yticks=np.arange(len(results)),yticklabels=labels,xlim=(0,100),title=f'칸 {k}',xlabel='넓이 비율 (%)');ax.invert_yaxis()
    fig.suptitle(a.site+' · 결과 면의 다섯 구분',x=.02,ha='left',fontsize=18)
    fig.text(.03,.01,'초록 τ 안 · 빨강 뜬 면 · 파랑 MVS 쪽 · 주황 사전 쪽 · 회색 그 밖·면 없음. 100패치 미만은 표본 부족.',fontsize=12)
    fig.tight_layout(rect=[0,.05,1,.96]);save_figure(fig,a.site+'_classes_A2',dict(site=a.site,rows=rows))
    fig,axs=plt.subplots(3,2,figsize=(15,13),squeeze=False);distribution=[]
    bins=np.linspace(-12,12,97);centres=(bins[:-1]+bins[1:])/2
    for i,res in enumerate(RESULTS):
        path=OUT/'diagnostics'/a.site/res/'all_views_reduced.npz'
        with np.load(path) as f:
            typ=f['pixel_type'];has=f['has_mvs'];mode='current' if res.startswith('nojudge') else 'dynamic'
            for j,term in enumerate(['prior','mvs']):
                ax=axs[i,j];right=ax.twinx();ratio=f[term+'_r_sigma'];force=f[mode+'_'+term+'_force']
                for kind,t,col in [('뜬 면',0,'#d9534f'),('지붕 면',1,'#2e8b57')]:
                    m=(typ==t)&(has if term=='mvs' else True);r=ratio[m];ff=force[m];counts,_=np.histogram(r,bins)
                    ax.step(centres,counts/max(1,len(r)),where='mid',color=col,label=kind+' r/σ')
                    ids=np.digitize(r,bins)-1;med=np.array([np.median(ff[ids==k]) if (ids==k).any() else np.nan for k in range(len(centres))])
                    right.plot(centres,np.maximum(med,1e-12),'--',color=col,alpha=.7)
                    distribution.append(dict(result=res,term=term,kind=kind,n=len(r),outside_plot=int((np.abs(r)>12).sum()),
                        histogram=counts.tolist(),edges=bins.tolist(),force_bin_medians=[float(v) if np.isfinite(v) else None for v in med]))
                right.set(yscale='log',ylim=(1e-9,.3),ylabel='자기 손실 힘');ax.set(xlabel='r/σ',ylabel='전체 화소 중 비율',title=NAMES[res]+' · '+('사전' if term=='prior' else 'MVS'))
                ax.legend(fontsize=8);ax.grid(alpha=.15)
    fig.suptitle(a.site+' · 거리 분포와 실제 깊이 항의 힘',fontsize=18,x=.02,ha='left')
    fig.text(.02,.01,'실선: 전체 해당 화소의 분포. 점선: 같은 r/σ 구간에서 실제 자기 손실 힘의 중앙값. 그림 밖 화소도 표의 분위수·관문에 포함한다.',fontsize=11)
    fig.tight_layout(rect=[0,.04,1,.96]);save_figure(fig,a.site+'_forces_A2',dict(site=a.site,distributions=distribution,force_curve='binwise median of exact per-pixel own force; not one assumed sigma/V'))
    grows=json.loads((DOC/'tables'/f'gradients_{a.site}{suffix}.json').read_text())['rows'];fig,axs=plt.subplots(1,2,figsize=(12,5))
    for ax,kind,label in zip(axs,['floating','roof'],['뜬 면 가우시안','지붕 면 가우시안']):
        for j,(res,col) in enumerate(zip(RESULTS,config()['colours']['results'])):
            r=next(x for x in grows if x['result']==res and x['case']=='전체' and x['kind']==kind)
            values=[r['photo_centre_gradient_median'],r['depth_centre_gradient_median']]
            vals=[v if v and v>0 else np.nan for v in values]
            ax.plot([0,1],vals,'o-',color=col,label=NAMES[res]);ax.text(1,vals[1] if np.isfinite(vals[1]) else 1e-10,f" N={r['count']:,}",fontsize=8)
        ax.set(yscale='log',xticks=[0,1],xticklabels=['사진','깊이'],title=label,ylabel='중심 기울기 크기 중앙값');ax.grid(alpha=.2);ax.legend()
    fig.suptitle(a.site+' · 모든 학습 사진에서 더한 중심 기울기',fontsize=15);fig.tight_layout()
    save_figure(fig,a.site+'_gradients_A2',dict(site=a.site,rows=grows,zero_handling='true zero not shown on log axis; retained in tables'))

if __name__=='__main__':main()
