"""Inspect schema only; never print sealed patch values."""
import numpy as np
from common import *
def main():
    roots=[OUT/'r2/stage0/development',OUT/'holdout/r2/stage0',JN/'core_points',JN/'holdout/core_points',PH/'main_widen0_v2/PHD-MAIN-WIDEN0-v2/patch_values',OUT/'r2/stage0/evaluation']
    for root in roots:
        fs=sorted(root.glob('*.npz'));print(str(root),len(fs))
        if fs:
            with np.load(fs[0]) as z:print([(k,z[k].shape,str(z[k].dtype)) for k in z.files])
    for root in [OUT/'r2/stage0/development',OUT/'holdout/r2/stage0']:
        n=0;count=0
        for f in root.glob('*.npz'):
            with np.load(f) as z:n+=len(z['region']);count+=int((z['region']==0).sum())
        print('AGGREGATE',root.name,n,count)
if __name__=='__main__':main()
