"""R10: source-backed building context, paired geometry and normal-distance inset."""
import argparse
import hashlib
import io
import os
import platform
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import maximum_filter, gaussian_filter
from matplotlib.colors import to_rgb

from common import CFG, DOC, PAY, REPO, RAW, G, load, dump, sha, now
import slide5_draft_revision_08 as R8
import slide5_3d_revision_09 as R9

OUT=DOC/'revision_10'; CACHE=PAY/'revision_10'; CONFIG=CFG/'slide5_context_revision_10.json'
INK='#172B40';MUTED='#5B6B7C';GOLD='#C08A2B';BLUE='#2C6AA0';REF='#3A4A5E'


def inspect():
    c=load(CFG/'slide5_3d_revision_09.json')
    for key in ['roof','wall']:
        pm=load(c['sources'][key+'_photo'])['photo'];p=pm['source']['photo']
        with zipfile.ZipFile(RAW) as z: raw=z.read(p['original_member'])
        assert hashlib.sha256(raw).hexdigest()==p['original_sha256']
        im=Image.open(io.BytesIO(raw)).convert('RGB')
        if pm['display_rotation_deg']==90:im=im.transpose(Image.Transpose.ROTATE_90)
        im.thumbnail((1200,900));im.save(CACHE/f'inspect_{key}_native.png')
        print(key,{k:pm.get(k) for k in ['crop_in_rotated_native_px','display_rotation_deg']},p['view'])
    z=np.load(c['sources']['roof_prior_mesh'])
    print('ALS',len(z['V']),z['V'].min(0),z['V'].max(0),z.files)
    for key in ['roof_mvs','roof_reference']:
        a=np.load(c['sources'][key],mmap_mode='r');print(key,a.shape,a.min(0),a.max(0))


def lock():
    c=load(CONFIG);s=load(c['frozen_sources_config'])['sources'];p=OUT/'input_lock.json'
    sources={k:dict(path=v,sha256=sha(v)) for k,v in s.items()}
    if p.exists():
        old=load(p);assert old['sources']==sources and old['config_sha256']==sha(CONFIG)
    else:dump(p,dict(task_id=c['task_id'],scientific_verdict=None,locked_at=now(),config_sha256=sha(CONFIG),sources=sources))
    amendment=CFG/'slide5_context_revision_10_display_01.json';amendlock=OUT/'display_lock.json'
    if amendlock.exists():assert load(amendlock)['sha256']==sha(amendment)
    else:dump(amendlock,dict(path=amendment,sha256=sha(amendment),locked_at=now(),scientific_verdict=None))
    amendment=CFG/'slide5_context_revision_10_display_02.json';amendlock=OUT/'display_lock_02.json'
    if amendlock.exists():assert load(amendlock)['sha256']==sha(amendment)
    else:dump(amendlock,dict(path=amendment,sha256=sha(amendment),locked_at=now(),scientific_verdict=None))
    return c,s


