"""Complete manually named glass masks from stored input-only place membership."""
import shutil
import numpy as np
from scipy.spatial import cKDTree
from common import *
from stratify_r5 import zload,finish
SL=PH/'main_fill_v1/PHD-MAIN-FILL-v1';MP=PH/'main_meshpatch_v1/PHD-MAIN-MESHPATCH-v1'
def main():
 paths=[UN/'work/places.npz',UN/'work/places.json',SL/'prep/undecidable/definitions.json',REPO/'scripts/phd/main_fill_v1/undecidable/und_defs.py',REPO/'scripts/phd/main_stage1_v1/regions_v3.py']+[SL/'work/undecidable'/f'regions_B173nb_b10_{p}.npz' for p in ['ALS','LoD2']]
 binding=dict(at=stamp(),reason='Found original UNCERT region-index glass masks and input-only place_skylight after MESHPATCH case list search. Complete requested manual labels; no result-driven rule change.',files={str(p):sha(p) for p in paths},rule='Use glass_strip and glass_dome stored indices; use place_skylight, never GT-filtered case_skylight or case_band. Other units only exact centre/normal/area identity; no nearest transfer.',scientific_verdict=None)
 dump(CFG/'manual_glass_r5.lock.json',binding);T2=json.loads((OUT/'r2/stage0/T2.json').read_text())['fits']['main_u']['T2_m']
 for prior in ['ALS','LoD2']:
  source=zload(OUT/'r2/targets'/f'B173nb_b10_{prior}.npz');places=zload(UN/'work/places.npz');sk=zload(SL/'work/undecidable'/f'regions_B173nb_b10_{prior}.npz',['place_skylight'])['place_skylight']
  masks={'유리 띠':np.isin(np.arange(len(sk)),places[f'glass_strip__{prior}']),'유리 둥근 지붕':np.isin(np.arange(len(sk)),places[f'glass_dome__{prior}']),'B173 유리 채광창':sk}
  for site in ['B173nb_b10','B173_b0']:
   root=OUT/'r5/places'/f'{site}_{prior}';old=zload(root/'strata.npz');summary=json.loads((root/'summary.json').read_text());d=zload(OUT/'r2/targets'/f'{site}_{prior}.npz');e=zload(OUT/'r2/stage0/evaluation'/f'{site}_{prior}.npz');d.update(cell=e['cell'],gt_offset=e['gt_med'])
   if site=='B173nb_b10':ix=np.arange(len(sk));valid=np.ones(len(sk),bool)
   else:
    dis,ix=cKDTree(source['centre']).query(d['centre'],distance_upper_bound=1e-8);valid=np.isfinite(dis);ix=np.minimum(ix,len(sk)-1)
    valid&=np.isclose(source['area'][ix],d['area'],rtol=1e-8,atol=1e-9)&(source['kind'][ix]==d['kind'])&((np.linalg.norm(source['normal'][ix]-d['normal'],axis=1)<1e-6))
   manual=np.zeros(len(ix),bool);notes={k:v for k,v in summary['manual_glass'].items() if k.startswith('type_') or k=='missing_building_ids'}
   for name,m in masks.items():
    sel=valid&m[ix];manual|=sel;notes[name]=dict(status='available' if sel.any() else 'unavailable',source_site='B173nb_b10',source_members=int(m.sum()),matched_patches=int(sel.sum()),area_m2=float(d['area'][sel].sum()),source='UNCERT stored glass place indices' if name!='B173 유리 채광창' else 'FILL place_skylight: input LoD2 named faces / preexisting ALS XY membership, not GT-filtered case mask',identity='original same-unit indices' if site=='B173nb_b10' else 'exact centre, normal, area and kind only')
   before=root/'before_original_glass_masks';before.mkdir(exist_ok=False)
   for name in ['strata.npz','summary.json']:shutil.copy2(root/name,before/name)
   dump(root/'manual_glass_binding.json',binding)
   finish(d,old['mvs_face_type'],old['mvs_edge_band'],manual,root,'experiment',prior,site,T2,notes)
if __name__=='__main__':main()
