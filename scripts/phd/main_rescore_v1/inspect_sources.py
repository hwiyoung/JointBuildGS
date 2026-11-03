"""Bounded read-only source inspection before the inventory is compiled."""
from common import *
def main():
 cfg();out={}
 for p in [TG/'r8/targets/B173nb_b10_ALS.npz',TG/'r8/targets/B173nb_b10_LoD2.npz',JA/'core_points/B0_b10__LoD2.npz',JA/'training_regions/B0_b10__LoD2.npz']:
  with np.load(p) as z:out[str(p)]={k:dict(shape=list(z[k].shape),dtype=str(z[k].dtype)) for k in z.files}
 print(json.dumps(out,indent=1));dump(O/'inspection/npz_schema.json',out)
 roots=[TG/'r7/runs',TG/'r7_continue/runs',TG/'r8/runs',TG/'r8_recorded_continue/runs']
 models=[q for p in roots for q in p.glob('*/model')]
 for task in ['main_stage3_v1/PHD-MAIN-STAGE3-v1','main_baselines_v1/PHD-MAIN-BASELINES-v1','main_fill_v1/PHD-MAIN-FILL-v1']:
  models += [q for q in (PH/task/'runs').glob('*/*/model') if any(s in str(q) for s in ['nojudge_','imgonly_2dgs_s0/','geogs_ALS_fix1/','cdgsnofit_']) and not any(s in str(q) for s in ['old_','flsmoke'])]
 rows=[]
 for p in models:
  row=dict(model=str(p),iterations=[int(q.name.split('_')[-1]) for q in (p/'point_cloud').glob('iteration_*')],files=[q.name for q in p.iterdir() if q.is_file()],metadata=[q.name for q in p.parent.iterdir() if q.is_file() and q.suffix=='.json'])
  rows.append(row)
 dump(O/'inspection/models.json',rows)
 print('MODELS',json.dumps(rows,ensure_ascii=False));print('TARGET_FILES',[str(q) for q in (TG/'stage0_r1/inputs').glob('*.npz')])
if __name__=='__main__':main()
