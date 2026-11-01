from common import *
import numpy as np
SL=PH/'main_fill_v1/PHD-MAIN-FILL-v1'
for p in [SL/'work/undecidable/regions_B173nb_b10_ALS.npz',SL/'work/undecidable/regions_B173nb_b10_LoD2.npz',UN/'work/places.npz']:
 with np.load(p) as z:print(str(p),[(k,z[k].shape,str(z[k].dtype)) for k in z.files if 'sky' in k or 'place' in k or 'glass' in k or k=='centre'])
