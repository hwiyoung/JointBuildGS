"""9.2/9.4: frozen XY views and seed-fate bars, complete data without sampling."""
import argparse
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.colors import ListedColormap
from inputs import OUT,SITES,PRIORS,save,sha
from side_tables import VARS

font_manager.fontManager.addfont('/fonts/NotoSansCJK-Regular.ttc')
plt.rcParams.update({'font.family':'Noto Sans CJK JP','font.size':9,'axes.unicode_minus':False})
FIG=Path('/docs/figures');FIG.mkdir(exist_ok=True)
LABELS={'lt_fixgt':'고정 · 참값','lt_dyngt':'다이내믹 · 참값','lt_dynsoft':'다이내믹 · 약한 참값','lt_dynnow':'다이내믹 · 평균값','lt_fixnow':'고정 · 평균값'}

def maps(site,prior):
    root=OUT/'direct_stage1_v2'/(site+'__'+prior)
    with np.load(root/'evaluation.npz') as z:e={k:z[k] for k in ['centre','in_eval','scoring_allowed','has_mvs','cell','p_mvs','p_gt','tau','area']}
    with np.load(root/'values.npz') as z:
        m=e['in_eval']&e['scoring_allowed']&e['has_mvs']&(e['cell']<4)&(np.abs(e['p_mvs'])/np.sqrt(z['sigma_prior'].astype(float)**2+z['sigma_mvs'].astype(float)**2)>3)
    ids=np.flatnonzero(m);xy=e['centre'][m,:2];A=e['area'][m];N=len(ids)
    # Same scene's fixed in_eval domain controls all panels; outcomes never select the view.
    domain=e['centre'][e['in_eval'],:2];lo=domain.min(0)-.25;hi=domain.max(0)+.25
    paths=[(v,OUT/'patch_z'/f'{site}__{prior}__{v}_{prior}_s0.npz') for v in VARS]
    paths=[(v,p) for v,p in paths if p.exists()]
    if not paths:return
    paths.append(('analytic',OUT/'patch_z'/f'{site}__{prior}__analytic_dyn_gt.npz'))
    fig,axes=plt.subplots(1,len(paths),figsize=(3.5*len(paths),5),squeeze=False,sharex=True,sharey=True)
    records=[];cmap=ListedColormap(['#c94448','#2b8c6b'])
    for ax,(v,p) in zip(axes[0],paths):
        with np.load(p) as z:hit=np.isfinite(z['z'][m])&(np.abs(z['z'][m]-e['p_gt'][m])<=e['tau'][m])
        ratio=float(100*A[hit].sum()/A.sum()) if len(A) else None
        ax.scatter(xy[:,0],xy[:,1],c=hit.astype(int),cmap=cmap,vmin=0,vmax=1,s=1.5,marker='s',linewidths=0,rasterized=True)
        ax.set(xlim=(lo[0],hi[0]),ylim=(lo[1],hi[1]),aspect='equal',title=LABELS.get(v,'학습 없는 시험 · 판 2'),xlabel='x (m)')
        ax.text(.02,.02,'τ 안 '+('확인 불가' if ratio is None else f'{ratio:.2f}%'),transform=ax.transAxes,fontsize=9,bbox={'facecolor':'white','alpha':.9,'edgecolor':'none'})
        records.append(dict(variant=v,source=str(p),sha256=sha(p),success_count=int(hit.sum()),success_area_m2=float(A[hit].sum()),within_tau_percent=ratio))
    axes[0,0].set_ylabel('y (m)')
    title=f'{site} · {prior}: 차가 설명 안 되는 곳의 τ 안·밖을 같은 범위에서 본다'
    fig.suptitle(title,x=.035,ha='left',fontsize=13)
    fig.text(.04,.02,f'패치 {N:,}개 · 넓이 {A.sum():.3f} m² · 초록 τ 안 / 빨강 τ 밖(면 없음 포함)',fontsize=9)
    fig.tight_layout(rect=[0,.06,1,.93]);key=f'map_{site}_{prior}';fig.savefig(FIG/(key+'.png'),dpi=300);plt.close(fig)
    save(FIG/(key+'.json'),dict(title=title,panels=records,patches=N,area_m2=float(A.sum()),patch_indices=ids.tolist(),
        xlim=[float(lo[0]),float(hi[0])],ylim=[float(lo[1]),float(hi[1])],no_statistical_subsampling=True,visual_review='PENDING',scientific_verdict=None))
    p=OUT/'patch_z'/f'{site}__{prior}__lt_dyngt_{prior}_s0.npz';q=OUT/'patch_z'/f'{site}__{prior}__analytic_dyn_gt.npz'
    if p.exists():
        with np.load(p) as z,np.load(q) as a:same=z['side'][m]==a['side'][m]
        fig,ax=plt.subplots(figsize=(6,6));ax.scatter(xy[:,0],xy[:,1],c=same.astype(int),cmap=cmap,vmin=0,vmax=1,s=2,marker='s',linewidths=0)
        ax.set(xlim=(lo[0],hi[0]),ylim=(lo[1],hi[1]),aspect='equal',xlabel='x (m)',ylabel='y (m)',title='판 2: 도착점과 같은 쪽에 선 곳')
        ratio=float(100*A[same].sum()/A.sum()) if A.sum() else None
        fig.text(.04,.02,f'{site} · {prior} · 패치 {N:,}개 · 같은 쪽 {ratio:.2f}% · 초록 같음 / 빨강 다름',fontsize=9)
        fig.tight_layout(rect=[0,.06,1,1]);key=f'side_map_{site}_{prior}';fig.savefig(FIG/(key+'.png'),dpi=300);plt.close(fig)
        save(FIG/(key+'.json'),dict(source=str(p),sha256=sha(p),analytic=str(q),analytic_sha256=sha(q),
            patches=N,same_side_percent=ratio,area_m2=float(A.sum()),xlim=[float(lo[0]),float(hi[0])],ylim=[float(lo[1]),float(hi[1])],visual_review='PENDING',scientific_verdict=None))
    print(site,prior,'maps written',flush=True)

