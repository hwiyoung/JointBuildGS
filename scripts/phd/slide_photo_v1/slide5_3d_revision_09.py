"""Frozen-input 3D comparison for slide 5; no training or invented geometry."""
import argparse
import os
import platform

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.spatial import Delaunay, ConvexHull
from matplotlib.collections import PolyCollection, LineCollection
from matplotlib.colors import to_rgb

from common import CFG, DOC, PAY, REPO, load, dump, sha, now, plot_setup
import slide5_draft_revision_08 as R8

OUT=DOC/'revision_09'
CACHE=PAY/'revision_09'
INK='#172B40';MUTED='#5B6B7C';GOLD='#C08A2B';BLUE='#2C6AA0';REF='#3A4A5E'
CONFIG=CFG/'slide5_3d_revision_09.json'


def lock_inputs():
    c=load(CONFIG);p=OUT/'input_lock.json'
    signatures={k:dict(path=v,sha256=sha(v)) for k,v in c['sources'].items()}
    if p.exists():
        old=load(p)
        assert old['sources']==signatures and old['config_sha256']==sha(CONFIG)
    else:
        dump(p,dict(task_id=c['task_id'],scientific_verdict=None,locked_at=now(),config_sha256=sha(CONFIG),sources=signatures))
    return c


def crop_points(path, lo, hi):
    a=np.load(path,mmap_mode='r');parts=[];ids=[]
    for start in range(0,len(a),250000):
        x=np.asarray(a[start:start+250000]);ok=np.all((x>=lo)&(x<=hi),axis=1)
        parts.append(x[ok].astype(np.float64));ids.append(start+np.flatnonzero(ok))
    return np.concatenate(parts),np.concatenate(ids),len(a)


def voxel(X,size):
    q=np.floor(X/size).astype(np.int64)
    _,idx=np.unique(q,axis=0,return_index=True)
    idx.sort()
    return X[idx],idx


def clip_polygon(poly,axis,bound,keep_above):
    if not len(poly):return poly
    result=[]
    for a,b in zip(poly,np.roll(poly,-1,axis=0)):
        ia=(a[axis]>=bound) if keep_above else (a[axis]<=bound)
        ib=(b[axis]>=bound) if keep_above else (b[axis]<=bound)
        if ia:result.append(a)
        if ia!=ib:
            t=(bound-a[axis])/(b[axis]-a[axis]);result.append(a+t*(b-a))
    return np.asarray(result).reshape(-1,3)


def crop_mesh(V,F,lo,hi):
    Q=V[F];ok=np.all(Q.max(1)>=lo,axis=1)&np.all(Q.min(1)<=hi,axis=1)
    polygons=[];source_ids=[]
    for index in np.flatnonzero(ok):
        poly=Q[index]
        for axis in range(3):
            poly=clip_polygon(poly,axis,lo[axis],True)
            poly=clip_polygon(poly,axis,hi[axis],False)
        if len(poly)>=3:
            for j in range(1,len(poly)-1):
                polygons.append(poly[[0,j,j+1]]);source_ids.append(index)
    out=np.asarray(polygons)
    assert np.all(out>=lo-1e-8) and np.all(out<=hi+1e-8)
    # Clipping creates only points in each source triangle's plane.
    parent=Q[np.asarray(source_ids)];n=np.cross(parent[:,1]-parent[:,0],parent[:,2]-parent[:,0])
    n/=np.maximum(np.linalg.norm(n,axis=1)[:,None],1e-15)
    residual=np.abs(np.sum((out-parent[:,:1])*n[:,None],axis=2))
    assert residual.max()<1e-7
    return out,np.asarray(source_ids),float(residual.max())


