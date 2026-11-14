"""Addendum 4 work sa (copy of addendum3/a3_train_entry.py; addendum4 config; stop switch aware): verify the locked FINALTRAIN inputs (own targets), install the FINALTRAIN speed renderer, enter train.py of the mounted fork (r31).
TRAINERR te_train_entry.py rule (own arm), with the addendum3 config sha in the binding. argv: <site> <prior> <run> <train.py args...>"""
import runpy
sys_path = __import__('sys').path; sys_path.insert(0, '/repo/scripts/phd/main_trainerr_v1')
from common import *
def main():
    site, prior, run = sys.argv[1:4]; stem = f'{site}__{prior}'
    argv = sys.argv[4:]
    if '--jbgs_targets' in argv:   # sa-3: inputs built by a4_sa3_build.py (addendum4_sa3.json)
        root = Path(argv[argv.index('--jbgs_target_dir')+1]); tfile = Path(argv[argv.index('--jbgs_targets')+1]); rec = json.loads((root/'ready.json').read_text())
        assert sha(tfile) == rec['target_sha256'] and sha(root/'seeds.npz') == rec['seeds_sha256'] and sha(root/'maps/index.json') == rec['index_sha256']
        c3 = R/'configs/phd/main_trainerr_v1/addendum4_sa3.json'; assert sha(c3) == json.loads(c3.with_name('addendum4_sa3.lock.json').read_text())['config_sha256']
    else:
        rec = json.loads((FT/'verification'/f'inputs_{stem}.json').read_text()); assert rec['status'] == 'PASS'
        tfile = FT/'targets'/f'{stem}.npz'; root = FT/'stage1'/stem
        assert sha(tfile) == rec['target_sha256'] and sha(root/'seeds.npz') == rec['seeds_sha256'] and sha(root/'maps/index.json') == rec['index_sha256']
        assert argv[argv.index('--jbgs_target_dir')+1] == str(root) and '--jbgs_targets' not in argv
    for meta in json.loads((root/'maps/index.json').read_text())['views'].values(): assert sha(root/'maps'/meta['file']) == meta['sha256']
    model = Path(argv[argv.index('-m')+1]); assert not model.exists()
    cfgp = R/'configs/phd/main_trainerr_v1/addendum4.json'; lock = json.loads(cfgp.with_name('addendum4.lock.json').read_text()); assert sha(cfgp) == lock['config_sha256']
    dump(model.parent/'input_binding.json', dict(at=now(), run=run, stem=stem, addendum4_config_sha256=sha(cfgp), source_files={str(p.relative_to('/source')): sha(p) for p in sorted(Path('/source').glob('*.py'))},
        inputs=rec, trainlog_config=os.environ.get('JBGS_TRAINLOG_CONFIG'), trainlog_config_sha256=sha(os.environ['JBGS_TRAINLOG_CONFIG']) if os.environ.get('JBGS_TRAINLOG_CONFIG') else None,
        argv=sys.argv, scientific_verdict=None))
    sys.path.insert(0, '/source'); sys.path.append('/repo/scripts/phd/main_finaltrain_v1')
    from renderer import install
    install(); sys.argv = ['/source/train.py']+argv; runpy.run_path('/source/train.py', run_name='__main__')
    last = int(argv[argv.index('--jbgs_a4_stop_at')+1]) if '--jbgs_a4_stop_at' in argv else int(argv[argv.index('--iterations')+1])  # r31 stop switch
    assert (model/f'jbgs_complete/iteration_{last}/checkpoint.pth').is_file()
    dump(model.parent/'TRAINING_COMPLETE.json', dict(at=now(), iteration=last, scientific_verdict=None))
if __name__ == '__main__': main()
