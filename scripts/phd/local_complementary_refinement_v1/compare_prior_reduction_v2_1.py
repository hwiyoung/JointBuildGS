"""Read-only reanalysis: global prior reduction versus matched LC, fixed support."""
import argparse,csv,hashlib,json,shutil,time
from datetime import datetime,timezone
from pathlib import Path
import numpy as np

def read(p):return json.loads(p.read_text())
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(8<<20),b''):h.update(b)
    return h.hexdigest()
def require(ok,why):
    if not ok:raise ValueError(why)
def save_csv(p,rows):
    with p.open('x') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def main():
    p=argparse.ArgumentParser()
    for key in ['task','parent','output']:p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();require(Path('/.dockerenv').exists(),'Docker required');start=time.time();inputs={}
    out=a.output/('attempt_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'));out.mkdir(parents=True,exist_ok=False)
    def bind(path,expected=None):
        digest=sha(path);require(expected is None or digest==expected,'Bound input differs: '+str(path));inputs[str(path)]=dict(path=str(path),sha256=digest);return digest
    pointer=read(a.task/'review_site/current.json');packet=a.task/'review_site'/pointer['packet'];bind(packet/'receipt.json',pointer['receipt_sha256']);pr=read(packet/'receipt.json')
    require(pr['status']=='PASS_REVIEW_PACKET' and pr['scientific_verdict'] is None,'Verified technical packet required')
    for name in ['data.json','sources.json']:bind(packet/name,next(x['sha256'] for x in pr['outputs'] if x['path']==name))
    data=read(packet/'data.json');policy=read(packet/'sources.json');full=[];bands=[];transitions=[];sources=[];checks=0
    evals={sha(x):x.parent for x in (a.task/'evaluation').glob('attempt_*/receipt.json')}
    for bundle in policy['bundles']:
        sp=a.task/bundle['summary']/'receipt.json';bind(sp);sr=read(sp)
        ep=evals[next(x['sha256'] for x in sr['inputs'] if x['path']=='/evaluation/receipt.json')];er=read(ep/'receipt.json');bind(ep/'receipt.json')
        gi=a.task/bundle['summary']/'geometry_all_thresholds_raw_post.csv';bind(gi,next(x['sha256'] for x in sr['outputs'] if x['path']==gi.name))
        with gi.open() as f:geometry=list(csv.DictReader(f))
        sealed={x['path']:x['sha256'] for x in er['outputs']}
        for region in bundle['regions']:
            selected=[x for x in data['rows'] if x['region']==region]
            metric_path=ep/region/selected[0]['condition']/'raw_metrics.json';bind(metric_path,sealed[str(metric_path.relative_to(ep))]);bounds=np.array(read(metric_path)['bounds_half_open'])
            ids=['ANCHOR']+[f'D{d}_P{m}' for d in ['005','0005','0'] for m in ['native','release']]+[x['condition'] for x in selected]
            for kind in ['raw','post']:
                arrays={};reference=None;original_ids=None
                for candidate in ids:
                    if candidate.startswith('LC_'):
                        path=ep/region/candidate/(kind+'_distances.npz');expected=sealed[str(path.relative_to(ep))]
                    else:
                        parent_id='D005_Pnative.anchor_512.'+kind if candidate=='ANCHOR' else candidate+'.mesh_512.'+kind
                        path=a.parent/'evaluation/geometry'/region/parent_id/'sample0.1_reference0.1.npz'
                        hs={x['sha256'] for x in er['inputs'] if x['path'].endswith('/'+str(path.relative_to(a.parent)))}
                        require(len(hs)==1,'Unique sealed global cache required');expected=hs.pop()
                    bind(path,expected)
                    with np.load(path,allow_pickle=False) as z:
                        ref=z['reference_points'];ref_ids=z['reference_original_indices'];rd=z['reference_to_triangle_distance'];pd=z['prediction_to_reference_distance'];pred=z['prediction_surface_samples']
                    if reference is None:reference=ref;original_ids=ref_ids
                    require(np.array_equal(ref,reference) and np.array_equal(ref_ids,original_ids),'Reference identity/order/XYZ mismatch');checks+=1
                    arrays[candidate]=rd
                    for t in [.1,.2,.25,.5,1.,2.]:
                        precision=float(np.mean(pd<t)) if len(pd) else 0.;recall=float(np.mean(rd<t));f1=2*precision*recall/(precision+recall) if precision+recall else 0.
                        old=next(x for x in geometry if x['region']==region and x['candidate']==candidate and x['mesh_kind']==kind and float(x['threshold_m'])==t)
                        require(all(abs(value-float(old[key]))<1e-12 for key,value in [('precision',precision),('recall',recall),('f1',f1)]),'Recomputed whole-region metric differs');checks+=1
                        full.append(dict(region=region,candidate=candidate,mesh_kind=kind,threshold_m=t,precision=precision,recall=recall,f1=f1,reference_count=len(rd)))
                    if kind=='raw':
                        for axis in [0,1]:
                            center=float(bounds[axis].mean());rs=np.abs(ref[:,axis]-center)<.25;ps=np.abs(pred[:,axis]-center)<.25
                            precision=float(np.mean(pd[ps]<.5)) if ps.any() else 0.;recall=float(np.mean(rd[rs]<.5)) if rs.any() else None
                            bands.append(dict(region=region,candidate=candidate,fixed_axis='XY'[axis],center_m=center,width_m=.5,reference_count=int(rs.sum()),surface_sample_count=int(ps.sum()),precision=precision,recall=recall,
                                metric_scope='3D distances of fixed-band samples to full counterpart; not 2D plot intersections'))
                pairs=[]
                for mode in ['native','release']:
                    pairs.extend(('GLOBAL_PRIOR_REDUCTION',f'D005_P{mode}',f'D{d}_P{mode}') for d in ['0005','0'])
                for row in selected:
                    pairs.append(('MATCHED_LOCAL_INCREMENT',row['parent_condition'],row['condition']))
                for contrast,before,after in pairs:
                    for t in [.1,.2,.25,.5,1.,2.]:
                        g=arrays[before]<t;l=arrays[after]<t;corrected=int((~g&l).sum());damaged=int((g&~l).sum())
                        require(corrected-damaged==int(l.sum())-int(g.sum()),'Paired conservation failed');checks+=1
                        transitions.append(dict(region=region,contrast=contrast,before=before,after=after,mesh_kind=kind,threshold_m=t,reference_count=len(g),before_near=int(g.sum()),after_near=int(l.sum()),corrected=corrected,damaged=damaged,delta_recall_pp=100*(l.mean()-g.mean())))
                del arrays
    save_csv(out/'all_metrics.csv',full);save_csv(out/'fixed_band_3d_metrics.csv',bands);save_csv(out/'paired_reference_changes.csv',transitions)
    bind(Path(__file__));shutil.copyfile(Path(__file__),out/Path(__file__).name)
    receipt=dict(status='PASS_PRIOR_REDUCTION_REANALYSIS',scientific_verdict=None,source_packet=pointer,evaluated_local_conditions=data['evaluated_conditions'],reused_global_conditions=18,
        checks=checks,whole_metric_rows=len(full),fixed_band_rows=len(bands),paired_rows=len(transitions),wall_seconds=time.time()-start,inputs=list(inputs.values()),
        new_training=False,new_geometry_extraction=False,independent_repetitions=False,mean_matched_global_control=False,controller_replay=False,reference_used_for_parameter_selection=False,
        outputs=[dict(path=x.name,sha256=sha(x)) for x in out.iterdir() if x.is_file()])
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({k:receipt[k] for k in ['status','evaluated_local_conditions','checks','scientific_verdict']}|dict(output=str(out))))
    for region in ['P1','P2','P3']:
        for mode in ['native','release']:
            names=[f'D{d}_P{mode}' for d in ['005','0005','0']]+[f'LC_D{d}_P{mode}' for d in ['005','0005','0']]
            rows={x['candidate']:x for x in full if x['region']==region and x['mesh_kind']=='raw' and x['threshold_m']==.5}
            print(json.dumps(dict(region=region,protection=mode,metrics={name:{k:rows[name][k] for k in ['precision','recall','f1']} if name in rows else None for name in names})))
if __name__=='__main__':main()
