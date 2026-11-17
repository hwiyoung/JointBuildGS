"""묶음 만들기: delivery/PHD-MAIN-JUDGEABL-v1_<가|나>_<월일>-<시분>_light.zip (보고서, 표, 그림, 설정, SHA256SUMS). 사용: a9_package.py <가|나>"""
from common import *
import zipfile, datetime as dt
def main(tag):
    ts = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime('%m%d-%H%M'); out = O/'delivery'/f'PHD-MAIN-JUDGEABL-v1_{tag}_{ts}_light.zip'; out.parent.mkdir(exist_ok=True)
    files = [D/'판단비교절제_보고_v1.md', D/'issues.md', D/'progress.md', C/'judgeabl_v1.json', C/'judgeabl_v1.lock.json'] + sorted((D/'tables').glob('*')) + sorted((D/'figures').glob('*'))
    if tag == '가': files = [f for f in files if not (f.parent.name == 'figures' and not f.name.startswith(('fig1', 'fig2', 'fig5')))]
    sums = []
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for f in files:
            arc = ('configs/' if f.parent == C else '') + str(f.relative_to(D)) if f.parent != C else 'configs/' + f.name
            z.write(f, arc); sums.append(f'{sha(f)}  {arc}')
        z.writestr('SHA256SUMS', '\n'.join(sums) + '\n')
    print('PACKAGE', out, len(files), out.stat().st_size); progress(f'묶음 {tag}: {out.name} ({len(files)} 파일, {out.stat().st_size} B)')
if __name__ == '__main__': main(sys.argv[1])
