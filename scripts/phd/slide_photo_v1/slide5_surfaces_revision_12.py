"""R12 source inspection and same-style building comparison."""
import argparse
import ctypes
import hashlib
import io
import os
import subprocess
import zipfile
from pathlib import Path
import numpy as np
from shapely.geometry import Polygon,Point
from matplotlib.path import Path as MPath
from matplotlib.colors import LinearSegmentedColormap, to_rgb
from PIL import Image,ImageDraw
from common import CFG,DOC,PAY,REPO,PH,RAW,W,G,geometry,load,dump,sha,now
import slide5_draft_revision_08 as R8

OUT=DOC/'revision_12';CACHE=PAY/'revision_12'
CONFIG=CFG/'slide5_surfaces_revision_12.json'
INK='#172B40';MUTED='#5B6B7C';GOLD='#C08A2B';BLUE='#2C6AA0'
PALETTE=['#E9EDF0','#DFBE88','#CF754B','#A82B3D']


def lock():
    c=load(CONFIG);s=load(c['sources_config'])['sources'].copy()
    for name in ['roof_mvs_mesh','roof_mvs_receipt','roof_footprints']:s[name]=c[name]
    s['wall_candidates']=str(DOC/'figures/task0_specular_candidates.json')
    row=load(s['wall_candidates'])['selected']
    assert row['component_id']==c['wall_candidate'] and len(row['tiles'])==1
    tile=row['tiles'][0];prior=row['prior']
    s['wall_mvs']=str(PAY/'task0/mvs_v4'/f'{tile}_{prior}.npz')
    s['wall_gt']=str(PAY/'task0/gt'/f'{tile}_{prior}.npz')
    s['wall_geometry']=str(W/'patch_values'/f'{tile}__{prior}__R1.5.npz')
    pins={k:dict(path=v,sha256=sha(v)) for k,v in s.items()}
    path=OUT/'input_lock.json'
    if path.exists():
        old=load(path);assert old['sources']==pins and old['config_sha256']==sha(CONFIG)
    else:dump(path,dict(task_id=c['task_id'],scientific_verdict=None,locked_at=now(),config_sha256=sha(CONFIG),sources=pins))
    display=CFG/'slide5_surfaces_revision_12_display_01.json'
    if display.exists():
        pin=OUT/'display_lock.json'
        if pin.exists():assert load(pin)['sha256']==sha(display)
        else:dump(pin,dict(path=display,sha256=sha(display),locked_at=now(),scientific_verdict=None))
    return c,s


def ply_maps(path):
    with open(path,'rb') as f:
        lines=[]
        while True:
            ln=f.readline().decode('ascii').strip();lines.append(ln)
            if ln=='end_header':break
        offset=f.tell()
    assert lines[1]=='format binary_little_endian 1.0'
    nv=int(next(x for x in lines if x.startswith('element vertex')).split()[-1])
    nf=int(next(x for x in lines if x.startswith('element face')).split()[-1])
    dtype=np.dtype([('x','<f8'),('y','<f8'),('z','<f8'),('red','u1'),('green','u1'),('blue','u1')])
    v=np.memmap(path,mode='r',dtype=dtype,offset=offset,shape=(nv,))
    f=np.memmap(path,mode='r',dtype=[('n','u1'),('indices','<u4',(3,))],offset=offset+nv*dtype.itemsize,shape=(nf,))
    assert path.stat().st_size==offset+nv*27+nf*13
    return v,f


def mesh_chunks(s,key,chunk=150000):
    if key=='prior':
        z=np.load(s['roof_prior_mesh']);v=z['V']+np.asarray(load(s['roof_registration'])['registration']['shift_applied']);f=z['F']
        for start in range(0,len(f),chunk):
            ids=np.arange(start,min(start+chunk,len(f)));yield v[f[ids]],ids
    else:
        v,f=ply_maps(Path(s['roof_mvs_mesh']))
        for start in range(0,len(f),chunk):
            ids=np.arange(start,min(start+chunk,len(f)));row=f[ids];assert np.all(row['n']==3)
            ix=row['indices'];tri=np.stack([v[k][ix] for k in ['x','y','z']],axis=-1)
            yield tri,ids


