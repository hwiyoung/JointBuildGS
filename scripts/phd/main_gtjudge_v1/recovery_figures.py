"""Render the existing three-view figure one panel at a time without dropping faces."""
import gc
import subprocess
import sys
import figures as f
from figures import np, plt, Path, json, O, D, dump, now, sha
from PIL import Image, ImageChops
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

ANGLES = [(90, -90), (35, -55), (35, 125)]


def shell(n, title):
    fig = plt.figure(figsize=(6*n, 15))
    fig.suptitle(title)
    fig.subplots_adjust(top=.95, wspace=.15, hspace=.15)
    return fig


def panel(fig, n, j, i, tri, colors, limits, method):
    lo, hi, zlo, zhi = limits
    ax = fig.add_subplot(3, n, i*n+j+1, projection='3d')
    ax.add_collection3d(Poly3DCollection(tri, facecolors=colors, edgecolors='none', rasterized=True))
    ax.view_init(*ANGLES[i])
    ax.set(xlim=(lo[0], hi[0]), ylim=(lo[1], hi[1]), zlim=(zlo-.2, zhi+.2),
           title=method+f' · 시점 {i+1}')
    ax.set_box_aspect((hi[0]-lo[0], hi[1]-lo[1], zhi-zlo+.4))


def prepare(site, prior, method, lo, hi, cache):
    path = cache / (method+'.json')
    if path.exists():
        return json.loads(path.read_text())
    root = O / 'scenes' / f'{site}__{prior}'
    meta = json.loads((root/'distances'/f'{method}.json').read_text())
    vertices, faces = f.read_surface(meta['mesh'])
    chunks = []
    for start in range(0, len(faces), 100000):
        tri = vertices[faces[start:start+100000]]
        mid = tri.mean(1)
        keep = ((mid[:, :2] >= lo) & (mid[:, :2] <= hi)).all(1)
        chunks.append(tri[keep])
    tri = np.concatenate(chunks)
    del vertices, faces, chunks
    gc.collect()
    assert len(tri), 'inherited ROI contains no faces'
    if method == 'FINALTRAIN_30000':
        points = f.loadz(f.score_dir(site, prior, method)/'points.npz', ['sample_xyz'])['sample_xyz']
    else:
        points = f.loadz(root/'distances'/f'{method}_samples.npz', ['xyz'])['xyz']
    z = f.loadz(root/'distances'/f'{method}.npz', ['sample_s', 'sample_tau'])
    indices = f.cKDTree(points).query(tri.mean(1), workers=4)[1]
    colors = f.colors(z['sample_s'][indices], z['sample_tau'][indices])
    np.save(cache/(method+'_tri.npy'), tri)
    np.save(cache/(method+'_colors.npy'), colors)
    rec = dict(method=method, faces=len(tri), zmin=float(tri[:, :, 2].min()),
        zmax=float(tri[:, :, 2].max()), mesh_sha256=meta['mesh_sha256'],
        geometry_filter='inherited inclusive face-centroid XY ROI', faces_dropped_for_memory=0)
    dump(path, rec)
    print('FIGURE_ROI_READY', method, len(tri), flush=True)
    return rec


def render_panel(cache, j, i):
    cache = Path(cache)
    meta = json.loads((cache/'layout.json').read_text())
    method = meta['methods'][j]
    tri = np.load(cache/(method+'_tri.npy'), mmap_mode='r')
    colors = np.load(cache/(method+'_colors.npy'), mmap_mode='r')
    fig = shell(len(meta['methods']), meta['title'])
    panel(fig, len(meta['methods']), j, i, tri, colors, meta['limits'], method)
    fig.savefig(cache/f'panel_{j}_{i}.png', dpi=300, facecolor='white')
    plt.close(fig)
    print('FIGURE_PANEL_READY', method, i, flush=True)


def multiview(site, prior, stage, methods, sec, sources):
    if sec['status'] != 'PASS':
        return
    stem = f'{site}__{prior}'
    output = D/'figures'/f'{stem}_{stage}_mesh_views.png'
    if output.exists() and output.with_suffix('.json').exists():
        return
    cache = O/'figure_cache/recovery_20261106'/f'{stem}_{stage}'
    cache.mkdir(parents=True, exist_ok=True)
    ends = np.array([sec['start'], sec['end']])
    lo, hi = ends.min(0)-2, ends.max(0)+2
    recs = [prepare(site, prior, m, lo, hi, cache) for m in methods]
    limits = [lo.tolist(), hi.tolist(), min(r['zmin'] for r in recs), max(r['zmax'] for r in recs)]
    title = stem+' · 정답 판단 결과 메시 · 흰색 τ 안 / 파랑 음 / 빨강 양 / 회색 면 없음'
    layout = dict(methods=methods, title=title, limits=limits)
    if (cache/'layout.json').exists():
        assert json.loads((cache/'layout.json').read_text()) == layout
    else:
        dump(cache/'layout.json', layout)
    composed = None
    for j in range(len(methods)):
        for i in range(3):
            path = cache/f'panel_{j}_{i}.png'
            if not path.exists():
                subprocess.run([sys.executable, __file__, 'panel', str(cache), str(j), str(i)], check=True)
            with Image.open(path) as raw:
                image = raw.convert('RGB')
                composed = image.copy() if composed is None else ImageChops.darker(composed, image)
    composed.save(output, dpi=(300, 300))
    dump(output.with_suffix('.json'), dict(at=now(), stage=3, methods=methods, section=sec,
        face_color='nearest saved result-side cylinder sample', camera_angles=ANGLES,
        dpi=300, crs='EPSG:25832; inherited local XY [690953,5336071]',
        sources=[dict(path=str(p), sha256=sha(p)) for p in sources], script_sha256=sha(__file__),
        memory_recovery='same full layout, ROI and faces; render one panel per process',
        faces_by_method=recs, scientific_verdict=None))


