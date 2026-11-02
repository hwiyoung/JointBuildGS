"""Apply task-computed missing uncertainties before the frozen calibration."""
import json
import numpy as np
import geometry as G
from preflight import C,O,Path,sha,dump,now

original_load=G.loadz
def load_with_recomputed_uncertainty(p):
    d=original_load(p)
    if Path(p).parent.name=='geometry_raw':
        ring=original_load(O/'r1/ring_recompute'/Path(p).name)
        assert np.array_equal(d['patch_id'],ring['patch_id'])
        d['u_mvs']=ring['u_mvs'];d['u_recomputed_status']=ring['recomputed_status']
    return d

if __name__=='__main__':
    assert len(list((O/'r1/ring_recompute').glob('*.npz')))==len(list((O/'r1/inputs').glob('*.npz')))
    dump(C/'calibration.reply1.lock.json',dict(at=now(),config_sha256=sha(C/'judgecheck_v1.json'),
        adapter_sha256=sha(Path(__file__)),base_implementation_sha256=sha(Path(G.__file__)),
        rule='Finite inherited u_M unchanged; missing entries use exact task-local ring recomputation before sigma_W and r',
        truth_opened=False,scientific_verdict=None))
    G.loadz=load_with_recomputed_uncertainty
    G.calibrate()
