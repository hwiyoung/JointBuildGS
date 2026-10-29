"""Host orchestration of isolated GPU unit/preflight jobs; no training launch."""
import sys
from runtime import *


def baseline_arguments(model):
    cfg=read(CFG/'farpull_v1_prune_v1.json')
    template=next(r for r in cfg['runs'] if r['site']=='B173nb_b10' and r['name']=='fp_prune_dynnow_ALS_s0')
    args=args_for(template,model)
    args[args.index('--jbgs_lt_farpull_lambda')+1]='0.0'
    assert args[args.index('--jbgs_mv_consistency')+1]=='off'
    assert args[args.index('--jbgs_appearance')+1]=='off'
    return args


def main():
    phase=sys.argv[1];gpu=int(sys.argv[2]) if len(sys.argv)>2 else 1
    assert phase in ['unit','preflight']
    p=CFG/'farpull_v1_freespace_v1.json'
    assert sha(p)==read(p.with_suffix('.lock.json'))['sha256']
    attempt=int(sys.argv[3]) if len(sys.argv)>3 else 0
    suffix='' if not attempt else f'_attempt_{attempt}'
    dest=OUT/'freespace_v1/execution'/(phase+suffix)
    if phase=='unit':entry=['/repo/scripts/phd/main_farpull_v1/check_freespace.py']
    else:
        assert read(OUT/'freespace_v1/unit.json')['status']=='PASS'
        inputs={str(q.relative_to(REPO)):sha(q) for q in [*SCRIPTS.glob('*freespace*.py'),REPO/'src/phd/forks/GeoGS-conf-guided-v1-r18/jbgs_freespace.py']}
        save(OUT/('freespace_v1/implementation_lock'+suffix+'.json'),dict(at=now(),files=inputs,config_sha256=sha(p),scientific_verdict=None),True)
        entry=['/repo/scripts/phd/main_farpull_v1/preflight_freespace.py',*baseline_arguments('/o/freespace_v1/preflight_model'+suffix)]
    with gpu_lock(gpu):
        admission()
        assert execute(docker('freespace-'+phase,entry,gpu,'B173nb_b10'),dest)==0


if __name__=='__main__':main()
