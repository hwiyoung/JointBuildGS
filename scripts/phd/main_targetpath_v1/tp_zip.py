"""Pack the delivery zip (CPU). usage: tp_zip.py light | fill
light: 목표전달셈_요약.md, 관찰.md, 발주문_v1.md, issues.md, progress.md, checks.json, tables/, points/tp_*.npz, figures/ (orders 2-4, 6), scripts.
fill : the order-5 files (tables/tp_fill*, figures/fill_*, 채움_요약.md) + scripts. Writes /tp/zips/PHD-MAIN-TARGETPATH-v1_<MMDD-HHMM>_<kind>.zip."""
import sys, zipfile
sys.path.insert(0, '/repo/scripts/phd/main_targetpath_v1')
from tp_common import *

def main(kind):
    stamp = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime('%m%d-%H%M')
    name = f'PHD-MAIN-TARGETPATH-v1_{stamp}_light.zip' if kind == 'light' else f'PHD-MAIN-TARGETPATH-v1_채움_{stamp}.zip'
    files = []
    if kind == 'light':
        for p in ['목표전달셈_요약.md', '관찰.md', '발주문_v1.md', 'issues.md', 'progress.md', 'checks.json']:
            if (D/p).exists(): files.append((D/p, p))
        for sub in ['tables', 'figures', 'points']:
            for p in sorted((D/sub).glob('*')):
                if p.is_file() and not p.name.startswith(('tp_fill', 'fill_')): files.append((p, f'{sub}/{p.name}'))
    else:
        for p in ['채움_요약.md', 'issues.md']:
            if (D/p).exists(): files.append((D/p, p))
        for sub in ['tables', 'figures']:
            for p in sorted((D/sub).glob('*')):
                if p.name.startswith(('tp_fill', 'fill_')): files.append((p, f'{sub}/{p.name}'))
    for p in sorted((R/'scripts/phd/main_targetpath_v1').glob('*')):
        if p.is_file(): files.append((p, f'scripts/{p.name}'))
    out = O/'zips'/name; out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for src, arc in files: z.write(src, f'PHD-MAIN-TARGETPATH-v1/{arc}')
    dump(out.with_suffix('.json'), dict(at=now(), zip=name, files=[a for _, a in files], bytes=out.stat().st_size, sha256=sha(out), scientific_verdict=None))
    print('ZIP', out, len(files), out.stat().st_size, flush=True)

if __name__ == '__main__': main(sys.argv[1])
