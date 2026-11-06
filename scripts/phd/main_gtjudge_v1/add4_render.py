"""CPU, exact full-distortion camera shared by photographs and geometry panels."""
from add4_common import *
from add4_figures import camera_projection
from cylinder import Cylinder
import cv2
from scipy.ndimage import distance_transform_edt
from add4_viewclip import faces,point_mask

def rays(cam,y0,y1):
    W,H=cam['output_size_px'];a,b,c,d=cam['crop_xyxy_px'];yy,xx=np.meshgrid(np.arange(y0,y1),np.arange(W),indexing='ij')
    # PIL EXTENT uses output pixel centres mapped into the original image.
    pts=np.c_[a+(xx.ravel()+.5)*(c-a)/W,b+(yy.ravel()+.5)*(d-b)/H]
    fx,fy,cx,cy,*dist=cam['parameters'];K=np.array([[fx,0,cx],[0,fy,cy],[0,0,1.]])
    xy=cv2.undistortPointsIter(pts[:,None],K,np.array(dist),None,None,(cv2.TERM_CRITERIA_EPS|cv2.TERM_CRITERIA_MAX_ITER,50,1e-10)).reshape(-1,2)
    D=np.c_[xy,np.ones(len(xy))]@np.asarray(cam['R']);orig=np.broadcast_to(cam['centre'],D.shape)
    return np.ascontiguousarray(np.c_[orig,D],'f4'),D

def mesh_render(c,rec,projection):
    method='prior' if c['id'].startswith(('c1','c2')) else 'mvs';path=meshpath(c,method);V,F=read_surface(path);cam=rec['camera'];F=faces(V,F,cam);scene=MeshScene(V,F);W,H=cam['output_size_px']
    refpath=O/'reference'/c['site']/'dense.npz';ref=loadz(refpath);tree=cKDTree(ref['xyz']);cy=Cylinder(ref['xyz'])
    with (R/'docs/experiments/phd/main_release_v1/tables/stage0/tau_values.csv').open() as f:tr=next(x for x in csv.DictReader(f) if x['site']==c['site'] and x['prior']==c['prior'])
    ids=np.full((H,W),-1,'i4');light=np.zeros((H,W),'f4');signed=np.full((H,W),np.nan,'f4');tau=np.full((H,W),np.nan,'f4')
    for y in range(0,H,100):
        rr,d=rays(cam,y,min(H,y+100));hit=scene.sc.cast_rays(scene.o3d.core.Tensor(rr));depth=hit['t_hit'].numpy();good=np.isfinite(depth);fi=hit['primitive_ids'].numpy().astype('i8');fi[~good]=-1
        n=hit['primitive_normals'].numpy();unit=d/np.linalg.norm(d,axis=1)[:,None];l=.35+.65*abs((n*unit).sum(1));h=min(H,y+100)-y
        ids[y:y+h]=fi.reshape(h,W);light[y:y+h]=l.reshape(h,W)
        if good.any():
            points=rr[good,:3].astype(float)+depth[good,None]*rr[good,3:].astype(float);nn=n[good].astype(float);nn/=np.linalg.norm(nn,axis=1)[:,None]
            near=tree.query(points,workers=2)[1];rn=ref['normal'][near].copy()
            if c['prior']=='ALS':rn[rn[:,2]<0]*=-1
            nn*=np.where((nn*rn).sum(1)<0,-1,1)[:,None];wall=ref['wall'][near] if c['prior']=='LoD2' else np.zeros(len(near),bool)
            measured,_=cy.query(points,nn,np.where(wall,5.,10.),float(ref['radius']))
            sv=signed[y:y+h].reshape(-1);tv=tau[y:y+h].reshape(-1);sv[good]=-measured;tv[good]=np.where(wall,float(tr['wall_tau_m']),float(tr['roof_tau_m']))
        if y%500==0:print('ADD4_PIXEL_DISTANCE',c['id'],y,H,flush=True)
    cy.close();del scene;gc.collect();good=ids>=0;far=good&np.isfinite(signed)&(abs(signed)>tau)
    gray=np.full((H,W,3),255,'u1');gray[good]=np.rint(207*light[good,None]).astype('u1');dist=np.full((H,W,3),255,'u1')
    red=np.array([216,55,48]);blue=np.array([42,120,214]);t=np.minimum(abs(signed[far]),1)[:,None]
    dist[far]=np.rint(255*(1-t)+np.where((signed[far]>0)[:,None],red,blue)*t).astype('u1');dist[good&~np.isfinite(signed)]=[140,149,163]
    base={k:projection[k] for k in ['A_px','Aprime_px','box_corners_px','line_polyline_px','line_visibility']};base['line_draw_mask']=projection.get('line_draw_mask');source=[path,refpath,AW/'cases'/f"{c['id']}.json",Path(__file__).with_name('add4_viewclip.py')]
    for tag,arr in [('wrong_gray',gray),('wrong_dist',dist)]:
        im=Image.fromarray(arr);draw_section(im,np.array(base['line_polyline_px']),np.array(base['line_visibility'][:-1])&np.array(base['line_visibility'][1:]),base['line_draw_mask'])
        savepng(im,AF/f"{c['id']}_{tag}.png",dict(case=c['id'],panel=tag,method=method,camera=cam,**base,
            geometry_render='exact rays through shared camera; complete original triangles; explicit camera.display_clip when present; no geometry repair',lighting=AC['missing_definitions']['lighting'],
            distance_color_rule='each visible pixel surface point along its oriented triangle normal to dense reference cylinder; signed result-minus-reference, white within tau, saturated at abs 1m; no mean',
            distance_sampling='visible_pixel_surface_point',distance_visual_only=True,visual_1m_euclidean_exclusion=False,scoring_definition_unchanged=True,radius_m=float(ref['radius']),visible_faces=len(np.unique(ids[good])),visible_pixels=int(good.sum()),pixels_no_reference_hit=int((good&~np.isfinite(signed)).sum()),
            color_no_reference_hit='#8C95A3',GT_triangulated=False),source)
    savez(AW/'renders'/f"{c['id']}_pixel_distance.npz",face_id=ids,signed_result_minus_reference_m=signed,tau=tau)
    print('ADD4_WRONG_RENDER',c['id'],int(good.sum()),flush=True)

