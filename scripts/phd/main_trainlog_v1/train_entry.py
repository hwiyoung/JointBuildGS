"""Verify locked inputs, install the FINALTRAIN speed renderer, enter r23 or r27 train.py (order 1.1)."""
import runpy, sys
from common import *
def main():
    site, prior = sys.argv[1:3]; c = cfg(); assert (site, prior) == (SITE, PRIOR)
    rec = json.loads((FT/'verification'/f'inputs_{STEM}.json').read_text()); assert rec['status'] == 'PASS'
    root = FT/'stage1'/STEM
    assert sha(FT/'targets'/f'{STEM}.npz') == rec['target_sha256']
    assert sha(root/'seeds.npz') == rec['seeds_sha256'] and sha(root/'maps/index.json') == rec['index_sha256']
    for meta in json.loads((root/'maps/index.json').read_text())['views'].values(): assert sha(root/'maps'/meta['file']) == meta['sha256']
    model = Path(sys.argv[sys.argv.index('-m')+1]); assert not model.exists()
    runtime = C/'trainlog_v1.runtime.lock.json'
    if os.environ.get('TRAINLOG_REQUIRE_RUNTIME') == '1':
        lock = json.loads(runtime.read_text()); assert lock['config_sha256'] == sha(C/'trainlog_v1.json')
        for p, h in lock['files'].items(): assert sha(p) == h, p
    dump(model.parent/'input_binding.json', dict(at=now(), config_sha256=sha(C/'trainlog_v1.json'), runtime_lock_sha256=sha(runtime) if runtime.exists() else None,
        source_files={str(p.relative_to('/source')): sha(p) for p in sorted(Path('/source').glob('*.py'))}, inputs=rec, renderer=c['renderer'],
        trainlog_config=os.environ.get('JBGS_TRAINLOG_CONFIG'), argv=sys.argv, scientific_verdict=None))
    sys.path.insert(0, '/source'); sys.path.append('/repo/scripts/phd/main_finaltrain_v1')
    from renderer import install
    install(); sys.argv = ['/source/train.py']+sys.argv[3:]; runpy.run_path('/source/train.py', run_name='__main__')
    last = int(sys.argv[sys.argv.index('--iterations')+1])
    assert (model/f'jbgs_complete/iteration_{last}/checkpoint.pth').is_file()
    dump(model.parent/'TRAINING_COMPLETE.json', dict(at=now(), iteration=last, scientific_verdict=None))
if __name__ == '__main__': main()
