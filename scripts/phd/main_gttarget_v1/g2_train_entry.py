"""Stage 2 training entry (GPU container, fork r28 at /source): verify the locked GT target inputs and the stage-1 checks, install the FINALTRAIN
speed renderer, run the unchanged train.py. argv: <stem> <train.py args...>"""
import runpy
import sys
sys.path.insert(0, '/repo/scripts/phd/main_gttarget_v1')
from gt_common import *

def main():
    stem = sys.argv[1]; argv = sys.argv[2:]; root = O/'stage1'/stem; tfile = O/'targets'/f'{stem}.npz'
    probe = int(argv[argv.index('--iterations')+1]) <= 300   # loader/record probe: no stage-2 lock or stage-1 check needed, never a result
    if probe: chk = dict(pass_={'probe': True}); chk['pass'] = {'probe': True}
    else:
        c = cfg(2); chk = json.loads((O/'checks'/f'{stem}.json').read_text())
        failed = [k for k, v in chk['pass'].items() if v is not True]
        assert not failed or (c['precheck'].get('user_override') and set(failed) <= {'target_mesh', 'target_depth'}), ('STAGE1_CHECK_NOT_PASSED', chk['pass'])
    rd = json.loads((root/'ready.json').read_text())
    assert sha(tfile) == rd['target_sha256'] and sha(root/'seeds.npz') == rd['seeds_sha256'] and sha(root/'maps/index.json') == rd['index_sha256']
    assert argv[argv.index('--jbgs_target_dir')+1] == str(root) and argv[argv.index('--jbgs_targets')+1] == str(tfile)
    for meta in json.loads((root/'maps/index.json').read_text())['views'].values(): assert sha(root/'maps'/meta['file']) == meta['sha256']
    model = Path(argv[argv.index('-m')+1]); assert not model.exists()
    dump(model.parent/'input_binding.json', dict(at=now(), stem=stem, title=TITLE, config_sha256=sha(C/'gttarget_v1.json'), stage1_check=chk['pass'],
        source_files={str(p.relative_to('/source')): sha(p) for p in sorted(Path('/source').glob('*.py'))}, ready=rd, trainlog_config=os.environ.get('JBGS_TRAINLOG_CONFIG'),
        trainlog_config_sha256=sha(os.environ['JBGS_TRAINLOG_CONFIG']), argv=sys.argv, scientific_verdict=None))
    sys.path.insert(0, '/source'); sys.path.append('/repo/scripts/phd/main_finaltrain_v1')
    import types  # the FINALTRAIN renderer reads cfg()['renderer'] from a module named common: bind it to finaltrain_v1.json read-only (as TRAINERR does)
    shim = types.ModuleType('common'); shim.sha = sha; shim.cfg = lambda: dict(renderer=json.loads((R/'configs/phd/main_finaltrain_v1/finaltrain_v1.json').read_text())['renderer'])
    sys.modules['common'] = shim
    from renderer import install
    install(); sys.argv = ['/source/train.py']+argv; runpy.run_path('/source/train.py', run_name='__main__')
    last = int(argv[argv.index('--iterations')+1])
    assert (model/f'jbgs_complete/iteration_{last}/checkpoint.pth').is_file()
    dump(model.parent/'TRAINING_COMPLETE.json', dict(at=now(), iteration=last, scientific_verdict=None))

if __name__ == '__main__': main()