def prepare(c,s):
    if (OUT/'geometry.json').exists():
        m=load(OUT/'geometry.json');assert m['config_sha256']==sha(CONFIG) and m['geometry_sha256']==sha(CACHE/'geometry.npz')
        return dict(np.load(CACHE/'geometry.npz')),m
    scope=load(DOC/'revision_09/geometry.json')['roof']
    corelo=np.asarray(scope['crop_min_xyz']);corehi=np.asarray(scope['crop_max_xyz'])
    lo=corelo-c['roof_context_padding_xyz_m'];hi=corehi+c['roof_context_padding_xyz_m']
    arrays={};counts={};shift=np.asarray(load(s['roof_registration'])['registration']['shift_applied'])
    for key in ['prior','mvs','gt']:
        if key=='prior':
            raw=np.load(s['roof_prior_mesh'])['V']+shift
            ids=np.flatnonzero(np.all((raw>=lo)&(raw<=hi),axis=1));points=raw[ids];total=len(raw)
        else:points,ids,total=R9.crop_points(s['roof_mvs' if key=='mvs' else 'roof_reference'],lo,hi)
        shown,ix=R9.voxel(points,c['roof_display_voxel_m'])
        arrays['roof_'+key]=shown;arrays['roof_'+key+'_ids']=ids[ix]
        arrays['roof_'+key+'_core']=np.all((shown>=corelo)&(shown<=corehi),axis=1)
        counts[key]=dict(source=total,in_context=len(points),shown=len(shown),highlighted=int(arrays['roof_'+key+'_core'].sum()))
    old=np.load(PAY/'revision_09/geometry.npz');wall=load(DOC/'revision_09/geometry.json')['wall']
    WB=np.asarray(wall['basis']);WC=np.asarray(wall['origin'])
    for key in ['prior','mvs','gt']:
        arrays['wall_'+key]=old['wall_'+key]@WB+WC
        arrays['wall_'+key+'_ids']=old['wall_'+key+'_source_ids']
    ex=load(s['roof_example'])['examples'][0]
    a=np.asarray(ex['start_xy']);b=np.asarray(ex['end_xy']);u=(b-a)/np.linalg.norm(b-a)
    xy=a+np.asarray(ex['bin_centres_m'])[:,None]*u
    H=np.asarray(ex['heights_model_m']);ok=np.isfinite(H[:,2])
    arrays['roof_reference_section']=np.c_[xy[ok],H[ok,2]]
    np.savez_compressed(CACHE/'geometry.npz',**arrays)
    m=dict(task_id=c['task_id'],scientific_verdict=None,config_sha256=sha(CONFIG),geometry_sha256=sha(CACHE/'geometry.npz'),
           context_min_xyz=lo,context_max_xyz=hi,highlight_min_xyz=corelo,highlight_max_xyz=corehi,roof_counts=counts,
           roof_registration_shift=shift,roof_basis=scope['basis'],roof_origin=scope['origin'],wall_basis=wall['basis'],wall_origin=wall['origin'],
           wall_counts={k:len(arrays['wall_'+k]) for k in ['prior','mvs','gt']},reference_section='Unchanged source binned reference medians at their original XY; a section guide, not a fitted surface')
    dump(OUT/'geometry.json',m);return arrays,m


def text(im,xy,value,size=26,col=INK,bold=False,anchor='lt',blind=False):
    if not blind:R8.text(im,xy,value,size,col,bold,anchor)


