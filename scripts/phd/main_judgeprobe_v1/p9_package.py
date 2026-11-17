"""마무리: 다시 셀 것 5 그림을 docs/figures 로 이름 바꿔 옮김(json 에 출처 더함), 묶음 light.zip (보고서, 표, 그림, 설정, SHA256SUMS)."""
from common import *
import shutil, zipfile, glob
def main():
    st = O/'rc5_stage/figures'; FIG = D/'figures'
    for p in sorted(st.glob('fig6_gt_clusters_*.png')):
        stem = p.stem.replace('fig6_gt_clusters_', 'rc5_outside_new_faces_'); shutil.copyfile(p, FIG/f'{stem}.png')
        j = json.loads(p.with_suffix('.json').read_text()); j.update(rule="recount 5: '윤곽 밖의 새 면' clusters after those in JC figure 6, area descending, <= 2 per building, 20; drawn by JC s10_images.fig6 (only_gt path, title text from JC code)", source_stem=p.stem); dump(FIG/f'{stem}.json', j)
    stamp = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime('%m%d-%H%M'); z = O/f'PHD-MAIN-JUDGEPROBE-v1_{stamp}_light.zip'; files = []
    for base, root in [(D, 'docs'), (C, 'configs')]:
        for p in sorted(base.rglob('*')):
            if p.is_file(): files.append((p, f'{root}/{p.relative_to(base)}'))
    sums = ''.join(f'{sha(p)}  {a}\n' for p, a in files)
    with zipfile.ZipFile(z, 'w', zipfile.ZIP_DEFLATED) as f:
        for p, a in files: f.write(p, a)
        f.writestr('SHA256SUMS', sums)
    print('ZIP', z, len(files), z.stat().st_size, flush=True)
if __name__ == '__main__': main()
