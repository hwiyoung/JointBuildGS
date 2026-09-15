#!/usr/bin/env python3
"""Surface-aware whole-R1 candidate judgments after input RGB context review."""
import argparse
import csv
import json
from pathlib import Path
import sys
import numpy as np
from scipy.spatial import cKDTree
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.path import Path as Polygon
from matplotlib import font_manager
from PIL import Image
sys.path.insert(0,'/repo')
from src.phd.region_view_support_v1 import sha256,object_basis,region_mask


def write(path,value):
    with path.open('x') as f:json.dump(value,f,indent=2,ensure_ascii=False,allow_nan=False)


def zoning(uv,zones):
    result=np.zeros(len(uv),np.uint8)
    for z in zones[1:]:result[Polygon(np.array(z['polygon'])).contains_points(uv,radius=1e-9)]=int(z['id'][1:])
    return result


def local_normals(xyz,cfg):
    tree=cKDTree(xyz);n=len(xyz);normals=np.empty((n,3));variation=np.empty(n);radius=np.empty(n)
    for start in range(0,n,4000):
        d,ids=tree.query(xyz[start:start+4000],k=cfg['normal_neighbors'],workers=2)
        p=xyz[ids];p-=p.mean(axis=1,keepdims=True);cov=np.einsum('nki,nkj->nij',p,p)/len(p[0])
        val,vec=np.linalg.eigh(cov);normals[start:start+len(p)]=vec[:,:,0];variation[start:start+len(p)]=val[:,0]/np.maximum(val.sum(1),1e-12);radius[start:start+len(p)]=d[:,-1]
    return normals,variation,radius