def prepare_roof(c,s):
    target=OUT/'geometry.json'
    if target.exists():return load(target)
    footprints=load(s['roof_footprints'])['footprints'];row=next(r for r in footprints if r['building']==c['roof_building'])
    poly=Polygon(row['ring_local']).buffer(c['roof_footprint_buffer_m']);path=MPath(np.asarray(poly.exterior.coords))
    xylo=np.array(poly.bounds[:2]);xyhi=np.array(poly.bounds[2:]);meta={}
    for key in ['prior','mvs']:
        count=0;lo=np.full(3,np.inf);hi=-lo;source=0
        with open(CACHE/f'{key}_triangles.bin','wb') as tf,open(CACHE/f'{key}_faces.bin','wb') as ix:
            for tri,ids in mesh_chunks(s,key):
                source+=len(ids);quick=np.all((tri[:,:,:2]>=xylo)&(tri[:,:,:2]<=xyhi),axis=(1,2));a=tri[quick];ii=ids[quick]
                if len(a):
                    good=path.contains_points(a[:,:,:2].reshape(-1,2)).reshape(-1,3).all(1);a=a[good];ii=ii[good]
                    if len(a):
                        np.asarray(a,'<f8').tofile(tf);np.asarray(ii,'<i8').tofile(ix);count+=len(a)
                        lo=np.minimum(lo,a.min(axis=(0,1)));hi=np.maximum(hi,a.max(axis=(0,1)))
        meta[key]=dict(source_faces=source,retained_faces=count,min_xyz=lo,max_xyz=hi,
            triangles_sha256=sha(CACHE/f'{key}_triangles.bin'),face_ids_sha256=sha(CACHE/f'{key}_faces.bin'))
        print('GEOMETRY',key,count,'of',source,'bounds',lo,hi,flush=True)
    meta.update(task_id=c['task_id'],scientific_verdict=None,config_sha256=sha(CONFIG),footprint=row,
        crop_polygon_xy=np.asarray(poly.exterior.coords),source_coordinates_preserved=True)
    dump(target,meta);return meta


def tris(key,meta):return np.memmap(CACHE/f'{key}_triangles.bin',mode='r',dtype='<f8',shape=(meta[key]['retained_faces'],3,3))


def camera(c,meta,size):
    # Retain the section-based local axes from the previously audited geometry.
    old=load(DOC/'revision_09/geometry.json')['roof'];B=np.asarray(old['basis']);origin=np.asarray(old['origin'])
    az,el=np.deg2rad([c['roof_camera']['azimuth_deg'],c['roof_camera']['elevation_deg']])
    eye=np.array([np.cos(el)*np.cos(az),np.cos(el)*np.sin(az),np.sin(el)])
    right=np.array([-np.sin(az),np.cos(az),0.]);up=np.cross(eye,right);R=np.stack([right,up,eye])@B
    lo=np.full(2,np.inf);hi=-lo
    for key in ['prior','mvs']:
        a=tris(key,meta)
        for start in range(0,len(a),150000):
            q=(a[start:start+150000].reshape(-1,3)-origin)@R.T;lo=np.minimum(lo,q[:,:2].min(0));hi=np.maximum(hi,q[:,:2].max(0))
    mid=(lo+hi)/2;scale=min((size[0]-100)/(hi[0]-lo[0]),(size[1]-120)/(hi[1]-lo[1]))
    return dict(rotation=R,origin=origin,mid=mid,bounds=[lo,hi],scale_px_per_m=scale,size=size)


def project(X,v):
    q=(np.asarray(X)-v['origin'])@np.asarray(v['rotation']).T;w,h=v['size'];scale=v['scale_px_per_m']
    return np.stack([(q[...,0]-v['mid'][0])*scale+w/2,h/2-(q[...,1]-v['mid'][1])*scale,q[...,2]],axis=-1)


