"""PHD-MAIN-TRAINUNIT-v2 bundles (host, stdlib only).
  python3 tu2_package.py <준비|가|final>   -> PH2/delivery/PHD-MAIN-TRAINUNIT-v2[_<stage>]_<MMDD-HHMM>.zip
Contents: docs/.../v2 (tables, figures, progress, issues, summaries), 보고_v2.md, order v2, config + lock, v2 scripts,
payload records (cells.json, stage1 receipts, run receipts/launch/command/trace files, post timing, prepared commands), SHA256SUMS.
"""
import datetime as dt
import hashlib
import json
import sys
import zipfile
from pathlib import Path

R = Path(__file__).resolve().parents[3]
TU = Path('/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_trainunit_v1/PHD-MAIN-TRAINUNIT-v2')
D = R / 'docs/experiments/phd/main_trainunit_v1'
KST = dt.timezone(dt.timedelta(hours=9))


def main(stage):
    t = dt.datetime.now(KST)
    name = 'PHD-MAIN-TRAINUNIT-v2' + ('' if stage == 'final' else f'_{stage}') + f'_{t:%m%d-%H%M}.zip'
    out = TU / 'delivery' / name
    out.parent.mkdir(parents=True, exist_ok=True)
    files = []
    for p in sorted((D / 'v2').rglob('*')):
        if p.is_file():
            files.append((p, 'docs/' + str(p.relative_to(D / 'v2'))))
    for p in sorted(D.glob('보고_v2*.md')) + sorted(D.glob('학습단위비교_발주문_v2*.md')):
        if p.exists():
            files.append((p, 'docs/' + p.name))
    for p in [R / 'configs/phd/main_trainunit_v1/trainunit_v2.json', R / 'configs/phd/main_trainunit_v1/trainunit_v2.lock.json']:
        files.append((p, 'config/' + p.name))
    for p in sorted((R / 'scripts/phd/main_trainunit_v1').glob('*')):
        if p.is_file() and (p.name.startswith(('tu2_', 'run2_')) or p.name in ('tu_train_entry.py', 'tu_campus.py', 'tu_cells.py', 'tu_postcpu.py',
                                                                                 'tu_post.py', 'tu_post_fix.py', 'tu_merge_tol.py', 'tu_host.py', 'tu_common.py', 'tu_tables.py', 'oom_guard.sh')):
            files.append((p, 'scripts/' + p.name))
    keep = ('.json', '.jsonl', '.log', '.md', '.txt')
    for sub in ['cells', 'stage1', 'runs', 'post', 'prepared', 'control']:
        for p in sorted((TU / sub).rglob('*')) if (TU / sub).exists() else []:
            if not p.is_file() or p.is_symlink() or p.suffix not in keep or '/maps/' in str(p) or p.stat().st_size > 50 << 20:
                continue
            if sub == 'runs' and p.suffix == '.log' and p.name != 'train.log':
                continue
            if sub == 'runs' and p.name == 'train.log':
                continue   # progress-bar logs: kept on disk, not bundled
            files.append((p, 'payload_records/' + str(p.relative_to(TU))))
    sums = []
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for src, arc in files:
            z.write(src, arc)
            sums.append(f'{hashlib.sha256(src.read_bytes()).hexdigest()}  {arc}')
        z.writestr('SHA256SUMS', '\n'.join(sums) + '\n')
        z.writestr('MANIFEST.json', json.dumps(dict(at=t.isoformat(), stage=stage, files=len(files), commit_at_bundle=None,
                                                    payload_root=str(TU), scientific_verdict=None), ensure_ascii=False, indent=1))
    print(out, len(files), round(out.stat().st_size / 2 ** 20, 1), 'MiB')


if __name__ == '__main__':
    main(sys.argv[1])