def test():
    """Verify panel composition against the original simultaneous rendering."""
    import io
    tri = np.array([[[0., 0., 0.], [1., 0., 0.], [0., 1., .6]],
                    [[1., 0., 0.], [1., 1., .2], [0., 1., .6]]])
    limits = [[0, 0], [1, 1], 0, .6]
    def pixels(fig):
        buf = io.BytesIO()
        fig.savefig(buf, format='png', dpi=40, facecolor='white')
        plt.close(fig)
        buf.seek(0)
        return Image.open(buf).convert('RGB')
    original = shell(4, 'composition verification')
    merged = None
    for j in range(4):
        for i in range(3):
            panel(original, 4, j, i, tri, ['#b2182b', '#2166ac'], limits, str(j))
            single = shell(4, 'composition verification')
            panel(single, 4, j, i, tri, ['#b2182b', '#2166ac'], limits, str(j))
            image = pixels(single)
            merged = image if merged is None else ImageChops.darker(merged, image)
    expected = np.asarray(pixels(original))
    actual = np.asarray(merged)
    assert np.array_equal(actual, expected), int((actual != expected).sum())
    dump(D/'verification/addendum2_recovery_figure_composition.json',
         dict(status='PASS', identical_pixels=True, panels=12, faces_dropped=0,
              script_sha256=sha(__file__), scientific_verdict=None))
    print('PASS_IDENTICAL_PANEL_COMPOSITION', flush=True)


def main(site, prior, arm):
    f.multiview = multiview
    # Existing map/section outputs are not rewritten by the recovery renderer.
    original_save = f.save
    def save_missing(fig, name, meta, sources):
        path = D/'figures'/(name+'.png')
        if path.exists() and path.with_suffix('.json').exists():
            plt.close(fig)
            return
        original_save(fig, name, meta, sources)
    f.save = save_missing
    if arm == 'fix':
        import add2_figures
        add2_figures.config2()
        add2_figures.fixed(site, prior)
    else:
        f.cfg()
        stem = f'{site}__{prior}'
        root = O/'scenes'/stem
        sec = f.section(site, prior)
        methods = ['FINALTRAIN_30000']+[m for m in ['A1', 'A2'] if (root/'distances'/f'{m}.npz').exists()]
        sources = [root/'rows.npz', root/'stage1_cells.npz', root/'section.json']
        sources += [root/'distances'/f'{m}.npz' for m in methods]
        title = f'{site} · {prior} · 정답 판단 진단'
        if not (D/'figures'/f'{stem}_{arm}_preservation_maps.png').exists():
            row = f.loadz(root/'rows.npz')
            cell = f.loadz(root/'stage1_cells.npz')
            take = cell['case_id'] == 2
            fig, axes = plt.subplots(1, len(methods), figsize=(7*len(methods), 7.5), squeeze=False)
            fig.subplots_adjust(bottom=.23, top=.87)
            for ax, method in zip(axes[0], methods):
                s = f.loadz(root/'distances'/f'{method}.npz', ['row_s'])['row_s']
                cc = np.where(np.isfinite(s)&(abs(s)<=row['row_tau_m']), f.STAT['correct'], f.STAT['wrong'])
                f.map_ax(ax, row['xyz'][take], cc[take], method, sec)
                f.legend(ax, [('τ 안', f.STAT['correct']), ('τ 밖', f.STAT['wrong'])])
            fig.suptitle(title+' · 보존 칸')
            f.save(fig, stem+'_'+arm+'_preservation_maps', dict(stage=3, methods=methods), sources)
        if not (D/'figures'/f'{stem}_{arm}_section.png').exists():
            fig, ax = plt.subplots(figsize=(14, 6))
            fig.subplots_adjust(bottom=.22, top=.85)
            if sec['status'] == 'PASS':
                for m, c in zip(methods, ['#4B2E8A', '#009e73', '#d55e00']):
                    ax.add_collection(f.LineCollection(f.segments(site, prior, m, sec), colors=c, lw=1, label=m))
                row = f.loadz(root/'rows.npz', ['xyz'])
                points = f.section_points(row['xyz'], sec)
                ax.scatter(points[:, 0], points[:, 1], s=4, color='black', label='참값')
                ax.autoscale_view()
                ax.set(xlim=(0, sec['length_m']), xlabel='단면 거리 (m)', ylabel='지역 높이 (m)')
                ax.legend(loc='upper center', bbox_to_anchor=(.5, -.15), ncol=4)
            fig.suptitle(title)
            f.save(fig, stem+'_'+arm+'_section', dict(stage=3, methods=methods, section=sec), sources)
        multiview(site, prior, arm, methods, sec, sources)


if __name__ == '__main__':
    if sys.argv[1] == 'panel':
        render_panel(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]))
    elif sys.argv[1] == 'test':
        test()
    else:
        main(*sys.argv[1:])
