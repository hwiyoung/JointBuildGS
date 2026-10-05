"""Input-reviewed structural contexts, conservative two-surface local prior masks."""
import csv
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from scipy.spatial import cKDTree
from matplotlib.path import Path as Polygon
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager

ROOT=Path('/run');CONFIG=json.loads(Path('/zones.json').read_text())
font_manager.fontManager.addfont('/font.ttf');plt.rcParams['font.family']=font_manager.FontProperties(fname='/font.ttf').get_name()
theta=np.deg2rad(70);B=np.array([[np.cos(theta),np.sin(theta)],[np.sin(theta),-np.cos(theta)]])
PALETTE=np.array([[154,157,163],[39,135,186],[230,160,26],[154,89,181],[71,123,85]])
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,x):
    with Path(p).open('x') as f:json.dump(x,f,ensure_ascii=False,indent=2)
def normals(points):
    tree=cKDTree(points);out=np.empty((len(points),3));good=np.zeros(len(points),bool)
    for start in range(0,len(points),4000):
        d,ix=tree.query(points[start:start+4000],k=20,workers=2);a=points[ix];a=a-a.mean(1,keepdims=True)
        values,vectors=np.linalg.eigh(np.einsum('nki,nkj->nij',a,a)/20)
        out[start:start+len(a)]=vectors[:,:,0];good[start:start+len(a)]=(values[:,0]/np.maximum(values.sum(1),1e-12)<=.06)&(d[:,-1]<=4)
    return out,good
def zone_ids(points,zones):
    uv=points[:,:2]@B.T;ids=np.zeros(len(points),np.uint8)
    for i,z in enumerate(zones):ids[Polygon(z['polygon']).contains_points(uv,radius=1e-9)]=i
    return ids

def review(region):
    root=ROOT/region;ev=np.load(root/'audit/result/surface_evidence.npz');mx=ev['mvs_xyz'];px=ev['prior_xyz']
    zones=[]
    for row in CONFIG[region]:
        zid,name,kind,u0,u1,v0,v1,test=row
        zones.append(dict(id=zid,name=name,kind=kind,polygon=[[u0,v0],[u1,v0],[u1,v1],[u0,v1]],correction_test=test))
    mi=zone_ids(mx,zones);pi=zone_ids(px,zones)
    _,mg=normals(mx);_,pg=normals(px)
    building=np.array([z['kind']=='building' for z in zones]);correction=np.array([z['correction_test'] for z in zones])
    mj=np.zeros(len(mx),np.uint8);pj=np.zeros(len(px),np.uint8)
    # No whole courtyard/circulation is silently assigned a building or accuracy label.
    target=mg&building[mi];rel=ev['mvs_relation'];mj[target&(rel==1)]=1;mj[target&np.isin(rel,[3,4])]=3
    mj[target&(rel==2)&correction[mi]]=2
    counts=ev['prior_relation_counts'];same=counts[:,1];behind=counts[:,2]
    ptarget=pg&building[pi]
    pj[ptarget&(same>=3)&(same/np.maximum(1,same+behind)>=.67)]=1
    pj[ptarget&correction[pi]&(behind>=3)&(behind/np.maximum(1,same+behind)>=.67)]=2
    output=root/'review';output.mkdir()
    metadata=dict(region=region,zones=zones,scientific_verdict=None,correction_semantics=CONFIG['correction_semantics'],
        inspection_source='audit/result/views_1.png plus full_input_atlas.png',inspection_sha256=sha(root/'audit/result/views_1.png'),
        normal_neighbors=20,max_variation=.06,max_radius_m=4,relation_receipt_sha256=sha(root/'audit/result/receipt.json'),
        mvs_counts={str(i):int((mj==i).sum()) for i in range(5)},prior_counts={str(i):int((pj==i).sum()) for i in range(5)})
    write(root/'review_zones.json',metadata)
    np.savez_compressed(output/'judgments.npz',mvs_judgment=mj,prior_judgment=pj,mvs_zone=mi,prior_zone=pi)
    uv=mx[:,:2]@B.T;bounds=zones[0]['polygon'];fig,axs=plt.subplots(1,2,figsize=(17,10))
    for ax,colors,title in [(axs[0],ev['mvs_rgb']/255,'현재 MVS · 원본 RGB'),(axs[1],PALETTE[mj]/255,'입력 검토 후보 · 주황은 prior 해제 가설')]:
        ax.scatter(uv[:,0],uv[:,1],s=3,c=colors)
        for z in zones[1:]:
            p=np.array(z['polygon']);closed=np.vstack([p,p[0]]);ax.plot(closed[:,0],closed[:,1],color='#f4d03f',lw=.8)
            ax.text(*p.mean(0),z['id'],fontsize=8,ha='center',bbox=dict(facecolor='white',alpha=.8,edgecolor='none'))
        ax.set_xlim(bounds[0][0],bounds[1][0]);ax.set_ylim(bounds[2][1],bounds[0][1]);ax.set_aspect('equal');ax.set_title(title);ax.set_xlabel('u [m]');ax.set_ylabel('v [m]')
    fig.suptitle(region+' 전체 구역 · 보존 / 보정 가설 / 보완 / 유보');fig.tight_layout();fig.savefig(output/'whole_area_judgment.png',dpi=140);plt.close(fig)
    with (output/'zone_judgments.csv').open('x') as f:
        w=csv.writer(f);w.writerow(['zone','name','mvs_total','preserve','correction_hypothesis','complete','unresolved','prior_correction'])
        for i,z in enumerate(zones):w.writerow([z['id'],z['name'],int((mi==i).sum())]+[int(((mi==i)&(mj==k)).sum()) for k in [1,2,3,0]]+[int(((pi==i)&(pj==2)).sum())])
    write(output/'receipt.json',dict(status='PASS_INPUT_REVIEW_HYPOTHESES',scientific_verdict=None,**{k:metadata[k] for k in ['mvs_counts','prior_counts']},files={p.name:sha(p) for p in output.iterdir() if p.is_file()}))
    return mx,px,mj,pj