def fates(site,prior):
    rows=[json.loads(p.read_text()) for p in sorted((Path('/docs/tables/fates')/site).glob(prior+'__*.json'))]
    if not any(r['result'].startswith('lt_') for r in rows):return
    rows=sorted(rows,key=lambda r: (0 if r['result'].startswith('nojudge') else list(VARS).index(r['result'].rsplit('_',2)[0])+1))
    colours=['#bdbdbd','#ae3434','#238b45','#756bb1'];cats=['removed','old_place','current_surface','neither']
    fig,axes=plt.subplots(1,2,figsize=(12,4.8),sharex=True,sharey=True)
    for ax,region,title in zip(axes,['prior_wrong_1_3','prior_correct_0_2'],['사전 정보 틀림 · 칸 1·3','사전 정보 맞음 · 칸 0·2']):
        for y,row in enumerate(rows):
            d=row['regions'][region];left=0
            for c,col in zip(cats,colours):
                val=100*d['shares'][c] if d['shares'][c] is not None else 0
                ax.barh(y,val,left=left,color=col,height=.62)
                if val>=8:ax.text(left+val/2,y,f'{val:.1f}',ha='center',va='center',fontsize=9)
                left+=val
            ax.text(101,y,f"N={d['seeds_planted']:,}",va='center',fontsize=8)
        names=['판정 끔' if r['result'].startswith('nojudge') else LABELS[r['result'].rsplit('_',2)[0]] for r in rows]
        ax.set(yticks=np.arange(len(rows)),yticklabels=names,xlim=(0,120),xticks=[0,25,50,75,100],xlabel='심긴 점 묶음의 비율 (%)',title=title)
    axes[0].invert_yaxis();fig.suptitle(f'{site} · {prior}: 사전 정보에서 심은 점의 남음·이동·지워짐',x=.04,ha='left',fontsize=13)
    for x,col,lab in zip([.08,.29,.51,.73],colours,['지워짐','옛 자리','지금 면','둘 다 아님']):fig.text(x,.02,lab,color='#595959' if col=='#bdbdbd' else col,fontsize=10)
    fig.tight_layout(rect=[0,.07,1,.92]);key=f'fates_{site}_{prior}';fig.savefig(FIG/(key+'.png'),dpi=300);plt.close(fig)
    save(FIG/(key+'.json'),dict(rows=rows,categories=cats,colours=colours,visual_review='PENDING',scientific_verdict=None))
    print(site,prior,'fate figure written',flush=True)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--site',choices=SITES);ap.add_argument('--prior',choices=PRIORS);a=ap.parse_args()
    for site in [a.site] if a.site else SITES:
        for prior in [a.prior] if a.prior else PRIORS:maps(site,prior);fates(site,prior)

if __name__=='__main__':main()
