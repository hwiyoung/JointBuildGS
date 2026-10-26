"""Saved old stage1 RGB/depth plus actual Gaussian ellipses. CPU only."""
from common import *
from PIL import Image
from matplotlib.collections import PolyCollection
def main():
    c=config();sel=load(PAY/'selection_d_crop.json')['selected'];assert sel is not None
    view=sel['view'];x0,y0,x1,y1=sel['crop_box_grid_px'];sl=np.s_[y0:y1,x0:x1]
    run=S1/'stage1/B0_b10/prop_LoD2_s0';d=run/'model/dump/iteration_30000';ex=S0/'s61/export/B0_b10/LoD2'
    rp=d/f'{view}_rgb.png';dp=d/f'{view}_depth.npy';assert rp.exists() and dp.exists(), 'Selected saved render missing'
    realp=S0/f'fork_inputs/s61/B0_b10/images/{view}.jpg';rgb=np.asarray(Image.open(realp))[sl];render=np.asarray(Image.open(rp))[sl]
    depths=[np.load(ex/'mvs'/f'{view}.npy')[sl],np.load(ex/'prior'/f'{view}.npy')[sl],np.load(dp)[sl]]
    cf=np.load(ex/'conf'/f'{view}.npy')[sl];depths[0]=np.where(cf>0,depths[0],np.nan)
    depths=[np.where(np.isfinite(a)&(a>0),a,np.nan) for a in depths];vals=np.concatenate([a[np.isfinite(a)] for a in depths]);lo=float(vals.min());hi=float(vals.max())
    # Exact trained in-plane rotation and scales from the historical PLY.
    from plyfile import PlyData
    gp=run/'model/point_cloud/iteration_30000/point_cloud.ply';v=PlyData.read(gp)['vertex'].data
    xyz=np.c_[v['x'],v['y'],v['z']];face=load(PAY/'selection_c_repr.json');z=np.load(U/'patch_values/B0_b10__LoD2__R1.5.npz');mid=np.median(z['centre'][face['patch_indices']],axis=0)
    ids=np.flatnonzero((abs(xyz[:,0]-mid[0])<=1.5)&(abs(xyz[:,1]-mid[1])<=1.5)&(abs(xyz[:,2]-mid[2])<=2)&(v['opacity']>-4))
    stride=max(1,int(np.ceil(len(ids)/4000)));ids=ids[::stride];q=np.c_[v['rot_0'][ids],v['rot_1'][ids],v['rot_2'][ids],v['rot_3'][ids]];q/=np.linalg.norm(q,axis=1)[:,None]
    R=np.stack([G.qR(a) for a in q]);scale=np.exp(np.c_[v['scale_0'][ids],v['scale_1'][ids]])*.25
    theta=np.linspace(0,2*np.pi,19);ell=xyz[ids,None,:]+R[:,:,0][:,None,:]*scale[:,0,None,None]*np.cos(theta)[None,:,None]+R[:,:,1][:,None,:]*scale[:,1,None,None]*np.sin(theta)[None,:,None]
    # A fixed side-oblique presentation of the input-selected 3m roof region.
    e1=np.array([1.,0.,0.]);e2=np.array([0.,-.5,np.sqrt(.75)]);uv=np.stack([(ell-mid)@e1,(ell-mid)@e2],axis=-1)
    colour=np.clip(.5+.28209479177387814*np.c_[v['f_dc_0'][ids],v['f_dc_1'][ids],v['f_dc_2'][ids]],0,1)
    plt=plot_setup(36);fig=plt.figure(figsize=(32,8),dpi=100)
    ax=fig.add_axes([.01,.20,.26,.62]);ax.add_collection(PolyCollection(uv,facecolors=colour,edgecolors=colour,linewidths=.55,alpha=.85));ax.autoscale_view();ax.set_aspect('equal');ax.axis('off');ax.set_title('가우시안의 집합',fontsize=36,pad=18)
    photo=Image.open(PAY/'c_repr_native.png');ax=fig.add_axes([.20,.02,.09,.22]);ax.imshow(photo);ax.axis('off');ax.set_title('실제 사진',fontsize=36)
    # Five views share their pixel crop; depth panels share exact colour limits.
    boxes=[(.35,.53,.28,.35),(.68,.53,.28,.35),(.34,.04,.19,.32),(.56,.04,.19,.32),(.78,.04,.19,.32)]
    labels=['실제 영상','렌더링 영상','MVS 깊이','렌더링 깊이','사전 정보 깊이']
    for i,(box,label,a) in enumerate(zip(boxes,labels,[rgb,render,depths[0],depths[2],depths[1]])):
        ax=fig.add_axes(box);ax.imshow(np.rot90(a),**(dict(cmap='viridis',vmin=lo,vmax=hi) if i>=2 else {}));ax.axis('off');ax.set_title(label,fontsize=36,pad=10)
    fig.text(.65,.98,'한 시점에서 세 대상과 비교',ha='center',va='top',fontsize=36)
    ax=fig.add_axes([0,0,1,1],frameon=False);ax.set(xlim=(0,1),ylim=(0,1));ax.axis('off')
    for a,b in [((.63,.70),(.68,.70)),((.53,.21),(.56,.21)),((.75,.21),(.78,.21)),((.29,.50),(.33,.50))]:ax.annotate('',b,a,arrowprops=dict(arrowstyle='<->' if a[0]>.3 else '->',lw=3,color='#3A4A5E'))
    p=DOC/'figures/figS_d_gs_real.png';fig.savefig(p,dpi=100,facecolor='white');plt.close(fig)
    dump(p.with_suffix('.json'),dict(task_id=c['task_id'],scientific_verdict=None,selection=sel,gaussian_file=str(gp),saved_rgb=str(rp),saved_depth=str(dp),actual_image=str(realp),depth_colour_range_m=[lo,hi],display_rotation_deg=90,gaussian_display=dict(centre_xyz=mid,xy_half_m=1.5,display_scale=.25,stride=stride,shown=len(ids),orientation='exact PLY quaternion; fixed oblique display',opacity_min_logit=-4),render=dict(source='saved iteration_30000 render; no new GPU rendering',training=False),amendments=['amendment_01_d_crop.json','amendment_02_d_full_roi.json']))
    print('DRAW d',view,sel['crop_box_grid_px'],len(ids),[lo,hi],flush=True)
if __name__=='__main__':main()