def photo(key,c,s,size):
    pm=load(s[key+'_photo'])['photo'];src=pm['source']['photo']
    with zipfile.ZipFile(RAW) as z:raw=z.read(src['original_member'])
    assert hashlib.sha256(raw).hexdigest()==src['original_sha256']
    native=Image.open(io.BytesIO(raw)).convert('RGB')
    if pm['display_rotation_deg']==90:native=native.transpose(Image.Transpose.ROTATE_90)
    crop=np.asarray(pm['crop_in_rotated_native_px'],float);centre=(crop[:2]+crop[2:])/2
    extent=np.minimum((crop[2:]-crop[:2])*c['photo_crop_expansion'],native.size)
    left=np.maximum(0,np.minimum(centre-extent/2,np.asarray(native.size)-extent))
    box=np.r_[np.floor(left),np.ceil(left+extent)].astype(int)
    # Fit without aspect distortion; a narrow unused margin is allowed.
    im=native.crop(tuple(box));factor=min(size[0]/im.width,size[1]/im.height)
    im=im.resize((round(im.width*factor),round(im.height*factor)),Image.Resampling.LANCZOS)
    canvas=Image.new('RGB',size,'white');off=(np.asarray(size)-im.size)//2;canvas.paste(im,tuple(off))
    X=np.asarray(pm['section_line_xyz'] if key=='roof' else pm['section_centre_line_xyz'])
    pose=dict(src['pose'],R=np.asarray(src['pose']['R']),t=np.asarray(src['pose']['t']))
    uv,z=G.project(X,pose,src['camera'])
    if pm['display_rotation_deg']==90:uv=np.c_[uv[:,1],src['camera']['w']-uv[:,0]]
    exact=(uv-box[:2])*(np.asarray(im.size)/(box[2:]-box[:2]))+off
    d=ImageDraw.Draw(canvas);hidden=pm.get('section_hidden_segments',[False]*(len(exact)-1))
    for j,(a,b) in enumerate(zip(exact[:-1],exact[1:])):
        if hidden[j] and j%4>=2:continue
        d.line([tuple(a),tuple(b)],fill=INK,width=8);d.line([tuple(a),tuple(b)],fill='#FFD60A',width=4)
    for index,name in [(0,'A'),(-1,'B')]:
        q=exact[index];d.ellipse((q[0]-7,q[1]-7,q[0]+7,q[1]+7),fill='#FFD60A',outline=INK,width=2)
        offset=np.array([-20,18] if key=='roof' and index==0 else [-20,-65])
        pos=np.clip(q+offset,[10,10],np.asarray(size)-[75,75]);f=R8.font(25,True)
        bb=d.textbbox(tuple(pos),name,font=f,anchor='lt');d.rectangle((bb[0]-6,bb[1]-4,bb[2]+6,bb[3]+4),fill='white')
        d.text(tuple(pos),name,font=f,fill=INK,anchor='lt')
    return canvas,dict(source_member=src['original_member'],source_sha256=src['original_sha256'],crop=box,output_size=size,
          photo_content_size=im.size,content_offset=off,section_line_xyz=X,section_line_px=exact,rotation=pm['display_rotation_deg'],
          projection='Original calibrated native camera; exact existing section; yellow line is not a material mask')


def camera(data,meta,az,el,size):
    B=np.asarray(meta['roof_basis']);origin=np.asarray(meta['roof_origin'])
    az,el=np.deg2rad([az,el]);eye=np.array([np.cos(el)*np.cos(az),np.cos(el)*np.sin(az),np.sin(el)])
    right=np.array([-np.sin(az),np.cos(az),0.]);up=np.cross(eye,right)
    R=np.stack([right,up,eye])@B;assert np.allclose(R@R.T,np.eye(3)) and np.isclose(np.linalg.det(R),1)
    pts=np.concatenate([data['roof_'+k] for k in ['prior','mvs','gt']]);q=(pts-origin)@R.T
    lo=q[:,:2].min(0);hi=q[:,:2].max(0);mid=(lo+hi)/2
    scale=min((size[0]-70)/(hi[0]-lo[0]),(size[1]-90)/(hi[1]-lo[1]))
    def project(X):
        q=(np.asarray(X)-origin)@R.T
        return np.c_[(q[...,0]-mid[0])*scale+size[0]/2, size[1]/2-(q[...,1]-mid[1])*scale,q[...,2]]
    return project,dict(rotation=R,origin=origin,scale_px_per_m=scale,projected_bounds=[lo,hi],mid=mid,canvas=size,azimuth_deg=float(np.rad2deg(az)),elevation_deg=float(np.rad2deg(el)))


