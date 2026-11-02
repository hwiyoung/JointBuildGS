"""Input-only common height boundaries and CPU counts for the four-by-four bins."""
import csv
import numpy as np
from common import *
ROOT=OUT/'r8_lod2_cause'

def clip(ring,lo,hi):
    q=np.asarray(ring,float)
    if np.allclose(q[0],q[-1]):q=q[:-1]
    for axis,bound,sign in [(0,lo[0],1),(0,hi[0],-1),(1,lo[1],1),(1,hi[1],-1)]:
        if not len(q):return q
        result=[]
        for a,b in zip(q,np.roll(q,-1,axis=0)):
            ina=sign*(a[axis]-bound)>=0;inb=sign*(b[axis]-bound)>=0
            if ina:result.append(a)
            if ina!=inb:result.append(a+(b-a)*(bound-a[axis])/(b[axis]-a[axis]))
        q=np.asarray(result)
    return q

def bins(xyz,b):
    uv=xyz[:,:2].astype('f8')@np.asarray(b['basis']).T;lo=np.asarray(b['lo']);hi=np.asarray(b['hi'])
    d=np.linalg.norm(np.maximum(np.maximum(lo-uv,uv-hi),0),axis=1)
    x=np.where(d==0,0,np.where(d<=50,1,np.where(d<=200,2,3))).astype('i1')
    z=xyz[:,2].astype('f8');t=b['height_local_m']
    h=np.where(z<t[0],0,np.where(z<=t[1],1,np.where(z<=t[2],2,3))).astype('i1')
    assert np.isfinite(xyz).all(), 'nonfinite Gaussian position requires explicit unavailable row'
    return x,h

