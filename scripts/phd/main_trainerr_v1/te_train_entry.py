"""Verify locked inputs (own: FINALTRAIN, gt: GTJUDGE targets_gt), install the FINALTRAIN speed renderer, enter train.py of the mounted fork.
argv: <site> <prior> <own|gt> <train.py args...>"""
import runpy
from common import *
def main():
    site, prior, arm = sys.argv[1:4]; stem = f'{site}__{prior}'; src = FT if arm == 'own' else GT
    rec = json.loads((src/'verification'/f'inputs_{stem}.json').read_text()); assert rec['status'] == 'PASS'
    tfile = (FT/'targets' if arm == 'own' else GT/'targets_gt')/f'{stem}.npz'; root = src/'stage1'/stem
    assert sha(tfile) == rec['target_sha256'] and sha(root/'seeds.npz') == rec['seeds_sha256'] and sha(root/'maps/index.json') == rec['index_sha256']
    argv = sys.argv[4:]
    assert argv[argv.index('--jbgs_target_dir')+1] == str(root)
    if arm == 'gt': assert argv[argv.index('--jbgs_targets')+1] == str(tfile)
    else: assert '--jbgs_targets' not in argv
    for meta in json.loads((root/'maps/index.json').read_text())['views'].values(): assert sha(root/'maps'/meta['file']) == meta['sha256']
    model = Path(argv[argv.index('-m')+1]); assert not model.exists()
    runtime = C/'trainerr_v1.runtime.lock.json'
    if os.environ.get('TE_REQUIRE_RUNTIME') == '1':
        lock = json.loads(runtime.read_text()); assert lock['config_sha256'] == sha(C/'trainerr_v1.json')
        for p, h in lock['files'].items(): assert sha(p) == h, p
    dump(model.parent/'input_binding.json', dict(at=now(), arm=arm, stem=stem, config_sha256=sha(C/'trainerr_v1.json'), runtime_lock_sha256=sha(runtime) if runtime.exists() else None,
        source_files={str(p.relative_to('/source')): sha(p) for p in sorted(Path('/source').glob('*.py'))}, inputs=rec, trainlog_config=os.environ.get('JBGS_TRAINLOG_CONFIG'),
        argv=sys.argv, scientific_verdict=None))
    sys.path.insert(0, '/source'); sys.path.append('/repo/scripts/phd/main_finaltrain_v1')
    from renderer import install
    install(); sys.argv = ['/source/train.py']+argv; runpy.run_path('/source/train.py', run_name='__main__')
    last = int(argv[argv.index('--iterations')+1])
    assert (model/f'jbgs_complete/iteration_{last}/checkpoint.pth').is_file()
    dump(model.parent/'TRAINING_COMPLETE.json', dict(at=now(), iteration=last, scientific_verdict=None))
if __name__ == '__main__': main()
