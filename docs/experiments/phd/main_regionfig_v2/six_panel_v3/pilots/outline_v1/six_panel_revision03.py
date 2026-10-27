"""Restore area-level 2x3 comparisons from frozen, supplied analysis values.

Run only through run_cpu.py. Old figures and all supplied values are immutable.
"""
from draw_figures import *
from six_panel_spatial import LAYER_KEYS, spatial_section, projected_guides
import html
import os
import re
import shutil
import zipfile
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.text import Text
from PIL import ImageDraw

REVISION = 'six_panel_v3'
OUT = DOC / REVISION
CONFIG = CFG / REVISION / 'presentation.json'
LOCK = CFG / REVISION / 'presentation.lock.json'
REGION_NAMES = ['다듬기', '보정', '보존', '둘 다 범위 밖', '상속·복원 결측', '상속·사진 부족']
JUDGE_NAMES = ['기존 면 지지', '기존 면 반박', '판단 유보', '검사 사진 부족']
RESULT_COLORS = {True: '#2171b5', False: '#d04a52'}


def source_figures():
    return sorted((DOC / 'figures').glob('영역표본_*.json'))


def prepare():
    assert not LOCK.exists(), 'Configuration already locked'
    protected = []
    for root in [DOC / 'figures', DOC / 'representative_v1', DOC / 'representative_v2',
                 CFG / 'representative_v1', CFG / 'representative_v2']:
        for p in sorted(root.rglob('*')):
            if p.is_file():
                protected.append(dict(path=str(p), sha256=sha(p)))
    inputs = [CFG/'regionfig_v2.json', CFG/'regionfig_v2.lock.json',
              PAY/'joined_ALS.npz', PAY/'joined_LoD2.npz',
              PAY/'input/ALS_sites.npz', PAY/'input/LoD2_sites.npz',
              W/'mvs/full/sparse/cameras.bin', W/'mvs/full/sparse/images.bin']
    dump(LOCK, dict(at=now(), task_id=load(CONFIG)['task_id'],
         config_sha256=sha(CONFIG), inputs=[dict(path=str(p), sha256=sha(p)) for p in inputs],
         protected=protected, source_head=os.environ['JBGS_SOURCE_HEAD'], scientific_verdict=None))
    OUT.mkdir(parents=True, exist_ok=True)
    dump(OUT/'delivery_status.json', dict(status='DRAFT_NOT_FOR_HANDOVER',
         reason='Awaiting eight rendered figures, independent numerical checks and author visual review.', scientific_verdict=None))
    print('LOCKED six-panel revision', len(protected), flush=True)


def settings():
    c, lock = load(CONFIG), load(LOCK)
    assert sha(CONFIG) == lock['config_sha256'], 'Presentation config changed after lock'
    assert sha(CFG/'regionfig_v2.json') == next(x['sha256'] for x in lock['inputs'] if x['path'].endswith('/regionfig_v2.json'))
    return c


def interest_area(ident, d, g, target):
    ids = g['ids'][d['roof_like'][g['ids']]]
    selected = regions(d)[ids] == target
    if ident in ['5', '6', '8']:
        selected &= d['judgment'][ids] == (0 if ident == '6' else 1)
    if ident == '8':
        selected &= d['cell'][ids] == 5
    mask = np.zeros(len(d['area']), dtype=bool); mask[ids[selected]] = True
    polys = g['polys'][d['roof_like'][g['ids']]][selected]
    low, high = g['corners'].min(axis=0), g['corners'].max(axis=0)
    shape = np.ceil(high-low).astype(int)+3
    canvas = Image.new('L', tuple(int(x) for x in shape), 0); draw = ImageDraw.Draw(canvas)
    for poly in polys:
        draw.polygon([tuple(q) for q in poly-low+1], fill=1)
    raster = np.array(canvas)
    area = float(d['area'][mask].astype(float).sum())
    assert area > 0, 'No case-specific area inside the displayed photo'
    result = dict(patch_ids=d['patch_id'][mask], area_m2=area,
                  selection='region and photo-check condition only; loss outcomes not used')
    for key in ['category', 'check']:
        ok = abs(d['z_'+key].astype(float)-d['gt_p'].astype(float)) <= d['tau'].astype(float)
        result['ok_'+key+'_pct'] = safe_pct(d['area'].astype(float), mask, ok)
    return result, (np.arange(shape[0])+low[0]-1, np.arange(shape[1])+low[1]-1, raster)


