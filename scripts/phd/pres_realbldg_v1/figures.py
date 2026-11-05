"""One building-ID driven photographic map script; CPU, existing surfaces only."""
from common import *
from photos import cameras,full_rgb
from visibility import prior_scene,wall_data,visible
from zones import eaves
import cv2,open3d as o3d,matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.collections import PolyCollection,LineCollection
from matplotlib.patches import Patch
from shapely.geometry import box
from shapely.ops import unary_union

font_manager.fontManager.addfont('/fonts/NotoSansCJK-Regular.ttc');plt.rcParams.update({'font.family':'Noto Sans CJK JP','axes.unicode_minus':False,'font.size':10,'hatch.linewidth':.45})
COL={0:'#888780',1:'#1D9E75',2:'#D85A30',3:'#ffffff',4:'#D85A30'}
NAMES={0:'둘 다 맞음',1:'영상만 맞음',2:'사전 정보만 맞음',3:'둘 다 틀림',4:'영상 없음'}
CONDS={'c1':'①','c2':'②','c3a':'③가','c3b':'③나','c4':'④'}

def background(b,cam,scene,shift,up):
    allxy=np.concatenate([np.asarray(r) for r in b['rings']])+shift[:2];lo=np.floor((allxy.min(0)-5)/.05)*.05;hi=np.ceil((allxy.max(0)+5)/.05)*.05
    xs=np.arange(lo[0],hi[0],.05)+.025;ys=np.arange(lo[1],hi[1],.05)+.025;xx,yy=np.meshgrid(xs,ys);top=np.max(np.asarray(b['roof_edges'])[:,:,2])+shift[2]+50
    rays=np.c_[xx.ravel(),yy.ravel(),np.full(xx.size,top),np.zeros(xx.size),np.zeros(xx.size),-np.ones(xx.size)].astype('f4')
    hit=scene.cast_rays(o3d.core.Tensor(rays),nthreads=4)['t_hit'].numpy();P=rays[:,:3].astype(float);P[:,2]-=hit;valid=np.isfinite(hit)
    centre=np.r_[allxy.mean(0),top-50];v=cam.centres-centre;angles=np.degrees(np.arccos(np.clip(v@up/np.linalg.norm(v,axis=1),-1,1)));chosen=None
    for j in np.argsort(angles):
        uv,_,ok=cam.project(centre[None],int(j))
        if ok[0] and 0<=uv[0,0]<cam.w and 0<=uv[0,1]<cam.h:chosen=int(j);break
    assert chosen is not None,'photo/camera not found for top map'
    archive=zipfile.ZipFile(RAW/'raw/uav/Images.zip');im=np.asarray(full_rgb(cam,chosen,archive));rgb=np.full((len(P),3),221,'u1');ids=np.flatnonzero(valid)
    for start in range(0,len(ids),16000):
        ii=ids[start:start+16000];Q=P[ii];v=Q-cam.centres[chosen];dist=np.linalg.norm(v,axis=1);r=np.c_[np.broadcast_to(cam.centres[chosen],Q.shape),v/dist[:,None]].astype('f4')
        dep=scene.cast_rays(o3d.core.Tensor(r),nthreads=4)['t_hit'].numpy();uv,_,guard=cam.project(Q,chosen);ok=guard&(dist<=dep+.3)&(uv[:,0]>=0)&(uv[:,0]<cam.w-1)&(uv[:,1]>=0)&(uv[:,1]<cam.h-1)
        pixels=cv2.remap(im,uv[:,0].astype('f4')[None],uv[:,1].astype('f4')[None],cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)[0];rgb[ii[ok]]=pixels[ok]
    info=archive.getinfo(cam.members[chosen]);archive.close()
    return rgb.reshape(xx.shape+(3,)),[lo[0],hi[0],lo[1],hi[1]],chosen,dict(grid_m=.05,cells=len(P),prior_surface_cells=int(valid.sum()),sight_tilt_degrees=float(angles[chosen]),member=cam.members[chosen],crc32=info.CRC)

def overlay(ax,polys,cases):
    for code in [0,1,2,4,3]:
        take=cases==code
        if not take.any():continue
        hatch='////' if code in [3,4] else None;edge='#777777' if code==3 else COL[code] if code==4 else 'none'
        ax.add_collection(PolyCollection(polys[take],facecolors=matplotlib.colors.to_rgba(COL[code],.48 if code!=3 else .7),edgecolors=edge,linewidths=0,hatch=hatch))