def writecsv(path,rows):
    with path.open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def main():
    lock=json.loads((CFG/'cause_r8_spatial.lock.r1.json').read_text())
    for p,h in lock['files'].items():assert sha(p)==h,p
    frame=json.loads((REPO/'configs/phd/main_prep_measure_v1/prep_v5.json').read_text())
    angle=np.deg2rad(frame['frame']['u_axis_angle_degrees_ccw_from_easting']);basis=np.array([[np.cos(angle),np.sin(angle)],[np.sin(angle),-np.cos(angle)]])
    shift=np.array(frame['frame']['world_shift_xyz_m']);bridge=frame['frame']['z_bridge_als_lod2_m']
    rng=json.loads(Path(lock['range']).read_text());lo=np.array([rng['eval_u'][0],rng['eval_v'][0]]);hi=np.array([rng['eval_u'][1],rng['eval_v'][1]])
    buildings=json.loads(Path(lock['lod2']).read_text());samples={'ground':[],'roof':[]};surfaces=[]
    for building in buildings:
        for kind in samples:
            for surface in building['surfaces'][kind]:
                local=np.asarray(surface['ext'],float)-shift;local[:,2]+=bridge
                uvz=local.copy();uvz[:,:2]=local[:,:2]@basis.T;q=clip(uvz,lo,hi)
                if len(q)<3:continue
                area=abs(np.sum(q[:,0]*np.roll(q[:,1],-1)-q[:,1]*np.roll(q[:,0],-1)))/2
                if area<=1e-8:continue
                unique=np.unique(q,axis=0);samples[kind].extend(unique[:,2].tolist())
                surfaces.append(dict(building=building['id'],surface=surface['id'],kind=kind,clipped_uvz=unique.tolist()))
    index=json.loads(Path(lock['camera_index']).read_text());centres=[]
    for name,meta in sorted(index['views'].items()):
        W=np.array(meta['W2C']);c=-W[:3,:3].T@W[:3,3];centres.append(dict(camera=name,xyz=c.tolist()))
    assert len(centres)==203
    ground=float(np.median(samples['ground']));roof=float(max(samples['roof']));camera=float(np.median([r['xyz'][2] for r in centres]));thresholds=[ground,roof+10,camera]
    assert thresholds[0]<thresholds[1]<thresholds[2],thresholds
    b=dict(at=stamp(),basis=basis.tolist(),lo=lo.tolist(),hi=hi.tolist(),height_local_m=thresholds,
        height_absolute_working_m=[z+shift[2] for z in thresholds],ground_local_m=ground,roof_max_local_m=roof,camera_median_local_m=camera,
        frame='EPSG:25832 XY, local height = DHHN2016 prior Z + 45.7 - 604; camera/model native local Z',
        height_labels=['지면 아래','지면 ~ 지붕 최고 + 10 m','지붕+10 ~ 카메라 중앙값','카메라 중앙값 위'],
        height_boundary_names=['지면','지붕 최고 + 10 m','카메라 중앙값'],
        xy_labels=['평가 상자 안','상자 밖 50 m 안','50~200 m','200 m 넘음'],
        ground_samples=len(samples['ground']),roof_samples=len(samples['roof']),surfaces=surfaces,cameras=centres,scientific_verdict=None)
    dump(ROOT/'boundaries.json',b);dump(CFG/'cause_r8_boundaries.lock.json',dict(at=stamp(),sha256=sha(ROOT/'boundaries.json'),rules_lock_sha256=sha(CFG/'cause_r8_spatial.lock.r1.json'),scientific_verdict=None))
    counts=[];gradrows=[]
    config=json.loads((CFG/'cause_r8_lod2.json').read_text())
    for row in config['rows']:
        dest=ROOT/'states'/row['key'];s=dict(np.load(dest/'arrays.npz'));x,h=bins(s['xyz'],b);tags=s['tag'].astype('i1')
        names=['SfM','사전 정보'] if row['family']=='base' else ['배경','패치','풀림']
        fine=tags.copy()
        if row['key']=='r8_LoD2_7000':fine[(tags==2)&(s['released_at']!=100)]=3;names=['배경','패치','풀림: 100회 자손','풀림: 그 밖']
        group=fine.astype('i4')*16+x*4+h
        np.savez_compressed(dest/'groups.npz',group=group,xy=x,height=h,provenance=fine)
        for t,name in enumerate(names):
            for xi in range(4):
                for zi in range(4):
                    mask=group==t*16+xi*4+zi;n=int(mask.sum())
                    counts.append(dict(state=row['key'],provenance=name,tag=t,xy_bin=xi,height_bin=zi,count=n,
                        longest_axis_median_m=float(np.median(s['longest_axis'][mask])) if n else None,
                        opacity_median=float(np.median(s['opacity'][mask])) if n else None))
        if row['gradient_requested']:
            inv=json.loads((dest/'inventory.json').read_text())['gradient'];gradrows.append(dict(state=row['key'],population='render PLY before densification',status=inv['status'],reason=inv.get('reason')))
            cp=dest/'checkpoint_gradient_arrays.npz'
            if cp.exists():
                a=dict(np.load(cp));cx,ch=bins(a['xyz'],b)
                for t,name in enumerate(['배경','패치','풀림']):
                    for xi in range(4):
                        for zi in range(4):
                            mask=(a['tag']==t)&(cx==xi)&(ch==zi);n=int(mask.sum());above=int((mask&a['gradient_above']).sum())
                            gradrows.append(dict(state=row['key'],population='complete checkpoint after densification, reset accumulators',status='AVAILABLE_SEPARATE_POPULATION',
                                provenance=name,xy_bin=xi,height_bin=zi,count=n,above=above,fraction=above/n if n else None,denom_positive=int((mask&(a['gradient_denom']>0)).sum()),threshold=inv['threshold']))
        print('SPATIAL',row['key'],len(group),flush=True)
    dump(ROOT/'counts.json',dict(rows=counts,scientific_verdict=None));writecsv(ROOT/'counts.csv',counts)
    dump(ROOT/'gradient.json',dict(rows=gradrows,scientific_verdict=None));print('BOUNDARIES',thresholds,flush=True)

if __name__=='__main__':main()
