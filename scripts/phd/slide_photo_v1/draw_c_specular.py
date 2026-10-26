from common import *
from photos import *
from task0_scan import cameras_depth
def main():
    c=config();row=load(DOC/'figures/task0_specular_candidates.json')['selected'];assert row
    Q=np.array(row['gt_representative']);C=np.array(row['centre']);N=np.array(row['normal']);poses,cam=cameras_depth();wanted=set(row['patch_ids']);cloud=[]
    mid=np.median(Q,axis=0);normal=np.median(N,axis=0);normal/=np.linalg.norm(normal)
    def local(X):
        d=X-mid;return np.linalg.norm(d-(d@normal)[:,None]*normal,axis=1)<=3
    for tile in row['tiles']:
        z=geometry(tile,row['prior']);m=dict(np.load(PAY/'task0/mvs_v4'/f'{tile}_{row["prior"]}.npz'));g=dict(np.load(PAY/'task0/gt'/f'{tile}_{row["prior"]}.npz'));sel=np.array([p in wanted for p in z['patch_id'][m['patch_index']]]);ix=m['patch_index'][sel];x=g['representative'][ix];per=m['per_view_signed'][sel]
        for i,name in enumerate(m['view_names']):
            ids=np.flatnonzero(np.isfinite(per[:,i])&local(x))
            if not len(ids):continue
            p=poses[str(name)];uv,zz=G.project(x[ids],p,cam);ij=np.floor(uv).astype(int);D=depth(W/'mvs/full/stereo/depth_maps'/f'{p["name"]}.geometric.bin');dd=D[ij[:,1],ij[:,0]];fx,fy,cx,cy=cam['p'];rays=np.c_[(ij[:,0]+.5-cx)/fx,(ij[:,1]+.5-cy)/fy,np.ones(len(ids))]@p['R'];cloud.append(-p['R'].T@p['t']+rays*dd[:,None])
    M=np.concatenate(cloud);fullQ=Q;keep=local(Q);Q=Q[keep];C=C[keep]
    # Orthographic side view of actual coordinates, not a fitted section curve.
    P=Q-mid;_,_,vt=np.linalg.svd(P-P@normal[:,None]*normal[None,:],full_matrices=False);e1=vt[0];e2=normal*np.cos(np.deg2rad(12))-np.cross(normal,e1)*np.sin(np.deg2rad(12))
    def proj(X):return np.c_[(X-mid)@e1,(X-mid)@e2]
    view=row['photos'][0]['view'];im,photo=crop_native(view,fullQ,aspect=1/2.1 if not row['roof'] else 2.1,pad=.12);im=outlined(im,photo['polygon_px'],False)
    if not row['roof']:im=im.transpose(Image.Transpose.ROTATE_90);photo['display_rotation_deg']=90
    plt=plot_setup(55);fig=plt.figure(figsize=(15,12.6),dpi=100);ax=fig.add_axes([.02,.52,.96,.46]);ax.imshow(im);ax.axis('off');ax.text(.01,.98,'금속 벽' if not row['roof'] else '금속 지붕',transform=ax.transAxes,va='top',fontsize=55,bbox=dict(facecolor='white',alpha=.9,edgecolor='none',pad=5))
    ax=fig.add_axes([.04,.08,.92,.36]);allp=[]
    for X,col,size,alpha in [(M,c['colours']['mvs'],5,.5),(C,c['colours']['prior'],35,.9),(Q,c['colours']['gt'],15,1)]:
        a=proj(X);allp.append(a);stride=max(1,int(np.ceil(len(a)/100000)));ax.scatter(a[::stride,0],a[::stride,1],color=col,s=size,alpha=alpha,linewidths=0)
    pq=proj(Q);ax.set_xlim(pq[:,0].min()-.3,pq[:,0].max()+.3);ax.set_ylim(pq[:,1].min()-1.0,pq[:,1].max()+1.0);ax.set_aspect('equal');ax.axis('off')
    for xpos,label,key in [(.01,'참값','gt'),(.30,'사전 정보','prior'),(.76,'MVS','mvs')]:ax.text(xpos,1.04,label,color=c['colours'][key],transform=ax.transAxes,fontsize=55)
    gap=row['mvs_abs_median_m'];direction=np.sign(row['mvs_signed_median_m']) or 1;xy=proj(np.stack([mid,mid+direction*gap*normal]));xy[:,0]=pq[:,0].max()+.1;ax.annotate('',xy[1],xy[0],arrowprops=dict(arrowstyle='<->',mutation_scale=12,lw=3,color='#202A35'));ax.text(.98,-.15,f'{gap*100:.0f} cm',transform=ax.transAxes,ha='right',fontsize=55)
    p=DOC/'figures/figS_c_specular.png';fig.savefig(p,dpi=100,facecolor='white');plt.close(fig)
    pm=proj(M);display=(pm[:,0]>=pq[:,0].min()-.3)&(pm[:,0]<=pq[:,0].max()+.3)&(pm[:,1]>=pq[:,1].min()-1)&(pm[:,1]<=pq[:,1].max()+1)
    dump(p.with_suffix('.json'),dict(task_id=c['task_id'],scientific_verdict=None,component_id=row['component_id'],photo=photo,view=dict(orthographic=True,axis1=e1,axis2=e2,centre=mid,tangent_display_radius_m=3,display_margin_normal_m=1,rule='input component median and fixed 3m tangent radius; normal projection axis covers GT plus 1m margin; numbers remain entire-component values'),point_counts=dict(gt=len(Q),prior=len(C),mvs=len(M),mvs_inside_display=int(display.sum()),mvs_outside_display=int((~display).sum())),reference_mvs_abs_median_m=gap,reference_prior_abs_median_m=row['prior_abs_median_m'],source='task0 recomputed input residuals; [이 발주에서 냄]',display_thinning='deterministic stride only, measurements use all samples'))
    np.savez_compressed(PAY/'task0/selected_clouds.npz',gt=Q,prior=C,mvs=M);print('DRAW c_specular',len(M),gap,flush=True)
if __name__=='__main__':main()