def wall_outline(w,mask):
    ids=np.flatnonzero(mask)
    if not len(ids):return []
    i=ids[0];a=w['tangent1'][i];b=w['tangent2'][i];normal=w['normal'][i];P=w['centre'][ids];uv=np.c_[P@a,P@b];origin=uv[0]-.125;cells=np.rint((uv-uv[0])/.25).astype(int);cells=np.unique(cells,axis=0);poly=unary_union([box(*(origin+q*.25),*(origin+(q+1)*.25)) for q in cells]);h=float(np.median(P@normal));out=[]
    for p in getattr(poly,'geoms',[poly]):
        if p.geom_type!='Polygon':continue
        xy=np.asarray(p.exterior.coords);out.append(xy[:,:1]*a+xy[:,1:]*b+h*normal)
    return out

def decorate(fig,ax,r,kind):
    title=r['building']+' · '+' '.join(CONDS[k] for k,v in r['conditions'].items() if v)
    fig.text(.5,.97,title,ha='center',va='top',fontsize=15)
    values=' · '.join(f'{NAMES[k]} {r["case_areas"][str(k)]:,.1f}' for k in [0,1,2,4,3])+' m²'
    fig.text(.5,.93,values,ha='center',va='top',fontsize=8.5)
    handles=[Patch(facecolor=COL[k],edgecolor='#777777' if k==3 else COL[k],hatch='////' if k in [3,4] else None,label=NAMES[k]) for k in [0,1,2,4,3]]
    fig.legend(handles=handles,ncol=3,loc='lower center',bbox_to_anchor=(.5,.015),frameon=False,fontsize=9)
    ax.set_xticks([]);ax.set_yticks([]);ax.set_aspect('equal');fig.patch.set_facecolor('white')

def annotate(ax,points,labels):
    # Number markers are anchored on measured components; short leaders keep
    # near-coincident conditions readable without moving the measured location.
    offsets=[(-18,16),(18,16),(-18,-18),(18,-18),(0,24)]
    for j,(P,label) in enumerate(zip(points,labels)):
        if not len(P):continue
        center=np.mean(P,axis=0);p=P[np.argmin(np.linalg.norm(P-center,axis=1))]
        ax.annotate(label,xy=p,xytext=offsets[j],textcoords='offset points',ha='center',va='center',fontsize=11,color='#222222',bbox=dict(boxstyle='circle,pad=.23',fc='white',ec='#333333',lw=.7),arrowprops=dict(arrowstyle='-',color='#333333',lw=.7),annotation_clip=True)

