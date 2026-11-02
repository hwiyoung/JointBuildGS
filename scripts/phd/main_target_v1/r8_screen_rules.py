"""Static source and recorded invocation audit. No source imports or mutation."""
import ast,csv
import torch
from common import *
ROOT=OUT/'r8_screen_prune'
def read(p):return json.loads(Path(p).read_text())
def lines(p,needle):return [i+1 for i,s in enumerate(Path(p).read_text().splitlines()) if needle in s]
def constants(p):
 out={}
 for node in ast.walk(ast.parse(Path(p).read_text())):
  if isinstance(node,ast.Assign):
   for target in node.targets:
    if isinstance(target,ast.Attribute) and isinstance(target.value,ast.Name) and target.value.id=='self':
     try:out[target.attr]=ast.literal_eval(node.value)
     except (ValueError,TypeError):pass
 return out
def methods(p):
 tree=ast.parse(Path(p).read_text());return {n.name:n for cls in tree.body if isinstance(cls,ast.ClassDef) for n in cls.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
def main():
 c=read(CFG/'r8_screen.json');lock=read(CFG/'r8_screen.lock.json');rows=[];details=[]
 for row in c['sources']:
  root=Path(row['source']);files={name:root/name for name in ['train.py','scene/gaussian_model.py','arguments/__init__.py']}
  for p in files.values():assert sha(p)==lock['files'][str(p)],str(p)
  opts=constants(files['arguments/__init__.py']);command=row.get('command',[])
  for k in ['opacity_reset_interval','densification_interval','densify_from_iter','densify_until_iter','opacity_cull']:
   if '--'+k in command:opts[k]=float(command[command.index('--'+k)+1])
  if row['name']=='CDGS_prepared_only':opts['opacity_cull']=.005
  begin=int(opts['densify_from_iter']);end=int(opts['densify_until_iter']);interval=int(opts['densification_interval']);reset=int(opts['opacity_reset_interval']);first=next(i for i in range(interval,end,interval) if i>max(begin,reset));last=max(i for i in range(interval,end,interval) if i>begin)
  gm=files['scene/gaussian_model.py'];mm=methods(gm);flow=mm['densify_and_prune'];calls=[dict(method=n.value.func.attr,line=n.lineno) for n in flow.body if isinstance(n,ast.Expr) and isinstance(n.value,ast.Call) and isinstance(n.value.func,ast.Attribute)]
  resetlines=lines(gm,'self.max_radii2D = torch.zeros');post=mm['densification_postfix'];post_reset=[i for i in resetlines if post.lineno<=i<=post.end_lineno];screenline=lines(gm,'big_points_vs =')[0];assert post_reset and all(next(t['line'] for t in calls if t['method']==m)<screenline for m in ['densify_and_clone','densify_and_split'])
  # Both clone/split call postfix at top method-body level: this also executes for zero selected rows.
  unconditional=[]
  for key in ['densify_and_clone','densify_and_split']:
   nn=mm[key];unconditional.append(any(isinstance(x,ast.Expr) and isinstance(x.value,ast.Call) and isinstance(x.value.func,ast.Attribute) and x.value.func.attr=='densification_postfix' for x in nn.body))
  assert all(unconditional)
  if row['name']=='r22_r8':exemption='현재 배경·패치·풀림 꼬리표별 예외 없음; 저장 frozen_mask 모두0'
  elif row['name'].startswith('baseline'):exemption='density_exempt: density_mask 있으면 그것, 아니면 frozen_mask; protection=1, judgment=0 실제 실행'
  elif row['name'].startswith('GeoGS'):exemption='8000회 이후 building frozen_mask 정리 제외; freeze_onlybldg=1로 나머지 밀도 제어 지속'
  else:exemption='정리 예외 마스크 없음'
  refs={name:{needle:lines(p,needle) for needle in ['max_radii2D','size_threshold','densify_and_prune','opacity_reset_interval','big_points_vs','big_points_ws','prune_mask','frozen_mask','density_exempt']} for name,p in files.items()}
  rr=dict(implementation=row['name'],execution='EXECUTED' if row['executed'] else 'NOT_EXECUTED_REFERENCE' if row['name']=='original_2DGS' else 'NOT_TRAINED_PREPARATION_GATE',source=str(root),screen_threshold_px=20,configured_screen_first_iteration=first,configured_last_densify_iteration=last,interval=interval,opacity_reset_interval=reset,world_size_multiplier=.1,min_opacity=opts['opacity_cull'],radii_reset_before_screen_comparison=True,unconditional_reset_even_without_children=True,postfix_reset_line=post_reset[0],screen_test_line=screenline,train_size_threshold_line=lines(files['train.py'],'size_threshold =')[0],exemption=exemption,scientific_verdict=None);rows.append(rr);details.append(dict(**rr,options=opts,method_call_order=calls,references=refs,receipt=row.get('receipt'),command=command))
 dump(ROOT/'rules.json',dict(rows=rows,scientific_verdict=None));dump(ROOT/'rule_evidence.json',dict(rows=details,scientific_verdict=None))
 with (ROOT/'rules.csv').open('w') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
 masks=[]
 for row in c['sources']:
  if not row['name'].startswith('baseline'):continue
  path=Path(row['model'])/'jbgs_complete/iteration_30000/checkpoint.pth';cp=torch.load(path,map_location='cpu');fm=cp.get('frozen_mask');dm=cp.get('density_mask');masks.append(dict(implementation=row['name'],iteration=cp['iteration'],gaussians=len(cp['model'][1]),frozen_count=int(fm.sum()) if fm is not None else 0,density_mask_saved=dm is not None,density_mask_count=int(dm.sum()) if dm is not None else None,checkpoint=str(path),saved_max_radii_max=float(cp['model'][7].max()),cameras_extent=float(cp['model'][-1])));del cp
 dump(ROOT/'baseline_saved_masks.json',dict(rows=masks,scientific_verdict=None));print('RULE_AUDIT_COMPLETE',len(rows),flush=True)
if __name__=='__main__':main()