def overlay(ax, ex, d, g, im, sec, mode, alpha, outline):
    photo(ax, ex, d, g, im, 'raw')
    roof = d['roof_like'][g['ids']]
    ids, polys = g['ids'][roof], g['polys'][roof]
    reg, judge = regions(d)[ids], judgments(d)[ids]
    if mode == 'region':
        colors = [REGION_COLORS[k] if k < 6 else 'none' for k in reg]
        ax.add_collection(PolyCollection(polys, facecolors=colors, edgecolors='none', alpha=alpha, zorder=5))
        wrong = d['cell'][ids] == 5
        ax.add_collection(PolyCollection(polys[wrong], facecolors='none', edgecolors='#333', linewidths=0, hatch='///', zorder=6))
    elif mode == 'judgment':
        for k in range(3):
            ax.add_collection(PolyCollection(polys[judge == k], facecolors=JUDGE_COLORS[k], edgecolors='none', alpha=alpha, zorder=5))
        ax.add_collection(PolyCollection(polys[judge == 3], facecolors='none', edgecolors='#333', linewidths=0, hatch='..', zorder=6))
    else:
        ok = abs(d['z_'+mode][ids].astype(float)-d['gt_p'][ids].astype(float)) <= d['tau'][ids].astype(float)
        ax.add_collection(PolyCollection(polys, facecolors=[RESULT_COLORS[bool(v)] for v in ok], edgecolors='none', alpha=alpha, zorder=5))
        # A pattern also identifies out-of-tolerance patches without relying on red/blue.
        ax.add_collection(PolyCollection(polys[~ok], facecolors='none', edgecolors='#77343a', linewidths=0, hatch='//', alpha=.5, zorder=6))
    contour = ax.contour(*outline, levels=[.5], colors=['white'], linewidths=1.1, zorder=10)
    for collection in contour.collections:
        collection.set_path_effects([patheffects.Stroke(linewidth=2.1, foreground='#52616c'), patheffects.Normal()])
    guides = projected_guides(sec, ex, g)
    for line in guides:
        ax.plot(line[:, 0], line[:, 1], color='#242b33', ls=(0, (3, 2)), lw=1.15,
                marker='.' if len(line) == 1 else None,
                path_effects=[patheffects.Stroke(linewidth=3.2, foreground='white'), patheffects.Normal()], zorder=11)
    first = guides[0][0]
    ax.annotate('시작 쪽', xy=first, xytext=(-10, 8), textcoords='offset points', fontsize=8,
                color='#263542', bbox=dict(fc='white', ec='none', alpha=.85, pad=1), zorder=12)
    ax.text(.97, .97, '북 ↑', transform=ax.transAxes, ha='right', va='top', fontsize=9,
            bbox=dict(fc='white', ec='none', alpha=.88, pad=2), zorder=13)
    return dict(patch_ids=d['patch_id'][ids], guide_display_px=guides,
                xlim=list(ax.get_xlim()), ylim=list(ax.get_ylim()))


def photo_legend(ax, mode):
    if mode == 'region':
        handles = [Patch(facecolor=c, label=n) for c, n in zip(REGION_COLORS, REGION_NAMES)]
        handles.append(Patch(facecolor='white', edgecolor='#333', hatch='///', label='상속 중 기존 면 범위 밖'))
        columns, size = 3, 9
    elif mode == 'judgment':
        handles = [Patch(facecolor=JUDGE_COLORS[k] if k < 3 else 'white', edgecolor='#777',
                         hatch='..' if k == 3 else None, label=label) for k, label in enumerate(JUDGE_NAMES)]
        columns, size = 2, 10
    else:
        handles = [Patch(facecolor=RESULT_COLORS[True], label='허용 범위 안'),
                   Patch(facecolor=RESULT_COLORS[False], edgecolor='#77343a', hatch='//', label='허용 범위 밖')]
        columns, size = 2, 10
    return ax.legend(handles=handles, loc='upper center', bbox_to_anchor=(.5, -.015),
                     ncol=columns, fontsize=size, frameon=False, handlelength=1.1,
                     columnspacing=.9, labelspacing=.45, borderaxespad=0)


def section_plot(fig, sec):
    ax = fig.add_axes([.720, .565, .245, .215])
    s, h = np.asarray(sec['bin_centres_m']), np.asarray(sec['heights_relative_m'])
    labels = ['기존 형상', '사진 기반 복원', '제공 참조면', '계산·범주별', '계산·사진 검사']
    styles = [dict(color='#252b32', lw=1.6), dict(color='#c48322', lw=1.6),
              dict(color='#328459', ls='none', marker='.', ms=4),
              dict(color='#888888', ls='--', lw=2.5), dict(color='#2171b5', lw=1.3)]
    for k in [0, 1, 3, 4, 2]:
        ax.plot(s, h[:, k], label=labels[k], **styles[k])
    ax.set_xlim(0, sec['length_m'])
    ax.set_xlabel('단면 시작점부터 거리 (m)', fontsize=10)
    ax.set_ylabel('상대 높이 (m)', fontsize=10)
    ax.tick_params(labelsize=10)
    ax.grid(axis='y', alpha=.17)
    ax.legend(loc='lower left', bbox_to_anchor=(-.02, 1.015), ncol=2, fontsize=9.5,
              frameon=False, borderaxespad=0, columnspacing=1, handlelength=2.1)
    ax.text(0, -.27, f'같은 공간 띠 ±{sec["half_width_m"]:g} m · 25 cm별 중앙값\n빈 구간은 연결하지 않음 · 학습 전 깊이 손실 분석',
            transform=ax.transAxes, fontsize=9.5, color='#576370', va='top', linespacing=1.45)
    for side in ['top', 'right']:
        ax.spines[side].set_visible(False)
    return ax


