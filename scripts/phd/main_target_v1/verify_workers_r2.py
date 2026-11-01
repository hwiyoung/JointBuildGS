"""Verify unchanged UNCERT results under an operational CPU worker-count increase."""
import sys,shutil
import numpy as np
from common import *
sys.path.insert(0,str(REPO/'scripts/phd/main_uncert_v1'))
import uc_common as U
import u2_run as R


def main():
    root=OUT/'r2/verification/worker_invariance';root.mkdir(exist_ok=True)
    source=OUT/'r2/background/B173nb_b10/ALS/uncert/patches_B173nb_b10_ALS.npz'
    with np.load(source) as z:
        np.savez_compressed(root/source.name,**{k:z[k][:800] for k in z.files})
    U.WORK=root;U.PTS=UN/'points'
    f=root/'val_B173nb_b10_ALS_mvs_a_R1.5.npz'
    if '--compare-only' not in sys.argv:
        R.run('B173nb_b10','ALS','mvs_a',[1.5],4)
        shutil.copy2(f,root/'workers4.npz')
        R.run('B173nb_b10','ALS','mvs_a',[1.5],16)
    with np.load(f) as a,np.load(root/'workers4.npz') as b:
        assert a.files==b.files
        fields=[k for k in a.files if k!='seconds']
        for k in fields:assert np.array_equal(a[k],b[k],equal_nan=True),k
    dump(OUT/'r2/verification/worker_invariance.json',dict(at=stamp(),status='PASS_IDENTICAL_4_AND_16_WORKERS',patches=800,fields=fields,
        timing_field_excluded='seconds is elapsed time, not a measurement; initial overly broad equality assertion was recorded',
        generator='same seed, site, prior, radius and patch index; worker assignment absent from RNG seed',
        source_sha256=sha(REPO/'scripts/phd/main_uncert_v1/u2_run.py'),scientific_verdict=None))
    print('WORKER_INVARIANCE_PASS',len(fields),flush=True)


if __name__=='__main__':main()
