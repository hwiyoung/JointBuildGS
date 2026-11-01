"""Inspect immutable r6 released descendants' last target sigma; no retraining."""
import numpy as np
from common import *
from report_stage0 import plt,save
from verify7000_r7 import loadz
def main():
    path=OUT/'r6/runs/tg_B173nb_b10_LoD2_s0_r6/model/target_monitor/snapshot_7000.npz';s=loadz(path);released=s['target_tag']==2;ix=s['target_index'][released]
    assert ((ix>=0)&(ix<len(s['patch_sigma']))).all();sigma=s['patch_sigma'][ix];assert np.isfinite(sigma).all()
    bins=np.array([0,.05,.1,.2,.5,1,2,5,10,np.inf]);counts=np.histogram(sigma,bins)[0];iterations=s['target_released_at'][released];rows=[]
    for it in np.unique(iterations):
        q=sigma[iterations==it];rows.append(dict(iteration=int(it),surviving_descendants=len(q),sigma_quantiles_m=dict(zip(['min','median','p95','max'],map(float,np.quantile(q,[0,.5,.95,1]))))))
    result=dict(at=stamp(),source_revision='r6',prior='LoD2',iteration=7000,phase='pre_density_control',released_descendants=int(released.sum()),prior_descendants=int((s['origin']==1).sum()),hist_bins_m=[float(x) if np.isfinite(x) else 'inf' for x in bins],hist_counts=counts.tolist(),quantiles_m=dict(zip(['min','median','p95','max'],map(float,np.quantile(sigma,[0,.5,.95,1])))),by_release_iteration=rows,definition='target_index is retained on permanent release; patch_sigma[target_index] is the last attached target sigma',snapshot_sha256=sha(path),scientific_verdict=None)
    dump(DOC/'tables/r6_released_last_sigma_r7.json',result)
    fig,axes=plt.subplots(1,2,figsize=(11,4));axes[0].bar(range(len(counts)),counts,color='#e09c36');axes[0].set(xticks=range(len(counts)),xticklabels=['0','.05','.1','.2','.5','1','2','5','10'],xlabel='마지막 목표 σ 구간 아래끝 (m)',ylabel='7,000회에 남은 풀림 자손 수');axes[1].plot([r['iteration'] for r in rows],[r['sigma_quantiles_m']['median'] for r in rows],'o-',color='#e09c36');axes[1].set(xlabel='풀린 반복',ylabel='마지막 목표 σ 중앙값 (m)');fig.subplots_adjust(top=.8,bottom=.23,wspace=.3)
    save(fig,'r7_r6_LoD2_released_last_sigma','r6 LoD2: 풀림 가우시안의 마지막 목표 폭을 확인했다',result,'밀도 제어 직전 7,000회 저장 · 같은 부모의 자손도 각각 셈 · 마지막 구간 10 m 이상')
    print('R6_RELEASE_SIGMA',result['released_descendants'],result['quantiles_m'],flush=True)
if __name__=='__main__':main()