def region_bars(fig, m, target):
    ax = fig.add_axes([.744, .168, .216, .245])
    for i, q in enumerate(m['per_region']):
        y = 5-i
        if q['area_m2'] < 1:
            ax.text(2, y, '넓이 < 1 m²', fontsize=9, color='#777', va='center')
            continue
        for offset, key, color, hatch in [(.17, 'category', '#888888', '//'), (-.17, 'check', '#2171b5', None)]:
            val = q['ok_'+key+'_pct']
            ax.barh(y+offset, val, height=.29, color=color, hatch=hatch, edgecolor='white', lw=.4)
            ax.text(val+1.4, y+offset, f'{val:.1f}', va='center', fontsize=9.5, color='#333')
        if i == target:
            ax.axhspan(y-.44, y+.44, color='#e9eef2', alpha=.55, zorder=-1)
    names = [f'{name}\n{q["area_m2"]:.1f} m²' for name, q in zip(REGION_NAMES, m['per_region'])]
    ax.set_yticks(np.arange(5, -1, -1), names, fontsize=9.5)
    ax.get_yticklabels()[target].set_fontweight('bold')
    ax.set_ylim(-.6, 5.6); ax.set_xlim(0, 121); ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_xlabel('허용 범위 안의 넓이 (%)', fontsize=10)
    ax.grid(axis='x', alpha=.16); ax.set_axisbelow(True)
    for side in ['top', 'right', 'left']:
        ax.spines[side].set_visible(False)
    ax.tick_params(axis='y', length=0)
    ax.legend(handles=[Patch(facecolor='#888888', hatch='//', label='범주별 신뢰도'),
                       Patch(facecolor='#2171b5', label='사진 검사 신뢰도')],
              loc='upper center', bbox_to_anchor=(.35, -.19), ncol=2, frameon=False, fontsize=9.5)
    return ax