def truth(c,rec,projection):
    cam=rec['camera'];W,H=cam['output_size_px'];p=O/'reference'/c['site']/'dense.npz';z=loadz(p);P=z['xyz'];N=z['normal'];uv,depth=camera_projection(P,cam)
    good=point_mask(P,cam)&np.isfinite(uv).all(1)&(depth>0)&(uv[:,0]>=0)&(uv[:,0]<W)&(uv[:,1]>=0)&(uv[:,1]<H);idx=np.flatnonzero(good);q=np.floor(uv[idx]).astype(int);pix=q[:,1]*W+q[:,0];order=np.argsort(depth[idx],kind='stable');_,ii=np.unique(pix[order],return_index=True);winner=idx[order[ii]];winpix=pix[order[ii]]
    look=np.array(cam['centre'])-P[winner];look/=np.linalg.norm(look,axis=1)[:,None];intensity=np.rint(207*(.35+.65*abs((N[winner]*look).sum(1)))).astype('u1')
    raw=np.full(H*W,255,'u1');occupied=np.zeros(H*W,bool);raw[winpix]=intensity;occupied[winpix]=True;raw=raw.reshape(H,W);occupied=occupied.reshape(H,W)
    dist,nearest=distance_transform_edt(~occupied,return_indices=True);fill=(~occupied)&(dist<=1.5);raw[fill]=raw[tuple(nearest[:,fill])]
    im=Image.fromarray(np.repeat(raw[:,:,None],3,axis=2));base={k:projection[k] for k in ['A_px','Aprime_px','box_corners_px','line_polyline_px','line_visibility']};base['line_draw_mask']=projection.get('line_draw_mask');draw_section(im,np.array(base['line_polyline_px']),np.array(base['line_visibility'][:-1])&np.array(base['line_visibility'][1:]),base['line_draw_mask'])
    savepng(im,AF/f"{c['id']}_truth_gray.png",dict(case=c['id'],panel='truth_gray',camera=cam,**base,
        geometry_render='z-buffered original reference points with AXES71 PCA normal shading; 1.5 output-pixel disc footprint',
        reference_surface_status='확인 불가: existing reference mesh unavailable; point rendering provided',GT_triangulated=False,lighting=AC['missing_definitions']['lighting'],reference_points_in_view=len(idx),occupied_pixels=int(occupied.sum())),[p,AW/'cases'/f"{c['id']}.json",Path(__file__).with_name('add4_viewclip.py')])
    print('ADD4_TRUTH_RENDER',c['id'],len(idx),flush=True)

if __name__=='__main__':
    c=case(sys.argv[1]);rec=getcase(c);projection=json.loads((AW/'cameras'/f"{c['id']}_projection.json").read_text());mesh_render(c,rec,projection);gc.collect();truth(c,rec,projection)