def render_surface(key,c,s,meta,view):
    libpath=str(CACHE/'surface_raster_12.so')
    cpp=Path(__file__).with_name('surface_raster_12.cpp');receipt=CACHE/'raster_build.json'
    if not receipt.exists() or load(receipt)['source_sha256']!=sha(cpp):
        subprocess.run(['g++','-O3','-ffp-contract=off','-shared','-fPIC',str(cpp),'-o',libpath],check=True)
        dump(receipt,dict(source_sha256=sha(cpp),binary_sha256=sha(libpath),compiler=subprocess.check_output(['g++','--version'],text=True).splitlines()[0]))
    lib=ctypes.CDLL(libpath);lib.raster.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int64,ctypes.c_int,ctypes.c_int,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int64]
    w,h=view['size'];depth=np.full((h,w),-np.inf);rgb=np.full((h,w,3),250.,dtype=np.float32);owner=np.full((h,w),-1,np.int64)
    a=tris(key,meta);lo,hi=np.asarray(load(s['roof_scope'])['bounds_xy']);light=np.array([.25,-.4,1.]);light/=np.linalg.norm(light)
    for start in range(0,len(a),150000):
        tri=np.asarray(a[start:start+150000]);q=np.ascontiguousarray(project(tri,view));cent=tri.mean(1)
        n=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);n/=np.maximum(np.linalg.norm(n,axis=1)[:,None],1e-12)
        focus=np.all((cent[:,:2]>=lo)&(cent[:,:2]<=hi),axis=1)&(np.abs(n[:,2])>=.7)
        shade=.55+.45*np.abs(n@light);col=np.tile(to_rgb('#BFC7CC'),(len(tri),1));col[focus]=to_rgb('#D6AB65')
        col=np.ascontiguousarray(col*shade[:,None]*255,dtype=np.float32)
        lib.raster(q.ctypes.data,col.ctypes.data,len(q),w,h,depth.ctypes.data,rgb.ctypes.data,owner.ctypes.data,start)
    valid=np.isfinite(depth);response=np.zeros((h,w));support=np.zeros((h,w))
    for dy,dx in [(0,5),(0,-5),(5,0),(-5,0)]:
        other=np.roll(np.roll(depth,dy,0),dx,1);ok=valid&np.isfinite(other)
        response[ok]+=np.clip(other[ok]-depth[ok],0,1);support[ok]+=1
    shade=1-.25*response/np.maximum(support,1);rgb[valid]*=shade[valid,None]
    im=Image.fromarray(np.clip(rgb,0,255).astype('uint8'));im.save(CACHE/f'roof_{key}_surface.png')
    np.savez_compressed(CACHE/f'roof_{key}_pixels.npz',owner=owner,depth=depth)
    return im,dict(occupied_pixels=int(valid.sum()),triangles=len(a),camera=view)


def original(src,rotation=90):
    with zipfile.ZipFile(RAW) as z:raw=z.read(src['original_member'])
    assert hashlib.sha256(raw).hexdigest()==src['original_sha256']
    im=Image.open(io.BytesIO(raw)).convert('RGB')
    if rotation==90:im=im.transpose(Image.Transpose.ROTATE_90)
    return im


def photo_project(X,src,rotation=90):
    p=dict(src['pose'],R=np.asarray(src['pose']['R']),t=np.asarray(src['pose']['t']))
    uv,z=G.project(X,p,src['camera'])
    if rotation==90:uv=np.c_[uv[:,1],src['camera']['w']-uv[:,0]]
    return uv,z


def fit(im,size):
    scale=min(size[0]/im.width,size[1]/im.height);wh=tuple(round(v*scale) for v in im.size)
    out=Image.new('RGB',size,'#FAFAFA');offset=(np.array(size)-wh)//2;out.paste(im.resize(wh,Image.Resampling.LANCZOS),tuple(offset))
    return out,dict(scale_xy=np.array(wh)/im.size,offset=offset,content_size=wh,canvas_size=size)


def t(im,xy,val,size=28,col=INK,bold=False):R8.text(im,xy,val,size,col,bold)


def leader(im,point,label,label_xy,col=INK):
    d=ImageDraw.Draw(im);a=np.asarray(point);b=np.array(label_xy)*2
    d.line([tuple(a),(b[0]-12,b[1]+26)],fill='white',width=9);d.line([tuple(a),(b[0]-12,b[1]+26)],fill=col,width=3)
    d.ellipse((a[0]-9,a[1]-9,a[0]+9,a[1]+9),fill=col,outline='white',width=3)
    box=d.textbbox(tuple(b),label,font=R8.font(27,True),anchor='lt');d.rectangle((box[0]-8,box[1]-5,box[2]+8,box[3]+5),fill='white')
    t(im,label_xy,label,27,col,True)


def save(im,name):
    (OUT/'figures').mkdir(exist_ok=True);(OUT/'previews').mkdir(exist_ok=True)
    im.save(OUT/'figures'/f'{name}.png');im.resize((1920,1080),Image.Resampling.LANCZOS).save(OUT/'previews'/f'{name}.png')