def prepare(c):
    meta_path=OUT/'geometry.json';cloud_path=CACHE/'geometry.npz'
    if meta_path.exists() and cloud_path.exists():
        m=load(meta_path);assert m['config_sha256']==sha(CONFIG) and m['geometry_sha256']==sha(cloud_path)
        return dict(np.load(cloud_path)),m
    source=c['sources'];scope=load(source['roof_scope']);e=load(source['roof_example'])['examples'][0]
    lo=np.r_[scope['bounds_xy'][0],scope['display_z_window_m'][0]]
    hi=np.r_[scope['bounds_xy'][1],scope['display_z_window_m'][1]]
    a=np.asarray(e['end_xy'])-e['start_xy'];a/=np.linalg.norm(a)
    B=np.array([[a[0],a[1],0],[-a[1],a[0],0],[0,0,1.]])
    origin=(lo+hi)/2
    mesh=np.load(source['roof_prior_mesh']);shift=np.asarray(load(source['roof_registration'])['registration']['shift_applied'])
    triangles,faces,clip_error=crop_mesh(mesh['V']+shift,mesh['F'],lo,hi)
    arrays={'roof_tri':(triangles-origin)@B.T,'roof_source_faces':faces}
    counts={};ids_meta={}
    for key,name in [('mvs','roof_mvs'),('gt','roof_reference')]:
        points,ids,total=crop_points(source[name],lo,hi)
        shown,ix=voxel(points,c['roof_display_voxel_m'])
        arrays['roof_'+key]=(shown-origin)@B.T
        arrays['roof_'+key+'_source_ids']=ids[ix]
        counts[key]=dict(total=total,in_fixed_volume=len(points),displayed=len(shown))
    section=load(source['wall_section']);z=np.load(source['wall_cloud'])
    C=np.asarray(section['source_view']['centre']);u=np.asarray(section['source_view']['axis1']);n=np.asarray(section['source_view']['axis2'])
    cross=np.cross(u,n)
    # Local x is the actual R7 section direction, y the original surface normal,
    # and z the cross-band tangent. This is a rigid coordinate change only.
    WB=np.stack([u,n,cross]);assert np.allclose(WB@WB.T,np.eye(3))
    for key in ['prior','gt','mvs']:
        ids=np.asarray(section['series'][key]['point_indices'])
        arrays['wall_'+key]=(z[key][ids]-C)@WB.T
        arrays['wall_'+key+'_source_ids']=ids
        assert np.allclose(arrays['wall_'+key][:,:2],section['series'][key]['projected_points'])
    w=arrays['wall_prior'];assert np.ptp(w[:,1])<1e-10
    tri=Delaunay(w[:,[0,2]]).simplices;arrays['wall_tri']=w[tri]
    np.savez_compressed(cloud_path,**arrays)
    meta=dict(task_id=c['task_id'],scientific_verdict=None,config_sha256=sha(CONFIG),geometry_sha256=sha(cloud_path),
        roof=dict(bounds_source='figS_c_change.json',crop_min_xyz=lo,crop_max_xyz=hi,origin=origin,basis=B,
                  registration_shift=shift,triangle_count=len(triangles),clip_plane_max_error_m=clip_error,point_counts=counts,
                  thinning='First original point in each 0.12 m voxel; identical MVS/reference rule, display only'),
        wall=dict(source='R7 exact raw point indices, no new filtering',origin=C,basis=WB,
                  counts={k:len(arrays['wall_'+k]) for k in ['prior','gt','mvs']},triangles=len(tri),
                  normal_min_max_m={k:[float(arrays['wall_'+k][:,1].min()),float(arrays['wall_'+k][:,1].max())] for k in ['prior','gt','mvs']},
                  prior_triangulation='Display tessellation strictly within the convex hull of frozen coplanar LoD2 prior points'),
        checks=dict(roof_original_triangle_planes_preserved=True,roof_all_source_layers_same_crop=True,
                    wall_all_frozen_points_retained=True,wall_r7_coordinate_replay=True,rigid_frame_transforms=True))
    dump(meta_path,meta);return arrays,meta