def render(ident):
    c = settings(); case = c['cases'][ident]
    ex = next(v for v in load(CFG/'regionfig_v2.json')['examples'] if v['id'] == ident)
    d = data(ex['prior'], ex['building']); g = geometry(ex, d)
    im = np.asarray(Image.open(DOC/f'figures/crops/{ident}_원본.png').convert('RGBA'))
    # Region and judgment maps now use the same roof/reference population as both outcome maps.
    m = metrics(d, g['inside'] & d['roof_like'])
    sec = spatial_section(ex, d, c['section']['bin_width_m'])
    target = case['target_region']; t = m['per_region'][target]
    interest, outline = interest_area(ident, d, g, target)
    fig = plt.figure(figsize=c['layout']['inches']); fig.set_facecolor('white')
    headings = []
    headings.append(fig.text(.035, .977, f'{ident}  {case["title"]}', va='top', fontsize=23, fontweight='bold', color='#172f43'))
    headings.append(fig.text(.035, .942, case['scene'], va='top', fontsize=14.5, color='#354654'))
    headings.append(fig.text(.035, .912, case['question'], va='top', fontsize=14.5, fontweight='bold', color='#214f6f'))
    prior = '기존 항공 LiDAR' if ex['prior'] == 'ALS' else '기존 지붕 모형'
    meta = f'건물 {ex["building"]} · {prior}  |  학습 전 깊이 손실 분석 · 학습된 형상 아님  |  제공 참조값 기준'
    if ex['selected_after_results']:
        meta += '  |  계산값 확인 후 선정한 자리'
    fig.text(.035, .880, meta, fontsize=10.5, color='#5b6570')
    positions = [[.035, .545, .285, .275], [.355, .545, .285, .275],
                 [.035, .145, .285, .275], [.355, .145, .285, .275]]
    modes = ['region', 'judgment', 'category', 'check']
    titles = ['가  실제 사진과 영역', '나  사진 검사의 판단',
              '라  학습 전 계산 · 범주별 신뢰도', '마  학습 전 계산 · 사진 검사 신뢰도']
    maps = {}; axes = []
    for rect, mode, title in zip(positions, modes, titles):
        ax = fig.add_axes(rect); axes.append(ax)
        maps[mode] = overlay(ax, ex, d, g, im, sec, mode, c['layout']['overlay_alpha'], outline)
        photo_legend(ax, mode)
        title_y = .856 if mode in ['region', 'judgment'] else .456
        fig.text(rect[0], title_y, title, fontsize=14, fontweight='bold', color='#172f43')
        if mode == 'region':
            note = f'흰 윤곽: 이 사례 조건에 해당하는 {REGION_NAMES[target]} {interest["area_m2"]:.1f} m²'
        elif mode == 'judgment':
            note = '색은 알고리즘의 지지·반박 판단이며 정확도 판정과 다름'
        else:
            note = f'흰 윤곽 안: 허용 범위 내 {fmt(interest["ok_"+mode+"_pct"])}%'
        fig.text(rect[0], title_y-.022, note, fontsize=10.2, color='#4f606e')
    # Only visual scene labels: no patch error or learned reconstruction claim is attached.
    if ident == '6':
        row = next(x for x in load(CFG/'representative_v1/design.json')['examples'] if x['id'] == '6')
        v = row['focus_values']; xyz = np.array(v['centre'])+v['gt_p']*np.array(v['normal'])
        uv, _ = project(xyz[None, :], g['pose'], g['cam'])
        flat = g['transform'].transform(uv-np.array(ex['photo']['crop_box_px'][:2]))[0]
        for label, xy, offset in [('평지붕', flat, (-70, 35)),
                                  ('흰 돌출물', case['scene_callout']['display_xy'], (32, -40))]:
            axes[0].annotate(label, xy=xy, xytext=offset, textcoords='offset points', fontsize=11,
                             bbox=dict(fc='white', ec='#617383', alpha=.95, pad=2),
                             arrowprops=dict(arrowstyle='->', color='#314859', lw=1), zorder=16)
    fig.text(.69, .856, '다  입력과 계산값의 공간 단면', fontsize=14, fontweight='bold', color='#172f43')
    section_plot(fig, sec)
    fig.text(.69, .456, '바  영역별 허용 범위 안의 넓이', fontsize=14, fontweight='bold', color='#172f43')
    fig.text(.69, .434, '사진 전체의 영역별 비율 · 흰 윤곽 밖도 포함', fontsize=10.2, color='#4f606e')
    region_bars(fig, m, target)
    fig.text(.035, .067, case['note'], fontsize=11, color='#3e505e')
    fig.text(.035, .043, f'사진 네 칸: 같은 사진·범위·회전·지붕 패치  |  표시 대상 {m["result_area_m2"]:.1f} m²  |  참조값 없음 {m["unpainted_no_reference_area_m2"]:.1f} m²는 색칠 제외', fontsize=10, color='#5b6570')
    fig.text(.035, .021, '검은 점선: 같은 공간 단면을 참조 높이에 투영한 위치 안내(가림 재검증 없음)  |  두 계산의 차이는 기존 면에 부여한 신뢰도  |  사진만으로 실패 원인을 확정하지 않음', fontsize=9.5, color='#5b6570')
    fig.canvas.draw(); renderer = fig.canvas.get_renderer()
    for text_obj in headings:
        bounds = text_obj.get_window_extent(renderer).transformed(fig.transFigure.inverted())
        assert bounds.x1 < .98 and bounds.x0 >= 0, ('Heading clipped', bounds.bounds)
    for name, item in maps.items():
        assert np.array_equal(item['patch_ids'], maps['region']['patch_ids']), name
        assert item['xlim'] == maps['region']['xlim'] and item['ylim'] == maps['region']['ylim']
    texts = [o.get_text() for o in fig.findobj(Text) if o.get_visible() and o.get_text()]
    assert not any(re.search(r'\b[AS]\b|A의 판정|결과 단면', s) for s in texts)
    path = OUT/f'영역그림_{ident}.png'
    fig.savefig(path, dpi=c['layout']['dpi'], facecolor='white')
    fig.savefig(OUT/f'미리보기_{ident}.png', dpi=c['layout']['preview_dpi'], facecolor='white')
    plt.close(fig)
    base = load(next(p for p in source_figures() if p.name.startswith(f'영역표본_{ident}_')))
    for q, old in zip(m['per_region'], base['metrics']['per_region']):
        for key in ['area_m2', 'ok_category_pct', 'ok_check_pct']:
            assert q[key] == old[key] or (q[key] is not None and old[key] is not None and abs(q[key]-old[key]) < 1e-7), (ident, key)
    record = dict(task_id=c['task_id'], id=ident, case=case, config_sha256=sha(CONFIG),
                  generator_sha256=sha(__file__), spatial_generator_sha256=sha(Path(__file__).with_name('six_panel_spatial.py')),
                  source_photo_sha256=sha(DOC/f'figures/crops/{ident}_원본.png'), source_figure_record_sha256=sha(next(p for p in source_figures() if p.name.startswith(f'영역표본_{ident}_'))),
                  figure_sha256=sha(path), preview_sha256=sha(OUT/f'미리보기_{ident}.png'),
                  metrics=m, interest_area=interest, spatial_section=sec, photo_panels=maps, texts=texts,
                  photos_have_identical_population_and_view=True, legacy_area_rates_unchanged=True,
                  source_selection=ex['selected_after_results'], environment=environment(), scientific_verdict=None)
    dump(OUT/f'영역그림_{ident}.json', record)
    print('RENDERED', ident, t['area_m2'], t['ok_category_pct'], t['ok_check_pct'], flush=True)


