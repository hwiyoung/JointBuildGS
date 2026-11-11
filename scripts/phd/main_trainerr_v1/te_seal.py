"""Seal the r28 source, this task's scripts and configs after the unit checks pass (TRAINLOG seal_runtime.py rule)."""
from common import *
def main():
    u = json.loads((O/'verification/unit_checks.json').read_text()); assert u['status'] == 'PASS', 'unit checks not PASS'
    files = {}
    for p in sorted(Path('/source').rglob('*')):
        if p.is_file() and '__pycache__' not in p.parts: files[str(p)] = sha(p)
    # training-path files only (analysis scripts stay editable while runs train)
    for p in [R/'scripts/phd/main_trainerr_v1/te_train_entry.py', R/'scripts/phd/main_trainerr_v1/common.py', R/'scripts/phd/main_finaltrain_v1/renderer.py',
              C/'trainerr_v1.json', C/'trainlog_te.json', C/'trainlog_te.lock.json', C/'unitcheck_v2.json', R/'configs/phd/main_finaltrain_v1/finaltrain_v1.json']: files[str(p)] = sha(p)
    dump(C/'trainerr_v1.runtime.lock.json', dict(sealed_at=now(), config_sha256=sha(C/'trainerr_v1.json'), unit_checks_sha256=sha(O/'verification/unit_checks.json'), files=files, scientific_verdict=None))
    print('SEALED', len(files))
if __name__ == '__main__': main()
