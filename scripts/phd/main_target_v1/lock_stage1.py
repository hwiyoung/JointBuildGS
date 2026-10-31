"""Freeze stage-1 implementation details before seed/map arithmetic."""
from common import *
import shutil,os

c,old=locked();previous=CFG/'revisions/r1';previous.mkdir(parents=True,exist_ok=True)
assert not (CFG/'target_v1.stage1.lock.json').exists()
shutil.copy2(CFG/'target_v1.json',previous/'target_v1.json')
shutil.copy2(CFG/'target_v1.stage0.lock.json',previous/'target_v1.stage0.lock.json')
c['stage_status']='STAGE1_IMPLEMENTATION_PREFLIGHT'
c['stage1']={
    'at':stamp(),'previous_stage0_config_sha256':old['config_sha256'],'base_fork_manifest':'fork_r19_base.json',
    'depth':{'function':'sum weighted absolute metric depth difference / full image pixel count; identical nojudge MVS function',
        'lambda':.05,'reference_sigma':'median finite positive target pixel sigma in each view','weight_clip':[.1,10],
        'disc':'oriented circular planar disc with area equal to source patch area; exact ray-plane intersection, nearest positive camera depth, ties original patch index',
        'fallback':'MVS depth passes the unchanged confidence map A>0, only pixels with no target disc',
        'fallback_sigma':'unrepresented MVS depth has no patch-specific u; same-unit raw roof-kind u median from that prior table, explicitly flagged as replaced; no zero',
        'storage':'immutable per-training-view float32 depth/sigma/weight and int32 owner, pinned CPU, copy one view to GPU'},
    'initialization':{'source':'same baseline scene points3D.ply, origin.npy, seat and location store; same retained seed scales/colours/opacity',
        'prior_counts':'same original seed count per owning prior patch; uncomputable patch and no owning patch receive no prior seeds',
        'prior_positions':'each retained seed starts exactly at its frozen patch target; patch outward normal',
        'image_exclusion':'exclude image-origin seeds whose XY falls in a prior roof patch footprint (radius sqrt(area/pi)); wall support tested in its plane within 3m normal distance',
        'background':'remaining original image/MVS-workspace sparse seeds; own point target; original normal when available, otherwise vertical up as order 3.2',
        'background_u':'own UNCERT 1.5m ring on same-unit mvs_a cloud; unavailable values filled with same-unit same-kind raw patch u median, flagged',
        'background_region':4,'background_not_a_prior_patch':True},
    'bounds':{'sigma_multiple':1.96,'float32_tolerance_m':3e-5,'tangent':'unconstrained','inheritance':'unchanged GaussianModel init_id parent propagation on split, clone and prune'},
    'monitor':{'sample_interval':100,'health_iteration':7000,'opacity_threshold':.05,'count_reference_iteration':6000,
        'growth_max':3,'reset_grace':'none added; unchanged scheduled opacity resets are recorded; health stop follows the supplied threshold',
        'checkpoint_iterations':[0,6000,7000,30000]},
    'stage0_targets':'immutable bytes; never recompute decisions during training','scientific_verdict':None}
c['amendments'].append({'at':stamp(),'reason':'Stage 1 engineering details frozen before seed/map arithmetic; stage 0 rules and target bytes unchanged',
    'previous_config_sha256':old['config_sha256'],'previous_config':'revisions/r1/target_v1.json'})
dump(CFG/'target_v1.json',c)
dump(CFG/'target_v1.stage1.lock.json',dict(at=stamp(),config_sha256=sha(CFG/'target_v1.json'),previous_stage0_config_sha256=old['config_sha256'],
    source_commit=os.environ['TARGET_COMMIT'],docker_image=os.environ['TARGET_IMAGE'],training_started=False,scientific_verdict=None))
print('STAGE1_CONFIG_LOCKED',sha(CFG/'target_v1.json'),flush=True)
