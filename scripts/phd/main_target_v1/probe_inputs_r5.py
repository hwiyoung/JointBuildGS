from common import *
import numpy as np
for p in [UN/'patch_values/B173nb_b10__ALS__R1.5.npz',UN/'work/patches_B173nb_b10_ALS.npz',OUT/'r2/stage0/evaluation/B173nb_b10_ALS.npz']:
 with np.load(p) as z:print(p,[(k,z[k].shape,str(z[k].dtype)) for k in z.files])
for prior in ['ALS','LoD2']:
 p=PH/'main_stage3_v1/PHD-MAIN-STAGE3-v1/runs/B173nb_b10'/f'nojudge_{prior}_s0/model/cfg_args';print(prior,p.read_text())
