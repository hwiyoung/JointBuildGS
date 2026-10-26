"""Compare identical CPU/GPU point IDs and all valid samples; derive timing bounds."""
from common import *
def main():
    prefix=O/'benchmark/6909_53361__LoD2';a=npz(str(prefix)+'_cpu_256.npz');b=npz(str(prefix)+'_cuda_256.npz')
    assert np.array_equal(a['point_id'],b['point_id'])
    finite=np.isfinite(a['curve'])&np.isfinite(b['curve']);diff=abs(a['curve'][finite].astype(float)-b['curve'][finite].astype(float))
    r=dict(matching_points=len(a['point_id']),finite_disagreement=int((np.isfinite(a['curve'])!=np.isfinite(b['curve'])).sum()),max_curve_difference=float(diff.max()),median_curve_difference=float(np.median(diff)),judgment_disagreement=int((a['judgment']!=b['judgment']).sum()),max_texture_difference=float(np.nanmax(abs(a['texture']-b['texture']))),environment=env())
    cpu=load(str(prefix)+'_cpu_256.json');gpu=load(str(prefix)+'_cuda_1024.json');total=sum(x['points'] for x in load(O/'geometry_summary.json')['rows'])
    r['timing']=dict(stage_b_points=total,cpu_seconds_per_point=cpu['seconds']/cpu['points'],gpu_seconds_per_point=gpu['seconds']/gpu['points'],cpu_hours=cpu['seconds']/cpu['points']*total/3600,gpu_hours=gpu['seconds']/gpu['points']*total/3600,scope='linear photo curve estimate; cached photographs; add view selection, initial image decode and reporting separately')
    r['status']='PASS' if r['finite_disagreement']==0 and r['max_curve_difference']<.003 and r['judgment_disagreement']==0 else 'FAIL'
    dump(O/'gates/benchmark.json',r);print(json.dumps(clean(r),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
