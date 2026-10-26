"""Freeze requested experiment rules; training remains gated by receipts."""
import json
import sys
from datetime import datetime
from pathlib import Path
from inputs import OUT, SITES, PRIORS, sha, save

def main():
    now=datetime.now().astimezone().isoformat()
    c=dict(task_id='PHD-MAIN-LOSSTRAIN-v1',saved_at=now,repo_commit=sys.argv[1],branch='exp/main-experiment',
        status='PREPARATION_BLOCKED_ON_PATCH_JOIN',scientific_verdict=None,
        units=[dict(site=s,prior=p,seed=0) for s in SITES for p in PRIORS],
        variants={
            'lt_fixgt':dict(loss='fixed',vprior='gt',destination='z_fixed_gt'),
            'lt_dyngt':dict(loss='dynamic',vprior='gt',destination='z_dyn_gt'),
            'lt_dynsoft':dict(loss='dynamic',vprior='soft',destination='z_dyn_soft'),
            'lt_dynnow':dict(loss='dynamic',vprior='now',destination='z_dyn_now'),
            'lt_fixnow':dict(loss='fixed',vprior='now',destination='z_fixed_now',optional=True)},
        common=dict(iterations=30000,width=1024,height=741,judgment=0,seed=0,initial_normal='cell',
            cuda_alloc_conf='expandable_segments:True',depth_norm='all image pixels',
            unchanged=['initialization','RGB loss and weight','observation confidence mask','protection','density control','reread'],
            docker_image='jointbuildgs:geogs-conf-guided-v1',fork='src/phd/forks/GeoGS-conf-guided-v1-r17'),
        loss=dict(fixed='0.5*V*(Dhat-Dsource)^2/sigma_ray^2',
            dynamic='-logaddexp(log(V)-log(sigma_ray)-0.5*log(2*pi)-0.5*((Dhat-Dsource)/sigma_ray)^2,log1p(-V)+log(c))',
            c_per_m=.1,sigma_ray='sigma_normal / max(abs(dot(unit_ray,unit_patch_normal)),0.25)',
            support='prior-patch pixels only; MVS additionally requires finite positive depth, observation mask, finite v_mvs',
            missing_mvs='prior term only',no_prior_patch='no depth term',rendered_depth='surf_depth'),
        lambda_selection=dict(default=.0025,multipliers=[1/3,1,3],site='B173nb_b10',prior='ALS',iterations=3000,
            variant='lt_dyngt',control='current nojudge',default_depth_to_RGB_gradient_below=.10,
            low_gradient_choice='x3',PSNR_drop_above_dB=1.,PSNR_drop_choice='x1/3',both_trigger='STOP and ask',
            gradient_window=[2901,3000],GT_evaluation_used=False,selected_lambda=None),
        join=dict(current=json.loads(Path('/config/join_v2.json').read_text()),
            history=[dict(rule='same prior, nearest registered centre <=0.05m',state='superseded by user reply',
                evidence='checks/join_patches.json')],
            fallback='nearest same-prior file values; v_prior_now even in oracle variants; excluded from scoring'),
        scoring=dict(tau_m={'LoD2':.20,'ALS':.1266},min_cell_patches=100,
            scored='finite MVS, both positive finite sigmas, finite gt_p, cell 0..3; joined patches in frozen evaluation range',
            unexplained='abs(mvs_p)/sqrt(sigma_prior^2+sigma_mvs^2)>3',
            ray_start='max(6,mvs_p+0.5,gt_p+0.5)',ray_end='min(-6,mvs_p-0.5,gt_p-0.5)',
            surface='first outer-to-inner mesh intersection along outward patch normal',missing_surface='separate area, fails tolerance',
            sides=dict(prior='abs(z)<=3*sigma_prior',mvs='abs(z-mvs_p)<=3*sigma_mvs',
                both='smaller standardized distance',neither='other',absent='no surface'),
            change_threshold='max(pooled existing variation,2.8*abs(stage1_seed0-stage1_seed1)/sqrt(2),300/N)',
            axes='unchanged PHD-MAIN-AXES71-v2 methods',interpretation='none'),
        figures=dict(sections=[
            dict(name='B173 날개',site='B173nb_b10',priors=PRIORS,start=[146.68,96.32],end=[136.63,99.34],half_width=.6),
            dict(name='R1 계단 지붕과 틈',site='R1rep_b10',priors=['LoD2'],start=[7.24,32.08],end=[14.98,18.08],half_width=.6),
            dict(name='60042 높은 단 가장자리',site='R1rep_b10',priors=['ALS'],start=[-64.03,40.64],end=[-56.57,37.76],half_width=.5)],
            maps='frozen per-unit evaluation XY bounds; same view and colors for all variants',
            render_camera='PENDING exact camera freeze before training',dpi=300,per_figure_json=True),
        schedule=dict(first=['B173nb_b10/ALS/'+v for v in ['lt_fixgt','lt_dyngt','lt_dynsoft','lt_dynnow']],
            interim_before_remaining=True,remaining=20,optional=6,optional_requires_no_stop_in_first_24=True,
            gpu_lanes=[0,1],one_run_per_GPU=True,TSDF_serial=True),
        postprocess=dict(voxel_m=.05,truncation_m=.25,depth_limit_m=300,mesh_cleanup=False),
        execution=dict(training_started=False,short_runs_completed=0,full_runs_completed=0))
    p=Path('/config/losstrain_v1.json');assert not p.exists()
    save(p,c)
    save('/config/losstrain_v1.lock.json',dict(saved_at=now,sha256=sha(p),first_training_started=False,
        status='rules snapshot; exact render camera and selected lambda remain unresolved, no training permitted'))
    print('configuration rules snapshot',sha(p))

if __name__=='__main__':main()