def roof_panel(data,meta,key,project,view,blind=False):
    w,h=view['canvas'];reference=data['roof_gt'];source=data['roof_'+key][data['roof_'+key+'_core']]
    X=np.concatenate([reference,source]);is_source=np.r_[np.zeros(len(reference),bool),np.ones(len(source),bool)];q=project(X)
    x=np.rint(q[:,0]).astype(int);y=np.rint(q[:,1]).astype(int)
    pixels=[];depths=[];indices=[]
    # Identical 5x5 point footprint for both sources and the shared context.
    for dy,dx in [(a,b) for a in range(-2,3) for b in range(-2,3)]:
        xx=x+dx;yy=y+dy;ok=(xx>=0)&(xx<w)&(yy>=0)&(yy<h)
        pixels.append(yy[ok]*w+xx[ok]);depths.append(q[ok,2]);indices.append(np.flatnonzero(ok))
    pix=np.concatenate(pixels);dep=np.concatenate(depths);ix=np.concatenate(indices)
    order=np.lexsort((-dep,pix));p=pix[order];first=np.r_[True,p[1:]!=p[:-1]];chosen=order[first]
    d=np.full(w*h,np.nan);d[pix[chosen]]=dep[chosen]
    owner=np.full(w*h,-1,int);owner[pix[chosen]]=ix[chosen];owner=owner.reshape(h,w);d=d.reshape(h,w)
    valid=owner>=0;rgba=np.ones((h,w,3))*255
    core=is_source[owner[valid]]
    base=np.tile(np.asarray(to_rgb('#AEB8C0')),(int(valid.sum()),1));base[core]=to_rgb(GOLD if key=='prior' else BLUE)
    # Screen-space depth contrast improves shape reading without moving points.
    response=np.zeros_like(d);support=np.zeros_like(d)
    for dy,dx in [(0,5),(0,-5),(5,0),(-5,0)]:
        neighbor=np.roll(np.roll(d,dy,axis=0),dx,axis=1);good=valid&np.isfinite(neighbor)
        response[good]+=np.maximum(neighbor[good]-d[good],0);support[good]+=1
    response/=np.maximum(support,1);shade=.78+.22*np.exp(-response[valid]*.8)
    rgba[valid]=np.clip(base*shade[:,None]*255,0,255)
    im=Image.fromarray(rgba.astype(np.uint8));draw=ImageDraw.Draw(im)
    ref=project(data['roof_reference_section']);line=[tuple(p[:2]) for p in ref]
    draw.line(line,fill='white',width=10,joint='curve');draw.line(line,fill=REF,width=5,joint='curve')
    profile=project(data['roof_'+key+'_section']);line=[tuple(p[:2]) for p in profile]
    draw.line(line,fill='white',width=10,joint='curve');draw.line(line,fill=GOLD if key=='prior' else BLUE,width=5,joint='curve')
    for i,name in [(0,'A'),(-1,'B')]:
        pt=ref[i,:2];draw.ellipse((pt[0]-6,pt[1]-6,pt[0]+6,pt[1]+6),fill=REF,outline='white',width=2)
        roof_marker(im,pt,name)
    if key=='prior':midpoint_arrow(im,data,project,view)
    x0=42;y0=h-30;length=5*view['scale_px_per_m'];draw.line((x0,y0,x0+length,y0),fill=MUTED,width=3)
    R8.text(im,((x0+length/2)/2,(y0-45)/2),'5 m',24,MUTED,anchor='mt')
    return im


def roof_marker(im,point,name):
    draw=ImageDraw.Draw(im);offset=np.array([20,12] if name=='A' else [-52,-58]);pos=point+offset
    font=R8.font(25,True);bb=draw.textbbox(tuple(pos),name,font=font,anchor='lt')
    draw.rectangle((bb[0]-5,bb[1]-3,bb[2]+5,bb[3]+3),fill='white')
    draw.text(tuple(pos),name,font=font,fill=REF,anchor='lt')


def midpoint_arrow(im,data,project,view):
    draw=ImageDraw.Draw(im);w,h=view['canvas'];a,b=project(data['roof_midpoint_comparison'])[:,:2]
    delta=b-a;length=np.linalg.norm(delta)
    if length<=12:return
    u=delta/length;v=np.array([-u[1],u[0]])
    draw.line([tuple(a),tuple(b)],fill='white',width=9);draw.line([tuple(a),tuple(b)],fill=INK,width=4)
    for p,direction in [(a,1),(b,-1)]:
        draw.polygon([tuple(p),tuple(p+direction*u*15+v*7),tuple(p+direction*u*15-v*7)],fill=INK)
    for p,label,col,dy in [(a,'사전',GOLD,-55),(b,'참조',REF,20)]:
        pos=np.clip(p+[92,dy],[10,10],[w-125,h-65]);f=R8.font(24,True);bb=draw.textbbox(tuple(pos),label,font=f,anchor='lt')
        draw.line([tuple(p),(pos[0]-8,pos[1]+20)],fill='white',width=6);draw.line([tuple(p),(pos[0]-8,pos[1]+20)],fill=col,width=3)
        draw.rectangle((bb[0]-5,bb[1]-3,bb[2]+5,bb[3]+3),fill='white');draw.text(tuple(pos),label,font=f,fill=col,anchor='lt')