def project_rgb(points,v):
    c=points@np.array(v['R']).T+v['t'];q=c@np.array(v['K']).T
    return q[:,:2]/np.maximum(q[:,2:3],1e-9),c[:,2]


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',required=True);args=ap.parse_args();out=Path(args.output);out.mkdir(exist_ok=False)
    root=Path('/evidence');cfgpath=Path('/repo/configs/phd/r1_area_judgment_v1/review_v1.json');cfg=json.loads(cfgpath.read_text());write(out/'config.json',cfg)
    receipt=json.loads((root/'receipt.json').read_text())
    for name in ('surface_evidence.npz','per_view_relations.npz','coverage_grid.npz'):assert sha256(root/name)==receipt['files'][name]
    data=np.load(root/'surface_evidence.npz');per=np.load(root/'per_view_relations.npz');cover=np.load(root/'coverage_grid.npz');acfg=json.loads((root/'config.json').read_text())
    mx=data['mvs_xyz'];px=data['prior_xyz'];nm=len(mx);points=np.concatenate((mx,px));basis=object_basis(70);uv=points[:,:2]@basis.T;zones=cfg['zones'];zone=zoning(uv,zones);byid={int(z['id'][1:]):z for z in zones}
    gpath=Path('/repo',cfg['gravity_manifest']);up=np.array(json.loads(gpath.read_text())['gravity']['up']);up/=np.linalg.norm(up)
    old=np.load('/p1_source.npz');oldxyz=old['source_xyz'][old['whole_r1']];oldxy=old['source_native_xy'][old['whole_r1']].astype(int)
    ground_height=float(np.median(oldxyz@up))
    # Never fit normals across competing source surfaces.
    mn,mv,md=local_normals(mx,cfg);pn,pv,pd=local_normals(px,cfg)
    normals=np.concatenate((mn,pn));var=np.r_[mv,pv];radius=np.r_[md,pd];dot=np.abs(normals@up)
    good=(var<=cfg['maximum_surface_variation'])&(radius<=cfg['maximum_normal_radius_m'])
    height=points@up;ground=good&(dot>=cfg['ground_min_abs_dot_up'])&(height<=ground_height+cfg['ground_height_above_C1_median_m'])
    wall=good&(dot<=cfg['wall_max_abs_dot_up']);roof=good&~ground&~wall
    part=np.full(len(points),3,np.uint8);part[ground]=0;part[roof]=1;part[wall]=2
    # Geometric part names are diagnostics; semantic context remains separately reviewed.
    partnames={0:'낮은 수평면 후보',1:'지붕·경사면 후보',2:'외벽·급경사면 후보',3:'거친 표면·경계·법선 불확실'}
    kinds=np.array([byid[int(i)]['kind'] for i in zone]);building=np.isin(kinds,['building'])
    target=good&building&~ground
    excluded=((kinds=='landscape')&((height<=ground_height+cfg['landscape_low_height_above_C1_median_m'])|~good))|((kinds=='circulation')&ground)
    # Narrow passages can contain actual adjacent building walls; do not blanket-exclude them.
    target|=good&(kinds=='circulation')&wall
    views=json.loads(Path('/input/scene/split_manifest.json').read_text())['train'];names=[v['name'] for v in views];assert names==data['names'].tolist()
    structural_review=[]
    for item in cfg.get('visible_structural_polygons',[]):
        i=names.index(item['name']);v=views[i];q,z=project_rgb(points,v);inside=np.zeros(len(points),bool)
        for polygon in item['polygons']:inside|=Polygon(np.array(polygon)).contains_points(q)
        visible=np.r_[per['mvs'][i]>0,per['prior'][i]==1]
        selected=inside&(z>0)&visible&np.isin(zone,item['zones'])&good&~ground
        target|=selected;excluded[selected]=False
        structural_review.append(dict(name=item['name'],zones=item['zones'],selected_mvs_points=int(selected[:nm].sum()),selected_prior_points=int(selected[nm:].sum())))
    dist,_=cKDTree(oldxyz).query(mx,workers=2);c1=dist<=cfg['C1_current_point_match_m']
    judgments=np.zeros(len(points),np.uint8);reason=np.full(len(points),'AMBIGUOUS_INPUT_OR_CONTEXT',dtype='U80')
    judgments[excluded]=4;reason[excluded]='REVIEWED_LANDSCAPE_OR_CIRCULATION_CONTEXT'
    ml=data['mvs_relation'];support=data['mvs_view_count'];strong=(support>=3)&(data['mvs_camera_span_m']>=5)
    preserve=target[:nm]&(ml==1);complete=target[:nm]&np.isin(ml,[3,4]);correct=c1&strong&(ml==2)
    mj=judgments[:nm];mr=reason[:nm]
    mj[preserve]=1;mr[preserve]='CURRENT_PRIOR_AGREE_STABLE_BUILDING_SURFACE'
    mj[complete]=3;mr[complete]='SUPPORTED_CURRENT_SURFACE_PRIOR_MISSING_OR_BEHIND'
    mj[correct]=2;mr[correct]='C1_REVIEWED_CURRENT_GROUND_PRIOR_IN_FRONT'
    mj[c1&strong&(ml==1)]=1;mr[c1&strong&(ml==1)]='C1_BOUNDARY_CURRENT_PRIOR_AGREE'
    mr[(mj==0)&(support<3)]='FEWER_THAN_THREE_CURRENT_SUPPORT_VIEWS'
    mr[(mj==0)&(ml==2)]='PRIOR_IN_FRONT_OUTSIDE_REVIEWED_CORRECTION_CORE'
    mr[(mj==0)&~good[:nm]]='MIXED_SURFACE_OR_GEOMETRIC_BOUNDARY'
    cindex=names.index('DJI_20241217084553_0100_D.JPG');source=views[cindex]
    # Existing manually inspected non-building polygons; visibility required for current points.
    xy,z=project_rgb(mx,source);p1=json.loads(Path('/p1_config.json').read_text());ex=np.zeros(nm,bool)
    for poly in p1['manual_sources'][0]['polygons']:
        if poly['region']==4:ex|=Polygon(np.array(poly['xy'])).contains_points(xy)
    ex&=(per['mvs'][cindex]>0)&(z>0);mj[ex]=4;mr[ex]='VISIBLE_SOURCE_RGB_NON_BUILDING_EXCLUSION'
    # Prior source has its own judgment. An occluding current hit is never removal evidence.
    pc=data['prior_relation_counts'];pa=pc[:,1];behind=pc[:,2];front=pc[:,3];available=pc[:,1:4].sum(1)+pc[:,5]
    pq=judgments[nm:];pr=reason[nm:];compatible=target[nm:]&(pa>=3)&(data['prior_mvs_camera_span_m']>=5)&(pa/np.maximum(1,pa+behind)>=.67)
    pq[compatible]=1;pr[compatible]='PRIOR_SURFACE_CONFIRMED_IN_CURRENT_DEPTH_VIEWS'
    cam=px@np.array(source['R']).T+source['t'];native=cam@np.array(source['maps']['depth']['K']).T
    pix=np.floor(native[:,:2]/np.maximum(native[:,2:3],1e-9)+.5).astype(int);w=source['maps']['depth']['width'];h=source['maps']['depth']['height']
    mask=np.zeros((h,w),bool);mask[oldxy[:,1],oldxy[:,0]]=True;inside=(cam[:,2]>0)&(pix[:,0]>=0)&(pix[:,0]<w)&(pix[:,1]>=0)&(pix[:,1]<h)
    pc1=inside&mask[np.clip(pix[:,1],0,h-1),np.clip(pix[:,0],0,w-1)]
    old_upper=pc1&(behind>=3)&(behind/np.maximum(1,pa+behind)>=.67)&(per['prior'][cindex]==2)
    pq[old_upper]=2;pr[old_upper]='C1_VISIBLE_PRIOR_UPPER_SURFACE_CURRENT_BEHIND'
    pr[(pq==0)&(front>pa+behind)]='CURRENT_OCCLUSION_DOES_NOT_DISPROVE_PRIOR'
    pr[(pq==0)&(available==0)]='NO_COMPARABLE_CURRENT_DEPTH_FOR_PRIOR'
    assert set(np.unique(judgments))<=set(range(5)) and len(judgments)==len(points)
    assert np.all(c1[mj==2]) and np.all(pc1[pq==2])
    np.savez_compressed(out/'surface_judgments.npz',xyz=points,source=np.r_[np.zeros(nm,np.uint8),np.ones(len(px),np.uint8)],
        source_index=np.r_[np.arange(nm),np.arange(len(px))],zone=zone,part=part,judgment=judgments,reason=reason,
        normals=normals.astype(np.float32),surface_variation=var.astype(np.float32),normal_radius_m=radius.astype(np.float32),
        height_along_estimated_up=height.astype(np.float32),C1_current=c1,C1_prior=pc1)
    # Exact complete XY inventory. Sample-free cells stay unresolved, never nearest-label filled.
    nv,nu=cover['state'].shape;y,x=np.indices((nv,nu));griduv=np.column_stack((-135+(x.ravel()+.5)*.5,-65+(y.ravel()+.5)*.5));gz=zoning(griduv,zones)
    membership=np.floor((uv-[-135,-65])/.5).astype(int);flat=membership[:,1]*nu+membership[:,0]
    counts=np.zeros((nv*nu,5),np.uint32)
    for k in range(5):np.add.at(counts[:,k],flat[judgments==k],1)
    gj=np.full(nv*nu,0,np.uint8);active=(counts>0).sum(1);single=active==1;gj[single]=np.argmax(counts[single],axis=1)
    np.savez_compressed(out/'complete_R1_inventory.npz',zone=gz.reshape(nv,nu),coverage_state=cover['state'],sample_judgment_counts=counts.reshape(nv,nu,5),
        mixed_source_or_surface=active.reshape(nv,nu)>1,unsampled_cell=counts.sum(1).reshape(nv,nu)==0,unambiguous_sample_judgment=gj.reshape(nv,nu))
    colors=[cfg['colors'][str(k)] for k in range(5)];labelnames=[cfg['judgments'][str(k)] for k in range(5)]
    font_manager.fontManager.addfont('/font.ttf');plt.rcParams['font.family']=font_manager.FontProperties(fname='/font.ttf').get_name()
    rows=[];cards=[]
    for zid in sorted(byid):
        z=byid[zid];m=zone[:nm]==zid;p=zone[nm:]==zid;cells=gz==zid;scores=(per['mvs'][:,m]>0).sum(1);rank=np.argsort(-scores,kind='stable')[:3]
        selectedviews=[dict(name=names[i],supported_mvs_samples=int(scores[i])) for i in rank if scores[i]>0]
        row=dict(id=z['id'],name=z['name'],kind=z['kind'],review=z['review'],xy_cells=int(cells.sum()),xy_partition_m2=float(cells.sum()*.25),
            mvs_samples=int(m.sum()),prior_samples=int(p.sum()),mvs_judgments={labelnames[k]:int((mj[m]==k).sum()) for k in range(5)},
            prior_judgments={labelnames[k]:int((pq[p]==k).sum()) for k in range(5)},
            source_coverage={str(k):int((cover['state'].ravel()[cells]==k).sum()) for k in range(4)},
            parts={partnames[k]:int((part[:nm][m]==k).sum()) for k in range(4)},inspection_views=selectedviews)
        rows.append(row)
        if selectedviews:cards.append((zid,int(rank[0])))
    write(out/'zone_judgments.json',dict(scientific_verdict=None,zones=rows))
    with (out/'zone_judgments.csv').open('x',newline='') as f:
        records=[dict(id=r['id'],name=r['name'],xy_partition_m2=r['xy_partition_m2'],mvs_samples=r['mvs_samples'],prior_samples=r['prior_samples'],**r['mvs_judgments'],review=r['review']) for r in rows]
        w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
    features=[]
    for order,z in enumerate(zones):
        poly=np.array(z['polygon']);world=poly@basis+np.array(acfg['frame']['world_shift_xyz_m'][:2]);closed=np.vstack((world,world[0]))
        features.append(dict(type='Feature',properties=dict(id=z['id'],name=z['name'],precedence=order,role='inspection_context_not_uniform_surface_judgment'),geometry=dict(type='Polygon',coordinates=[closed.tolist()])))
    write(out/'inspection_zones_epsg25832.geojson',dict(type='FeatureCollection',crs=dict(type='name',properties=dict(name='EPSG:25832')),features=features))
    background=np.load('/overview/top_projection.npz')['rgb']
    fig,axs=plt.subplots(2,1,figsize=(17,16))
    axs[0].imshow(background,extent=[-135,70,35,-65],origin='upper',alpha=.8)
    for z in zones[1:]:
        poly=np.vstack((z['polygon'],z['polygon'][0]));axs[0].plot(poly[:,0],poly[:,1],c='#147d88',lw=1.3)
    for z in zones:
        x,y=z['label_xy'];axs[0].text(x,y,z['id'],ha='center',va='center',fontsize=10,weight='bold',bbox=dict(facecolor='white',alpha=.9,edgecolor='#147d88',pad=3))
    axs[0].set_title('R1 전체 검토구역 · 구역 내부도 지붕/외벽/지면과 출처를 나누어 판단',fontsize=15)
    for k in [0,4,3,1,2]:
        mask=mj==k;axs[1].scatter(uv[:nm][mask,0],uv[:nm][mask,1],s=3,c=colors[k],label=labelnames[k],rasterized=True)
    axs[1].legend(loc='upper left',ncol=5,fontsize=11,markerscale=3);axs[1].set_title('현재 MVS 표면별 판단 초안 · 보정은 C1 확인 대응에 한정 / 회색도 검토 후 유보',fontsize=14)
    for ax in axs:ax.set_xlim(-135,70);ax.set_ylim(35,-65);ax.set_aspect('equal');ax.set_xlabel('객체축 u [m]');ax.set_ylabel('객체축 v [m]')
    fig.tight_layout();fig.savefig(out/'R1_whole_area_judgment.png',dpi=155);fig.savefig(out/'R1_whole_area_judgment.pdf');plt.close(fig)
    fig,axs=plt.subplots(1,2,figsize=(18,6))
    for ax,xx,jj,title in zip(axs,[mx,px],[mj,pq],['현재 MVS 표면','과거 ALS 표면']):
        q=xx[:,:2]@basis.T
        for k in [0,4,3,1,2]:
            m=jj==k;ax.scatter(q[m,0],q[m,1],s=2,c=colors[k],label=labelnames[k])
        ax.set_title(title);ax.set_xlim(-135,70);ax.set_ylim(35,-65);ax.set_aspect('equal')
    axs[0].legend(loc='upper left',fontsize=8);fig.suptitle('출처별 판단을 분리 · 같은 XY의 과거 상부 표면과 현재 지면은 별도 표본',fontsize=14)
    fig.tight_layout();fig.savefig(out/'R1_source_separated_judgment.png',dpi=150);plt.close(fig)
    # Auditable region context cards: only currently depth-supported points are projected.
    allcards=[]
    for start in range(0,len(cards),4):
        fig,axs=plt.subplots(2,2,figsize=(16,11))
        for ax,(zid,i) in zip(axs.ravel(),cards[start:start+4]):
            view=views[i];imagepath=Path('/input/scene/images')/view['name'];ax.imshow(Image.open(imagepath))
            m=(zone[:nm]==zid)&(per['mvs'][i]>0);xy,_=project_rgb(mx[m],view)
            ax.scatter(xy[:,0],xy[:,1],s=4,c=np.array(colors)[mj[m]],alpha=.7)
            if len(xy):
                lo=xy.min(0)-50;hi=xy.max(0)+50;ax.set_xlim(max(0,lo[0]),min(view['width'],hi[0]));ax.set_ylim(min(view['height'],hi[1]),max(0,lo[1]))
            ax.set_title(byid[zid]['id']+' '+byid[zid]['name']+'\n'+view['name'],fontsize=10);ax.axis('off')
            allcards.append(dict(zone=byid[zid]['id'],name=view['name'],rgb_sha256=sha256(imagepath),shown_points=int(m.sum())))
        for ax in axs.ravel()[len(cards[start:start+4]):]:ax.axis('off')
        fig.tight_layout();fig.savefig(out/f'zone_review_{start//4+1}.png',dpi=140);plt.close(fig)
    write(out/'inspected_context_cards.json',allcards)
    stats=dict(status='PASS_WHOLE_R1_CANDIDATE_JUDGMENT_DRAFT',scientific_verdict=None,config_sha256=sha256(cfgpath),
        script_sha256=sha256(__file__),input_audit_receipt_sha256=sha256(root/'receipt.json'),gravity_manifest_sha256=sha256(gpath),
        ground_height_from_C1_median=ground_height,all_mvs_points=nm,all_prior_points=len(px),all_xy_cells=nv*nu,
        total_zone_cells=sum(r['xy_cells'] for r in rows),zone_count=len(rows),unassigned_points=0,unassigned_cells=0,
        mvs_judgments={labelnames[k]:int((mj==k).sum()) for k in range(5)},prior_judgments={labelnames[k]:int((pq==k).sum()) for k in range(5)},
        caution='Full spatial accounting includes explicit unresolved and sample-free cells; not complete semantic ground truth or exact facade area. Context polygons are approximate and height is retained in point records.',
        structural_source_review=structural_review,training_runs=0,manual_loss_weights=None,files={p.name:sha256(p) for p in out.iterdir() if p.is_file()})
    assert stats['total_zone_cells']==82000 and sum(stats['mvs_judgments'].values())==nm
    write(out/'receipt.json',stats);print(json.dumps(stats,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