def projection(key, data, azimuth, elevation):
    az,el=np.deg2rad([azimuth,elevation]);eye=np.array([np.cos(el)*np.cos(az),np.cos(el)*np.sin(az),np.sin(el)])
    right=np.array([-np.sin(az),np.cos(az),0.]);up=np.cross(eye,right)
    basis=np.stack([right,up,eye]);assert np.allclose(basis@basis.T,np.eye(3))
    pts=np.concatenate([data[key+'_tri'].reshape(-1,3),data[key+'_mvs'],data[key+'_gt']])
    centre=(pts.min(0)+pts.max(0))/2
    def project(X):return (X-centre)@basis.T
    q=project(pts);lo=q[:,:2].min(0);hi=q[:,:2].max(0)
    return project,dict(azimuth_deg=azimuth,elevation_deg=elevation,basis=basis,centre=centre,lo=lo,hi=hi)


def render(key,data,mode,azimuth,elevation):
    rotation=np.eye(3)
    if key=='wall':
        section=load(load(CONFIG)['sources']['wall_section'])
        old=np.stack([section['source_view']['axis1'],section['source_view']['axis2'],section['cross_axis']])
        horizontal=old[0].copy();horizontal[2]=0;horizontal/=np.linalg.norm(horizontal)
        # Align the display with source-coordinate vertical. This is not a new
        # gravity estimate or source registration; all points undergo one rotation.
        upright=np.stack([horizontal,-old[1],np.array([0.,0.,1.])])
        rotation=upright@old.T
        assert np.allclose(rotation@rotation.T,np.eye(3)) and np.isclose(np.linalg.det(rotation),1)
        changed=dict(data)
        for k in ['prior','gt','mvs','tri']:
            changed[key+'_'+k]=data[key+'_'+k]@rotation.T
            assert np.allclose(np.linalg.norm(changed[key+'_'+k],axis=-1),np.linalg.norm(data[key+'_'+k],axis=-1))
        data=changed
    plt=plot_setup(18);project,view=projection(key,data,azimuth,elevation)
    view['display_rotation_from_frozen_frame']=rotation
    fig=plt.figure(figsize=(8.6,4.50),dpi=200,facecolor='white');ax=fig.add_axes([.02,.02,.96,.96])
    lo=np.asarray(view['lo']);hi=np.asarray(view['hi']);span=hi-lo
    ax.set_xlim(lo[0]-.07*span[0],hi[0]+.07*span[0]);ax.set_ylim(lo[1]-.08*span[1],hi[1]+.10*span[1]);ax.set_aspect('equal');ax.axis('off')
    # A quiet floor grid gives perspective without representing a measured ground.
    pts=np.concatenate([data[key+'_tri'].reshape(-1,3),data[key+'_mvs'],data[key+'_gt']]);mn=pts.min(0);mx=pts.max(0)
    floor=mn[2]-.03*(mx[2]-mn[2]);segments=[]
    for v in np.linspace(mn[0],mx[0],5):segments.append([[v,mn[1],floor],[v,mx[1],floor]])
    for v in np.linspace(mn[1],mx[1],4):segments.append([[mn[0],v,floor],[mx[0],v,floor]])
    ax.add_collection(LineCollection([project(np.asarray(s))[:,:2] for s in segments],colors='#E9EDF1',linewidths=.65,zorder=0))
    if mode in ['prior','all']:
        t=data[key+'_tri'];qp=project(t);order=np.argsort(qp[:,:,2].mean(1))
        normals=np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]);normals/=np.maximum(np.linalg.norm(normals,axis=1)[:,None],1e-12)
        light=np.array([-.3,-.4,1.]);light/=np.linalg.norm(light)
        shade=.72+.28*np.abs(normals@light)
        colour=np.clip(np.asarray(to_rgb(GOLD))[None]*shade[:,None]+(1-shade[:,None])*.8,0,1)
        face=np.c_[colour,np.full(len(t),.38 if key=='roof' else .30)]
        if key=='wall':
            plane=data['wall_prior'];hull=ConvexHull(plane[:,[0,2]]).vertices
            polygon=project(plane[hull])[:,:2]
            ax.add_collection(PolyCollection([polygon],facecolors=[(*to_rgb(GOLD),.24)],edgecolors=[GOLD],linewidths=1.1,zorder=1))
        else:
            ax.add_collection(PolyCollection(qp[order,:,:2],facecolors=face[order],edgecolors=(.75,.54,.17,.11),linewidths=.3,zorder=1))
    # Source layers are transparent overlays, deliberately not opaque occluders.
    g=project(data[key+'_gt']);order=np.argsort(g[:,2])
    ax.scatter(g[order,0],g[order,1],s=1.4 if key=='roof' else 13,c=REF,alpha=.47 if key=='roof' else .95,linewidths=0,zorder=2)
    if mode in ['mvs','all']:
        m=project(data[key+'_mvs']);order=np.argsort(m[:,2]);v=(m[:,2]-m[:,2].min())/max(np.ptp(m[:,2]),1e-9)
        base=np.asarray(to_rgb(BLUE));col=base[None]* (.80+.20*v[:,None])+(1-v[:,None])*.16
        ax.scatter(m[order,0],m[order,1],s=1.5 if key=='roof' else 7,c=np.clip(col[order],0,1),alpha=.76 if key=='roof' else .70,linewidths=0,zorder=3)
        if key=='wall':
            # Repeat reference marks on top for visibility through the overlay;
            # source positions remain unchanged and are recorded as an X-ray view.
            ax.scatter(g[:,0],g[:,1],s=15,c=REF,edgecolors='white',linewidths=.35,zorder=4)
    # Fixed measured-length scale; independent of the visualisation frame.
    unit=5 if key=='roof' else 1
    x=lo[0]+.04*span[0];y=lo[1]-.045*span[1]
    ax.plot([x,x+unit],[y,y],c=MUTED,lw=1.6);ax.text(x+unit/2,y+.025*span[1],f'{unit} m',ha='center',va='bottom',fontsize=18,color=MUTED)
    path=CACHE/f'{key}_{mode}.png';fig.savefig(path,dpi=200,facecolor='white');plt.close(fig)
    view['limits']=[lo,hi];view['uniform_metric_scale']=True;view['transparent_overlay']=True
    return Image.open(path).convert('RGB'),view


