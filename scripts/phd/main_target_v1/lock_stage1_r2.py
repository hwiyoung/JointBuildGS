"""Freeze runtime code, unchanged optimization defaults and literal target health scope."""
import ast,os
from common import *


def main():
    cfg,lock=locked_r2();dest=CFG/'target_v1.stage1.r2.lock.json';assert not dest.exists()
    fork=REPO/'src/phd/forks/GeoGS-conf-guided-v1-r19'
    tree=ast.parse((fork/'arguments/__init__.py').read_text())
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='OptimizationParams')
    init=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='__init__');defaults={}
    for n in init.body:
        if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Attribute):
            try:defaults[n.targets[0].attr]=ast.literal_eval(n.value)
            except ValueError:pass
    expected=dict(iterations=30000,position_lr_init=.00016,position_lr_final=.0000016,position_lr_delay_mult=.01,
        position_lr_max_steps=30000,feature_lr=.0025,opacity_lr=.05,scaling_lr=.005,rotation_lr=.001,
        percent_dense=.01,lambda_dssim=.2,lambda_dist=0.,lambda_normal=.05,opacity_cull=.05,
        densification_interval=100,opacity_reset_interval=3000,densify_from_iter=500,densify_until_iter=15000,densify_grad_threshold=.0002)
    for k,v in expected.items():assert defaults[k]==v,(k,defaults[k],v)
    base=json.loads((CFG/'fork_r19_base.json').read_text());unchanged=0
    for name,digest in base['base_file_sha256'].items():
        if name=='train.py':continue
        assert sha(fork/name)==digest,name;unchanged+=1
    files={str(p.relative_to(REPO)):sha(p) for p in fork.rglob('*') if p.is_file()}
    record=dict(at=stamp(),config_sha256=lock['config_sha256'],source_commit=os.environ.get('TARGET_COMMIT'),
        files=files,optimization_defaults=expected,base_files_unchanged=unchanged,seed=0,
        background_binding_sha256=sha(CFG/'background_r2.lock.json'),representatives_sha256=sha(CFG/'representatives_v1.json'),
        depth_lambda=.05,normal_activation='iteration > 7000, same baseline',
        opacity_population=dict(previous_implementation='r1 prior-origin descendants only',
            r2='all target-bound descendants including MVS background; prior-only median also recorded',
            reason='11/1 explicitly makes MVS background target-bound; order 3.6 says Gaussians seeded at targets',threshold=.05,
            thresholds_changed=False,definition_fixed_before_first_r2_render_and_training=True),
        checkpoint_evidence='7000 saved model, all training-view depth and RGB plus target coverage; continue training after recording; external CPU mesh check may stop both arms',
        training_started=False,scientific_verdict=None)
    dump(dest,record);print('STAGE1_R2_LOCKED',sha(dest),unchanged,flush=True)


if __name__=='__main__':main()