def roof_surface(data,meta,s,project,view):
    path=CACHE/'display_mesh.npz';mp=OUT/'display_mesh.json'
    if path.exists():
        m=load(mp);assert m['sha256']==sha(path);tri=np.load(path)['triangles']
    else:
        source=np.load(s['roof_prior_mesh']);V=source['V']+meta['roof_registration_shift']
        tri,ids,err=R9.crop_mesh(V,source['F'],np.asarray(meta['context_min_xyz']),np.asarray(meta['context_max_xyz']))
        np.savez_compressed(path,triangles=tri,source_faces=ids)
        dump(mp,dict(source=s['roof_prior_mesh'],source_sha256=sha(s['roof_prior_mesh']),sha256=sha(path),
             triangle_count=len(tri),clip_plane_max_error_m=err,source_coordinates_preserved=True))
    w,h=view['canvas'];depth=np.full((h,w),-np.inf);rgb=np.ones((h,w,3))*255
    # Project each original triangle; resolve actual frontmost surfaces.
    Q=project(tri.reshape(-1,3)).reshape(-1,3,3)
    n=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);n/=np.maximum(np.linalg.norm(n,axis=1)[:,None],1e-12)
    light=np.array([.2,-.3,1.]);light/=np.linalg.norm(light);shade=.64+.36*np.abs(n@light)
    corelo=np.asarray(meta['highlight_min_xyz']);corehi=np.asarray(meta['highlight_max_xyz'])
    for i,q in enumerate(Q):
        x0,y0=np.maximum(np.floor(q[:,:2].min(0)).astype(int),[0,0]);x1,y1=np.minimum(np.ceil(q[:,:2].max(0)).astype(int),[w-1,h-1])
        if x1<x0 or y1<y0:continue
        a,b,c=q;den=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
        if abs(den)<1e-10:continue
        xx,yy=np.meshgrid(np.arange(x0,x1+1)+.5,np.arange(y0,y1+1)+.5)
        wa=((b[1]-c[1])*(xx-c[0])+(c[0]-b[0])*(yy-c[1]))/den
        wb=((c[1]-a[1])*(xx-c[0])+(a[0]-c[0])*(yy-c[1]))/den;wc=1-wa-wb
        zz=wa*a[2]+wb*b[2]+wc*c[2];patch=depth[y0:y1+1,x0:x1+1]
        hit=(wa>=-1e-8)&(wb>=-1e-8)&(wc>=-1e-8)&(zz>patch)
        if not hit.any():continue
        X=wa[hit,None]*tri[i,0]+wb[hit,None]*tri[i,1]+wc[hit,None]*tri[i,2]
        core=np.all((X>=corelo)&(X<=corehi),axis=1)
        colours=np.tile(to_rgb('#AEB8C0'),(len(X),1));colours[core]=to_rgb(GOLD)
        target=rgb[y0:y1+1,x0:x1+1];target[hit]=colours*shade[i]*255;patch[hit]=zz[hit]
    im=Image.fromarray(rgb.astype(np.uint8));draw=ImageDraw.Draw(im)
    ref=project(data['roof_reference_section']);pts=[tuple(p[:2]) for p in ref]
    draw.line(pts,fill='white',width=10,joint='curve');draw.line(pts,fill=REF,width=5,joint='curve')
    for i,name in [(0,'A'),(-1,'B')]:
        roof_marker(im,ref[i,:2],name)
    # A fixed section midpoint identifies the height direction. These endpoints
    # are existing binned prior/reference values, not selected maxima or edits.
    endpoints=project(data['roof_midpoint_comparison'])[:,:2]
    a,b=endpoints;delta=b-a;length=np.linalg.norm(delta)
    if length>12:
        u=delta/length;v=np.array([-u[1],u[0]])
        draw.line([tuple(a),tuple(b)],fill='white',width=9)
        draw.line([tuple(a),tuple(b)],fill=INK,width=4)
        for p,direction in [(a,1),(b,-1)]:
            draw.polygon([tuple(p),tuple(p+direction*u*15+v*7),tuple(p+direction*u*15-v*7)],fill=INK)
        for p,label,col,dy in [(a,'사전',GOLD,-55),(b,'참조',REF,20)]:
            pos=np.clip(p+[92,dy],[10,10],[w-125,h-65]);f=R8.font(24,True);bb=draw.textbbox(tuple(pos),label,font=f,anchor='lt')
            draw.line([tuple(p),(pos[0]-8,pos[1]+20)],fill='white',width=6)
            draw.line([tuple(p),(pos[0]-8,pos[1]+20)],fill=col,width=3)
            draw.rectangle((bb[0]-5,bb[1]-3,bb[2]+5,bb[3]+3),fill='white');draw.text(tuple(pos),label,font=f,fill=col,anchor='lt')
    x=42;y=h-30;length=5*view['scale_px_per_m'];draw.line((x,y,x+length,y),fill=MUTED,width=3)
    R8.text(im,((x+length/2)/2,(y-45)/2),'5 m',24,MUTED,anchor='mt')
    return im