def label(im,xy,s,size=28,col=INK,bold=False,anchor='lt'):
    R8.text(im,xy,s,size,col,bold,anchor)


def compose(plots,mode):
    im=Image.new('RGB',(3840,2160),'white')
    label(im,(64,35),'두 자료의 오류 · 3차원 비교',25,MUTED)
    label(im,(64,82),'사전 정보와 영상은 서로 다른 곳에서 어긋난다',46,bold=True)
    legend=[(64,'사전 정보',GOLD),(310,'영상 MVS',BLUE),(565,'참조 · 드론 LiDAR',REF)]
    for x,s,col in legend:
        ImageDraw.Draw(im).ellipse((x*2,157*2,(x+15)*2,172*2),fill=col)
        label(im,(x+26,151),s,27,col)
    stage={'prior':'① 사전 정보와 참조','mvs':'② 영상과 참조','all':'③ 세 자료를 겹쳐 보기'}[mode]
    label(im,(1848,151),stage,27,MUTED,anchor='rt')
    for i,key in enumerate(['roof','wall']):
        x=64+i*960
        label(im,(x,225),'01  바뀐 지붕' if i==0 else '02  깊이가 어긋난 벽',34,bold=True)
        # Reuse the actual source image and exact projected section locator.
        R8.CACHE=CACHE
        meta=load(load(CONFIG)['sources'][key+'_photo']);pic,pm=R8.photo(meta,key)
        pic=pic.resize((720,400),Image.Resampling.LANCZOS);im.paste(pic,(x*2,290*2))
        label(im,(x+395,302),'노란 선 주변을',29,MUTED)
        label(im,(x+395,346),'3차원으로 확대',29,MUTED)
        label(im,(x+395,412),'항공 LiDAR ↔ MVS' if i==0 else 'LoD2 벽면 ↔ MVS',27)
        im.paste(plots[key],(x*2,500*2))
        captions={
            'prior':['사전 정보의 옛 지붕이 현재 참조보다 높음','사전 면이 현재 참조점 가까이에 위치'],
            'mvs':['현재 영상과 참조가 비슷한 위치에 놓임','영상 점들이 참조점의 앞뒤로 흩어짐'],
            'all':['옛 지붕은 위에 남고, 영상·참조는 아래에 겹침','사전 면은 참조 가까이, 영상 점은 앞뒤로 흩어짐']}
        label(im,(x,961),captions[mode][i],28,bold=True)
    R8.line(im,[(984,225),(984,1010)],'#E2E8EE',1)
    label(im,(64,1035),'실제 좌표 그대로 · 사선 시점의 투명 겹침 · 벽은 기존 6 m × 1.2 m 비교 구간 · 선·점은 서로 다른 자료',24,MUTED)
    return im


