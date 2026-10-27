"""Same-coordinate prior outline and image geometry overlay for slide 5."""
import argparse
import hashlib
import json
import os
import platform
import zipfile

import numpy as np
from PIL import Image,ImageDraw
from scipy.ndimage import binary_erosion
from matplotlib.colors import to_rgb

from common import CFG,DOC,PAY,REPO,load,dump,sha,now,plot_setup
import slide5_draft_revision_08 as R8
import slide5_context_revision_10 as R10

OUT=DOC/'revision_11';CACHE=PAY/'revision_11';CONFIG=CFG/'slide5_overlay_revision_11.json'
INK=R10.INK;MUTED=R10.MUTED;GOLD=R10.GOLD;BLUE=R10.BLUE;REF=R10.REF


def inputs():
    c=load(CONFIG);s=load(c['source_config'])['sources']
    paths=dict(s,geometry10=PAY/'revision_10/geometry.npz',geometry9=PAY/'revision_09/geometry.npz',
               meta10=DOC/'revision_10/geometry.json',meta9=DOC/'revision_09/geometry.json',
               audit10=DOC/'revision_10/verification.json')
    signatures={k:dict(path=str(v),sha256=sha(v)) for k,v in paths.items()}
    lock=OUT/'input_lock.json'
    if lock.exists():assert load(lock)['sources']==signatures and load(lock)['config_sha256']==sha(CONFIG)
    else:dump(lock,dict(task_id=c['task_id'],scientific_verdict=None,locked_at=now(),config_sha256=sha(CONFIG),sources=signatures))
    amendment=CFG/'slide5_overlay_revision_11_display_01.json';ap=OUT/'display_lock.json'
    if ap.exists():assert load(ap)['sha256']==sha(amendment)
    else:dump(ap,dict(path=str(amendment),sha256=sha(amendment),locked_at=now()))
    assert load(paths['audit10'])['status']=='PASS'
    data=dict(np.load(paths['geometry10']));meta=load(paths['meta10']);old=np.load(paths['geometry9'])
    data['roof_tri']=old['roof_tri']@np.asarray(meta['roof_basis'])+meta['roof_origin']
    return c,s,data,meta


def camera(data,meta,az,el,size):
    B=np.asarray(meta['roof_basis']);origin=np.asarray(meta['roof_origin']);a,e=np.deg2rad([az,el])
    eye=np.array([np.cos(e)*np.cos(a),np.cos(e)*np.sin(a),np.sin(e)])
    right=np.array([-np.sin(a),np.cos(a),0.]);R=np.stack([right,np.cross(eye,right),eye])@B
    X=np.concatenate([data['roof_tri'].reshape(-1,3),data['roof_mvs'][data['roof_mvs_core']]])
    q=(X-origin)@R.T;lo=q[:,:2].min(0);hi=q[:,:2].max(0);mid=(lo+hi)/2
    scale=min((size[0]-120)/(hi[0]-lo[0]),(size[1]-160)/(hi[1]-lo[1]))
    def project(X):
        q=(np.asarray(X)-origin)@R.T
        return np.stack([(q[...,0]-mid[0])*scale+size[0]/2,size[1]/2-(q[...,1]-mid[1])*scale,q[...,2]],axis=-1)
    return project,dict(rotation=R,origin=origin,scale_px_per_m=scale,canvas=size,mid=mid,bounds=[lo,hi],azimuth_deg=az,elevation_deg=el)


def source_depth(X,project,size):
    w,h=size;q=project(X);x=np.rint(q[:,0]).astype(int);y=np.rint(q[:,1]).astype(int)
    depth=np.full(w*h,-np.inf)
    for dy in range(-2,3):
        for dx in range(-2,3):
            xx=x+dx;yy=y+dy;ok=(xx>=0)&(xx<w)&(yy>=0)&(yy<h)
            np.maximum.at(depth,yy[ok]*w+xx[ok],q[ok,2])
    return depth.reshape(h,w)


def mesh_depth(tri,project,size):
    w,h=size;depth=np.full((h,w),-np.inf);Q=project(tri)
    for q in Q:
        x0,y0=np.maximum(np.floor(q[:,:2].min(0)).astype(int),[0,0]);x1,y1=np.minimum(np.ceil(q[:,:2].max(0)).astype(int),[w-1,h-1])
        if x1<x0 or y1<y0:continue
        a,b,c=q;den=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
        if abs(den)<1e-10:continue
        xx,yy=np.meshgrid(np.arange(x0,x1+1)+.5,np.arange(y0,y1+1)+.5)
        wa=((b[1]-c[1])*(xx-c[0])+(c[0]-b[0])*(yy-c[1]))/den
        wb=((c[1]-a[1])*(xx-c[0])+(a[0]-c[0])*(yy-c[1]))/den;wc=1-wa-wb
        z=wa*a[2]+wb*b[2]+wc*c[2];p=depth[y0:y1+1,x0:x1+1]
        hit=(wa>=-1e-8)&(wb>=-1e-8)&(wc>=-1e-8)&(z>p);p[hit]=z[hit]
    return depth