def roof_figure(c,s,meta):
    size=(1240,1330);v=camera(c,meta,size);panels={};stats={}
    for key in ['prior','mvs']:panels[key],stats[key]=render_surface(key,c,s,meta,v)
    im=Image.new('RGB',(3840,2160),'white');t(im,(60,34),'5쪽 시안 · 사전 정보의 시간 차이',27,MUTED)
    t(im,(60,89),'같은 건물인데, 지붕의 높이가 다르다',43,INK,True)
    t(im,(60,177),'현재 사진',30,INK,True);t(im,(600,177),'사전 정보 · 항공 LiDAR',30,GOLD,True);t(im,(1250,177),'영상으로 복원한 표면 · MVS',30,BLUE,True)
    src=load(s['roof_photo'])['photo']['source']['photo'];ph=original(src);ph,fitmeta=fit(ph,(980,1330));im.paste(ph,(120,450))
    im.paste(panels['prior'],(1180,450));im.paste(panels['mvs'],(2480,450))
    ex=load(s['roof_example'])['examples'][0];bins=np.array(ex['bin_centres_m']);H=np.array(ex['heights_model_m']);k=int(np.argmin(abs(bins-ex['length_m']/2)))
    unit=np.array(ex['end_xy'])-ex['start_xy'];unit/=np.linalg.norm(unit);xy=np.array(ex['start_xy'])+bins[k]*unit
    anchors={key:np.array([*xy,H[k,j]]) for key,j in [('prior',0),('mvs',1)]}
    uv,_=photo_project(np.array([[*xy,H[k,2]]]),src);point=uv[0]*fitmeta['scale_xy']+fitmeta['offset']+[120,450]
    leader(im,point,'비교 지붕',(86,710))
    reference=np.array([*xy,H[k,2]]);p_ref=project(reference[None],v)[0,:2];d=ImageDraw.Draw(im)
    guide_y=float(p_ref[1]+450)
    for key,x in [('prior',1180),('mvs',2480)]:
        pt=project(anchors[key][None],v)[0,:2]+[x,450]
        leader(im,pt,'사전 지붕' if key=='prior' else '영상 지붕',((pt[0]-230)/2,(pt[1]-155)/2),GOLD if key=='prior' else BLUE)
        # The same one-location datum in both panels; not a reconstructed contour.
        px=p_ref[0]+x
        for xx in np.arange(px-150,px+210,22):
            d.line((xx,guide_y,xx+12,guide_y),fill='white',width=8);d.line((xx,guide_y,xx+12,guide_y),fill=INK,width=3)
        d.ellipse((px-8,guide_y-8,px+8,guide_y+8),fill=INK,outline='white',width=3)
        t(im,((px+220)/2,(guide_y-20)/2),'현재 참조 높이',26,INK,True)
        if key=='prior':
            arrow_x=pt[0]+100;top=min(pt[1],guide_y);bottom=max(pt[1],guide_y)
            d.line((pt[0],pt[1],arrow_x+12,pt[1]),fill=GOLD,width=4)
            d.line((arrow_x,top,arrow_x,bottom),fill='white',width=10);d.line((arrow_x,top,arrow_x,bottom),fill=INK,width=4)
            for y,sign in [(top,1),(bottom,-1)]:d.polygon([(arrow_x,y),(arrow_x-10,y+sign*18),(arrow_x+10,y+sign*18)],fill=INK)
    t(im,(60,936),'비교 구역의 높이 차 중앙값',27,MUTED);t(im,(60,981),'사전 − 참조  +4.56 m',34,GOLD,True)
    t(im,(600,940),'같은 시점 · 같은 축척 · 같은 표면 표현',29,INK,True)
    t(im,(600,991),'황토색은 같은 비교 구역  |  참조: 현재 드론 LiDAR',26,MUTED)
    save(im,'slide5_roof_surfaces')
    dump(OUT/'roof.json',dict(task_id=c['task_id'],scientific_verdict=None,panels=stats,photo_source=src,photo_fit=fitmeta,
        midpoint_bin=k,anchors=anchors,reference_anchor=reference,reference_guide_canvas_y_px=guide_y,local_prior_minus_reference_m=float(H[k,0]-H[k,2]),
        reference_value_cm=ex['values']['prior_minus_gt_cm'],value_scope='Original correction-patch median from REGIONFIG; not the local arrow length, whole-building mean or MVS-mesh distance.'))


