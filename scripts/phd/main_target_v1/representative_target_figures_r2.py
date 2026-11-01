"""Show all frozen target maps while remaining background uncertainties are computed."""
import numpy as np
from PIL import Image
from matplotlib.colors import ListedColormap,BoundaryNorm
from matplotlib.patches import Patch
from common import *
from report_stage0 import plt,save

def main():
    cfg,lock=locked_r2();reps=json.loads((CFG/'representatives_v1.json').read_text())['rows']
    colors=['#a78bc2','#54ad80','#e6ab42','#478ac3','#c8c2b4'];cm=ListedColormap(colors);norm=BoundaryNorm(np.arange(-.5,5.5),5)
    checked=json.loads((DOC/'tables/stage1_representative_pixels_r2.json').read_text())['rows']
    for rep in reps:
        site=rep['site'];name=rep['camera']['name'];camera=rep['camera']
        for prior in rep['priors']:
            with np.load(OUT/'r2/stage1'/f'{site}_{prior}'/'maps'/f'{name}.npz') as z:m={k:z[k] for k in z.files}
            with np.load(OUT/'r2/targets'/f'{site}_{prior}.npz') as z:d={k:z[k] for k in ['h','region']}
            owner=m['owner'];has=owner>=0;h=np.full(owner.shape,np.nan);h[has]=d['h'][owner[has]]
            region=np.full(owner.shape,np.nan);region[has]=d['region'][owner[has]];region[(~has)&np.isfinite(m['depth'])]=4
            candidates=list((S0/'fork_inputs/s61'/site/f'scene_{prior}/images').glob(name+'.*'));assert len(candidates)==1
            photo=np.asarray(Image.open(candidates[0]).convert('RGB').resize((owner.shape[1],owner.shape[0]),Image.Resampling.BILINEAR))
            fig,ax=plt.subplots(1,3,figsize=(12,4.5));ax[0].imshow(photo);ax[0].set_title('고정한 학습 사진')
            line=np.c_[np.array([rep['start'],rep['end']]),np.full(2,rep['center_xyz'][2])]
            M=np.asarray(camera['W2C']);xyz=line@M[:3,:3].T+M[:3,3]
            u=camera['fx']*xyz[:,0]/xyz[:,2]+camera['cx'];v=camera['fy']*xyz[:,1]/xyz[:,2]+camera['cy']
            ax[0].plot(u,v,color='white',lw=3);ax[0].plot(u,v,color='black',ls='--',lw=1.5)
            im=ax[1].imshow(h,cmap='coolwarm',vmin=-5,vmax=5);ax[1].set_title('목표의 법선 방향 h (m)');fig.colorbar(im,ax=ax[1],fraction=.045,extend='both')
            ax[2].imshow(region,cmap=cm,norm=norm);ax[2].set_title('학습 전 고정한 영역')
            for a in ax:a.axis('off')
            fig.legend(handles=[Patch(color=c,label=t) for c,t in zip(colors,['관측 없음','일치','보존','보정','배경 MVS'])],ncol=5,loc='lower center',bbox_to_anchor=(.5,.085),fontsize=8)
            fig.subplots_adjust(top=.79,bottom=.24,wspace=.08)
            val=next(r for r in checked if r['representative']==rep['id'] and r['prior']==prior)
            save(fig,f'r2_stage1_rep{rep["id"]}_{prior}_target',f'{rep["name"]} · {prior}: 목표 높이와 영역을 학습 전에 고정했다',val,
                f'원반 화소 전체 h 복원 오차 중앙값 {val["absolute_h_error_median_m"]*1000:.4f} mm · h 색 범위 ±5 m, 범위 밖은 끝 색')
    print('REPRESENTATIVE_TARGET_FIGURES_COMPLETE',flush=True)

if __name__=='__main__':main()
