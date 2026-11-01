"""Deterministic 0.25 m raster maps, metric wall strips and purity chart."""
import math
import struct
import time
from collections import defaultdict
import numpy as np
from PIL import Image
from scipy import ndimage
from shapely.geometry import Polygon, box
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager, patheffects
from matplotlib.colors import ListedColormap, BoundaryNorm
from matplotlib.patches import Patch
from common import *
from geometry import Catalog, inside

REGION_COLORS=['#ffffff','#8f68b6','#379766','#e69432','#3d87c7','#999999']
REGION_PALETTE=dict(zip([-1,0,1,2,3,5],REGION_COLORS))
TRUTH_COLORS=['#d8d8d8','#3d87c7','#e69432','#4c4c4c','#ffffff','#ffffff','#ffffff']
TRUTH_NAMES=['칸 0 둘 다 맞음','칸 1 사전 정보만 틀림','칸 2 영상만 틀림','칸 3 둘 다 틀림','칸 4~6 자료 없음']

def setup():
    font=next(Path('/fonts').glob('NotoSansCJK-Regular.ttc'))
    font_manager.fontManager.addfont(str(font))
    plt.rcParams.update({'font.family':font_manager.FontProperties(fname=str(font)).get_name(),
        'axes.unicode_minus':False,'font.size':10,'axes.titlesize':12,'figure.facecolor':'white','savefig.facecolor':'white'})

def raster(xy,area,region,cell,face,step=.25):
    """Area plurality by class. Grid occupancy never replaces original area sums."""
    origin=np.floor(xy.min(0)/step)*step
    q=np.floor((xy-origin)/step+1e-9).astype(int);nx,ny=(q.max(0)+1)
    key=q[:,1]*nx+q[:,0];size=int(nx*ny)
    assert size<8_000_000,'raster exceeds fixed CPU memory bound'
    counts=np.bincount(key,minlength=size);tot=np.bincount(key,weights=area,minlength=size)
    def majority(labels,values):
        mass=np.array([np.bincount(key,weights=area*(labels==v),minlength=size) for v in values])
        best=mass.max(0);choice=np.array(values)[mass.argmax(0)].astype(int);choice[counts==0]=-99
        ties=((mass==best)&(best>0)).sum(0)>1
        return choice.reshape(ny,nx),int(ties.sum())
    rg,rt=majority(region,[-1,0,1,2,3,5]);cg,ct=majority(cell,list(range(7)))
    face_names=np.unique(face);fg,ft=majority(face,list(face_names)) if np.issubdtype(face.dtype,np.integer) else (None,0)
    return dict(region=rg,cell=cg,face=fg,counts=counts.reshape(ny,nx),area=tot.reshape(ny,nx),
        origin=origin,step=step,extent=[origin[0],origin[0]+nx*step,origin[1],origin[1]+ny*step],
        overlapping_cells=int((counts>1).sum()),region_tie_cells=rt,truth_tie_cells=ct,face_tie_cells=ft,
        occupied_cells=int((counts>0).sum()),patch_count=len(area))

def edges(ax,grid,g,color='#d23838',style='--',width=1):
    if not np.any(grid):return
    pad=np.pad(grid.astype(float),1)
    xs=g['origin'][0]+(np.arange(pad.shape[1])-.5)*g['step']
    ys=g['origin'][1]+(np.arange(pad.shape[0])-.5)*g['step']
    ax.contour(xs,ys,pad,levels=[.5],colors=[color],linestyles=[style],linewidths=[width],zorder=7)

def mismatch_grid(g):
    r,c=g['region'],g['cell'];valid=np.isin(r,[1,2,3])&np.isin(c,[0,1,2])
    good=((r==1)&(c==0))|((r==2)&(c==2))|((r==3)&(c==1))
    return valid&~good

