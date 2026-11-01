from common import *
import numpy as np
for site in ['B0_b10','B173nb_b10','B173_b0','R1rep_b10']:
 p=(OUT/'b173_uncert_r1/patch_values' if site=='B173_b0' else UN/'patch_values')/f'{site}__ALS__R1.5.npz'
 with np.load(p) as z:print(site,[k for k in z.files if k in ['z_a','signed_difference_over_uncertainty','mvs_a_u','u_mvs','mvs_p','mvs_a_p','u_prior']])
