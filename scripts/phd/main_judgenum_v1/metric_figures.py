"""Requested static distributions; every curve carries its exact source and values."""
import json
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from scipy.special import erf
from figures import data,export,setup,O,C,D
from analyse import save
from lock_config import sha

GROUPS=[('LoD2',1,'roof','LoD2 지붕'),('LoD2',2,'wall','LoD2 벽'),('ALS',1,'roof','항공 LiDAR 지붕')]
COLORS={1:'#0072b2',2:'#d55e00'}

def table(name):return json.loads((D/'tables'/f'{name}.json').read_text())['rows']

def main():
    setup();cal=json.loads((O/'calibration.json').read_text())['values']
    selected=table('selected_values');medians=[];dlrows=[]
    for prior in ['LoD2','ALS']:
        d,sources=data(prior);base=cal[prior]['base']
        for _,kind,group,title in [g for g in GROUPS if g[0]==prior]:
            mask=d['kind']==kind;A=base['A'][str(kind)]
            maxima=[r for r in table(f'{prior}_base_null_buildings') if r['kind']==kind]
            v=np.array([r['largest_false_component_m2'] for r in maxima]);positive=v[v>0]
            fig,ax=plt.subplots(figsize=(7,4))
            if len(positive):
                bins=np.geomspace(min(.02,float(positive.min())*.8),max(2.,float(positive.max())*1.2),24)
                ax.hist(positive,bins=bins,color='#607d8b',edgecolor='white')
            ax.set_xscale('log');ax.axvline(1,color='#777777',ls='--',label='1 m²')
            if A is not None and A>0:ax.axvline(A,color='#d55e00',label=f'A = {A:.3f} m²')
            ax.text(.98,.95,f'건물 {len(v)}동 · 0 m² {int((v==0).sum())}동',ha='right',va='top',transform=ax.transAxes)
            ax.set(title=title,xlabel='건물마다 가장 큰 우연한 덩어리 (m²)',ylabel='건물 수');ax.legend();fig.tight_layout()
            export(fig,f'false_components_{prior}_{group}',{'rows':maxima,'A_m2':A,'photos':[],
              'source':f'tables/{prior}_base_null_buildings.json','zero_not_on_log_axis':int((v==0).sum())})
            index=base['photo_choices'][group];pi,ti=divmod(index,9);threshold=[.3,.5,.75,1,1.5,2,3,5,None][ti]
            fig,axs=plt.subplots(1,2,figsize=(11,4),gridspec_kw={'width_ratios':[1.5,1]});payload=[]
            edges=np.geomspace(1,1000,32)
            for cell in [1,2]:
                m=mask&(d['judgment_after']==1)&(d['photo_judgments'][:,pi]>=2)&(d['cell']==cell)&np.isfinite(d['d_mean_cm'])
                vv=np.abs(d['d_mean_cm'][m]);aa=d['area'][m];den=float(aa.sum())
                hist=np.histogram(vv,bins=edges,weights=aa)[0]/den if den else np.zeros(len(edges)-1)
                axs[0].stairs(hist,edges,color=COLORS[cell],lw=2,label=f'칸 {cell} · {den:.1f} m²')
                br=[]
                for bid in sorted(set(d['building'][m])):
                    b=m&(d['building']==bid);median=float(np.median(np.abs(d['d_mean_cm'][b])))
                    row={'prior':prior,'kind':kind,'building':bid,'cell':cell,'patch_count':int(b.sum()),'area_m2':float(d['area'][b].sum()),'median_abs_d_cm':median}
                    br.append(row);medians.append(row)
                ys=np.linspace(-.16,.16,len(br)) if len(br)>1 else np.zeros(len(br))
                axs[1].scatter([r['median_abs_d_cm'] for r in br],cell+ys,s=15,c=COLORS[cell],alpha=.7)
                payload.append({'cell':cell,'patch_ids':d['patch_id'][m].tolist(),'edges_cm':edges.tolist(),'area_fraction_per_bin':hist.tolist(),
                  'denominator_area_m2':den,'below_1cm_area_m2':float(aa[vv<1].sum()),'above_1000cm_area_m2':float(aa[vv>1000].sum()),'building_medians':br})
            for ax in axs:
                ax.set_xscale('log');ax.set_xlim(1,1000);ax.set_xlabel('|d| (cm)');ax.grid(alpha=.15)
                if threshold is not None:ax.axvline(threshold*100,color='#222222',ls='--')
            axs[0].set_ylabel('해당 칸의 넓이 비율');axs[0].legend(fontsize=8)
            axs[1].set(yticks=[1,2],yticklabels=['칸 1','칸 2'],ylim=(.6,2.4),title='건물마다 중앙값')
            fig.suptitle(title+' · 사진 모름 · 문턱 '+('없음' if threshold is None else f'{threshold:g} m'));fig.tight_layout()
            export(fig,f'distance_distributions_{prior}_{group}',{'sources':sources,'photo_index':pi,'threshold2_m':threshold,'rows':payload,'photos':[]})
            grid=table(f'{prior}_base_{group}_grid');values=np.array([r['wrong_fraction'] for r in grid],float).reshape(15,9)
            fig,ax=plt.subplots(figsize=(9,7));im=ax.imshow(values*100,cmap='magma_r',aspect='auto')
            ax.add_patch(Rectangle((ti-.5,pi-.5),1,1,fill=False,edgecolor='#00a6a6',lw=3))
            ax.set_xticks(np.arange(9),['.3','.5','.75','1','1.5','2','3','5','없음'])
            ax.set_yticks(np.arange(15),[f'{delta:.2f} / {score:g}' for delta in [.05,.1,.15,.2,.3] for score in [0,.3,.5]])
            ax.set(xlabel='두 번째 문턱 (m)',ylabel='δ / 최소 점수',title=title+' · 처음 선택이 틀린 넓이 비율')
            fig.colorbar(im,ax=ax,label='%');fig.tight_layout()
            export(fig,f'choice_heatmap_{prior}_{group}',{'rows':grid,'chosen_index':index,'photos':[]})
            for rt in ['all']+sorted(set(d['roof_type'][mask])):
                m=mask if rt=='all' else mask&(d['roof_type']==rt)
                finite=m&np.isfinite(d['DL_cm']);vals=d['DL_cm'][finite]
                dlrows.append({'prior':prior,'kind':kind,'roof_type':str(rt),'patch_count':int(finite.sum()),
                  'area_m2':float(d['area'][finite].sum()),'unavailable_patch_count':int((m&~np.isfinite(d['DL_cm'])).sum()),
                  'median_DL_cm':float(np.median(vals)) if len(vals) else None})
        # Equal-core empirical CDF matches the unweighted quantiles in section 5.1.
        kinds=[1,2] if prior=='LoD2' else [1]
        fig,axs=plt.subplots(1,len(kinds),figsize=(6*len(kinds),4),squeeze=False);curves=[]
        for ax,kind in zip(axs[0],kinds):
            m=(d['kind']==kind)&(d['cell']==0)&np.isfinite(d['DL_cm'])&(d['DL_cm']>0)&np.isfinite(d['d_mean_cm'])
            strata=sorted(set(d['roof_type'][m])) if prior=='LoD2' and kind==1 else ['all']
            for rt in strata:
                mm=m if rt=='all' else m&(d['roof_type']==rt)
                vals=np.sort(np.abs(d['d_mean_cm'][mm])/d['DL_cm'][mm]*1.96)
                if not len(vals):continue
                ix=np.unique(np.linspace(0,len(vals)-1,min(3000,len(vals))).astype(int));x=vals[ix];y=(ix+1)/len(vals)
                ax.plot(x,y,label=f'{rt} · {len(vals):,}개')
                curves.append({'kind':kind,'roof_type':str(rt),'patch_count':len(vals),'x':x.tolist(),'cdf':y.tolist(),
                  'patch_selection':'kind, cell==0, finite positive DL; exact source rows, no area weighting'})
            x=np.linspace(0,10,1000);ax.plot(x,erf(x/np.sqrt(2)),color='black',ls='--',label='표준 정규 절댓값')
            ax.set(xlim=(0,10),ylim=(0,1),xlabel='|d| ÷ DL × 1.96',ylabel='누적 비율',title='지붕' if kind==1 else '벽');ax.legend(fontsize=8);ax.grid(alpha=.15)
        fig.suptitle(('항공 LiDAR' if prior=='ALS' else prior)+' · 흔들림 모형');fig.tight_layout()
        export(fig,f'model_cdf_{prior}',{'sources':sources,'curves':curves,'photos':[],'display_x_max':10,'full_quantiles':'tables/model_quantiles.json'})
    save('unknown_photo_building_medians',medians);save('DL_medians',dlrows)
    print('METRIC_FIGURES_COMPLETE',flush=True)

if __name__=='__main__':main()
