"""North-up maps of development prior errors only."""
import numpy as np
from analysis_common import load,font,figure,CFG
def main():
    plt=font()
    for prior in ['LoD2','ALS']:
        d=load(prior);fig,axs=plt.subplots(1,2,figsize=(12,7),sharex=True,sharey=True);data=[]
        for ax,roof in zip(axs,[True,False]):
            shape=d['roof_like']==roof;known=shape&(d['gt_status']==0);bad=known&(np.abs(d['gt_p'])>CFG['tau_m'][prior]);xy=d['centre'][:,:2]+[690953.,5336071.]
            ax.scatter(xy[shape,0],xy[shape,1],s=.12,c='#dddddd',rasterized=True)
            im=ax.scatter(xy[bad,0],xy[bad,1],s=.25,c=d['gt_p'][bad],cmap='coolwarm',vmin=-4,vmax=4,rasterized=True)
            ax.set_aspect('equal');ax.set_title('지붕꼴' if roof else '벽꼴');ax.set_xlabel('동쪽 좌표 (m)');ax.ticklabel_format(useOffset=False,style='plain');ax.tick_params(axis='x',rotation=35)
            data.append(dict(shape='roof' if roof else 'wall',patches=int(shape.sum()),gt_available=int(known.sum()),wrong_patches=int(bad.sum()),wrong_area_m2=float(d['area'][bad].sum()),
                colour_clip_m=[-4,4],tau_m=CFG['tau_m'][prior],crs='EPSG:25832'))
        axs[0].set_ylabel('북쪽 좌표 (m)');fig.colorbar(im,ax=axs.tolist(),label='참값의 자리 (m), 바깥 +',shrink=.7)
        fig.suptitle(prior+' · 사전 정보가 틀린 곳 · 정하는 곳')
        figure(fig,f'사전정보_틀린곳_지도_{prior}',data);plt.close(fig)
    print('development prior maps complete',flush=True)
if __name__=='__main__':main()