def wall_panel(data,meta,s,size,key,blind=False):
    from common import plot_setup
    C=np.asarray(meta['wall_origin']);u=np.asarray(meta['wall_basis'])[0].copy();u[2]=0;u/=np.linalg.norm(u)
    n=np.asarray(meta['wall_basis'])[1];pm=load(s['wall_photo'])['photo']['source']['photo'];R=np.asarray(pm['pose']['R']);t=np.asarray(pm['pose']['t'])
    sign=float(np.sign((-R.T@t-C)@n));n*=sign
    points={key:np.c_[(data['wall_'+key]-C)@u,(data['wall_'+key]-C)@n] for key in ['prior','mvs','gt']}
    allp=np.concatenate(list(points.values()));lo=allp.min(0);hi=allp.max(0)
    # True top view of the fixed points: horizontal along-wall position vs normal.
    plt=plot_setup(17.28);fig=plt.figure(figsize=(size[0]/200,size[1]/200),dpi=200);ax=fig.add_axes([.04,.12,.92,.80])
    ax.set_xlim(lo[0]-.35,hi[0]+.35);ax.set_ylim(lo[1]-.32,hi[1]+.32);ax.set_aspect('equal');ax.axis('off')
    p=points['prior'];order=np.argsort(p[:,0])
    if key=='prior':ax.plot(p[order,0],p[order,1],c=GOLD,lw=3,ls=(0,(5,3)),zorder=3)
    g=points['gt'];ax.scatter(g[:,0],g[:,1],c=REF,s=16,edgecolors='white',linewidths=.5,zorder=4)
    m=points['mvs']
    if key=='mvs':ax.scatter(m[:,0],m[:,1],c=BLUE,s=9,alpha=.85,linewidths=0,zorder=2)
    section=load(s['wall_section']);bins=np.asarray(section['bin_centres_m']);k=int(np.argmin(abs(bins)))
    old_u=np.asarray(section['source_view']['axis1']);old_n=np.asarray(section['source_view']['axis2'])
    endpoints=np.stack([C+bins[k]*old_u+section['series'][source]['median'][k]*old_n for source in ['gt','mvs']])
    arrow=np.c_[(endpoints-C)@u,(endpoints-C)@n]
    if key=='mvs':
        for colour,width in [('white',5),(INK,2)]:
            ax.annotate('',xy=arrow[1],xytext=arrow[0],arrowprops=dict(arrowstyle='->',lw=width,color=colour,mutation_scale=17),zorder=7)
    # Label source identities only; the blind version omits the intended finding.
    fig.text(.04,.98,'위에서 본 위치',color=MUTED,fontsize=18,va='top')
    fig.text(.96,.98,'사진 쪽 ↑',color=MUTED,fontsize=17.28,ha='right',va='top')
    for x,label in [(p[:,0].min(),'A'),(p[:,0].max(),'B')]:ax.text(x,float(np.median(p[:,1]))+.15,label,color=INK,fontsize=18,ha='center',va='bottom',weight='bold')
    y=lo[1]-.25;x=lo[0];ax.plot([x,x+1],[y,y],c=MUTED,lw=1.5);ax.text(x+.5,y+.05,'1 m',color=MUTED,fontsize=17.28,ha='center',va='bottom')
    path=CACHE/f'wall_{key}_{"blind" if blind else "top"}.png';fig.savefig(path,dpi=200,facecolor='white');plt.close(fig)
    record=dict(horizontal_axis=u,normal_axis=n,normal_sign_to_photo_camera=sign,origin=C,unit_scale_equal=True,point_counts={k:len(v) for k,v in points.items()},
         limits_xy=[lo,hi],orthographic_top_view=True,no_new_point_selection=True,
         midpoint_arrow=dict(rule='Existing bin nearest the geometric section midpoint, lower-index tie break; drawn in MVS panel',bin_index=k,endpoints_xyz=endpoints))
    return Image.open(path).convert('RGB'),record


