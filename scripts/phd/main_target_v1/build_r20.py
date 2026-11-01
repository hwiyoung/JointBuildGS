"""Reproducible, bounded source edits from the preserved r19 fork."""
from pathlib import Path
R=Path(__file__).resolve().parents[3];F=R/'src/phd/forks/GeoGS-conf-guided-v1-r20'
for name in ['jbgs_target.py','scene/gaussian_model.py','train.py','jbgs_state.py']:
 (F/name).write_bytes((F.with_name('GeoGS-conf-guided-v1-r19')/name).read_bytes())
def edit(name,old,new):
 p=F/name;s=p.read_text();assert s.count(old)==1,(name,old[:80],s.count(old));p.write_text(s.replace(old,new))
edit('jbgs_target.py',"    parser.add_argument('--jbgs_target_dir',default='')", "    parser.add_argument('--jbgs_target_rev',choices=['r4n','r6'],default='r4n')\n    parser.add_argument('--jbgs_target_dir',default='')")
edit('jbgs_target.py',"    return Target(args,scene,g) if args.jbgs_target=='on' else None", "    if args.jbgs_target=='on' and args.jbgs_target_rev=='r6':\n        from jbgs_target_r6 import TargetR6\n        return TargetR6(args,scene,g)\n    return Target(args,scene,g) if args.jbgs_target=='on' else None")
edit('scene/gaussian_model.py','        self.init_id = None  # [jbgs_judgment] index of the initial disk (-1: none); inherited by children', '        self.init_id = None  # [jbgs_judgment] index of the initial disk (-1: none); inherited by children\n        self.target_r6 = None  # Optional r6 metadata and immediate density callbacks; default off')
edit('scene/gaussian_model.py','            self.init_id = self.init_id[valid_points_mask]', '            self.init_id = self.init_id[valid_points_mask]\n        if self.target_r6 is not None:\n            self.target_r6.pruned(self, valid_points_mask)')
edit('scene/gaussian_model.py','new_origin=None, new_init_id=None):  # [jbgs_judgment]', 'new_origin=None, new_init_id=None, new_target_meta=None):  # [jbgs_judgment, target r6]')
edit('scene/gaussian_model.py','            self.init_id = torch.cat((self.init_id, new_init_id.to(torch.int32)), dim=0)', '            self.init_id = torch.cat((self.init_id, new_init_id.to(torch.int32)), dim=0)\n        if self.target_r6 is not None:\n            self.target_r6.extended(self, new_target_meta)')
# Both clone and split inherit dynamic target metadata before immediate nearest-target update.
p=F/'scene/gaussian_model.py';s=p.read_text()
old='        self.densification_postfix(new_xyz, new_features_dc, new_features_rest, new_opacity, new_scaling, new_rotation, new_origin=new_origin, new_init_id=new_init_id)'
new='        meta = self.target_r6.child_metadata(self, selected_pts_mask, N) if self.target_r6 is not None else None\n'+old.replace('new_init_id=new_init_id)', 'new_init_id=new_init_id, new_target_meta=meta)')
assert s.count(old)==1;s=s.replace(old,new)
old='        self.densification_postfix(new_xyz, new_features_dc, new_features_rest, new_opacities, new_scaling, new_rotation, new_origin=new_origin, new_init_id=new_init_id)'
new='        meta = self.target_r6.child_metadata(self, selected_pts_mask, 1) if self.target_r6 is not None else None\n'+old.replace('new_init_id=new_init_id)', 'new_init_id=new_init_id, new_target_meta=meta)')
assert s.count(old)==1;s=s.replace(old,new);p.write_text(s)
edit('train.py','        iter_start.record()','        if target_control is not None and args.jbgs_target_rev == "r6":\n            target_control.iteration = iteration\n        iter_start.record()')
edit('train.py','        gaussians.optimizer.step()\n        if target_control is not None:\n            target_control.project_bounds(gaussians)', '        gaussians.optimizer.step()\n        if target_control is not None:\n            if args.jbgs_target_rev == "r6" and iteration % 100 == 0:\n                target_control.reattach(gaussians, "periodic")\n            target_control.project_bounds(gaussians)')
edit('jbgs_state.py',"        'source_sha256': digest(Path(__file__).with_name('train.py')),", "        'target_r6': env['target_control'].capture(g) if getattr(args, 'jbgs_target_rev', None) == 'r6' and env.get('target_control') is not None else None,\n        'source_sha256': digest(Path(__file__).with_name('train.py')),")
edit('jbgs_state.py','def restore_state(path, env, functions):\n    state = torch.load(path)', 'def restore_state(path, env, functions):\n    state = torch.load(path)\n    if state.get("target_r6") is not None:\n        from jbgs_target_r6 import restore_complete\n        return restore_complete(path, state, env)')
edit('train.py', '''        if target_control is not None:
            target_control.project_bounds(gaussians)
            target_control.observe(iteration, gaussians, total_loss, rgb_loss, da_depth_loss, cam_name)
        if jbgs_state.after_step(locals()):
            break''', '''        if target_control is not None:
            target_control.project_bounds(gaussians)
        # r6 saves complete 7000 state even when its following health gate fails.
        r6_state_done = target_control is not None and args.jbgs_target_rev == "r6"
        r6_stop_after = jbgs_state.after_step(locals()) if r6_state_done else False
        if target_control is not None:
            target_control.observe(iteration, gaussians, total_loss, rgb_loss, da_depth_loss, cam_name)
        if r6_stop_after or (not r6_state_done and jbgs_state.after_step(locals())):
            break''')
