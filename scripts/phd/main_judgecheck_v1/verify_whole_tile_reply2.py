"""Full maximum-tile CPU/GPU parity and original-method overlap checks."""
import json
import numpy as np
from preflight import C,D,O,Path,sha,dump,now
from geometry import loadz
BASE=O/'r2'
def compare(a,b,label,tol):
    assert a.shape==b.shape,(label,a.shape,b.shape);same=np.array_equal(np.isfinite(a),np.isfinite(b));assert same,(label,'finite status');m=np.isfinite(a);error=float(np.max(abs(a[m]-b[m]))) if m.any() else 0.;assert error<tol,(label,error,tol);return error

def main():
    tile=json.loads((BASE/'target_census.json').read_text())['benchmark_tile'];g=loadz(BASE/'photo_prepared'/f'{tile}.npz');cpu=loadz(BASE/'cpu_benchmark'/tile/'scores.npz');gpu=loadz(BASE/'photo_scores'/tile/'scores.npz');errors={}
    assert np.array_equal(cpu['point_id'],gpu['point_id']) and np.array_equal(g['point_id'],gpu['point_id'])
    for key in ['curves','best_score','best_height','texture','texture_by_view']:errors[key]=compare(cpu[key],gpu[key],key,2e-4 if key.startswith('texture') else 2e-5)
    assert np.array_equal(cpu['valid_image_count'],gpu['valid_image_count']) and np.array_equal(cpu['pyramid_levels'],gpu['pyramid_levels'])
    old=loadz(O/'r1/photo_benchmark/scores_cpu.npz');planes=loadz(O/'r1/photo_benchmark/planes.npz');sample=json.loads((O/'r1/photo_benchmark_selection.json').read_text())['sample'];lookup={(int(group),pid):i for i,(group,pid) in enumerate(zip(g['group'],g['point_id']))};overlap=[]
    for i,r in enumerate(sample):
        _,prior,kind=Path(r['file']).stem.split('__');group=0 if prior=='ALS' else (1 if kind=='1' else 2);key=(group,planes['point_id'][i])
        if key not in lookup:continue
        j=lookup[key];diff={}
        for field in ['best_score','best_height','texture','texture_by_view']:diff[field]=compare(old[field][:,i],gpu[field][:,j],f'original {field} {key}',2e-4 if field.startswith('texture') else 2e-5)
        valid=np.isfinite(planes['heights'][i]);curve_error=[]
        for face in range(2):
            l,h=g['plane_row_ptr'][2*j+face:2*j+face+2]
            if h==l:continue
            curve_error.append(compare(old['curves'][:,i,face][:,valid],gpu['curves'][:,l:h],f'original curve {key} {face}',2e-5))
        overlap.append(dict(group=group,point_id=str(key[1]),errors=diff,curve_error=max(curve_error,default=0.)))
    assert len(overlap)==27
    result=dict(at=now(),status='PASS_WHOLE_TILE_PHOTO_PARITY',tile=tile,points=len(g['point_id']),height_rows=len(g['row_height']),errors=errors,original_200_reference_overlap=overlap,overlap_count=len(overlap),
        score_tolerance=2e-5,texture_tolerance=2e-4,finite_status_exact=True,source_sha256=sha(Path(__file__)),scientific_verdict=None)
    dump(BASE/'photo_scores'/tile/'numeric_parity.json',result);dump(D/'tables/reply2_whole_tile_numeric_parity.json',result);print(result['status'],errors,flush=True)
if __name__=='__main__':main()