def compose(data,meta,c,s,az,el,blind=False):
    data=dict(data)
    data['roof_reference_section']=np.asarray(load(s['roof_photo'])['photo']['section_line_xyz'])
    example=load(s['roof_example'])['examples'][0];bins=np.asarray(example['bin_centres_m'])
    k=int(np.argmin(abs(bins-example['length_m']/2)));u=np.asarray(example['end_xy'])-example['start_xy'];u/=np.linalg.norm(u)
    xy=np.asarray(example['start_xy'])+bins[k]*u;H=np.asarray(example['heights_model_m'])
    data['roof_midpoint_comparison']=np.array([[*xy,H[k,0]],[*xy,H[k,2]]])
    profile_xy=np.asarray(example['start_xy'])+bins[:,None]*u
    for key,column in [('prior',0),('mvs',1)]:
        valid=np.isfinite(H[:,column]);data['roof_'+key+'_section']=np.c_[profile_xy[valid],H[valid,column]]
    im=Image.new('RGB',(3840,2160),'white');R8.TEXT_RECORDS.clear()
    def T(x,y,v,size=26,col=INK,bold=False):text(im,(x,y),v,size,col,bold,blind=blind)
    T(60,32,'두 자료의 오류',25,MUTED);T(60,77,'건물의 같은 부분을 사전 정보와 영상으로 비교',42,INK,True)
    T(60,156,'01  현재와 달라진 지붕',32,INK,True)
    T(60,205,'현재 사진 · 노란 A–B 구간',26,MUTED)
    T(615,205,'사전 정보 · 과거 항공 LiDAR',27,GOLD,True)
    T(1240,205,'영상에서 추정한 형상 · MVS',27,BLUE,True)
    photos={}
    pic,photos['roof']=photo('roof',c,s,(1040,620));im.paste(pic,(120,490))
    project,view=camera(data,meta,az,el,(1190,650))
    for key,x in [('prior',600),('mvs',1225)]:
        pane=roof_panel(data,meta,key,project,view,blind)
        im.paste(pane,(x*2,470));pane.save(CACHE/f'roof_{key}.png')
    T(615,566,'높은 옛 형상이 남아 있음',26,GOLD,True)
    T(1240,566,'현재 참조 단면 가까이에 위치',26,BLUE,True)
    R8.line(im,[(60,618),(1860,618)],'#DEE5EB',1)
    T(60,651,'02  벽의 위치를 벗어난 영상 깊이',32,INK,True)
    T(60,700,'현재 사진 · 벽과 지면',26,MUTED)
    T(615,700,'사전 정보 · LoD2 벽면',27,GOLD,True)
    T(1240,700,'영상에서 추정한 위치 · MVS',27,BLUE,True)
    pic,photos['wall']=photo('wall',c,s,(1040,580));im.paste(pic,(120,1470))
    wallviews={}
    for key,x in [('prior',600),('mvs',1225)]:
        pane,wallviews[key]=wall_panel(data,meta,s,(1190,510),key,blind);im.paste(pane,(x*2,1480))
    T(615,1003,'참조점과 사전 면이 가까이 모임',25,GOLD,True)
    T(1240,1003,'영상 점이 벽면 앞뒤로 흩어짐',25,BLUE,True)
    T(60,1045,'회색 건물·짙은 선/점: 현재 참조(드론 LiDAR) · 주황: 사전 정보 · 파랑: 영상 MVS · 실제 좌표·동일 축척',24,MUTED)
    if blind:
        for y in [205,700]:
            for x,v,col in [(60,'사진',MUTED),(615,'사전 정보',GOLD),(1240,'영상 MVS',BLUE)]:R8.text(im,(x,y),v,27,col,True)
        R8.text(im,(60,1045),'회색 건물·짙은 선/점: 현재 드론 LiDAR 참조 · 각 행은 같은 위치의 비교',24,MUTED)
    return im,dict(roof_view=view,wall_views=wallviews,photos=photos,text_records=list(R8.TEXT_RECORDS),
        roof_guide_xyz=data['roof_reference_section'],roof_midpoint_annotation=dict(rule='Nearest existing bin to geometric section midpoint; lower-index tie break',bin_index=k,bin_m=bins[k],endpoints_xyz=data['roof_midpoint_comparison'],height_difference_m=H[k,0]-H[k,2]),
        roof_source_sections={key:data['roof_'+key+'_section'] for key in ['prior','mvs']},
        roof_rendering=dict(prior='Original ALS vertices, existing registration, only the fixed highlighted volume',mvs='Original MVS points, only the fixed highlighted volume',
           shared_context='Identical current UAS reference points in both roof panels; gray, evaluation only',point_footprint_export_px=5,
           reference='Exact calibrated photo section guide',source_profiles='Unchanged binned source section values; not reconstructed roof edges'))


