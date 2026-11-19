#!/usr/bin/env python3
"""PHD-MAIN-BASE151-v1 interim light bundle (host, stdlib; request 2026-11-19 '중간 묶음' 3절).

  python3 b151_package_interim.py
  -> PH/delivery/PHD-MAIN-BASE151-v1_중간_<MMDD>-<HHMM>_light.zip
Members: 중간보고.md at the top, then the tables (md, json), figures (png + json), reports and config files; no meshes, no models, no scripts.
A manifest with sha256 of every member is written inside. scientific_verdict: null
"""
import datetime as dt
import hashlib
import json
import zipfile
from pathlib import Path

W = Path(__file__).resolve().parents[3]
PH = (W.parent / 'JointBuildGS-artifacts').resolve() / 'phase-payloads/phd'
DOC = W / 'docs/experiments/phd/main_base151_v1'
KST = dt.timezone(dt.timedelta(hours=9))
TABLES = ['gt_buildings', 'gt_summary', 'inputs_sizes', 'method_filter', 'run_records', 'stops', 'running_status']


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(8 << 20), b''):
            h.update(b)
    return h.hexdigest()


def main():
    t = dt.datetime.now(KST)
    dest = PH / 'delivery' / f'PHD-MAIN-BASE151-v1_중간_{t:%m%d}-{t:%H%M}_light.zip'
    files = [DOC / '중간보고.md', DOC / '준비.md', DOC / 'issues.md', DOC / 'progress.md', DOC / 'lgdm_notes.md', DOC / '비교방법151_발주문_v1.md',
             DOC / 'tables/differences.md']
    for n in TABLES:
        files += [DOC / 'tables' / f'{n}.md', DOC / 'tables' / f'{n}.json']
    files += sorted(p for p in (DOC / 'tables/interim').glob('*') if p.suffix in ('.md', '.json') and not p.name.startswith('t42_gap'))
    files += sorted(p for p in (DOC / 'figures/interim').rglob('*') if p.suffix in ('.png', '.json'))
    files += sorted(p for p in (W / 'configs/phd/main_base151_v1').rglob('*') if p.is_file())
    missing = [str(p) for p in files if not p.exists()]
    assert not missing, missing
    man = []
    with zipfile.ZipFile(dest, 'w', zipfile.ZIP_DEFLATED) as z:
        for p in files:
            arc = p.name if p.name == '중간보고.md' else str(p.relative_to(W))
            z.write(p, arc)
            man.append(dict(path=arc, bytes=p.stat().st_size, sha256=sha(p)))
        z.writestr('MANIFEST.json', json.dumps(dict(at=t.isoformat(), task='PHD-MAIN-BASE151-v1', label='중간 light', files=man,
                                                    note='no meshes, no models, no scripts (request 3)', scientific_verdict=None), ensure_ascii=False, indent=1))
    print('ZIP', dest, len(man), dest.stat().st_size, sha(dest))


if __name__ == '__main__':
    main()