def label(im,p,value,col=INK,size=26):
    d=ImageDraw.Draw(im);f=R8.font(size,True);bb=d.textbbox(tuple(p),value,font=f,anchor='lt')
    d.rectangle((bb[0]-8,bb[1]-5,bb[2]+8,bb[3]+5),fill='white');d.text(tuple(p),value,font=f,fill=col,anchor='lt')


def roof(data,meta,s,az,el,size):
    project,view=camera(data,meta,az,el,size);w,h=size
    md=source_depth(data['roof_mvs'][data['roof_mvs_core']],project,size);pd=mesh_depth(data['roof_tri'],project,size)
    mask=np.isfinite(pd);edge=mask&~binary_erosion(mask,iterations=3)
    ex=load(s['roof_example'])['examples'][0];bins=np.asarray(ex['bin_centres_m']);H=np.asarray(ex['heights_model_m'])
    k=int(np.argmin(abs(bins-ex['length_m']/2)));u=np.asarray(ex['end_xy'])-ex['start_xy'];u/=np.linalg.norm(u)
    xy=np.asarray(ex['start_xy'])+bins[k]*u;endpoints=np.array([[*xy,H[k,0]],[*xy,H[k,1]]]);a,b=project(endpoints)[:,:2]
    panels={}
    for mode in ['prior','mvs','overlay']:
        rgb=np.ones((h,w,3))*255
        if mode!='prior':
            valid=np.isfinite(md);depth=md[valid];v=(depth-depth.min())/max(np.ptp(depth),1e-8)
            rgb[valid]=np.clip(np.asarray(to_rgb(BLUE))[None]*(.78+.22*v[:,None])+.12*(1-v[:,None]),0,1)*255
        if mode!='mvs':
            rgb[mask]=rgb[mask]*.92+np.asarray(to_rgb(GOLD))*255*.08;rgb[edge]=np.asarray(to_rgb(GOLD))*255
        im=Image.fromarray(rgb.astype('uint8'));d=ImageDraw.Draw(im)
        if mode=='overlay':
            d.line([tuple(a),tuple(b)],fill='white',width=11);d.line([tuple(a),tuple(b)],fill=INK,width=5)
            v=(b-a)/np.linalg.norm(b-a);n=np.array([-v[1],v[0]])
            for p,t in [(a,1),(b,-1)]:d.polygon([tuple(p),tuple(p+t*v*20+n*9),tuple(p+t*v*20-n*9)],fill=INK)
            label(im,a+[30,-70],'사전 지붕',GOLD);label(im,b+[30,20],'영상 지붕',BLUE)
        ref=np.asarray(load(s['roof_photo'])['photo']['section_line_xyz']);q=project(ref)
        for i,name in [(0,'A'),(-1,'B')]:
            p=q[i,:2];d.ellipse((p[0]-7,p[1]-7,p[0]+7,p[1]+7),fill=INK,outline='white',width=2)
            label(im,p+[-23,20 if i==0 else -60],name,INK,25)
        unit=5*view['scale_px_per_m'];d.line((40,h-40,40+unit,h-40),fill=MUTED,width=3)
        R8.text(im,((40+unit/2)/2,(h-95)/2),'5 m',24,MUTED,anchor='mt')
        panels[mode]=im;im.save(CACHE/f'roof_{mode}.png')
    ann=dict(bin_index=k,bin_m=bins[k],endpoints_xyz=endpoints,prior_minus_mvs_m=H[k,0]-H[k,1],rule='Nearest existing bin to fixed section midpoint')
    return panels,dict(view=view,annotation=ann,triangle_count=len(data['roof_tri']),mvs_points=int(data['roof_mvs_core'].sum()),xray_overlay=True)


def wall(data,meta,s,size):
    C=np.asarray(meta['wall_origin']);u=np.asarray(meta['wall_basis'])[0].copy();u[2]=0;u/=np.linalg.norm(u)
    n=np.asarray(meta['wall_basis'])[1];pm=load(s['wall_photo'])['photo']['source']['photo'];R=np.asarray(pm['pose']['R']);t=np.asarray(pm['pose']['t']);sign=float(np.sign((-R.T@t-C)@n));n*=sign
    pts={k:np.c_[(data['wall_'+k]-C)@u,(data['wall_'+k]-C)@n] for k in ['prior','mvs','gt']}
    allp=np.concatenate(list(pts.values()));lo=allp.min(0);hi=allp.max(0)
    plt=plot_setup(18);fig=plt.figure(figsize=(size[0]/200,size[1]/200),dpi=200);ax=fig.add_axes([.06,.13,.88,.72])
    ax.set_xlim(lo[0]-.2,hi[0]+.2);ax.set_ylim(lo[1]-.25,hi[1]+.25);ax.set_aspect('equal');ax.axis('off')
    p=pts['prior'];order=np.argsort(p[:,0]);ax.plot(p[order,0],p[order,1],color=GOLD,lw=3,ls=(0,(5,3)),zorder=4)
    m=pts['mvs'];g=pts['gt'];ax.scatter(m[:,0],m[:,1],s=11,color=BLUE,alpha=.8,linewidths=0,zorder=2)
    ax.scatter(g[:,0],g[:,1],s=13,c=REF,edgecolors='white',linewidths=.4,zorder=5)
    fig.text(.06,.96,'위에서 본 위치',color=MUTED,fontsize=18,va='top');fig.text(.94,.96,'사진 쪽 ↑',color=MUTED,fontsize=18,va='top',ha='right')
    for x,name in [(p[:,0].min(),'A'),(p[:,0].max(),'B')]:ax.text(x,float(np.median(p[:,1]))+.12,name,color=INK,fontsize=19,weight='bold',ha='center')
    ax.plot([lo[0],lo[0]+1],[lo[1]-.15]*2,c=MUTED,lw=1.5);ax.text(lo[0]+.5,lo[1]-.1,'1 m',color=MUTED,fontsize=18,ha='center')
    file=CACHE/'wall_overlay.png';fig.savefig(file,dpi=200,facecolor='white');plt.close(fig)
    return Image.open(file).convert('RGB'),dict(origin=C,horizontal_axis=u,normal_axis=n,normal_sign_to_camera=sign,limits=[lo,hi],points={k:len(v) for k,v in pts.items()},equal_metric_scale=True)