def main():
    p=argparse.ArgumentParser();p.add_argument('--inspect',action='store_true');p.add_argument('--roof-az',type=float,default=-65);p.add_argument('--roof-el',type=float,default=28);args=p.parse_args()
    if args.inspect:inspect();return
    c,s=lock();data,meta=prepare(c,s)
    (OUT/'figures').mkdir(exist_ok=True);(OUT/'previews').mkdir(exist_ok=True);(OUT/'qa').mkdir(exist_ok=True)
    im,rec=compose(data,meta,c,s,args.roof_az,args.roof_el)
    im.save(OUT/'figures/slide5_context_pairs.png');im.resize((1920,1080),Image.Resampling.LANCZOS).save(OUT/'previews/slide5_context_pairs.png')
    raw,_=compose(data,meta,c,s,args.roof_az,args.roof_el,True);raw.resize((1920,1080),Image.Resampling.LANCZOS).save(OUT/'qa/slide5_without_explanations.png')
    dump(OUT/'render.json',dict(task_id=c['task_id'],scientific_verdict=None,created_at=now(),config_sha256=sha(CONFIG),
        script_sha256=sha(REPO/'scripts/phd/slide_photo_v1/slide5_context_revision_10.py'),base_commit=os.environ['TASK_BASE_COMMIT'],
        sources=s,render=rec,no_training=True,no_gpu=True,new_registration=False,projection_scale_exaggeration=False))
    print('R10 rendered',meta['roof_counts'],meta['wall_counts'])


if __name__=='__main__':main()
