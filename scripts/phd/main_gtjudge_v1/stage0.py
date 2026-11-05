"""Stage 0 normal-ray scoring and pointcloud cylinder accuracy, cached once."""
import sys,gc,time,traceback
import numpy as np
from scipy.spatial import cKDTree
from common import *
from geometry_add1 import reference,rows,read_surface,MeshScene,Grid,sample_normals
from normal_line import measure,values
from cylinder import Cylinder

def main(site,prior,only='all'):
    cfg();stage_lock(0);start=time.monotonic();stem=f'{site}__{prior}';root=O/'scenes'/stem
    ref=reference(site);row=rows(site,prior,ref);tree=cKDTree(ref['xyz']);radius=float(ref['radius'])
    oldcell=row['score_cell_1p0'];tau=row['row_tau_m'];pool=[];signals=[]
    with (R/'docs/experiments/phd/main_release_v1/tables/stage0/tau_values.csv').open() as f:
        tolerance=next(x for x in csv.DictReader(f) if x['site']==site and x['prior']==prior)
    cy=None
    methods=METHODS if only=='all' else ['prior','mvs'] if only=='gate' else [only]
    for method in methods:
        out=root/'distances'/f'{method}.npz';meta=out.with_suffix('.json')
        cached=None
        if out.exists() and meta.exists():
            oldmeta=json.loads(meta.read_text())
            if prior!='ALS' or oldmeta.get('accuracy_ALS_all_nonwall'):
                print('REUSE_DISTANCE',stem,method,flush=True);continue
            cached=loadz(out)
        original=score_dir(site,prior,method);v=json.loads((original/'values.json').read_text());data=loadz(original/'points.npz')
        V,F=read_surface(v['mesh']);sc=MeshScene(V,F)
        s,offset=(cached['row_s'],cached['row_offset']) if cached is not None else measure(sc,row['xyz'],row['normal'],row['wall'])
        # Signs for the saved nearest comparison, with the historical magnitude unchanged.
        near=sc.sc.compute_closest_points(sc.o3d.core.Tensor(row['xyz'].astype('f4')))['points'].numpy()
        oldsign=np.where(((near-row['xyz'])*row['normal']).sum(1)<0,-1.,1.)
        n=oldcell==0;signal=bool(n.sum()>=1000 and np.mean(np.isfinite(s[n])&(abs(s[n])<=tau[n]))<.9)
        rerun=False
        if method in ['prior','mvs'] and signal:
            first=s.copy();s,offset=measure(sc,row['xyz'],row['normal'],row['wall'],extra_diagonals=True);rerun=True
            savez(root/'distances'/f'{method}_first_five.npz',row_s=first)
        del sc,near;gc.collect()
        # Result sampling is inherited exactly; regenerate triangle IDs only because the old cache lacks them.
        shared=O/'shared'/site/v['mesh_sha256'];shared.mkdir(parents=True,exist_ok=True)
        qfile=shared/('cylinder_roof.npz' if prior=='ALS' else 'cylinder.npz')
        if qfile.exists():q=loadz(qfile)
        else:
            P,N=sample_normals(V,F,Grid(site),data['sample_xyz'])
            euclidean,idx=tree.query(P,workers=4)
            nearest_normal=ref['normal'][idx].copy()
            if prior=='ALS':nearest_normal[nearest_normal[:,2]<0]*=-1
            N*=np.where((N*nearest_normal).sum(1)<0,-1.,1.)[:,None]
            wall=ref['wall'][idx] if prior=='LoD2' else np.zeros(len(idx),bool);length=np.where(wall,5.,10.);eligible=euclidean<=1
            if cy is None:cy=Cylinder(ref['xyz'])
            qs=np.full(len(P),np.nan);qi=np.full(len(P),-1,'i4')
            qs[eligible],qi[eligible]=cy.query(P[eligible],N[eligible],length[eligible],radius)
            q=dict(sample_s=qs,sample_reference_index=qi,sample_eligible=eligible,sample_euclidean_m=euclidean,
                sample_normal=N.astype('f4'),sample_nearest=idx)
            savez(qfile,**q)
            dump(qfile.with_suffix('.json'),dict(at=now(),radius_m=radius,samples=len(P),reference_points=len(ref['xyz']),
                excluded_no_reference_1m=int((~eligible).sum()),mesh=v['mesh'],mesh_sha256=v['mesh_sha256'],scientific_verdict=None))
            del P,N;gc.collect()
        # Preserve exact RELEASE reference-row attribution for result-side per-case bins.
        assignment=loadz(RL/'stage0'/stem/(method+'_assignment.npz'))['sample_reference_row']
        qsigned_old=data['sample_region_distance_m']*np.where(np.einsum('ij,ij->i',ref['xyz'][q['sample_nearest']]-data['sample_xyz'],ref['normal'][q['sample_nearest']])<0,-1.,1.)
        savez(out,row_s=s,row_offset=offset,row_nearest_signed=oldsign*data['row_distance_m'],
            sample_s=q['sample_s'],sample_eligible=q['sample_eligible'],sample_reference_row=assignment,
            sample_tau=np.where(ref['wall'][q['sample_nearest']]&(prior=='LoD2'),float(tolerance['wall_tau_m']),float(tolerance['roof_tau_m'])),sample_nearest_tau=data['sample_tau_m'],sample_nearest_signed=qsigned_old,
            sample_old_eligible=np.isfinite(data['sample_region_distance_m'])&np.isfinite(data['sample_region_lat_m'])&(data['sample_region_lat_m']<=.5))
        p1=float(np.mean(np.isfinite(s[n])&(abs(s[n])<=tau[n]))*100) if n.any() else None
        dump(meta,dict(at=now(),site=site,prior=prior,method=method,mesh=v['mesh'],mesh_sha256=v['mesh_sha256'],
            radius_m=radius,accuracy_ALS_all_nonwall=prior=='ALS',old_both_correct_n=int(n.sum()),normal_within_pct=p1,
            initial_signal=signal if method in ['prior','mvs'] else None,implementation_correction_attempts=int(rerun),
            remaining_signal=bool(n.sum()>=1000 and p1<90) if method in ['prior','mvs'] else None,
            accuracy_sample_source=str(original/'points.npz'),scientific_verdict=None))
        print('DISTANCE_DONE',stem,method,'old_both_correct',p1,'seconds',time.monotonic()-start,flush=True)
        del V,F,data,q;gc.collect()
    if cy:cy.close()
    for method in METHODS:
        p=root/'distances'/f'{method}.npz'
        if not p.exists():continue
        z=loadz(p);idx=z['sample_reference_row'];qc=np.full(len(idx),-1,'i1');ok=idx>=0;qc[ok]=oldcell[idx[ok]]
        for case in [0,1,2,4,3,-1,'all']:
            mask=oldcell==case if case!='all' else np.ones(len(oldcell),bool)
            qmask=qc==case if case!='all' else np.ones(len(qc),bool)
            for distance,label,eligible in [('normal_line','row_s','sample_eligible'),('nearest_comparison','row_nearest_signed','sample_old_eligible')]:
                rv=values(z[label][mask],tau[mask]);qv=values(z['sample_s' if distance=='normal_line' else 'sample_nearest_signed'][qmask],z.get('sample_nearest_tau',z['sample_tau'])[qmask] if distance=='nearest_comparison' else z['sample_tau'][qmask],z[eligible][qmask])
                pool.append(dict(site=site,prior=prior,case_id=case,case_basis='RECOUNT nearest cells',method=method,distance=distance,
                    n_gt=rv['n'],small='적음' if rv['n']<1000 else '',completeness_pct=rv['within_pct'],accuracy_pct=qv['within_pct'],
                    **{'gt_'+k:v for k,v in rv.items()},**{'result_'+k:v for k,v in qv.items()}))
    table('stage0/'+stem,pool)
    dump(root/'stage0_progress.json',dict(at=now(),methods=[m for m in METHODS if (root/'distances'/f'{m}.npz').exists()],scientific_verdict=None))

if __name__=='__main__':
    import fcntl
    lock=O/'queue'/('stage0_'+sys.argv[1]+'__'+sys.argv[2]+'.lock');lock.parent.mkdir(exist_ok=True)
    with lock.open('a') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX);main(*sys.argv[1:])