def compose(c,s,panels,wp,mode,blind=False):
    im=Image.new('RGB',(3840,2160),'white');R8.TEXT_RECORDS.clear()
    def T(x,y,v,size=26,col=INK,bold=False):
        if not blind:R8.text(im,(x,y),v,size,col,bold)
    T(60,30,'두 자료의 오류 · 같은 위치에 겹쳐 보기',25,MUTED)
    T(60,77,'지붕의 높이 변화와 벽의 깊이 어긋남',42,INK,True)
    if not blind:R8.text(im,(1860,30),{'prior':'지붕 ① 사전만','mvs':'지붕 ② 영상만','overlay':'지붕 ③ 겹침'}[mode],25,MUTED,anchor='rt')
    for x,v,col in [(650,'주황 윤곽 · 사전 정보',GOLD),(1080,'파랑 · 영상 MVS',BLUE)]:R8.text(im,(x,161),v,27,col,True)
    T(60,161,'01  지붕',31,INK,True)
    photos={};pic,photos['roof']=R10.photo('roof',c,s,(1040,650));im.paste(pic,(120,425))
    im.paste(panels[mode],(1220,365))
    T(60,550,'현재 사진 · 노란 A–B 주변',25,MUTED)
    T(650,601,{'prior':'사전 정보에 남아 있는 지붕 형상','mvs':'현재 영상에서 추정한 지붕 형상','overlay':'같은 자리에서 사전 지붕이 영상 지붕보다 높음'}[mode],27,INK,True)
    R8.line(im,[(60,653),(1860,653)],'#DEE5EB',1)
    T(60,676,'02  벽',31,INK,True)
    pic,photos['wall']=R10.photo('wall',c,s,(1040,560));im.paste(pic,(120,1460))
    im.paste(wp,(1230,1350))
    T(60,1015,'현재 사진 · 노란 A–B 주변',25,MUTED)
    T(650,990,'영상 점이 사전 벽면의 앞뒤로 퍼짐',27,INK,True)
    R8.text(im,(650,1038),'짙은 점: 현재 드론 LiDAR 참조 · 같은 좌표·동일 축척',24,MUTED)
    if blind:
        for y in [161,676]:R8.text(im,(60,y),'현재 사진',27,MUTED,True)
    return im,dict(photos=photos,text_records=list(R8.TEXT_RECORDS))


def main():
    p=argparse.ArgumentParser();p.add_argument('--az',type=float,default=-65);p.add_argument('--el',type=float,default=15);a=p.parse_args()
    c,s,data,meta=inputs();panels,roofrec=roof(data,meta,s,a.az,a.el,(2500,820));wp,wallrec=wall(data,meta,s,(2480,620))
    records={}
    for mode in ['prior','mvs','overlay']:
        im,records[mode]=compose(c,s,panels,wp,mode);im.save(OUT/f'figures/slide5_{mode}.png')
        im.resize((1920,1080),Image.Resampling.LANCZOS).save(OUT/f'previews/slide5_{mode}.png')
    im,_=compose(c,s,panels,wp,'overlay',True);im.resize((1920,1080),Image.Resampling.LANCZOS).save(OUT/'qa/without_explanations.png')
    dump(OUT/'render.json',dict(task_id=c['task_id'],scientific_verdict=None,created_at=now(),config_sha256=sha(CONFIG),
         script_sha256=sha(REPO/'scripts/phd/slide_photo_v1/slide5_overlay_revision_11.py'),base_commit=os.environ['TASK_BASE_COMMIT'],
         roof=roofrec,wall=wallrec,composition=records,no_training=True,no_gpu=True,new_registration=False,source_geometry_unchanged=True))
    print('R11 rendered',roofrec['annotation'],wallrec['points'])


if __name__=='__main__':main()