def draw_grid(ax,g,which,outline=True):
    values=g[which];colors=REGION_COLORS if which=='region' else TRUTH_COLORS
    image=np.zeros((*values.shape,4),float)
    from matplotlib.colors import to_rgba
    for code in ([-1,0,1,2,3,5] if which=='region' else range(7)):
        image[values==code]=to_rgba(REGION_PALETTE[code] if which=='region' else colors[code])
    ax.imshow(image,origin='lower',extent=g['extent'],interpolation='nearest')
    unknown=values==-1 if which=='region' else np.isin(values,[4,5,6])
    if which=='region' and unknown.any():
        xs=g['origin'][0]+(np.arange(values.shape[1])+.5)*g['step'];ys=g['origin'][1]+(np.arange(values.shape[0])+.5)*g['step']
        if len(xs)>1 and len(ys)>1:ax.contourf(xs,ys,np.ma.masked_where(~unknown,unknown),levels=[.5,1.5],colors='none',hatches=['////'],zorder=2)
    mis=mismatch_grid(g);components=0
    if outline:
        for face in np.unique(g['face'][mis]):
            if face<0:continue
            mask=mis&(g['face']==face);_,n=ndimage.label(mask);components+=n
            edges(ax,mask,g)
    ax.set_aspect('equal');ax.set_facecolor('#f6f6f4')
    ax.spines[['top','right']].set_visible(False)
    return dict(mismatch_cells=int(mis.sum()),mismatch_components=int(components))

def qrot(q):
    w,x,y,z=q
    return np.array([[1-2*(y*y+z*z),2*(x*y-w*z),2*(x*z+w*y)],
        [2*(x*y+w*z),1-2*(x*x+z*z),2*(y*z-w*x)],
        [2*(x*z-w*y),2*(y*z+w*x),1-2*(x*x+y*y)]])

class Cameras:
    def __init__(self,site,ledger):
        self.ledger=ledger;self.root=S0/'fork_inputs/s61'/site
        self.cal=ledger.json(self.root/'scene_LoD2/jbgs_calibration.json')['images']
        self.split=ledger.json(self.root/'split.json');self.poses={}
        with ledger.add(self.root/'scene_LoD2/sparse/0/images.bin').open('rb') as f:
            count=struct.unpack('<Q',f.read(8))[0]
            for _ in range(count):
                iid=struct.unpack('<i',f.read(4))[0];q=struct.unpack('<4d',f.read(32));t=np.array(struct.unpack('<3d',f.read(24)));cid=struct.unpack('<i',f.read(4))[0]
                name=bytearray()
                while True:
                    ch=f.read(1)
                    if ch==b'\0':break
                    if not ch:raise ValueError('truncated pose')
                    name.extend(ch)
                n=struct.unpack('<Q',f.read(8))[0];f.seek(n*24,1)
                self.poses[Path(name.decode()).stem]=(qrot(q),t)

    def project(self,name,xyz):
        R,t=self.poses[name];K=np.array(self.cal[name]['K']);q=xyz@R.T+t
        with np.errstate(divide='ignore',invalid='ignore'):uv=q[:,:2]/q[:,2:3]
        return uv@K[:2,:2].T+K[:2,2],q[:,2]

    def choose(self,centre):
        candidates=[]
        for name in sorted(self.split['train']):
            if name not in self.poses or name not in self.cal:continue
            uv,z=self.project(name,np.asarray(centre)[None,:]);w,h=self.cal[name]['width'],self.cal[name]['height']
            if z[0]<=0 or not (0<=uv[0,0]<w and 0<=uv[0,1]<h):continue
            R,t=self.poses[name];direction=R.T@np.array([0,0,1.]);tilt=float(np.degrees(np.arccos(np.clip(-direction[2],-1,1))))
            score=float(np.linalg.norm((uv[0]-[w/2,h/2])/[w,h]));candidates.append(dict(name=name,tilt_deg=tilt,centre_distance=score))
        if not candidates:return None,dict(status='확인 불가',reason='건물 중심이 보이는 학습 영상 없음')
        near=[c for c in candidates if c['tilt_deg']<=15]
        fallback=not bool(near)
        if fallback:
            minimum=min(c['tilt_deg'] for c in candidates);near=[c for c in candidates if c['tilt_deg']<=minimum+1]
        chosen=min(near,key=lambda c:(c['centre_distance'],c['tilt_deg'],c['name']))
        return chosen['name'],dict(status='selected',**chosen,near_nadir_fallback=fallback,candidates=candidates)

    def draw(self,ax,faces,centre,eval_polygon):
        name,meta=self.choose(centre)
        if name is None:ax.text(.5,.5,'학습 영상 확인 불가',ha='center',va='center',transform=ax.transAxes);ax.axis('off');return meta
        path=self.root/'images'/f'{name}.jpg';self.ledger.add(path,role='selected_training_photo')
        im=np.asarray(Image.open(path).convert('RGB'));w,h=self.cal[name]['width'],self.cal[name]['height']
        assert im.shape[:2]==(h,w)
        yy,xx=np.mgrid[0:h,0:w];pix=np.column_stack([xx.ravel(),yy.ravel()]);mask=np.zeros((h,w),bool)
        outlines=[]
        for f in faces:
            if f['type']!='roof':continue
            uv,z=self.project(name,f['ext'])
            if np.any(z<=0) or not np.isfinite(uv).all():continue
            pg=Polygon(uv).buffer(0);mask|=inside(pg,pix).reshape(h,w);outlines.append(uv)
        # Source imagery outside the approved experiment building is removed.
        if not mask.any():ax.text(.5,.5,'영상 범위 확인 불가',ha='center',transform=ax.transAxes);ax.axis('off');return dict(meta,status='확인 불가',reason='투영한 지붕이 화면 밖')
        view=im.copy();view[~mask]=248
        y,x=np.nonzero(mask);pad=12;x0=max(0,x.min()-pad);x1=min(w,x.max()+pad+1);y0=max(0,y.min()-pad);y1=min(h,y.max()+pad+1)
        ax.imshow(view);ax.set_xlim(x0,x1);ax.set_ylim(y1,y0);ax.axis('off')
        ax.set_title('학습 영상',loc='left',fontweight='bold')
        meta.update(path=str(path),sha256=sha(path),crop_xyxy=[int(x0),int(y0),int(x1),int(y1)],outside_building_masked=True)
        return meta

