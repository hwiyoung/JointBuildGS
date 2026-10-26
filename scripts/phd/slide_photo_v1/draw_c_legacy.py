from common import *
from photos import *
from matplotlib.collections import LineCollection
def geometry_helpers():
    sys.path.insert(0,'/repo/scripts/phd/main_photofig_v1')
    import pf_geo
    return pf_geo
def draw_change():
    c=config();rec=load(REPO/'docs/experiments/phd/main_regionfig_v1/tables/영역예시_보정_숫자.json')['examples'][0]
    ex=load(REPO/'configs/phd/main_regionfig_v1/regionfig_v1.json')['examples'][0]
    a=np.array(ex['end_xy'])-ex['start_xy'];a/=np.linalg.norm(a);b=np.array([-a[1],a[0]]);mid=(np.array(ex['end_xy'])+ex['start_xy'])/2
    lo=np.minimum(ex['start_xy'],ex['end_xy'])-6;hi=np.maximum(ex['start_xy'],ex['end_xy'])+6
    paths=[U/'points/B173nb_b10/als_xyz.npy',U/'points/B173nb_b10/gt_xyz.npy'];points=[]
    for path in paths:
        x=np.load(path,mmap_mode='r');m=np.all((x[:,:2]>=lo)&(x[:,:2]<=hi),axis=1);points.append(np.array(x[m]))
    # Layout-only revision: focus both panels on the same roof-height window.
    H=np.asarray(rec['heights_model_m']);display_z=[float(np.nanmin(H))-1,float(np.nanmax(H))+1]
    points=[x[(x[:,2]>=display_z[0])&(x[:,2]<=display_z[1])] for x in points]
    allx=np.concatenate(points);z0=float(allx[:,2].min());z1=float(allx[:,2].max());elev=np.deg2rad(35)
    poses,cams=models();names=load(S0/'fork_inputs/s61/B173nb_b10/split.json')['train']
    oblique=[n for n in names if G.tilt(poses[Path(n).stem])>30]
    view=dict(virtual=True,elevation_deg=35,axis_xy=a,mid_xy=mid)
    try:
        best,_=choose_native(allx[::max(1,len(allx)//10000)],oblique)
        pose=poses[best['view']];camera=cams[pose['cam']]
        coords=[G.project(x,pose,camera)[0]*[1,-1] for x in points]
        view=dict(virtual=False,training_view=best['view'],pose=pose,camera=camera,selection=best)
    except AssertionError:
        coords=[]
        for x in points:
            xy=x[:,:2]-mid;coords.append(np.c_[xy@a,(x[:,2]-z0)*np.cos(elev)-(xy@b)*np.sin(elev)])
        view['reason']='No oblique training image contains 95 percent of the fixed wing context.'
    xyall=np.concatenate(coords);xmin,xmax=xyall[:,0].min(),xyall[:,0].max();ymin,ymax=xyall[:,1].min(),xyall[:,1].max()
    plt=plot_setup(55);fig,axs=plt.subplots(2,1,figsize=(15,12.6),dpi=100);fig.subplots_adjust(left=.02,right=.98,bottom=.02,top=.90,hspace=.24)
    for row,(ax,x,q,label) in enumerate(zip(axs,points,coords,['2022 항공 LiDAR','2024 드론 LiDAR · 참값'])):
        order=np.argsort(x[:,2]);ax.scatter(q[order,0],q[order,1],c=x[order,2],vmin=z0,vmax=z1,cmap='viridis',s=3 if len(x)>50000 else 30,linewidths=0,rasterized=True)
        ax.set(xlim=(xmin-.4,xmax+.4),ylim=(ymin-.4,ymax+.4));ax.set_aspect('equal');ax.axis('off');ax.set_title(label,fontsize=55,pad=10,loc='left')
        centre=np.r_[mid,np.nanmedian(H[:,0 if row==0 else 2])]
        if view['virtual']:
            target=np.array([0,(centre[2]-z0)*np.cos(elev)])
        else:target=G.project(centre[None,:],pose,camera)[0][0]*[1,-1]
        ax.annotate('옛 지붕' if row==0 else '낮아진 지붕',xy=target,xytext=(.05,.15 if row==0 else .85),textcoords='axes fraction',fontsize=55,arrowprops=dict(arrowstyle='->',color='#202A35',lw=4),bbox=dict(facecolor='white',edgecolor='none',alpha=.9,pad=4))
    p=DOC/'figures/figS_c_change.png';fig.savefig(p,dpi=100,facecolor='white');plt.close(fig)
    dump(p.with_suffix('.json'),dict(task_id=c['task_id'],scientific_verdict=None,inputs=[str(p) for p in paths],source_numbers=str(REPO/'docs/experiments/phd/main_regionfig_v1/tables/영역예시_보정_숫자.json'),view=view,bounds_xy=[lo,hi],height_colour_range_m=[z0,z1],display_z_window_m=display_z,point_counts=[len(x) for x in points],reference_prior_minus_gt_cm=455.63414286315316,reference_source='REGIONFIG-v1 final number JSON; not recomputed',revision='First blind reader noticed point density, not changed roof; one layout-only revision focuses both panels on the same roof height range and labels the roof. Site and measured values unchanged.'))
    print('DRAW c_change',flush=True)
def draw_repr():
    c=config();sel=load(PAY/'selection_c_repr.json');assert sel['status']=='PASS';gg=geometry_helpers();site='B0_b10'
    with np.load(U/'patch_values/B0_b10__LoD2__R1.5.npz') as zz:z={k:zz[k] for k in ['centre','normal','in_eval','roof_like','surf','gt_p','mvs_a_p','mvs_a_status']}
    ix=np.array(sel['patch_indices']);C=z['centre'][ix];X=C+z['normal'][ix]*z['gt_p'][ix,None]
    names=load(S0/'fork_inputs/s61/B0_b10/split.json')['train']
    from task0_scan import cameras_depth
    _,gridcam=cameras_depth();poses,_=models();visible=[]
    for name in names:
        stem=Path(name).stem;uv,depthq=G.project(X,poses[stem],gridcam);ij=np.floor(uv).astype(int);ok=(depthq>0)&(ij[:,0]>=0)&(ij[:,0]<1024)&(ij[:,1]>=0)&(ij[:,1]<741)
        if ok.mean()<.95:continue
        pdepth=np.load(S0/'s61/export/B0_b10/LoD2/prior'/f'{stem}.npy');seen=np.zeros(len(X),bool);seen[ok]=abs(pdepth[ij[ok,1],ij[ok,0]]-depthq[ok])<=.5
        if seen.mean()>=.8:visible.append(stem)
    best,rank=choose_native(X,visible,np.median(z['normal'][ix],axis=0),oblique=True)
    im,photo=crop_native(best['view'],X,aspect=2.2,pad=.18)
    # Show actual LoD2 mesh edges projected in the same original photo.
    mesh=np.load(PH/'main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1/s02_box/B0_b10/lod2_mesh.npz')
    shift=np.array(load(S0/'s61/box/B0_b10/LoD2/summary.json')['registration']['shift_applied']);V=mesh['V']+shift
    F=mesh['F'][mesh['tri_surface']==sel['face']];edges=np.concatenate([F[:,[0,1]],F[:,[1,2]],F[:,[2,0]]]);edges=np.unique(np.sort(edges,axis=1),axis=0)
    uv,_=G.project(V,photo['pose'],photo['camera']);uv-=photo['crop_box_px'][:2]
    # Section length fixed from face PCA before plotting, 5m through centre.
    mid=np.median(C[:,:2],axis=0);_,_,vt=np.linalg.svd(C[:,:2]-mid,full_matrices=False);axis=vt[0];across=np.array([-axis[1],axis[0]])
    s=(C[:,:2]-mid)@axis;cross=(C[:,:2]-mid)@across;keep=(abs(s)<=2.5)&(abs(cross)<=.6);bins=np.arange(-2.5,2.5001,.25);lines=[]
    for k in range(len(bins)-1):
        j=keep&(s>=bins[k])&(s<bins[k+1])
        lines.append([float((bins[k]+bins[k+1])/2),*([float(np.median(v[j])) for v in [C[:,2],X[:,2],C[:,2]+z['mvs_a_p'][ix]*z['normal'][ix,2]]] if j.any() else [np.nan]*3)])
    lines=np.array(lines);zero=float(np.nanmin(lines[:,2]));lines[:,1:]-=zero
    plt=plot_setup(55);fig=plt.figure(figsize=(15,12.6),dpi=100);ax=fig.add_axes([.02,.51,.96,.47]);ax.imshow(im);ax.add_collection(LineCollection(uv[edges],colors=c['colours']['prior'],linewidths=4));ax.axis('off')
    ax=fig.add_axes([.12,.18,.84,.25]);ax.scatter(lines[:,0],lines[:,2],s=95,c=c['colours']['gt'],label='참값');ax.plot(lines[:,0],lines[:,1],color=c['colours']['prior'],ls='--',lw=5,label='LoD2');ax.plot(lines[:,0],lines[:,3],color=c['colours']['mvs'],lw=4,label='MVS')
    ax.set_xlim(-2.5,2.5);ax.set_xticks([-2,0,2]);ax.set_xlabel('거리 (m)',fontsize=55);ax.set_yticks([]);ax.spines['left'].set_visible(False)
    for xpos,label,key in [(.02,'참값','gt'),(.35,'LoD2','prior'),(.72,'MVS','mvs')]:ax.text(xpos,1.05,label,color=c['colours'][key],transform=ax.transAxes,fontsize=55)
    k=np.nanargmin(abs(lines[:,0]-1));v=lines[k];ax.annotate('',(v[0],v[1]),(v[0],v[2]),arrowprops=dict(arrowstyle='<->',lw=3,color='black'));ax.text(.98,.90,f'{abs(sel["prior_signed_median_m"])*100:.1f} cm',ha='right',va='top',transform=ax.transAxes,fontsize=55)
    p=DOC/'figures/figS_c_repr.png';fig.savefig(p,dpi=100,facecolor='white');plt.close(fig)
    dump(p.with_suffix('.json'),dict(task_id=c['task_id'],scientific_verdict=None,selection={k:v for k,v in sel.items() if k!='all_faces'},photo=photo,photo_selection=best,section=dict(mid_xy=mid,axis_xy=axis,length_m=5,half_width_m=.6,bin_m=.25,heights=lines,zero_m=zero,vertical_exaggeration=True),reference_tau_cm=19.75,source='Existing UNCERT input measurements; aggregation [이 발주에서 냄]'))
    im.save(PAY/'c_repr_native.png');dump(PAY/'c_repr_photo.json',photo);print('DRAW c_repr',best,flush=True)
if __name__=='__main__':
    draw_change();draw_repr()
