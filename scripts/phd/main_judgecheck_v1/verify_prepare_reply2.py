"""Independent packed-plane check against the frozen 200-point preparation."""
import json
import numpy as np
from preflight import C,D,O,Path,sha,dump,now
from geometry import loadz

def main():
    base=O/'r2';tile=json.loads((base/'target_census.json').read_text())['benchmark_tile'];a=loadz(O/'r1/photo_benchmark/planes.npz');b=loadz(base/'photo_prepared'/f'{tile}.npz');index={(int(gr),v):i for i,(gr,v) in enumerate(zip(b['group'],b['point_id']))};rows=[];sample=json.loads((O/'r1/photo_benchmark_selection.json').read_text())['sample']
    for i,pid in enumerate(a['point_id']):
        _,prior,kind=Path(sample[i]['file']).stem.split('__');group=0 if prior=='ALS' else (1 if kind=='1' else 2);key=(group,pid)
        if key not in index:continue
        j=index[key];assert np.array_equal(a['available'][i],b['available'][j]);errors={}
        for k in ['centres','normals','tangent1','tangent2']:
            x=a[k][i];y=b[k][j];assert np.array_equal(np.isfinite(x),np.isfinite(y)),(pid,k);m=np.isfinite(x);err=float(np.max(abs(x[m]-y[m]))) if m.any() else 0;assert err<1e-8,(pid,k,err);errors[k]=err
        assert np.array_equal(a['selected_images'][i],b['selected_images'][j]),str(pid)
        for face in range(2):
            if not a['available'][i,face]:continue
            l,r=b['plane_row_ptr'][2*j+face:2*j+face+2];valid=np.isfinite(a['heights'][i]);assert np.allclose(a['heights'][i,valid],b['row_height'][l:r],atol=1e-14,rtol=0)
            mask=np.unpackbits(b['mask_bits'][l:r],axis=1,count=625).astype(bool);assert np.array_equal(a['masks'][i,face,valid],mask),(str(pid),face,'mask')
        rows.append(dict(point_id=str(pid),errors=errors))
    assert len(rows)>=1
    out=dict(at=now(),status='PASS_PACKED_PLANE_PARITY',points=len(rows),tile=tile,rows=rows,scientific_verdict=None);dump(base/'photo_prepared/parity.json',out);dump(D/'tables/packed_plane_parity.json',out);print('PLANE_PARITY_PASS',len(rows),flush=True)
if __name__=='__main__':main()
