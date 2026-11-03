"""Additive rfix recording. Immutable r22 and prior recorded runtime are untouched."""
import time
import r8_record_hooks as H
from common import *
import torch,numpy as np
ROOT=OUT/'rfix_continue'
BASE_BEGIN=H.begin_iteration
BASE_RENDER=H.training_render
BLOCK=[]
START=None
ITER_START=None
CAMS={}

def begin(env):
    global START,ITER_START
    BASE_BEGIN(env)
    if (ROOT/'STOP_REQUEST.json').exists():
        H.PHASE='training_forward_before_optimizer'
        raise RuntimeError('RFIX_ADDEND_MISMATCH_STOP_REQUEST')
    ITER_START=time.perf_counter()
    if START is None:START=ITER_START
    if not CAMS:
        for c in env['scene'].getTrainCameras():
            if c.image_name in H.CONFIG['near_cameras']:CAMS[c.image_name]=c.camera_center.detach().cpu().numpy()
        assert len(CAMS)==3

def training_render(env,render,cam,g,pipe,bg):
    pkg=BASE_RENDER(env,render,cam,g,pipe,bg)
    s=H.MODULE.jbgs_get_guard()
    BLOCK.append(dict(iteration=env['iteration'],camera=cam.image_name,overlaps=s[1],binning_bytes=s[2],free_bytes=s[3]))
    return pkg

def install(cfg):
    H.ROOT=ROOT
    def load():
        if H.MODULE is None:
            from rfix_measure import module_from
            H.MODULE=module_from(Path(cfg['extension']),'jbgs_rfix_target')
        return H.MODULE
    H.load_extension=load
    H.begin_iteration=begin;H.training_render=training_render
    H.install(cfg)
    from jbgs_target_r8 import TargetR8
    original=TargetR8.observe
    def observe(self,it,g,*args,**kw):
        global START
        if it%100==0:
            torch.cuda.synchronize();now=time.perf_counter();xyz=H.cpu(g._xyz)
            near={name:int((np.einsum('ij,ij->i',xyz-centre,xyz-centre)<=900).sum()) for name,centre in CAMS.items()}
            views={}
            for r in BLOCK:
                old=views.get(r['camera'])
                if old is None or r['overlaps']>old['overlaps']:views[r['camera']]=r
            H.append(Path(cfg['model'])/'recording/rfix_100.jsonl',dict(at=stamp(),iteration=it,completed_in_block=len(BLOCK),
                block_seconds=now-START,seconds_per_iteration=(now-START)/len(BLOCK),sample_iteration_seconds=now-ITER_START,
                near_camera30_counts=near,view_maxima=list(views.values()),maximum_overlap=max(r['overlaps'] for r in BLOCK),
                maximum_binning_bytes=max(r['binning_bytes'] for r in BLOCK),gpu=H.memory(),scientific_verdict=None))
            BLOCK.clear();START=now
        return original(self,it,g,*args,**kw)
    TargetR8.observe=observe