def verify():
    c = settings(); lock = load(LOCK); checks = []
    def check(label, ok):
        checks.append(dict(check=label, passed=bool(ok)))
        assert ok, label
    for source in lock['inputs']+lock['protected']:
        check('unchanged '+source['path'], sha(source['path']) == source['sha256'])
    for ident in c['cases']:
        r = load(OUT/f'영역그림_{ident}.json')
        check(ident+' config', r['config_sha256'] == sha(CONFIG))
        check(ident+' generator', r['generator_sha256'] == sha(__file__) and r['spatial_generator_sha256'] == sha(Path(__file__).with_name('six_panel_spatial.py')))
        check(ident+' image bytes', sha(OUT/f'영역그림_{ident}.png') == r['figure_sha256'] and sha(OUT/f'미리보기_{ident}.png') == r['preview_sha256'])
        with Image.open(OUT/f'영역그림_{ident}.png') as im:
            check(ident+' resolution', im.size == (6000, 4200) and abs(im.info['dpi'][0]-300) < .1)
        check(ident+' no A or S markers', not any(re.search(r'\b[AS]\b|A의 판정|결과 단면', t) for t in r['texts']))
        check(ident+' visible analysis scope', any('학습된 형상 아님' in t for t in r['texts']))
        ex = next(x for x in load(CFG/'regionfig_v2.json')['examples'] if x['id'] == ident)
        d = data(ex['prior'], ex['building']); lookup = {str(p): i for i, p in enumerate(d['patch_id'])}
        ids = np.array([lookup[p] for p in r['photo_panels']['region']['patch_ids']])
        check(ident+' unique roof reference population', len(np.unique(ids)) == len(ids) and d['roof_like'][ids].all() and np.isfinite(d['gt_p'][ids]).all())
        interest = r['interest_area']; ii = np.array([lookup[p] for p in interest['patch_ids']])
        target = c['cases'][ident]['target_region']
        expected_interest = []
        for ix in ids:
            cell, judge = int(d['cell'][ix]), int(d['judgment'][ix])
            region = cell if cell < 4 else 5 if judge == 4 else 4
            include = region == target
            if ident in ['5', '6', '8']: include = include and judge == (0 if ident == '6' else 1)
            if ident == '8': include = include and cell == 5
            if include: expected_interest.append(str(d['patch_id'][ix]))
        check(ident+' outlined area membership', set(expected_interest) == set(interest['patch_ids']) and len(ii) == len(set(interest['patch_ids'])))
        area = sum(float(d['area'][ix]) for ix in ii)
        check(ident+' outlined area denominator', abs(area-interest['area_m2']) < 1e-7)
        for key in ['category', 'check']:
            numerator = sum(float(d['area'][ix]) for ix in ii if abs(float(d['z_'+key][ix])-float(d['gt_p'][ix])) <= float(d['tau'][ix]))
            check(ident+' outlined area rate '+key, abs(100*numerator/area-interest['ok_'+key+'_pct']) < 1e-7)
        for mode in ['judgment', 'category', 'check']:
            q = r['photo_panels'][mode]; p = r['photo_panels']['region']
            check(ident+' same photo population '+mode, q['patch_ids'] == p['patch_ids'] and q['xlim'] == p['xlim'] and q['ylim'] == p['ylim'] and q['guide_display_px'] == p['guide_display_px'])
        # Reconcile independently using scalar accumulation over the actual displayed patch IDs.
        sums = [[0., 0., 0.] for _ in range(6)]
        for ix in ids:
            cell = int(d['cell'][ix]); region = cell if cell < 4 else 5 if int(d['judgment'][ix]) == 4 else 4
            area = float(d['area'][ix]); sums[region][0] += area
            for column, key in [(1, 'z_category'), (2, 'z_check')]:
                if abs(float(d[key][ix])-float(d['gt_p'][ix])) <= float(d['tau'][ix]):
                    sums[region][column] += area
        for i, (area, cat, chk) in enumerate(sums):
            q = r['metrics']['per_region'][i]
            check(f'{ident} region {i} area', abs(area-q['area_m2']) < 1e-6)
            for key, val in [('category', cat), ('check', chk)]:
                expected = 100*val/area if area else None
                actual = q['ok_'+key+'_pct']
                check(f'{ident} region {i} {key}', actual == expected or (actual is not None and expected is not None and abs(actual-expected) < 1e-7))
        sec = r['spatial_section']; start, end = np.array(ex['start_xy']), np.array(ex['end_xy'])
        vec = (end-start)/np.linalg.norm(end-start); cross = np.array([-vec[1], vec[0]])
        edges = np.array(sec['bin_edges_m']); heights = np.array(sec['heights_model_m'], float)
        for k, layer in enumerate(sec['layers']):
            key = layer['key']; disp = np.zeros(len(d['centre'])) if key == 'prior' else d[key].astype(float)
            xyz = d['centre']+disp[:, None]*d['normal']
            along = (xyz[:, :2]-start) @ vec; across = (xyz[:, :2]-start) @ cross
            # Direct geometric band test, independently of the stored layer membership.
            keep = d['matched'] & d['roof_like'] & np.isfinite(xyz).all(axis=1) & (along >= 0) & (along <= sec['length_m']) & (abs(across) <= ex['half_width_m'])
            check(ident+' complete actual-XY membership '+key, list(d['patch_id'][keep]) == layer['patch_ids'])
            jj = np.flatnonzero(keep)
            check(ident+' XYZ '+key, np.allclose(xyz[jj], np.asarray(layer['xyz']).reshape(-1, 3), atol=1e-10, rtol=0))
            recomputed = []
            for b in range(len(edges)-1):
                in_bin = keep & (along >= edges[b]) & ((along < edges[b+1]) if b < len(edges)-2 else (along <= edges[b+1]))
                vals = sorted(float(z) for z in xyz[in_bin, 2]); n = len(vals)
                value = (vals[n//2] if n % 2 else (vals[n//2-1]+vals[n//2])/2) if n else float('nan')
                recomputed.append(value)
            check(ident+' medians '+key, np.allclose(recomputed, heights[:, k], atol=1e-10, rtol=0, equal_nan=True))
        for guide in sec['photo_guide_xyz']:
            xyz = np.array(guide)
            check(ident+' photo guide shares spatial plane', np.max(abs((xyz[:, :2]-start) @ cross)) < 1e-8)
        check(ident+' scientific verdict null', r['scientific_verdict'] is None)
    dump(OUT/'verification.json', dict(status='PASS', at=now(), checks=checks, passed=len(checks), total=len(checks),
         limitations=['Numerical and coordinate checks do not replace visual inspection or independently verify reference/surface identity.'], scientific_verdict=None))
    print('VERIFIED', len(checks), flush=True)


def finish():
    c = settings(); v = load(OUT/'verification.json'); review = load(OUT/'visual_review.json')
    assert v['status'] == 'PASS' and review['status'] == 'PASS'
    assert sorted(q['id'] for q in review['items']) == sorted(c['cases'])
    for item in review['items']:
        assert item['preview_sha256'] == sha(OUT/f'미리보기_{item["id"]}.png')
    lines = ['# 영역별 사진 검사와 학습 전 계산 비교', '',
             '여덟 장 모두 원래 두 줄·세 칸 구성이다. 실제 사진의 영역, 사진 검사의 판단, 두 신뢰도 설정의 계산값과 영역별 비율을 함께 본다.', '',
             '**모든 계산값은 제공된 학습 전 깊이 손실 최소점이다. 학습된 형상이나 메시가 아니며, 향후 학습 결과를 예측한 그림도 아니다.**', '',
             '## 읽는 순서', '',
             '가: 기존 면과 사진 기반 복원의 제공 참조값 기준 영역. 나: 사진 검사 알고리즘의 판단. 다: 같은 공간 띠의 입력·계산값 단면. 라·마: 제공 참조값 기준 허용 범위 안팎. 바: 각 영역의 참조값이 있는 지붕 넓이로 계산한 비율.', '',
             'A·S와 한 패치의 별도 오차 판정은 제거했다. 네 사진의 원본, 자른 범위, 회전, 색칠 대상 패치가 같다. 흰 윤곽은 사례의 영역 조건에 해당하는 모든 패치다. 5번은 검사 반박, 6번은 검사 지지, 8번은 검사 반박이면서 기존 면이 허용 범위 밖인 조건을 추가한다. 윤곽 선정에 두 계산값의 성공/실패는 사용하지 않았다.', '',
             '라·마의 사진 위 비율은 흰 윤곽 안을 분모로 한다. 바의 막대는 사진 전체의 각 영역을 분모로 하므로 범위가 다르며 그 차이를 그림에 표시했다. 원래 영역별 비율은 모두 보존한다. 지역의 수치를 다른 부위나 지붕 전체 성능으로 확대하지 않는다.', '',
             '## 단면 대응 수정', '',
             '이전 단면은 기존 패치의 XY에 모든 높이를 놓았다. 새 단면은 기존 형상, MVS, 참조면, 두 최소점 각각에 대해 `XYZ = centre + displacement × normal`을 구하고, 각자의 실제 XY가 같은 단면 띠 안에 드는 경우만 집계한다. 원래 단면의 시작·끝 XY와 폭은 유지했다. 25 cm 구간의 높이 중앙값을 사용하며 결측을 연결하지 않는다.', '',
             '따라서 각 곡선은 같은 공간 띠의 집계지만 같은 패치 집합을 강제하지 않는다. 이것은 제공값의 공간 배치이며 새 표면 재구성이나 손실 최적화가 아니다. 사진 점선은 그 단면의 참조 높이를 투영한 위치 안내다. 투영 패치와 위치선의 가림을 재검증하지 않았고, 독립적인 같은 표면의 진실을 확정하지 않는다.', '',
             '## 계산과 판정', '',
             '`z_category`와 `z_check`는 전달받은 값이다. 높이는 `centre_z + z × normal_z`, 허용 범위 판정은 `abs(z − gt_p) <= tau`이다. 두 설정은 기존 면의 유효 확률을 정하는 방식이 다르다. 학습·새 사진 검사·새 최소점 계산은 실행하지 않았다. 원 손실의 세부 구현은 이 전달 ZIP에 없으므로 재구현하거나 추정하지 않았다.', '',
             '영역별 비율은 원래 여섯 패널의 값과 일치한다. 영역/검사 사진도 두 계산 사진과 같은 참조값이 있는 지붕 패치로 통일했다. 기존 그림과 ZIP은 그대로 보존했다.', '']
    cards = []
    for ident, case in c['cases'].items():
        r = load(OUT/f'영역그림_{ident}.json'); q = r['metrics']['per_region'][case['target_region']]
        target = r['interest_area']
        note = f'흰 윤곽 {target["area_m2"]:.1f} m²: 범주별 {fmt(target["ok_category_pct"])}%, 사진 검사 기반 {fmt(target["ok_check_pct"])}%. 사진 전체 {REGION_NAMES[case["target_region"]]} {q["area_m2"]:.1f} m²: {fmt(q["ok_category_pct"])}% / {fmt(q["ok_check_pct"])}%.'
        lines += [f'## {ident}. {case["title"]}', '', case['scene'], '', case['question'], '', note, '', case['note'], '', f'![{case["title"]}](미리보기_{ident}.png)', '']
        cards.append(f'<article><h2>{ident}. {html.escape(case["title"])}</h2><p>{html.escape(case["scene"])}</p><a href="영역그림_{ident}.png"><img src="미리보기_{ident}.png" alt="{html.escape(case["title"])}"></a><p>{html.escape(note)} {html.escape(case["note"])}</p></article>')
    lines += ['## 검증과 한계', '', f'수치·원본 보존·공간 대응 검사 {v["passed"]}/{v["total"]} 통과. 저자 시각 검토를 완료했으며 독립적인 제목 숨김 검토는 이번 개정에서 수행하지 않았다. `scientific_verdict: null`.', '',
              '재실행: `python scripts/phd/main_regionfig_v2/run_cpu.py six3-render python six_panel_revision03.py render 2`와 같은 보호 실행기를 사용한다. `prepare`, `verify`, `finish`, `package` 단계도 같은 실행기 아래서 수행한다.', '']
    (OUT/'영역그림_보고.md').write_text('\n'.join(lines))
    (OUT/'index.html').write_text('<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>영역별 사진 검사와 학습 전 계산</title><style>body{font:16px/1.6 sans-serif;color:#263542;background:#f5f6f8;margin:0}main{max-width:1600px;margin:auto;padding:24px}article{background:white;padding:18px;margin:28px 0}img{width:100%;height:auto}a{color:#196aab}</style><main><h1>영역별 사진 검사와 학습 전 계산</h1><p>두 줄·세 칸으로 복원한 여덟 사례. 학습된 형상이 아닌, 제공된 깊이 손실 최소점 분석입니다.</p><p><a href="영역그림_8장.pdf">8장 PDF</a> · <a href="영역그림_보고.md">설명과 검증</a></p>'+''.join(cards)+'</main></html>')
    with PdfPages(OUT/'영역그림_8장.pdf') as pdf:
        for ident in c['cases']:
            with Image.open(OUT/f'영역그림_{ident}.png') as im:
                fig = plt.figure(figsize=c['layout']['inches']); ax = fig.add_axes([0, 0, 1, 1])
                ax.imshow(np.asarray(im)); ax.axis('off'); pdf.savefig(fig, dpi=200); plt.close(fig)
    fig, axes = plt.subplots(4, 2, figsize=(16, 22.4))
    for ident, ax in zip(c['cases'], axes.flat):
        with Image.open(OUT/f'미리보기_{ident}.png') as im:
            ax.imshow(np.asarray(im)); ax.axis('off')
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0, wspace=.015, hspace=.02)
    fig.savefig(OUT/'여덟사례_한눈에.png', dpi=110); plt.close(fig)
    receipts = OUT/'run_receipts'; receipts.mkdir(exist_ok=True)
    for p in sorted((PAY/'logs').glob('*-six3-*.json')):
        if load(p).get('status') != 'RUNNING':
            shutil.copyfile(p, receipts/p.name)
    dump(OUT/'delivery_status.json', dict(status='READY_FOR_HANDOVER', at=now(), numerical_verification='PASS', author_visual_review='PASS', independent_blind_review=False, scientific_verdict=None))
    print('REPORT AND PDF READY', flush=True)


def package():
    c = settings(); assert load(OUT/'delivery_status.json')['status'] == 'READY_FOR_HANDOVER'
    root = PAY/REVISION/'handover'; root.mkdir(parents=True, exist_ok=True)
    path = root/'PHD-MAIN-REGIONFIG-v2_six_panel_v3.zip'; assert not path.exists()
    sources = {}
    for base, prefix in [(OUT, 'figures'), (CFG/REVISION, 'configs/six_panel_v3')]:
        for p in sorted(base.rglob('*')):
            if p.is_file(): sources[prefix+'/'+str(p.relative_to(base))] = p
    for filename in ['six_panel_revision03.py', 'six_panel_spatial.py', 'draw_figures.py', 'rfcore.py', 'run_cpu.py']:
        sources['scripts/'+filename] = Path(__file__).parent/filename
    sources['configs/regionfig_v2.json'] = CFG/'regionfig_v2.json'
    sources['configs/resource_approval.json'] = CFG/'resource_approval.json'
    for p in sorted((PAY/'input').glob('*')):
        if p.is_file(): sources['supplied_inputs/'+p.name] = p
    for ident in c['cases']:
        p = DOC/f'figures/crops/{ident}_원본.png'; sources['source_photos/'+p.name] = p
    for key in ['ALS', 'LoD2']:
        p = PAY/f'joined_{key}.npz'; sources['joined_geometry/'+p.name] = p
    hashes = {}
    text = ('영역별 사진 검사와 학습 전 계산 비교\n\nfigures/영역그림_8장.pdf 또는 figures/영역그림_1.png ~ 8.png를 여세요.\n'
            'PNG, PDF, 설명, 패치별 값과 공간 단면, 원본 사진 조각, 입력값, 설정, 검증 기록을 포함합니다.\n'
            '학습된 형상이나 메시가 아닙니다. 기존 형상과 MVS의 깊이 손실에 대한 제공 최소점 분석입니다.\n'
            '이전 전달 ZIP은 수정하지 않았습니다. 현재 묶음에는 이번 개정에 필요한 검토 자료를 담았습니다.\n'
            '원본 항공사진 전체와 카메라/기존 공통 스크립트/Docker 이미지는 저장소 및 외부 입력에서 참조하므로 완전 독립 실행 환경은 아닙니다.\n'
            '모든 파일의 SHA-256은 SHA256SUMS에 있습니다. scientific_verdict: null.\n')
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for name, p in sources.items():
            hashes[name] = sha(p); z.write(p, name)
        payload = text.encode(); z.writestr('먼저읽기.txt', payload)
        import hashlib
        hashes['먼저읽기.txt'] = hashlib.sha256(payload).hexdigest()
        sums = ''.join(f'{h}  {name}\n' for name, h in sorted(hashes.items()))
        z.writestr('SHA256SUMS', sums)
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        assert len(z.namelist()) == len(set(z.namelist())) == len(hashes)+1
        for name, expected in hashes.items():
            h = hashlib.sha256()
            with z.open(name) as f:
                for chunk in iter(lambda: f.read(1 << 20), b''): h.update(chunk)
            assert h.hexdigest() == expected, name
    for name, p in sources.items():
        assert sha(p) == hashes[name]
    receipt = dict(status='PASS', path=str(path), bytes=path.stat().st_size, sha256=sha(path),
                   members=len(hashes)+1, crc='PASS', member_sha256='PASS', source_head=os.environ['JBGS_SOURCE_HEAD'], scientific_verdict=None)
    dump(root/'package_receipt.json', receipt)
    path.with_suffix('.zip.sha256').write_text(receipt['sha256']+'  '+path.name+'\n')
    print('PACKAGED', receipt, flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('stage', choices=['prepare', 'render', 'verify', 'finish', 'package']); p.add_argument('id', nargs='?')
    a = p.parse_args()
    if a.stage == 'render':
        assert a.id in [str(i) for i in range(1, 9)]; render(a.id)
    else:
        globals()[a.stage]()