def masks(region,mx,px,mj,pj,inputs):
    root=ROOT/region;output=root/'masks';output.mkdir();views=json.loads((inputs/'scene/split_manifest.json').read_text())['train']
    current_tree=cKDTree(mx);prior_tree=cKDTree(px);rows=[];total=0
    for i,v in enumerate(views):
        name=Path(v['name']).stem;pd=np.load(inputs/'prior/raw_depth'/(name+'.npy'));md=np.load(inputs/'mvs_rgb/raw_depth'/(name+'.npy'))
        valid=np.isfinite(pd)&(pd>0)&np.isfinite(md)&(md>pd+1.)
        y,x=np.nonzero(valid);K=np.array(v['K']);R=np.array(v['R']);t=np.array(v['t'])
        keep=np.zeros(pd.shape,bool)
        if len(x):
            pp=(np.column_stack([x+.5,y+.5,np.ones(len(x))])@np.linalg.inv(K).T*pd[y,x,None]-t)@R
            d,ix=prior_tree.query(pp,workers=2);selected=(d<=.9)&(pj[ix]==2)
            if selected.any():
                xx=x[selected];yy=y[selected]
                mp=(np.column_stack([xx,yy,np.ones(len(xx))])@np.linalg.inv(K).T*md[yy,xx,None]-t)@R
                distance,j=current_tree.query(mp,workers=2);active=(distance<=1.2)&(mj[j]==2)
                keep[yy[active],xx[active]]=True
        path=output/(name+'.npy');np.save(path,keep,allow_pickle=False);count=int(keep.sum());total+=count
        rows.append(dict(name=name,path=path.name,sha256=sha(path),pixels=count))
    status='PASS' if total else 'NO_SUPPORTED_INTERVENTION'
    receipt=dict(status=status,region=region,scientific_verdict=None,reviewed_correction_surfaces=True,masks=rows,total_pixels=total,
        contributing_views=sum(r['pixels']>0 for r in rows),mask_source='Reviewed hypotheses, not reference geometry or confirmed temporal-change labels',
        policy='Original prior RGB rays (+0.5) and MVS resampled integer rays; both endpoints near separately reviewed correction samples; per-view MVS > prior + 1m; nearest-prior distance <=0.9m, nearest-current <=1.2m',
        outside_multiplier=1,inside_multiplier=0,base_prior_weight=.005,native_protection_retained=True)
    write(output/('receipt.json' if total else 'no_intervention.json'),receipt)
    print(json.dumps(dict(region=region,status=status,total_pixels=total,contributing_views=receipt['contributing_views'])),flush=True)

for region in ['R2','R3','R4','R5']:
    mx,px,mj,pj=review(region);masks(region,mx,px,mj,pj,ROOT/region/'preparation/input')
j=np.load('/r1review/surface_judgments.npz');m=j['source']==0;p=~m
(ROOT/'R1').mkdir(exist_ok=True)
masks('R1',j['xyz'][m],j['xyz'][p],j['judgment'][m],j['judgment'][p],Path('/r1input'))
