"""Delivery zip: docs (report, tables, figures, progress, issues), config + locks, scripts, compact payload records, SHA256SUMS.

  python3 tu_package.py <name_prefix>     e.g. PHD-MAIN-TRAINUNIT-v1_가다
"""
import datetime as dt
import hashlib
import sys
import zipfile
from pathlib import Path

from tu_host import C, D, KST, R, TU

RECORD_GLOBS = ['cells/cells.json', 'targets/*.json', 'targets/overlap_check.json', 'stage1/*/ready.json', 'stage1/*/seed_receipt.json',
                'scenes/*/scene_receipt.json', 'scenes/*/split.json', 'runs/*/*/receipt.json', 'runs/*/*/attempt*/receipt.json',
                'runs/*/*/attempt*/launch.json', 'runs/*/*/attempt*/time_check_500.json', 'runs/*/*/attempt*/TIME_STOP.json',
                'runs/*/*/attempt*/DEADLINE_STOP.json', 'runs/*/*/attempt*/ERROR.json', 'runs/*/*/*/receipt.json',
                'runs/*/*/*/attempt*/receipt.json', 'runs/*/*/*/attempt*/time_check_500.json', 'runs/*/*/*/attempt*/ERROR.json',
                'runs/cells/*/merged/point_cloud.json', 'post/*/*.json', 'prepared/*/*.json', 'gt/meshes/*/final.json',
                'gt/scenes/*/distances/*_s0.json', 'gt/scenes/*/distances/seed1_s1.json',
                # addenda 12-17: filter runs (scene radius, filter record), merged filter cells, seed-1 filter scores
                'runs/*/*/attempt*/extent_override.json', 'runs/*/*/attempt*/addendum12_filter.json', 'runs/ef/*/merged/point_cloud.json',
                'gt/scenes/*/distances/ef_s1.json']


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(8 << 20), b''):
            h.update(b)
    return h.hexdigest()


def main(prefix):
    stamp = dt.datetime.now(KST).strftime('%m%d-%H%M')
    out = TU / 'delivery' / f'{prefix}_{stamp}.zip'
    out.parent.mkdir(parents=True, exist_ok=True)
    files = []
    for base, arc in [(D, 'docs'), (C, 'configs'), (R / 'scripts/phd/main_trainunit_v1', 'scripts')]:
        for p in sorted(base.rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts:
                files.append((p, f'{arc}/{p.relative_to(base)}'))
    for g in RECORD_GLOBS:
        for p in sorted(TU.glob(g)):
            if p.is_file() and not p.is_symlink():
                files.append((p, f'payload_records/{p.relative_to(TU)}'))
    seen = set()
    sums = []
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for p, a in files:
            if a in seen:
                continue
            seen.add(a)
            z.write(p, a)
            sums.append(f'{sha(p)}  {a}')
        z.writestr('SHA256SUMS', '\n'.join(sums) + '\n')
    print(out, len(sums), flush=True)


if __name__ == '__main__':
    main(sys.argv[1])
