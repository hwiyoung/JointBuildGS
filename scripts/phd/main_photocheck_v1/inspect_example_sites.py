"""Locate requested illustration sites from prior geometry and MVS, without GT/score."""
from common import *
from cameras import Cameras
from projection_figures import plotting
def main():
    rows=[];pieces=[]
    for f in sorted((O/'geometry').glob('*__LoD2.npz')):
        p=npz(f);mask=(p['building']=='DEBY_LOD2_4906975')&(p['kind']==1)
        pieces.append({k:v[mask] for k,v in p.items()})
        for surf in np.unique(p['surf'][mask]):
            m=mask&(p['surf']==surf);v=p['mvs_p'][m]
            rows.append(dict(tile=f.stem.split('__')[0],surface=int(surf),points=int(m.sum()),area_m2=p['area'][m].sum(),centre=np.average(p['centre'][m],weights=p['area'][m],axis=0),xy_min=p['centre'][m,:2].min(0),xy_max=p['centre'][m,:2].max(0),mvs_median=np.nanmedian(v) if np.isfinite(v).any() else None))
    dump(O/'inspection/r1_prior_surfaces.json',rows)
    p={k:np.concatenate([d[k] for d in pieces]) for k in pieces[0]};plt=plotting();cam=Cameras();j=74;photo=cam.rgb(j)
    fig,axs=plt.subplots(1,2,figsize=(14,7));axs[0].scatter(p['centre'][:,0],p['centre'][:,1],c=p['centre'][:,2],s=4);axs[0].set_aspect('equal');axs[1].imshow(photo)
    uv,_,guard=cam.project(p['centre'],j);axs[1].scatter(uv[guard,0],uv[guard,1],s=.2,c=p['centre'][guard,2],alpha=.3)
    for r in rows:
        c=np.array(r['centre']);u,_,g=cam.project(c,j);label=f'{r["surface"]} / {r["tile"][-5:]}'
        axs[0].text(c[0],c[1],label,fontsize=7,bbox=dict(facecolor='white',alpha=.7));axs[1].text(u[0],u[1],str(r['surface']),fontsize=8,bbox=dict(facecolor='white',alpha=.7))
    axs[1].set_xlim(1750,4750);axs[1].set_ylim(3600,0);fig.tight_layout();fig.savefig(O/'inspection/r1_prior_surfaces.png',dpi=160);plt.close(fig)
    print('R1 prior-only surface inspection saved')
if __name__=='__main__':main()
