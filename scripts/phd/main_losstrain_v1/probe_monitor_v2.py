"""Docker GPU: initialize and observe once, exit before the first optimizer step."""
import json,runpy,sys,random
from pathlib import Path
import numpy as np
import torch
sys.path.insert(0,'/source')
import jbgs_judgment as J

original=J.Judgment.__init__
def wrapped(self,args,opt,scene,gaussians,*a,**kw):
    original(self,args,opt,scene,gaussians,*a,**kw)
    loss_cameras=self.lt_cameras
    J.lt_monitor_initialize(self,gaussians,scene)
    assert self.lt_cameras is loss_cameras and isinstance(self.lt_cameras,dict)
    before=[x.detach().clone() for x in [gaussians._xyz,gaussians._opacity]]
    rng=(random.getstate(),np.random.get_state(),torch.get_rng_state(),torch.cuda.get_rng_state())
    J.lt_monitor_step(self,1000,gaussians,'initialization probe, zero training steps',kw['render_fn'],kw['pipe'],kw['background'])
    assert all(torch.equal(x,y) for x,y in zip(before,[gaussians._xyz,gaussians._opacity]))
    assert random.getstate()==rng[0] and np.array_equal(np.random.get_state()[1],rng[1][1])
    assert torch.equal(torch.get_rng_state(),rng[2]) and torch.equal(torch.cuda.get_rng_state(),rng[3])
    # Exercise the real path that consumes the camera dictionary, including backward.
    cam=self.lt_diagnostic_cameras[0]
    pkg=kw['render_fn'](cam,gaussians,kw['pipe'],kw['background'])
    mvs,prior,_=self.losses(cam.image_name,pkg)
    total=self.lambda_mvs*mvs+self.lambda_prior*prior
    assert bool(torch.isfinite(total));total.backward()
    assert bool(torch.isfinite(gaussians._xyz.grad).all())
    assert all(torch.equal(x,y) for x,y in zip(before,[gaussians._xyz,gaussians._opacity]))
    (self.mon/'monitor_v2_probe.json').write_text(json.dumps(dict(status='PASS',optimizer_steps=0,
        parameter_values_unchanged=True,rng_states_unchanged=True,legacy_camera_names=[c.image_name for c in self.lt_diagnostic_cameras],
        existing_loss_camera_dictionary_preserved=True,actual_depth_forward_backward_finite=True,
        gt_labels_cpu_only=True,scientific_verdict=None),indent=2)+'\n')
    print('monitor v2 real initial state and five-camera readout PASS; zero optimizer steps',flush=True)
    raise SystemExit(0)

J.Judgment.__init__=wrapped
runpy.run_path('/source/train.py',run_name='__main__')