def main(bid):
    cfg();rank=json.loads((O/'ranking.json').read_text());r=next(x for x in rank['top5'] if x['building']==bid);stem=r['scene'];site=r['site'];b=json.loads((O/'buildings.json').read_text())[bid]
    d=loadz(O/'data'/f'{stem}.npz');z=loadz(O/'zones'/f'{stem}.npz');hi=loadz(O/'highlights'/f'{stem}.npz')['mask'];w=wall_data(stem);wh=loadz(O/'wall_highlights'/f'{stem}.npz');v=loadz(O/'visibility'/f'{stem}.npz');cam=cameras(site)
    ids=np.flatnonzero((d['building']==bid)&(d['area']>0)&np.isin(d['case'],list(COL)))
    tile=None
    if site=='outside':
        tt,ii=np.unique(d['tile'][d['building']==bid],return_inverse=True);tile=str(tt[np.argmax(np.bincount(ii,weights=d['area'][d['building']==bid]))])
    scene,sources=prior_scene(site,tile);shift=np.asarray(json.loads((O/'data'/f'{stem}.json').read_text())['shift']) if site!='outside' else np.asarray(json.loads((W/'holdout/internal/registration'/tile/'LoD2/summary.json').read_text())['registration']['shift_applied'])
    gravity=RAW/'work/gate_s0/freeze_recovery_v1/P2-GATE-S0-FREEZE-RECOVERY-v1/checkpoints/030-dense_mvs_and_gravity.json';up=np.asarray(json.loads(gravity.read_text())['payload']['gravity']['up']);up/=np.linalg.norm(up)
    bg,extent,jtop,bgmeta=background(b,cam,scene,shift,up);ed,_,_,_=eaves(b,shift);outlines=wall_outline(w,wh['c4']&(w['building']==bid))
    fig=plt.figure(figsize=(10,8));ax=fig.add_axes([.035,.14,.93,.72]);ax.imshow(bg,origin='lower',extent=extent)
    order=ids[np.argsort(d['xyz'][ids,2],kind='stable')];xy=d['xyz'][order,:2];q=np.floor(xy/.25)*.25;polys=np.stack([q,q+[.25,0],q+[.25,.25],q+[0,.25]],axis=1)
    overlay(ax,polys,d['case'][order]);ax.add_collection(LineCollection(ed[:,:,:2],colors='#222222',linewidths=.65))
    for p in outlines:ax.plot(p[:,0],p[:,1],ls='--',color=COL[4],lw=1.1)
    positions=[];labels=[]
    for k,col in [('c1',0),('c2',1),('c3a',2),('c3b',3)]:
        if r['conditions'][k]:positions.append(d['xyz'][(d['building']==bid)&hi[:,col],:2]);labels.append(CONDS[k])
    if r['conditions']['c4']:positions.append(w['centre'][wh['c4']&(w['building']==bid),:2]);labels.append('④')
    annotate(ax,positions,labels);ax.set_xlim(extent[:2]);ax.set_ylim(extent[2:]);decorate(fig,ax,r,'top')
    dest=D/'figures'/f'{bid}_가_위에서';dest.parent.mkdir(parents=True,exist_ok=True);fig.savefig(dest.with_suffix('.png'),dpi=300);plt.close(fig)
    shared=dict(building=bid,scene=stem,case_source=r['case_source'],case_areas_m2=r['case_areas'],conditions=r['conditions'],dpi=300,crs='EPSG:25832; local [690953,5336071,604], inherited vertical bridge 45.7m',sources=sources+[source(O/'data'/f'{stem}.npz'),source(O/'ranking.json'),source(Path(__file__))],scientific_verdict=None)
    dump(dest.with_suffix('.json'),dict(**shared,camera=cam.names[jtop],background=bgmeta))
    bits=np.unpackbits(v['packed_views'],axis=1)[:,:len(cam.names)].astype(bool);wall=v['indices'][w['building'][v['indices']]==bid];vv=bits[w['building'][v['indices']]==bid].sum(0);tilt=np.degrees(np.arccos(np.clip(-cam.R[:,2,:]@up,-1,1)))
    choices=np.flatnonzero(tilt>30);fallback=not len(choices)
    if fallback:choices=np.flatnonzero(tilt==tilt.max())
    j=int(choices[np.argmax(vv[choices])]);archive=zipfile.ZipFile(RAW/'raw/uav/Images.zip');im=np.asarray(full_rgb(cam,j,archive));info=archive.getinfo(cam.members[j])
    physical=np.r_[d['xyz'][d['building']==bid],w['centre'][w['building']==bid]];uv,_,valid=cam.project(physical,j);valid&=(uv[:,0]>=0)&(uv[:,0]<cam.w)&(uv[:,1]>=0)&(uv[:,1]<cam.h)
    assert valid.any(),'photo/camera not found for oblique crop';lo=np.maximum(0,np.floor(uv[valid].min(0)-70).astype(int));high=np.minimum([cam.w,cam.h],np.ceil(uv[valid].max(0)+70).astype(int))
    fig=plt.figure(figsize=(10,8));ax=fig.add_axes([.035,.14,.93,.72]);ax.imshow(im[lo[1]:high[1],lo[0]:high[0]],extent=[lo[0],high[0],high[1],lo[1]])
    ii=visible(d['xyz'][ids],d['normal'][ids],cam,j,scene);chosen=ids[ii]
    P=d['xyz'][chosen];corners=P[:,None]+np.array([[-1,-1],[1,-1],[1,1],[-1,1]])[None,:,0,None]*.125*d['t1'][chosen,None]+np.array([[-1,-1],[1,-1],[1,1],[-1,1]])[None,:,1,None]*.125*d['t2'][chosen,None]
    poly,_,guard=cam.project(corners,j);ok=guard.all(1);overlay(ax,poly[ok],d['case'][chosen[ok]])
    for p in outlines:
        uv,_,guard=cam.project(p,j)
        if guard.all():ax.plot(uv[:,0],uv[:,1],ls='--',color=COL[4],lw=1.1)
    positions=[];labels=[]
    for k,col in [('c1',0),('c2',1),('c3a',2),('c3b',3)]:
        if r['conditions'][k]:
            ix=chosen[hi[chosen,col]];uv,_,ok=cam.project(d['xyz'][ix],j);positions.append(uv[ok]);labels.append(CONDS[k])
    if r['conditions']['c4']:
        uv,_,ok=cam.project(w['centre'][wh['c4']&(w['building']==bid)],j);positions.append(uv[ok]);labels.append('④')
    annotate(ax,positions,labels);ax.set_xlim(lo[0],high[0]);ax.set_ylim(high[1],lo[1]);decorate(fig,ax,r,'oblique')
    dest=D/'figures'/f'{bid}_나_경사사진';fig.savefig(dest.with_suffix('.png'),dpi=300);plt.close(fig)
    dump(dest.with_suffix('.json'),dict(**shared,camera=cam.names[j],camera_tilt_degrees=float(tilt[j]),oblique_fallback=fallback,visible_wall_patches=int(vv[j]),visible_case_points=len(chosen),photo_member=cam.members[j],photo_crc32=info.CRC,crop=[lo.tolist(),high.tolist()]))
    print('FIGURES',bid,'top',cam.names[jtop],'oblique',cam.names[j],float(tilt[j]),flush=True)
if __name__=='__main__':main(sys.argv[1])
