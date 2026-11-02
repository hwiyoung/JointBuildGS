"""Compare no-removal measurements with prior current-mesh evidence; read only."""
import json,datetime
from r8_screen_prepare import O,R,dump,sha
def main():
 rows=[]
 for key,prior,lane in [('base_ALS_30000','ALS','r7_continue'),('base_LoD2_30000','LoD2','r7_continue'),('r7_LoD2_30000','LoD2','r7_continue'),('r8_ALS_30000','ALS','r8')]:
  old=O/lane/'scoring'/key/'current/values.json';new=O/'screen_sim/scores'/key/'before'/prior/'values.json'
  if not new.exists():continue
  a=json.loads(old.read_text());b=json.loads(new.read_text());differences=[];compared=0
  for cell,x in a['metrics'].items():
   y=b['metrics'][cell]
   for side,fields in [('gt',['n_gt','R_tau','mean']),('E',['n','P_tau','mean'])]:
    xx=x['gt'] if side=='gt' else x['res']['E'];yy=y['gt'] if side=='gt' else y['res']['E']
    for f in fields:
     compared+=1
     if xx.get(f)!=yy.get(f):differences.append(dict(cell=cell,side=side,field=f,old=xx.get(f),new=yy.get(f)))
  for cell,x in a['surface'].items():
   for f in ['area_m2','floating_area_m2','no_surface_area_m2']:
    compared+=1
    if x[f]!=b['surface'][cell][f]:differences.append(dict(cell=cell,field=f,old=x[f],new=b['surface'][cell][f]))
  rows.append(dict(state=key,old=str(old),old_sha256=sha(old),new=str(new),new_sha256=sha(new),compared_values=compared,exact_equal=len(differences)==0,differences=differences,scientific_verdict=None))
 dest=R/'docs/experiments/phd/main_target_v1/screen_sim/tables/no_removal_regression.json';dump(dest,dict(at=datetime.datetime.now().astimezone().isoformat(),rows=rows,scientific_verdict=None));print([(r['state'],r['exact_equal']) for r in rows])
if __name__=='__main__':main()
