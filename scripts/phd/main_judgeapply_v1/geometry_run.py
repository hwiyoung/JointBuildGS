"""Production regional geometry. Reference values are never opened here."""
from common import *
from inherit import functions
from scipy.spatial import cKDTree
import subprocess,resource,warnings
BASE=O/'r1';S=HERE/'inherited'
scope=dict(np=np,cKDTree=cKDTree,Path=Path,sha=sha,dump=dump,now=now,subprocess=subprocess,time=time,BASE=BASE,S=S)
fit_normals,=functions('geometry.py',['fit_normals'],scope)
build,run=functions('cylinder.py',['build','run'],scope)
attach,=functions('main_widen0_v2__face_assignment.py',['attach'],scope)
functions('main_widen0_v2__face_assignment.py',['inside_triangle','triangle_distance'],scope)
DR=PH/'main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1'
def inputs(site,prior):
    source=TG/'stage0_r1/inputs'/f'{site}_{prior}.npz';d=loadz(source)
    idx=np.flatnonzero(d['in_eval']&np.isin(d['kind'],cfg()['priors'][prior]));d={k:v[idx] for k,v in d.items()}
    unit=loadz(S0/'s61/box'/site/prior/'units.npz',['loc_t1','loc_t2','loc_extra'])
    d.update(source_index=idx,patch_id=np.array([f'{prior}:{site}:{i}' for i in idx]),tangent1=unit['loc_t1'][idx],tangent2=unit['loc_t2'][idx],source_extra=unit['loc_extra'][idx])
    d['u_mvs']=d['mvs_a_u'].astype(float)
    if prior=='ALS':
        records=json.loads((DR/'s02_box'/site/'lod2_surfaces.json').read_text())['surfaces']
        mesh=loadz(DR/'s02_box'/site/'lod2_mesh.npz')
        print('ALS_ID_MESH',site,{k:list(v.shape) for k,v in mesh.items()},flush=True)
        faces,ordered=attach(d['centre'],np.abs(d['normal'][:,2])>=np.cos(np.pi/4),records,mesh)
        d['building']=np.array([ordered[i]['building'] if i>=0 else '' for i in faces]);d['identity_face']=faces
    d['sigma_P_m']=d['u_prior'].astype(float) if prior=='ALS' else np.array([cfg()['geometry']['prior_sigma_m']['LoD2_roof'].get(str(rt),.11) if k==1 else .144 for rt,k in zip(d['roof_type'],d['kind'])])
    d['region_name']=np.full(len(idx),site);d['prior']=np.full(len(idx),prior)
    return d
def main(site):
    assert site in cfg()['sites'];assert json.loads((O/'input_gate.json').read_text())['status']=='PASS_INPUT_ALIGNMENT'
    BASE.mkdir(exist_ok=True);start=time.monotonic()
    if not (BASE/'cylinders').exists():build()
    rows=[]
    for prior in ['LoD2','ALS']:
        dest=O/'geometry_raw'/f'{site}__{prior}.npz'
        if dest.exists():rows.append(json.loads(dest.with_suffix('.json').read_text()));continue
        t=time.monotonic();d=inputs(site,prior);N=len(d['centre']);points=UN/'points'/site
        if prior=='ALS':
            a=np.load(points/'als_xyz.npy');d['old_normal']=d['normal'].copy();d.update(fit_normals(a,d['centre']));del a
            v=run(points/'als_xyz.npy',d['centre'],d['normal'],[.75],O/'cylinders'/f'{site}__ALS_prior.bin')
            d['prior_n']=v[:,1,0,0].astype(int);d['prior_height_m']=np.where(d['prior_n']>=4,v[:,1,0,1],np.nan);del v
        else:d['prior_n']=np.full(N,-1,int);d['prior_height_m']=np.zeros(N)
        v=run(points/'mvs_a_xyz.npy',d['centre'],d['normal'],[.075,.125],O/'cylinders'/f'{site}__{prior}_mvs.bin')
        ri=np.where(d['kind']==1,0,1);hi=np.where(d['kind']==1,1,0);ii=np.arange(N);a=v[ii,hi,ri,:]
        d.update(n=a[:,0].astype(int),mvs_mean_m=a[:,1],mvs_median_m=a[:,2],mvs_sd_m=a[:,3],mvs_face_m=a[:,5],n5=v[ii,0,ri,0].astype(int),n10=v[ii,1,ri,0].astype(int),d10_m=v[ii,1,ri,1]-d['prior_height_m'])
        d['d_m']=d['mvs_mean_m']-d['prior_height_m'];del v
        # Preserve finite original uncertainty and recorded absence. The original
        # UNCERT status proves the same ring computation was already attempted.
        d['u_recomputed_status']=d['mvs_a_status'];d['u_source']=np.full(N,'UNCERT regional original ring; no floor or imputation')
        savez(dest,**d)
        rec=dict(at=now(),site=site,prior=prior,count=N,area_m2=float(d['area'].sum()),building_count=len(set(d['building'])-{''}),missing_building_count=int((d['building']=='').sum()),missing_u_count=int((~np.isfinite(d['u_mvs'])).sum()),seconds=time.monotonic()-t,output_sha256=sha(dest),GT_read=False,scientific_verdict=None)
        dump(dest.with_suffix('.json'),rec);rows.append(rec);print('GEOMETRY_COMPLETE',json.dumps(rec),flush=True)
    rec=dict(at=now(),site=site,seconds=time.monotonic()-start,rows=rows,peak_rss_gib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024**2,scientific_verdict=None)
    dump(O/'timing'/f'{site}_geometry.json',rec);progress(f'{site} 기하 셈 {rec["seconds"]:.1f}초 완료. 참값 읽기 없음.')
if __name__=='__main__':main(sys.argv[1])
