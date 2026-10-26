from common import *
from photos import *
from PIL import ImageOps
def save(name,im,rec):
    p=DOC/'figures'/f'figS_e_aim_{name}.png';scale=max(1080/im.width,600/im.height);cw,ch=1080/scale,600/scale
    rec['final_fit_box_after_rotation_px']=[(im.width-cw)/2,(im.height-ch)/2,(im.width+cw)/2,(im.height+ch)/2]
    ImageOps.fit(im,(1080,600),method=Image.Resampling.LANCZOS).save(p);dump(p.with_suffix('.json'),dict(task_id='PHD-SLIDE-PHOTO-v1',scientific_verdict=None,**rec))
def main():
    config();row=load(DOC/'figures/task0_specular_candidates.json')['selected'];assert row
    im,p=crop_native(row['photos'][0]['view'],np.array(row['gt_representative']),aspect=1/1.8 if not row['roof'] else 1.8,pad=.30);im=outlined(im,p['polygon_px'])
    if not row['roof']:im=im.transpose(Image.Transpose.ROTATE_90);p['display_rotation_deg']=90
    save('keep',im,dict(photo=p,component_id=row['component_id']))
    rec=load(REPO/'docs/experiments/phd/main_regionfig_v1/tables/영역예시_보정_숫자.json')['examples'][0];ex=load(REPO/'configs/phd/main_regionfig_v1/regionfig_v1.json')['examples'][0]
    with np.load(U/'patch_values/B173nb_b10__ALS__R1.5.npz') as z:
        C=z['centre'];lo=np.minimum(ex['start_xy'],ex['end_xy'])-6;hi=np.maximum(ex['start_xy'],ex['end_xy'])+6
        mask=z['in_eval']&np.isin(z['cell'],[1,2])&np.isfinite(z['gt_p'])&np.all((C[:,:2]>=lo)&(C[:,:2]<=hi),axis=1);ix=np.flatnonzero(mask);X=C[ix]+z['normal'][ix]*z['gt_p'][ix,None]
    view=rec['photo']['stem'];im,p=crop_native(view,X,aspect=1.8,pad=.2);save('correct',outlined(im,p['polygon_px']),dict(photo=p,source='REGIONFIG-v1 example a fixed correction patches',patch_indices=ix))
    p=load(PAY/'c_repr_photo.json');sel=load(PAY/'selection_c_repr.json');z=np.load(U/'patch_values/B0_b10__LoD2__R1.5.npz');ix=np.array(sel['patch_indices']);X=z['centre'][ix]+z['normal'][ix]*z['gt_p'][ix,None]
    im,p=crop_native(p['view'],X,aspect=1.8,pad=.2);save('refine',outlined(im,p['polygon_px']),dict(photo=p,face=sel['face']))
    # Fixed wall 53; identify what occludes its projected middle in a nadir input.
    site='B173nb_b10';unit=np.load(S0/'s61/box'/site/'LoD2/units.npz');surf=unit['surf_ext'][unit['loc_surface']];ix=np.flatnonzero(surf==53);wall=unit['loc_center'][ix]
    poses,_=models();names=[n for n in load(S0/'fork_inputs/s61'/site/'split.json')['train'] if G.tilt(poses[Path(n).stem])<=20]
    best,_=choose_native(wall,names,oblique=False);view=best['view']
    from task0_scan import cameras_depth
    _,cam=cameras_depth();uv,d=G.project(wall,poses[view],cam);ij=np.floor(uv).astype(int);inside=(d>0)&(ij[:,0]>=0)&(ij[:,0]<1024)&(ij[:,1]>=0)&(ij[:,1]<741)
    ex=S0/'s61/export'/site/'LoD2';lm=np.load(ex/'locmap'/f'{view}.npy');pd=np.load(ex/'prior'/f'{view}.npy');jj=lm[ij[inside,1],ij[inside,0]];near=pd[ij[inside,1],ij[inside,0]];occluded=(jj>=0)&(near<d[inside]-.5);other=jj[occluded].astype(int);faces=sorted(set(surf[other])-{53})
    occluder=unit['loc_center'][np.isin(surf,faces)] if faces else np.empty((0,3));X=np.concatenate([wall,occluder]) if len(occluder) else wall
    # No nadir training photo contains 95% of wall+roof; retain the fixed input camera.
    # Review revision changes orientation and crop only, with incomplete coverage recorded.
    im,p=crop_native(view,X,aspect=1/1.8,pad=.15);pose=p['pose'];cam=p['camera'];marked=im.convert('RGBA');layer=Image.new('RGBA',im.size);dr=ImageDraw.Draw(layer)
    for face in faces:
        poly,_=G.project(unit['loc_center'][surf==face],pose,cam);poly-=p['crop_box_px'][:2]
        try:poly=poly[ConvexHull(poly).vertices];dr.polygon([tuple(v) for v in poly],fill=(255,214,10,35))
        except Exception:pass
    # Trace the real top edge of the hidden wall; it is a locator, not visible wall texture.
    _,_,vt=np.linalg.svd(wall[:,:2]-wall[:,:2].mean(0),full_matrices=False);axis=vt[0];s=wall[:,:2]@axis;line=np.array([wall[np.argmin(s)],wall[np.argmax(s)]]);line[:,2]=wall[:,2].max();q,_=G.project(line,pose,cam);q-=p['crop_box_px'][:2];xy=[tuple(v) for v in q];width=max(8,round(im.width/1080*5));dr.line(xy,fill=(0,0,0,255),width=width+8);dr.line(xy,fill=(255,214,10,255),width=width)
    building=np.load(U/'patch_values/B173nb_b10__LoD2__R1.5.npz')['building'];owners={str(f):np.unique(building[surf==f]).tolist() for f in faces+[53]}
    p['display_rotation_deg']=90
    save('inherit',Image.alpha_composite(marked,layer).convert('RGB').transpose(Image.Transpose.ROTATE_90),dict(photo=p,wall_face=53,wall_patch_indices=ix,occluding_faces=faces,occluded_wall_fraction_initial_view=float(occluded.sum()/len(wall)),initial_occlusion_view='DJI_20241217091247_0146_D',face_building_ids=owners,occluder_identity='same building roof, not a verified neighbouring building',coverage_limitation='No nadir training photo contains 95 percent of combined wall and roof; only visible photograph extent shown',line_xyz=line,source='VISCMP-v4 V2 wall53; occlusion from frozen training prior depth and locmap; geometry and owner IDs from frozen inputs'))
    print('DRAW e',faces,flush=True)
if __name__=='__main__':main()