def main():
    p=argparse.ArgumentParser();p.add_argument('--prepare-only',action='store_true');p.add_argument('--roof-az',type=float,default=-58);p.add_argument('--roof-el',type=float,default=24);p.add_argument('--wall-az',type=float,default=-68);p.add_argument('--wall-el',type=float,default=28);args=p.parse_args()
    c=lock_inputs();data,meta=prepare(c)
    if args.prepare_only:
        print('GEOMETRY',meta['roof']['point_counts'],meta['roof']['triangle_count'],meta['wall']['counts']);return
    figures=OUT/'figures';previews=OUT/'previews';figures.mkdir(exist_ok=True);previews.mkdir(exist_ok=True)
    frames=[];views={};step_views={};R8.TEXT_RECORDS.clear()
    for mode in ['prior','mvs','all']:
        panels={}
        for key in ['roof','wall']:
            az=getattr(args,key+'_az');el=getattr(args,key+'_el')
            panels[key],views[key]=render(key,data,mode,az,el)
        step_views[mode]=dict(views)
        slide=compose(panels,mode);small=slide.resize((1920,1080),Image.Resampling.LANCZOS);frames.append(small)
        small.save(previews/f'slide5_3d_{mode}.png')
        if mode=='all':slide.save(figures/'slide5_3d_overlay.png')
    frames[0].save(figures/'slide5_3d_steps.gif',save_all=True,append_images=frames[1:],duration=[1800,1800,3200],loop=0,disposal=2)
    for key in ['roof','wall']:
        for mode in ['mvs','all']:
            for field in ['basis','centre','lo','hi','display_rotation_from_frozen_frame']:
                assert np.array_equal(step_views['prior'][key][field],step_views[mode][key][field])
    dump(OUT/'render.json',dict(task_id=c['task_id'],scientific_verdict=None,created_at=now(),config_sha256=sha(CONFIG),views=views,views_by_step=step_views,
         steps=['prior+reference','mvs+reference','prior+mvs+reference'],coordinates_equal_across_steps=True,
         all_frozen_wall_points_shown=True,depth_exaggeration=False,source_translation=False,reference_use='Evaluation only',
         labels=R8.TEXT_RECORDS,minimum_text_display_px=24,frame_grid='Orientation aid only, not measured ground',
         reader_review_record='qa/blind_reviews.json; valid only when the recorded image hash matches the current preview'))
    import PIL,matplotlib,scipy
    dump(OUT/'verification.json',dict(task_id=c['task_id'],scientific_verdict=None,verified_at=now(),base_commit=os.environ['TASK_BASE_COMMIT'],
         script_sha256=sha(REPO/'scripts/phd/slide_photo_v1/slide5_3d_revision_09.py'),
         versions=dict(python=platform.python_version(),numpy=np.__version__,pillow=PIL.__version__,matplotlib=matplotlib.__version__,scipy=scipy.__version__),
         checks={**meta['checks'],'frozen_source_hashes':True,'no_training':True,'no_gpu':True,'orthonormal_projection':True,'no_axis_exaggeration':True,'unchanged_coordinates_across_frames':True,'photo_projection_replay':True,'text_inside_canvas':True},
         files={str(f.relative_to(OUT)):dict(sha256=sha(f),bytes=f.stat().st_size) for f in sorted(figures.glob('*'))}))
    print('R9 saved',meta['roof']['point_counts'],meta['wall']['counts'],flush=True)


if __name__=='__main__':main()
