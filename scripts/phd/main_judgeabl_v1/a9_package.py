"""묶음 만들기: delivery/PHD-MAIN-JUDGEABL-v1_<가|나>_<월일>-<시분>_light.zip (보고서, 표, 그림, 설정, SHA256SUMS). 사용: a9_package.py <가|나>"""
from common import *
import zipfile, datetime as dt
def main(tag):
    ts = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime('%m%d-%H%M'); out = O/'delivery'/f'PHD-MAIN-JUDGEABL-v1_{tag}_{ts}_light.zip'; out.parent.mkdir(exist_ok=True)
    files = [D/'판단비교절제_보고_v1.md', D/'판단비교절제_보고_v1_부록.md', D/'issues.md', D/'progress.md', C/'judgeabl_v1.json', C/'judgeabl_v1.lock.json'] + sorted(x for x in (D/'tables').glob('*') if x.is_file()) + sorted(x for x in (D/'figures').glob('*') if x.is_file())
    if tag == '라':   # 덧붙임 2
        files = [D/'판단비교절제_덧붙임2_보고_v1.md', D/'issues.md', D/'progress.md'] + sorted(C.glob('judgeabl_v1_addendum2*.json')) + sorted((D/'tables/addendum2').glob('*')) + sorted((D/'figures/addendum2').glob('*')) \
                + [D/'tables'/f'{n}.{e}' for n in ['s_all_variants', 's_transitions', 's_main_summary'] for e in ['csv', 'md']]
    if tag == '전체':   # 본 작업 + 덧붙임 1 한 파일 (사용자 요청 11-17)
        files = [D/'판단비교절제_보고_v1.md', D/'판단비교절제_보고_v1_부록.md', D/'판단비교절제_덧붙임1_보고_v1.md', D/'판단비교절제_덧붙임2_보고_v1.md', D/'issues.md', D/'progress.md'] + sorted(C.glob('judgeabl_v1*.json')) \
                + sorted(x for x in (D/'tables').rglob('*') if x.is_file()) + sorted(x for x in (D/'figures').rglob('*') if x.is_file()) + sorted(x for x in (D/'fusion_all').rglob('*') if x.is_file())
    if tag == '다':   # 덧붙임 1
        files = [D/'판단비교절제_덧붙임1_보고_v1.md', D/'issues.md', D/'progress.md'] + sorted(C.glob('judgeabl_v1*.json')) + sorted((D/'tables/addendum1').glob('*')) + sorted((D/'figures/addendum1').glob('*')) \
                + sorted((D/'figures').glob('fig2_*')) + [D/'tables'/f'{n}.{e}' for n in ['s_all_variants', 's_transitions', 's_building_diff', 's_name_made'] for e in ['csv', 'md']]
    if tag == '가': files = [f for f in files if not (f.parent.name == 'figures' and not f.name.startswith(('fig1', 'fig2', 'fig5')))]
    sums = []
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for f in files:
            arc = str(f.relative_to(D)) if f.parent != C else 'configs/' + f.name
            z.write(f, arc); sums.append(f'{sha(f)}  {arc}')
        z.writestr('SHA256SUMS', '\n'.join(sums) + '\n')
    if out.stat().st_size > 28*2**20 and tag != '전체':   # 원격 보기 첨부 30 MiB 한도: 같은 내용을 두 조각으로도 (조각 2 = 그림 3 PNG)
        with zipfile.ZipFile(out) as z0:
            names = [n for n in z0.namelist() if n != 'SHA256SUMS']; big = [n for n in names if n.startswith('figures/fig3') and n.endswith('.png')]
            for k, part in enumerate([[n for n in names if n not in big], big], 1):
                q = out.with_name(out.stem + f'_part{k}.zip')
                with zipfile.ZipFile(q, 'w', zipfile.ZIP_DEFLATED) as z: [z.writestr(n, z0.read(n)) for n in part]; z.writestr('SHA256SUMS', z0.read('SHA256SUMS'))
                print('PART', q, q.stat().st_size)
    print('PACKAGE', out, len(files), out.stat().st_size); progress(f'묶음 {tag}: {out.name} ({len(files)} 파일, {out.stat().st_size} B)')
if __name__ == '__main__': main(sys.argv[1])