def save(fig,stem,metadata):
    p=writable(DOC/'figures'/f'{stem}.png');fig.savefig(p,dpi=240);plt.close(fig)
    dump(p.with_suffix('.json'),dict(**metadata,source_tag=TAG,scientific_verdict=None))
    print('FIGURE',stem,flush=True)

def boundaries(ax,faces,bounds,compact=False):
    labels=[];clip=box(*bounds)
    for f in faces:
        if f['type']!='roof' or f['poly'].is_empty:continue
        pg=f['poly'].intersection(clip)
        if pg.is_empty:continue
        for geom in getattr(pg,'geoms',[pg]):
            if geom.geom_type!='Polygon':continue
            x,y=geom.exterior.xy;ax.plot(x,y,color='#292929',lw=.45,alpha=.8,zorder=4)
            for ring in geom.interiors:ax.plot(*ring.xy,color='#292929',lw=.4,zorder=4)
        point=pg.representative_point();width=pg.bounds[2]-pg.bounds[0];height=pg.bounds[3]-pg.bounds[1]
        short=compact or min(width,height)<3 or pg.area<20
        label=str(f['number']) if short else f['name']
        ax.text(point.x,point.y,label,fontsize=7.5 if short else 8.5,ha='center',va='center',zorder=6,
                path_effects=[patheffects.withStroke(linewidth=2.5,foreground='white')])
        labels.append(dict(number=f['number'],name=f['name'],face_id=f['gml'],building=f['building']))
    return labels

