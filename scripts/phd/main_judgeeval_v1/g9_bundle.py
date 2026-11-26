"""묶음: 보고서, 표, 그림, 점검 묶음, 설정, SHA256SUMS. 사용: g9_bundle.py 가|나|다|라 (다·라 = 덧붙임 1, 뷰어 HTML 은 라에만)"""
from common import *
import zipfile
def main(tag):
    stamp = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime('%m%d-%H%M'); name = f'PHD-MAIN-JUDGEEVAL-v1_{tag}_{stamp}_light.zip'
    if tag == '가':
        files = [D/'판단평가_보고_가.md', D/'판단코드_옮겨적기.md'] + sorted(p for p in (D/'tables/가').rglob('*') if p.is_file()) + sorted((D/'figures').glob('fig0_*')) + sorted(p for p in (D/'audit/가').rglob('*') if p.is_file())
    elif tag == '다':
        files = [D/'판단평가_보고_다.md'] + sorted(p for p in (D/'tables/다').rglob('*') if p.is_file()) + sorted(p for p in (D/'figures').glob('fig_d*')) + sorted((D/'figures').glob('fig7_2_examples_v2*'))
    elif tag == '라':
        files = [D/'판단평가_보고_라.md', D/'판단평가_보고_다.md', D/'figures/viewer/viewer_README.md'] + sorted(p for p in (D/'figures/viewer').rglob('*') if p.is_file() and p.name != 'viewer_README.md')
    else:
        files = [D/'판단평가_보고_나.md', D/'판단평가_보고_가.md', D/'판단코드_옮겨적기.md'] + sorted(p for p in (D/'tables').rglob('*') if p.is_file()) + sorted(p for p in (D/'figures').rglob('*') if p.is_file()) + sorted(p for p in (D/'audit/가').rglob('*') if p.is_file())
    files += [D/'progress.md', D/'issues.md', C/'judgeeval_v1.json', C/'judgeeval_v1.lock.json'] + ([C/'judgeeval_v1_add1.json', C/'judgeeval_v1_add1.lock.json'] if tag in ('다', '라') else []) + sorted(p for p in (R/'scripts/phd/main_judgeeval_v1').rglob('*') if p.is_file())
    files = [f for f in files if f.exists()]
    arc = lambda f: 'PHD-MAIN-JUDGEEVAL-v1/' + (str(f.relative_to(D)) if str(f).startswith(str(D)) else 'configs/' + f.name if str(f).startswith(str(C)) else 'scripts/' + str(f.relative_to(R/'scripts/phd/main_judgeeval_v1')))
    sums = '\n'.join(f'{sha(f)}  {arc(f)}' for f in files) + '\n'; (O/'delivery').mkdir(exist_ok=True); z = O/'delivery'/name
    with zipfile.ZipFile(z, 'w', zipfile.ZIP_DEFLATED) as Z:
        for f in files: Z.write(f, arc(f))
        Z.writestr('PHD-MAIN-JUDGEEVAL-v1/SHA256SUMS', sums)
    dump(z.with_suffix('.json'), dict(at=now(), zip=str(z), sha256=sha(z), files=len(files) + 1, scientific_verdict=None)); print('ZIP', z, sha(z))
if __name__ == '__main__': main(sys.argv[1])
