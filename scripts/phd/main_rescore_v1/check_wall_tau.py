"""Inspect whether scene tolerances follow the explicit roof/wall rule."""
from common import *
from geometry import SiteGT
site='B173nb_b10';gt=SiteGT(site);wall=gt.G['vert_gt_points'][gt.bs_idx].astype(bool);tau=loadz(CELLS/f'{site}__LoD2.npz',['tau_v2_m','kind']) if False else None
for family in ['prior','baseline_30000','r8_7000']:
 p=O/'scores'/f'{site}__LoD2__{family}/points.npz';z=loadz(p,['scene_tau_m']);t=z['scene_tau_m'];expected=np.where(wall,.3923140804711729,.2470203074282035);print(family,'wrong_scene_kind_tau',int((abs(t-expected)>1e-12).sum()),'of',len(t))
