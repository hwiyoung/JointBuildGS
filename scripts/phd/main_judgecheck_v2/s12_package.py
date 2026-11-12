"""묶음 가·나 (발주 5.4, 7절). s12_package.py <ga|na> <MMDD-HHMM>
가: 5.1~5.3 표, 그림 1·2·6, 설정, 보고서 초안(5천 자 안), SHA256SUMS. 나: 모든 표·그림, 패치·참값 점·사진 점마다 값, 학습용 판정 파일, 설정, 보고서. 파일 하나 400 MB 넘으면 나눔."""
from common import *
import zipfile
def files_ga():
    T = sorted((D/'tables').glob('c1_*')) + sorted((D/'tables').glob('c5_*')) + sorted((D/'tables').glob('c6_*')) + sorted((D/'tables').glob('s0_*'))
    F = [p for p in sorted((D/'figures').glob('*')) if p.name.startswith(('fig1_', 'fig2_', 'fig6_'))]
    return [(p, f'tables/{p.name}') for p in T] + [(p, f'figures/{p.name}') for p in F]
def files_na():
    out = [(p, f'tables/{p.name}') for p in sorted((D/'tables').glob('*'))] + [(p, f'figures/{p.name}') for p in sorted((D/'figures').glob('*'))]
    for sub in ['core_points', 'gt_points', 'photo_points', 'training_regions']:
        out += [(p, f'{sub}/{p.name}') for p in sorted((O/sub).glob('*.npz'))]
    return out
def main(kind, stamp):
    cfg(); common = [(C/'judgecheck_v2.json', 'config/judgecheck_v2.json'), (C/'judgecheck_v2.initial.lock.json', 'config/judgecheck_v2.initial.lock.json'), (C/'order_v2.txt', 'config/order_v2.txt'),
                     (D/'progress.md', 'progress.md'), (D/'issues.md', 'issues.md')]
    if (C/'judgecheck_v2.final.lock.json').exists(): common.append((C/'judgecheck_v2.final.lock.json', 'config/judgecheck_v2.final.lock.json'))
    rep = D/('보고서초안_가_v2.md' if kind == 'ga' else '판단검증_보고_v2.md')
    if rep.exists(): common.append((rep, rep.name))
    items = common + (files_ga() if kind == 'ga' else files_na()); label = '가' if kind == 'ga' else '나'
    dest = O/'delivery'; dest.mkdir(exist_ok=True); base = f'PHD-MAIN-JUDGECHECK-v2_{label}_{stamp}'
    sums = [f'{sha(p)}  {arc}' for p, arc in items]; (O/'tmp'/f'{base}_SHA256SUMS').write_text('\n'.join(sums) + '\n')
    parts = []; cur = []; size = 0
    for p, arc in items:
        s = p.stat().st_size
        if cur and size + s > 400*2**20: parts.append(cur); cur = []; size = 0
        cur.append((p, arc)); size += s
    if cur: parts.append(cur)
    names = []
    for k, part in enumerate(parts):
        name = f'{base}.zip' if len(parts) == 1 else f'{base}_part{k + 1:02d}.zip'; z = zipfile.ZipFile(dest/name, 'w', zipfile.ZIP_DEFLATED)
        for p, arc in part: z.write(p, arc)
        z.write(O/'tmp'/f'{base}_SHA256SUMS', 'SHA256SUMS'); z.close(); names.append(name)
    rec = dict(at=now(), kind=label, files=len(items), parts=names, sizes={n: (dest/n).stat().st_size for n in names}, sha256={n: sha(dest/n) for n in names}, scientific_verdict=None)
    dump(dest/f'{base}.json', rec); print('PACKAGE', json.dumps(rec, ensure_ascii=False))
if __name__ == '__main__': main(sys.argv[1], sys.argv[2])