def wall_prepare(c,s):
    row=load(s['wall_candidates'])['selected'];src=next(x for x in row['photos'] if x['kind']=='best')
    geo=geometry(row['tiles'][0],row['prior']);m=np.load(s['wall_mvs']);g=np.load(s['wall_gt']);idx=m['patch_index']
    wanted=np.isin(geo['patch_id'][idx],row['patch_ids']);vi=int(np.flatnonzero(m['view_names']==src['view'])[0]);pv=m['per_view_signed'][:,vi]
    selected=np.flatnonzero(wanted&np.isfinite(pv));ix=idx[selected]
    X=g['representative'][ix];A=geo['tangent1'][ix];B=geo['tangent2'][ix]
    squares=np.stack([X+a*A+b*B for a,b in [(-.125,-.125),(.125,-.125),(.125,.125),(-.125,.125)]],axis=1)
    uv,z=photo_project(squares.reshape(-1,3),src);uv=uv.reshape(-1,4,2);z=z.reshape(-1,4)
    assert np.all(z>0)
    photo=original(src);centres,_=photo_project(np.array(row['gt_representative']),src);lo=centres.min(0);hi=centres.max(0);centre=(lo+hi)/2
    extent=(hi-lo)*(1+2*c['wall_photo_crop']['component_padding_fraction']);aspect=c['wall_photo_crop']['aspect'];extent=np.maximum(extent,[extent[1]*aspect,extent[0]/aspect]);extent=np.minimum(extent,photo.size)
    extent[1]=min(photo.height,extent[0]/aspect)
    lo=np.maximum(0,np.minimum(centre-extent/2,np.array(photo.size)-extent));box=np.r_[np.floor(lo),np.ceil(lo+extent)].astype(int);ph=photo.crop(tuple(box))
    ph,fitmeta=fit(ph,(1740,1200));q=(uv-box[:2])*fitmeta['scale_xy']+fitmeta['offset']
    values={'prior':g['prior_abs'][ix]*100,'mvs':m['mvs_abs'][selected]*100}
    np.savez_compressed(CACHE/'wall_support.npz',patch_indices=ix,mvs_rows=selected,patch_ids=geo['patch_id'][ix],squares_xyz=squares,squares_px=q,
        prior_cm=values['prior'],mvs_cm=values['mvs'],per_view_signed_m=pv[selected])
    stats=dict(task_id=c['task_id'],scientific_verdict=None,component=row['component_id'],building=row['building'],photo=src,
        crop=box,photo_fit=fitmeta,source_component_patches=len(row['patch_ids']),shown_patches=len(ix),visible_share=len(ix)/len(row['patch_ids']),
        view_index=vi,median_cm={key:float(np.median(a)) for key,a in values.items()},source_component_median_cm={'prior':row['prior_abs_median_m']*100,'mvs':row['mvs_abs_median_m']*100},
        values='Existing absolute wall-normal distance medians; MVS aggregates valid training views. Figure medians use exactly the shown patch subset.',support_sha256=sha(CACHE/'wall_support.npz'))
    dump(OUT/'wall.json',stats);return ph,q,values,stats


def wall_figure(c,s):
    photo,q,values,stats=wall_prepare(c,s);cmap=LinearSegmentedColormap.from_list('wall_distance',PALETTE)
    im=Image.new('RGB',(3840,2160),'white');t(im,(60,34),'5쪽 시안 · 영상 깊이의 위치 차이',27,MUTED)
    t(im,(60,89),'같은 벽인데, 영상 깊이는 벽면에서 더 벗어난다',43,INK,True)
    for key,x,label,col in [('prior',60,'사전 정보 · LoD2',GOLD),('mvs',990,'영상 깊이 · MVS',BLUE)]:
        t(im,(x,186),label,32,col,True);base=photo.convert('RGBA');lay=Image.new('RGBA',base.size);d=ImageDraw.Draw(lay)
        rgba=(cmap(np.clip(values[key]/60,0,1))*255).astype('uint8');rgba[:,3]=209
        for pts,colour in zip(q,rgba):d.polygon([tuple(a) for a in pts],fill=tuple(int(v) for v in colour))
        merged=Image.alpha_composite(base,lay).convert('RGB');im.paste(merged,(x*2,474));merged.save(CACHE/f'wall_{key}_photo.png')
        t(im,(x,866),'표시한 벽에서 참조와의 거리 중앙값',26,MUTED)
        t(im,(x,911),f'{stats["median_cm"][key]:.1f} cm',39,col,True)
    grad=np.tile(np.arange(800)/799,(28,1));bar=Image.fromarray((cmap(grad)*255).astype('uint8')).convert('RGB');im.paste(bar,(120,2022))
    for value in [0,20,40,60]:t(im,(60+value/60*400,1030),str(value)+('+' if value==60 else ''),26,MUTED)
    t(im,(500,1005),'cm  ·  붉을수록 참조 벽면과 멀다',27,INK,True)
    t(im,(1070,1005),'현재 드론 LiDAR 참조 · 유효한 25 cm 칸만 표시',26,MUTED)
    save(im,'slide5_wall_distances')