def plan_map(site,prior,d,faces,cameras,bid=None):
    good=d['assigned_building']==bid if bid else np.ones(len(d['area']),bool)
    if not good.any():return
    dd={k:v[good] for k,v in d.items()};faceids={f['gml']:i for i,f in enumerate(sorted(faces.values(),key=lambda f:f['gml']))}
    fi=np.array([faceids.get(k,-1) for k in dd['face']]);g=raster(dd['centre'][:,:2],dd['area'],dd['region'],dd['cell'],fi)
    wanted={str(b) for b in dd['assigned_building'] if b};fs=[f for f in faces.values() if f['building'] in wanted and f['gml'] in set(dd['face'])]
    # Photographic context uses the same building chosen for this panel; overviews use the largest evaluated building.
    if not bid and wanted:photo_bid=max(sorted(wanted),key=lambda b:float(dd['area'][dd['assigned_building']==b].sum()))
    else:photo_bid=bid
    photofs=[f for f in faces.values() if f['building']==photo_bid]
    if photofs:centre=np.mean(np.concatenate([f['ext'][:-1] for f in photofs if f['type']=='roof']),axis=0)
    else:centre=dd['centre'].mean(0)
    total=float(dd['area'].sum());match=float(dd['area'][((dd['region']==1)&(dd['cell']==0))|((dd['region']==2)&(dd['cell']==2))|((dd['region']==3)&(dd['cell']==1))].sum())
    label=SITES[site]+(' · '+building_label(bid) if bid else ' · 전체')
    title=f'{label}: 빨간 점선 안에서 판단과 참값의 짝이 다르다' if mismatch_grid(g).any() else f'{label}: 비교 가능한 칸에서 짝이 다른 곳이 없다'
    fig,axes=plt.subplots(1,3,figsize=(17,7.8),gridspec_kw={'width_ratios':[.95,1.2,1.2]})
    photo=cameras.draw(axes[0],photofs,centre,None)
    x0,x1,y0,y1=g['extent'];pad=max(1,min(x1-x0,y1-y0)*.025);bounds=[x0,y0,x1,y1]
    labels=[];misstats={}
    for ax,key,txt in zip(axes[1:],['region','cell'],['판단 영역','참값 칸']):
        misstats=draw_grid(ax,g,key);labels=boundaries(ax,fs,bounds,compact=(bid is None))
        ax.set_xlim(x0-pad,x1+pad);ax.set_ylim(y0-pad,y1+pad)
        ax.set_title(txt,loc='left',fontweight='bold');ax.set_xlabel('동쪽 (m)');ax.ticklabel_format(useOffset=False,style='plain')
    axes[1].set_ylabel('북쪽 (m)')
    region_handles=[Patch(facecolor=REGION_PALETTE[k],edgecolor='#777777',hatch='///' if k==-1 else None,label=LABELS[k]) for k in ([1,2,3,0,5,-1] if REV=='r7' else [1,2,3,0,-1])]
    truth_handles=[Patch(facecolor=TRUTH_COLORS[k],edgecolor='#777777',label=TRUTH_NAMES[k]) for k in range(5)]
    fig.legend(handles=region_handles,loc='lower left',bbox_to_anchor=(.34,.135),ncol=5,fontsize=8.5,frameon=False)
    fig.legend(handles=truth_handles,loc='lower left',bbox_to_anchor=(.34,.095),ncol=3,fontsize=8.5,frameon=False)
    # The on-image key must stay below the map, including long sawtooth roofs.
    keygroups=defaultdict(list)
    for r in labels:keygroups[r['building']].append(r['number'])
    short_table=' | '.join(f"{building_label(b)}: "+', '.join(map(str,sorted(set(nums)))) for b,nums in keygroups.items())
    short_table='번호표 — 숫자 n = 지붕 n · '+short_table
    fig.text(.35,.075,'짝이 맞으면 판단이 맞음 · 빨간 점선: 칸 0~2와 비교 가능한 판단의 불일치',fontsize=9)
    if len(short_table)>180:
        # Overview with several buildings; each building also has its own map/key.
        midpoint=short_table.rfind(' | ',0,len(short_table)//2+20)
        if midpoint<0:midpoint=len(short_table)//2
        fig.text(.035,.060,short_table[:midpoint],fontsize=8)
        fig.text(.035,.044,short_table[midpoint:].lstrip(' | '),fontsize=8)
    else:fig.text(.035,.048,short_table,fontsize=8.5)
    note='B173은 평면 범위가 같아도 높이가 다를 수 있음 · 기존 LoD2 면 경계' if any(building_label(b)=='B173' for b in wanted) else '면 경계는 기존 LoD2 · 번호는 원래 면 넓이 순서'
    fig.text(.035,.026,f'{note} | 평가 {total:,.1f} m² · 짝 맞음 {100*match/total:.1f}% · 0.25 m 칸 · 겹친 칸 {g["overlapping_cells"]:,} | {TAG}',fontsize=9)
    fig.suptitle(title,fontsize=17,x=.035,ha='left',fontweight='bold')
    fig.text(.035,.905,f'{"항공 LiDAR" if prior=="ALS" else "LoD2"} · {REV} · 평가 범위만 표시',fontsize=11,color='#555555')
    fig.subplots_adjust(left=.035,right=.98,top=.84,bottom=.25,wspace=.23)
    stem=f'map_{site}_{prior}_{REV}'+('_'+building_label(bid) if bid else '')
    meta=dict(scope=site,prior=prior,revision=REV,building=bid,photo_building=photo_bid,photo=photo,
        title=title,caption=note,face_labels=labels,eval_area_m2=total,match_area_m2=match,
        raster={k:v for k,v in g.items() if k not in ['region','cell','face','counts','area']},**misstats,
        mismatches_only_comparable=True,band_included=False,patch_source=str(OUT/f'{REV}/patches/{site}_{prior}.npz'),
        crs='EPSG:25832',world_shift_xyz_m=[690953,5336071,604],height_geometry='existing LoD2, not current truth')
    save(fig,stem,meta)

def wall_strip(site,bid,d,faces):
    fs=[f for f in faces.values() if f['building']==bid and f['type']=='wall' and np.any(d['face']==f['gml'])]
    if not fs:return
    pieces=[];cursor=0.;joins=[];previous=None
    for direct in ['남','동','북','서']:
        candidates=[f for f in fs if f['direction']==direct]
        pending=[]
        for f in candidates:
            n=f['normal'];t=np.array([-n[1],n[0],0.]);t/=np.linalg.norm(t)
            pr=f['ext']@t;lo,hi=float(pr.min()),float(pr.max())
            cen=f['centre'];start=cen[:2]+(lo-cen@t)*t[:2];end=cen[:2]+(hi-cen@t)*t[:2]
            pending.append((f,t,lo,hi,start,end))
        while pending:
            i=min(range(len(pending)),key=lambda i:(np.linalg.norm(pending[i][4]-previous) if previous is not None else 0,pending[i][0]['name']))
            f,t,lo,hi,start,end=pending.pop(i);ids=np.flatnonzero(d['face']==f['gml'])
            uv=np.column_stack([cursor+d['centre'][ids]@t-lo,d['centre'][ids,2]])
            gap=None if previous is None else float(np.linalg.norm(start-previous));joins.append(dict(face_id=f['gml'],face_name=f['name'],start_m=cursor,end_m=cursor+hi-lo,previous_corner_gap_m=gap))
            pieces.append((f,ids,uv,cursor,hi-lo,t,lo));cursor+=hi-lo;previous=end
    xy=np.concatenate([r[2] for r in pieces]);ids=np.concatenate([r[1] for r in pieces]);fids=np.concatenate([np.full(len(r[1]),j) for j,r in enumerate(pieces)])
    g=raster(xy,d['area'][ids],d['region'][ids],d['cell'][ids],fids)
    width=20;fig,axes=plt.subplots(2,1,figsize=(width,7),sharex=True,sharey=True)
    misstats={}
    for ax,key,txt in zip(axes,['region','cell'],['판단 영역','참값 칸']):
        misstats=draw_grid(ax,g,key);ax.set_aspect('auto');ax.set_ylabel('높이 (m)');ax.set_title(txt,loc='left',fontweight='bold')
        for j,(f,ii,uv,start,w,t,lo) in enumerate(pieces):
            poly=np.column_stack([start+f['ext']@t-lo,f['ext'][:,2]])
            ax.plot(poly[:,0],poly[:,1],color='#444444',lw=.6)
            ax.axvline(start,color='#777777',lw=.4,ls=':' if joins[j]['previous_corner_gap_m'] and joins[j]['previous_corner_gap_m']>.02 else '-')
            ax.text(start+w/2,g['extent'][3]+.15,str(j+1),ha='center',va='bottom',fontsize=8)
        ax.set_ylim(g['extent'][2]-.5,g['extent'][3]+1.5);ax.set_xlim(0,cursor)
    axes[-1].set_xlabel('펼친 벽면을 따른 거리 (m)')
    names=[f"{j+1} {r[0]['name']}" for j,r in enumerate(pieces)]
    # A readable number key is retained below; long buildings get a separate key figure.
    keylines=[' · '.join(names[i:i+10]) for i in range(0,len(names),10)]
    discontinuities=sum(r['previous_corner_gap_m'] is not None and r['previous_corner_gap_m']>.02 for r in joins)
    label=building_label(bid);title=f'{SITES[site]} · {label}: 벽을 펼치면 판단이 바뀌는 높이가 보인다'
    fig.suptitle(title,fontsize=16,x=.045,ha='left',fontweight='bold')
    handles=[Patch(facecolor=REGION_PALETTE[k],edgecolor='#777',label=LABELS[k],hatch='///' if k==-1 else None) for k in ([1,2,3,0,5,-1] if REV=='r7' else [1,2,3,0,-1])]
    fig.legend(handles=handles,loc='lower left',bbox_to_anchor=(.04,.05),ncol=5,frameon=False,fontsize=9)
    fig.text(.55,.075,'참값: 칸 0 연회색 · 칸 1 파랑 · 칸 2 주황 · 칸 3 진회색 · 칸 4~6 흰색',fontsize=8.5)
    fig.text(.55,.046,'짝이 맞으면 판단이 맞음 · 빨간 점선: 짝이 다른 곳',fontsize=9)
    note='높이는 작업 좌표의 Z · 면 사이 점선은 실제 모서리가 이어지지 않는 곳'
    if label=='B173':note+=' · 평면 범위가 같아도 높이는 다를 수 있음'
    fig.text(.045,.014,f'{note} | 평가 {d["area"][ids].sum():,.1f} m² · 벽 {len(fs)}개 · 끊긴 연결 {discontinuities}곳 | {TAG}',fontsize=8.5)
    visible_keys=keylines[:3]
    for i,line in enumerate(visible_keys):fig.text(.045,.18-i*.025,line,fontsize=8)
    if len(keylines)>3:fig.text(.045,.105,'전체 벽 이름: 같은 이름의 JSON 및 벽 이름표 그림',fontsize=8)
    fig.subplots_adjust(left=.045,right=.98,top=.83,bottom=.29,hspace=.5)
    stem=f'walls_{site}_{label}_LoD2_{REV}'
    save(fig,stem,dict(scope=site,prior='LoD2',building=bid,revision=REV,title=title,caption=note,faces=joins,
        direction_order=['남','동','북','서'],distance='sum of face horizontal widths; separated faces retain their own metric distance',
        discontinuous_corner_count=discontinuities,eval_area_m2=float(d['area'][ids].sum()),band_included=False,**misstats,
        raster={k:v for k,v in g.items() if k not in ['region','cell','face','counts','area']}))
    if len(keylines)>3:
        fig,ax=plt.subplots(figsize=(13,max(4,len(names)*.15)));ax.axis('off')
        ax.set_title(f'{label}: 벽 이름표',loc='left')
        half=math.ceil(len(names)/2)
        for j,txt in enumerate(names):ax.text(.02+.5*(j//half),.95-.9*(j%half)/half,txt,fontsize=9)
        fig.text(.05,.02,'짝이 맞으면 판단이 맞음 · '+TAG,fontsize=9)
        save(fig,stem+'_key',dict(scope=site,prior='LoD2',building=bid,labels=names,source_figure=stem))

def purity():
    rows=read(DOC/f'tables/purity_{REV}.json')['rows'];pick=[r for r in rows if r['scope'] in SITES and r['dominant_region']=='all']
    groups=[(s,p,k) for s in SITES for p,k in [('ALS','roof'),('LoD2','roof'),('LoD2','wall')]]
    fig,ax=plt.subplots(figsize=(13,8));y=np.arange(len(groups));left=np.zeros(len(groups))
    bins=['90% 이상','70~90%','70% 미만'];cols=['#245c87','#87b8d4','#dddfe2'];hatches=['','..','///']
    for bucket,col,hatch in zip(bins,cols,hatches):
        vals=np.array([next(r['area_fraction'] for r in pick if (r['scope'],r['prior'],r['face_kind'])==g and r['purity_bin']==bucket) or 0 for g in groups])*100
        ax.barh(y,vals,left=left,color=col,label=bucket,edgecolor='white',height=.68,hatch=hatch)
        for i,v in enumerate(vals):
            if v>=8:ax.text(left[i]+v/2,i,f'{v:.0f}%',ha='center',va='center',color='white' if bucket==bins[0] else '#202020',fontsize=10)
        left+=vals
    labels=[f'{SITES[s]}  |  {"항공 LiDAR" if p=="ALS" else "LoD2"} {"지붕" if k=="roof" else "벽"}' for s,p,k in groups]
    ax.set_yticks(y,labels);ax.invert_yaxis();ax.set_xlim(0,100);ax.set_xlabel('해당 종류의 평가 넓이 중 비율 (%)')
    ax.spines[['top','right']].set_visible(False);ax.legend(title='면 순도',ncol=3,loc='lower left',bbox_to_anchor=(.0,1.01),frameon=False)
    for cut in [2.5,5.5,8.5]:ax.axhline(cut,color='#dddddd',lw=.8)
    fig.suptitle('면별 판단의 섞임은 지역과 지붕·벽에 따라 다르다',x=.05,ha='left',fontsize=17,fontweight='bold')
    fig.text(.05,.03,'원래 면마다 가장 넓은 영역의 비율을 순도로 계산 · 작은 면도 개별 면으로 포함 · 지역은 서로 겹치므로 합산하지 않음 | '+TAG,fontsize=9)
    fig.subplots_adjust(left=.24,right=.96,top=.82,bottom=.12)
    save(fig,f'purity_{REV}',dict(title='면별 판단의 섞임은 지역과 지붕·벽에 따라 다르다',rows=pick,holdout_included=False,source=f'tables/purity_{REV}.json'))

def main():
    start=time.monotonic();check_locked();setup();ledger=Ledger();catalog=Catalog(ledger)
    held=set(read(JN/'holdout/scope_membership.json')['buildings'])
    for site in SITES:
        faces=catalog.context(site=site);cameras=Cameras(site,ledger)
        for prior in ['ALS','LoD2']:
            d=npz(OUT/f'{REV}/patches/{site}_{prior}.npz');assert not set(d['assigned_building'])&held
            plan_map(site,prior,d,faces,cameras)
            for bid in sorted(set(d['assigned_building'])-{''}):
                plan_map(site,prior,d,faces,cameras,bid)
                if prior=='LoD2':wall_strip(site,bid,d,faces)
    purity()
    dump(OUT/f'figure_inputs_{REV}.json',dict(entries=[r for r in ledger.entries.values() if not r['sealed']],scientific_verdict=None))
    dump(OUT/f'figures_complete_{REV}.json',dict(at=stamp(),seconds=time.monotonic()-start,scientific_verdict=None))

if __name__=='__main__':main()
