"""Seal r27 fork + TRAINLOG scripts + config before stage 2 (train_entry checks it with TRAINLOG_REQUIRE_RUNTIME=1)."""
from common import *
def main():
    out = C/'trainlog_v1.runtime.lock.json'; assert not out.exists()
    unit = json.loads((O/'verification/unit_checks.json').read_text()); assert unit['status'] == 'PASS', unit['status']
    files = {}
    for root in [R/'src/phd/forks/GeoGS-conf-guided-v1-r27', R/'scripts/phd/main_trainlog_v1', R/'scripts/phd/main_finaltrain_v1/renderer.py']:
        for p in ([root] if root.is_file() else sorted(root.rglob('*'))):
            if p.is_file() and '__pycache__' not in p.parts: files[str(p)] = sha(p)
    dump(out, dict(sealed_at=now(), config_sha256=sha(C/'trainlog_v1.json'), unit_checks_sha256=sha(O/'verification/unit_checks.json'), files=files, scientific_verdict=None))
    print('SEALED', len(files))
if __name__ == '__main__': main()
