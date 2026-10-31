"""Host stdlib: create the sole new fork; keep every inherited source untouched."""
from pathlib import Path
import shutil,json,hashlib,datetime,subprocess
R=Path(__file__).resolve().parents[3];S=R/'src/phd/forks/GeoGS-conf-guided-v1-r18';D=S.with_name('GeoGS-conf-guided-v1-r19')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert not D.exists(),'never overwrite a fork'
sources={str(p.relative_to(S)):sha(p) for p in sorted(S.rglob('*')) if p.is_file() and '__pycache__' not in p.parts}
shutil.copytree(S,D,symlinks=True,ignore=shutil.ignore_patterns('__pycache__','.git'))
p=D/'train.py';s=p.read_text()
def change(old,new):
    global s
    assert s.count(old)==1,(old,s.count(old));s=s.replace(old,new)
change('import jbgs_oom_record  #','import jbgs_target\nimport jbgs_oom_record  #')
change('    gaussians.training_setup(opt)\n','    target_control = jbgs_target.create(args, scene, gaussians, render, pipe)\n    gaussians.training_setup(opt)\n')
change('        if judgment is not None:  # [jbgs_judgment] weighted MVS term + truncated prior term\n',
'''        if target_control is not None:
            da_depth_loss = target_control.loss(cam_name, render_pkg["surf_depth"])
            lod_depth_loss = torch.zeros((), device="cuda")
            total_loss = rgb_loss + dist_loss + normal_loss + target_control.depth_lambda * da_depth_loss
            current_lod_weight, current_da_weight = 0.0, target_control.depth_lambda
            just_switched, stage2_active = False, True
        elif judgment is not None:  # [jbgs_judgment] weighted MVS term + truncated prior term
''')
change('        total_loss.backward()\n','        if target_control is not None:\n            target_control.check_loss(iteration, total_loss)\n        total_loss.backward()\n')
change('        gaussians.optimizer.step()\n','        gaussians.optimizer.step()\n        if target_control is not None:\n            target_control.project_bounds(gaussians)\n')
change('                scene.save(iteration)\n','                scene.save(iteration)\n                if target_control is not None:\n                    target_control.snapshot(iteration, gaussians)\n')
change('        if jbgs_state.after_step(locals()):\n','        if target_control is not None:\n            target_control.project_bounds(gaussians)\n            target_control.observe(iteration, gaussians, total_loss, rgb_loss, da_depth_loss, cam_name)\n        if jbgs_state.after_step(locals()):\n')
change('    jbgs_state.register_args(parser)\n','    jbgs_target.register_args(parser)\n    jbgs_state.register_args(parser)\n')
p.write_text(s)
receipt=dict(at=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat(),base=str(S.relative_to(R)),new_fork=str(D.relative_to(R)),
    base_last_tracked_commit=subprocess.check_output(['git','log','-1','--format=%H','--',str(S.relative_to(R))],cwd=R,text=True).strip(),
    workspace_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip(),
    base_file_sha256=sources,note='Full working bytes include inherited untracked files; the tracked commit alone does not identify this fork.',
    changed_files=['train.py','jbgs_target.py'],scientific_verdict=None)
out=R/'configs/phd/main_target_v1/fork_r19_base.json';out.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print('CREATED',D,len(sources),'inherited files')