def main():
    c,s=lock();meta=prepare_roof(c,s);roof_figure(c,s,meta);wall_figure(c,s)
    Image.open(OUT/'figures/slide5_roof_surfaces.png').crop((1180,330,3720,2080)).save(OUT/'figures/roof_pair_for_slide.png')
    Image.open(OUT/'figures/slide5_wall_distances.png').crop((120,350,3720,2130)).save(OUT/'figures/wall_pair_for_slide.png')
    dump(OUT/'render.json',dict(task_id=c['task_id'],scientific_verdict=None,rendered_at=now(),config_sha256=sha(CONFIG),
        script_sha256=sha(Path(__file__)),raster_sha256=sha(Path(__file__).with_name('surface_raster_12.cpp')),
        base_commit=os.environ.get('TASK_BASE_COMMIT'),canvas=[3840,2160],preview=[1920,1080]))
    print('R12 RENDER COMPLETE',flush=True)


def qa(round_name):
    out=OUT/'qa'/round_name;out.mkdir(parents=True,exist_ok=True)
    for name in ['slide5_roof_surfaces','slide5_wall_distances']:
        im=Image.open(OUT/'previews'/f'{name}.png').convert('RGB');im.save(out/f'{name}_full.png')
        d=ImageDraw.Draw(im);d.rectangle((0,0,1919,160),fill='white')
        if 'roof' in name:d.rectangle((0,905,565,1079),fill='white')
        else:d.rectangle((0,842,1919,980),fill='white')
        im.save(out/f'{name}_blind.png')

def inspect():
    import importlib.util
    print('MODULES',{n:importlib.util.find_spec(n) is not None for n in ['numba','open3d','plyfile','cv2']})
    s=load(CFG/'slide5_3d_revision_09.json')['sources']
    from pathlib import Path
    folder=Path(s['roof_prior_mesh']).parent
    e=load(s['roof_example'])['examples'][0];mid=(np.asarray(e['start_xy'])+e['end_xy'])/2
    print('SECTION',mid)
    for row in load(folder/'footprints.json')['footprints']:
        p=Polygon(row['ring_local'])
        if p.buffer(1).contains(Point(mid)):print('BUILDING',row['building'],'bounds',p.bounds,'area',p.area)
    for name in ['als_mesh.npz','lod2_mesh.npz','als_store.npz','lod2_store.npz']:
        with np.load(folder/name) as z:print(name,{k:(z[k].shape,str(z[k].dtype)) for k in z.files})
    z=np.load(folder/'als_mesh.npz');C=z['V'][z['F']].mean(1);lo,hi=load(s['roof_scope'])['bounds_xy'];sel=np.all((C[:,:2]>=lo)&(C[:,:2]<=hi),axis=1)&(np.abs(z['tri_normal'][:,2])>.7)
    area=z['tri_area'];sid=z['tri_surface'];ids=np.unique(sid[sel]);rank=sorted(ids,key=lambda i:-area[sel&(sid==i)].sum())
    print('ROOF SURFACES',[(int(i),float(area[sel&(sid==i)].sum()),int((sid==i).sum()),C[sid==i].min(0).tolist(),C[sid==i].max(0).tolist()) for i in rank[:6]])
    for name in ['als_surfaces.json','lod2_surfaces.json','range.json']:
        a=load(folder/name);print(name,'keys',list(a)[:12]);print(str(a)[:600])
    row=load(DOC/'figures/task0_specular_candidates.json')['selected']
    print('WALL', {k:v for k,v in row.items() if k not in ['centre','normal','gt_representative','patch_ids','photo_views'] and not isinstance(v,(dict,list))})
    print('WALL KEYS',list(row),'tiles',row['tiles'],'patches',len(row['patch_ids']))
    print('PHOTOS',row.get('photos'))
    with np.load(PAY/'task0/selected_clouds.npz') as z:print('wall clouds',{k:z[k].shape for k in z.files})
    for tile in row['tiles']:
        for kind in ['mvs_v4','gt']:
            p=PAY/'task0'/kind/f'{tile}_{row["prior"]}.npz'
            with np.load(p) as z:print(kind,tile,{k:(z[k].shape,str(z[k].dtype)) for k in z.files})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--inspect',action='store_true');p.add_argument('--qa');a=p.parse_args()
    if a.inspect:inspect()
    elif a.qa:qa(a.qa)
    else:main()
