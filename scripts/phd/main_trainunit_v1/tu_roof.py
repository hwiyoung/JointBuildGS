"""Addendum 8/9 read-out (no training, no GT): the two runaway roofs' images and ALS prior, and the probe3/probe4/probe3own
family monitor next to the cell and probe0 curves.

  python tu_roof.py images     -> tables/roof_images.*, figures/roof_photos.png
  python tu_roof.py prior      -> tables/roof_prior.*, roof_depth.*
  python tu_roof.py monitor    -> tables/roof_monitor.*, roof_runs.*, figures/roof_runs.png
"""
import sys

import cv2
import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager

from tu_common import *
from tu_campus import CAMPUS, cameras, read_depth
from tu_cells import coverage
from tu_cause import runs as cause_runs, write
from tu_growth import lineage

font_manager.fontManager.addfont('/fonts/NotoSansCJK-Regular.ttc')
plt.rcParams.update({'font.family': 'Noto Sans CJK JP', 'axes.unicode_minus': False, 'font.size': 9})

ROOFS = {
    'A': dict(probe='probe3', building='DEBY_LOD2_4906972', fams=[('cell0', 1), ('cell2', 1)], cells=['cell0', 'cell2']),
    'B': dict(probe='probe4', building='DEBY_LOD2_4959327', fams=[('cell3', 1)], cells=['cell3']),
    'ctl': dict(probe='probe0', building='DEBY_LOD2_4959458', fams=[('probe0', 1)], cells=[]),   # control: largest family in probe0
}
REGION = {1: '일치', 2: '보존', 3: '보정', 0: '결측', 5: '보정(빈 공간)', -1: '목표 없음'}


def fams():
    d = json.loads((D / 'tables/cause_top_families.json').read_text())
    return {(r['key'], r['rank']): r for r in (d['rows'] if isinstance(d, dict) else d)}


def box(roof):
    F = fams()
    rs = [F[k] for k in ROOFS[roof]['fams']]
    lo = np.min([[r['family_x_p01_p50_p99'][0], r['family_y_p01_p50_p99'][0], r['family_z_p01_p50_p99'][0]] for r in rs], 0)
    hi = np.max([[r['family_x_p01_p50_p99'][2], r['family_y_p01_p50_p99'][2], r['family_z_p01_p50_p99'][2]] for r in rs], 0)
    return lo, hi


def unit_images(unit):
    if unit.startswith('cell'):
        c = next(x for x in json.loads((TU / 'cells/cells.json').read_text())['cells'] if f'cell{x["id"]}' == unit)
        return c['images']
    src = 'probes.json' if unit in ('probe0', 'probe1') else 'probes_add8.json'
    return next(x for x in json.loads((TU / 'probes' / src).read_text())['probes'] if x['name'] == unit)['images']


def project(cam, lo, hi):
    corners = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])], float)
    M = np.asarray(cam['W2C'], float)
    c = corners @ M[:3, :3].T + M[:3, 3]
    c = c[c[:, 2] > 0]
    if len(c) < 3:
        return None
    return np.c_[cam['fx'] * c[:, 0] / c[:, 2] + cam['cx'], cam['fy'] * c[:, 1] / c[:, 2] + cam['cy']]


def view_geometry(cam, lo, hi):
    M = np.asarray(cam['W2C'], float)
    C = -M[:3, :3].T @ M[:3, 3]
    ctr = (np.asarray(lo) + np.asarray(hi)) / 2
    d = ctr - C
    off = float(np.degrees(np.arccos(abs(d[2]) / np.linalg.norm(d))))
    az = float(np.degrees(np.arctan2(d[1], d[0])))
    return float(np.linalg.norm(d)), off, az


def images():
    cfg()
    rows, picks = [], {}
    for roof, spec in ROOFS.items():
        lo, hi = box(roof)
        for unit in spec['cells'] + [spec['probe']]:
            names = unit_images(unit)
            seen = []
            for cam in cameras(names):
                f = coverage(cam, lo, hi)
                if f <= 0:
                    continue
                uv = project(cam, lo, hi)
                hull = cv2.convexHull(uv.astype(np.float32)).reshape(-1, 2)
                dist, off, az = view_geometry(cam, lo, hi)
                full = bool((uv[:, 0] >= 0).all() and (uv[:, 0] < cam['W']).all() and (uv[:, 1] >= 0).all() and (uv[:, 1] < cam['H']).all()) and len(uv) == 8
                seen.append(dict(name=cam['name'], coverage=f, hull_area_px=float(cv2.contourArea(hull)), distance_m=dist, off_nadir_deg=off, azimuth_deg=az,
                                 box_fully_inside=full))
            q = lambda k, p: [float(v) for v in np.quantile([s[k] for s in seen], p)] if seen else None
            rows.append(dict(roof=roof, building=spec['building'], unit=unit, training_images=len(names), images_seeing_family_box=len(seen),
                             family_box_min=lo.tolist(), family_box_max=hi.tolist(), box_area_m2=float(np.prod(hi[:2] - lo[:2])),
                             projected_area_px_p10_p50_p90=q('hull_area_px', [.1, .5, .9]), off_nadir_deg_p10_p50_p90=q('off_nadir_deg', [.1, .5, .9]),
                             distance_m_p10_p50_p90=q('distance_m', [.1, .5, .9]), images_box_fully_inside=int(sum(s['box_fully_inside'] for s in seen)),
                             azimuth_sectors_45deg=int(len(np.unique(np.floor(np.array([s['azimuth_deg'] for s in seen]) / 45)))) if seen else 0))
            if unit == spec['probe']:
                seen.sort(key=lambda s: (not s['box_fully_inside'], -(s['hull_area_px'] if s['box_fully_inside'] else s['coverage'])))
                pick = []
                for s in seen:
                    if all(abs(((s['azimuth_deg'] - p['azimuth_deg'] + 180) % 360) - 180) > 60 for p in pick) or not pick:
                        pick.append(s)
                    if len(pick) == 4:
                        break
                picks[roof] = (lo, hi, pick)
            print('IMG', roof, unit, len(names), len(seen), flush=True)
    write('roof_images', rows, 'training images that see the runaway family box (projection of the family xyz p01-p99 box); no training, no GT')
    fig, ax = plt.subplots(3, 4, figsize=(12, 8.4))
    for i, roof in enumerate(['A', 'B', 'ctl']):
        lo, hi, pick = picks[roof]
        for j in range(4):
            a = ax[i, j]
            a.axis('off')
            if j >= len(pick):
                continue
            s = pick[j]
            cam = cameras([s['name']])[0]
            img = cv2.cvtColor(cv2.imread(str(CAMPUS / 'images' / f'{s["name"]}.jpg')), cv2.COLOR_BGR2RGB)
            uv = project(cam, lo, hi)
            hull = cv2.convexHull(uv.astype(np.float32)).reshape(-1, 2)
            x0, y0 = hull.min(0); x1, y1 = hull.max(0)
            mx, my = max(40, .6 * (x1 - x0)), max(40, .6 * (y1 - y0))
            X0, Y0 = int(max(0, x0 - mx)), int(max(0, y0 - my)); X1, Y1 = int(min(img.shape[1], x1 + mx)), int(min(img.shape[0], y1 + my))
            a.imshow(img[Y0:Y1, X0:X1])
            h = np.vstack([hull, hull[:1]])
            a.plot(h[:, 0] - X0, h[:, 1] - Y0, color='#00e5ff', lw=1.2)
            for k in ROOFS[roof]['fams']:
                X = np.array(fams()[k]['seed_xyz'], float)
                M = np.asarray(cam['W2C'], float)
                c = M[:3, :3] @ X + M[:3, 3]
                if c[2] > 0:
                    a.plot(cam['fx'] * c[0] / c[2] + cam['cx'] - X0, cam['fy'] * c[1] / c[2] + cam['cy'] - Y0, marker='*', color='#ff1744', ms=9, mec='w', mew=.6)
            a.set_xlim(0, X1 - X0); a.set_ylim(Y1 - Y0, 0)
            a.set_title(f'{s["name"]}  기울기 {s["off_nadir_deg"]:.0f}°  방위 {s["azimuth_deg"]:.0f}°', fontsize=7.5)
        lab = {'A': f'지붕 A {ROOFS["A"]["building"]}\n(칸 0·2에서 폭주)', 'B': f'지붕 B {ROOFS["B"]["building"]}\n(칸 3에서 폭주)',
               'ctl': f'대조 {ROOFS["ctl"]["building"]}\n(probe0 1위 계보, 정상)'}[roof]
        ax[i, 0].text(-.04, .5, lab, transform=ax[i, 0].transAxes, ha='right', va='center', fontsize=8.5)
    fig.suptitle('폭주 계보 자리를 보는 학습 영상(하늘색 = 계보 xyz 1~99 % 상자의 투영, 별 = 폭주한 씨앗): 상자가 사진 안에 다 드는 영상 중 투영이 큰 것부터 방위 60° 이상 다르게 4장', fontsize=9.5)
    fig.tight_layout(rect=(.08, 0, 1, .96))
    out = D / 'figures/roof_photos.png'
    fig.savefig(out, dpi=130)
    dump(out.with_suffix('.json'), dict(at=now(), picks={k: [s['name'] for s in v[2]] for k, v in picks.items()}, scientific_verdict=None))
    print('FIG', out, flush=True)


def prior():
    cfg()
    U = loadz(TU / 'targets/campus__ALS.npz', ['centre', 'kind', 'area', 'sigma', 'h', 'region', 'judge_region', 'surface_exists',
                                                 'sigma_replaced', 'source', 'building', 'sigma_ref'])
    ref = float(U['sigma_ref'])
    act = U['surface_exists']
    w_all = np.clip(ref / U['sigma'][act], .1, 10)
    rows, drows = [], []
    for roof, spec in ROOFS.items():
        lo, hi = box(roof)
        c = U['centre']
        m = (c[:, 0] >= lo[0]) & (c[:, 0] < hi[0]) & (c[:, 1] >= lo[1]) & (c[:, 1] < hi[1]) & (c[:, 2] >= lo[2] - 2) & (c[:, 2] < hi[2] + 2)
        for kind in [1, 2]:
            k = m & (U['kind'] == kind)
            ka = k & act
            q = lambda a, p=(.1, .5, .9): [float(v) for v in np.quantile(a, p)] if len(a) else None
            rows.append(dict(roof=roof, building=spec['building'], kind={1: '지붕', 2: '벽'}[kind], patches=int(k.sum()), active=int(ka.sum()),
                             area_m2=float(U['area'][k].sum()), regions={REGION.get(int(r), str(r)): int(((U['region'] == r) & k).sum()) for r in np.unique(U['region'][k])},
                             judge_regions={REGION.get(int(r), str(r)): int(((U['judge_region'] == r) & k).sum()) for r in np.unique(U['judge_region'][k])},
                             sigma_m_p10_p50_p90=q(U['sigma'][ka]), weight_p10_p50_p90=q(np.clip(ref / U['sigma'][ka], .1, 10)),
                             h_m_p10_p50_p90=q(U['h'][ka]), sigma_replaced_share=float(U['sigma_replaced'][ka].mean()) if ka.any() else None,
                             buildings=sorted(set(U['building'][k].tolist()))[:6], sources=sorted(set(int(s) for s in U['source'][k]))))
        # prior target depth minus WIDEN0 MVS depth inside the projected family box, in the probe's maps
        unit = spec['probe']
        diffs, prior_px, bg_px, none_px, wts = [], 0, 0, 0, []
        names = unit_images(unit)
        for cam in cameras(names):
            if coverage(cam, lo, hi) <= 0:
                continue
            uv = project(cam, lo, hi)
            hull = cv2.convexHull(uv.astype(np.float32)).reshape(-1, 2)
            mask = np.zeros((cam['H'], cam['W']), np.uint8)
            cv2.fillConvexPoly(mask, np.round(hull).astype(np.int32), 1)
            mask = mask.astype(bool)
            z = loadz(TU / 'stage1' / f'{unit}__ALS/maps/{cam["name"]}.npz', ['depth', 'owner', 'weight'])
            mvs = read_depth(WD / 'mvs/full/stereo/depth_maps' / f'{cam["name"]}.JPG.geometric.bin')
            ok_mvs = np.isfinite(mvs) & (mvs > 0)
            has = (z['owner'] >= 0) & mask
            prior_px += int(has.sum()); bg_px += int((~(z['owner'] >= 0) & mask & ok_mvs).sum()); none_px += int((mask & ~(z['owner'] >= 0) & ~ok_mvs).sum())
            both = has & ok_mvs
            diffs.append((z['depth'][both] - mvs[both]).astype('f4'))
            wts.append(z['weight'][has])
        d = np.concatenate(diffs) if diffs else np.zeros(0)
        w = np.concatenate(wts) if wts else np.zeros(0)
        q = lambda a, p: [float(v) for v in np.quantile(a, p)] if len(a) else None
        drows.append(dict(roof=roof, unit=unit, pixels_in_box=prior_px + bg_px + none_px, prior_pixels=prior_px, background_mvs_pixels=bg_px, empty_pixels=none_px,
                          prior_with_mvs=int(len(d)), target_minus_mvs_m_p05_p25_p50_p75_p95=q(d, [.05, .25, .5, .75, .95]),
                          abs_gt_0p5m_share=float((np.abs(d) > .5).mean()) if len(d) else None, abs_gt_2m_share=float((np.abs(d) > 2).mean()) if len(d) else None,
                          pixel_weight_p10_p50_p90=q(w, [.1, .5, .9])))
        print('PRIOR', roof, int(m.sum()), len(d), flush=True)
    rows.append(dict(roof='campus', building='all', kind='all active', patches=int(act.sum()), weight_p10_p50_p90=[float(v) for v in np.quantile(w_all, [.1, .5, .9])],
                     sigma_m_p10_p50_p90=[float(v) for v in np.quantile(U['sigma'][act], [.1, .5, .9])]))
    write('roof_prior', rows, 'ALS prior patches inside the runaway family box (centre xy in box, z within box +-2 m), by kind; campus row for reference; no GT')
    write('roof_depth', drows, 'pixels of the probe maps inside the projected family box: prior target depth minus WIDEN0 MVS depth; no GT')


def monitor_rows(entry):
    run = TU / 'runs/probes' / f'{entry}_ALS_s0'
    att = sorted(run.glob('attempt*'), key=lambda p: int(p.name[7:]))
    f = att[-1] / 'family_monitor.jsonl' if att else None
    if not f or not f.exists():
        return att, []
    return att, [json.loads(l) for l in f.read_text().splitlines() if l.strip()]


def monitor():
    cfg()
    entries = ['probe3', 'probe4', 'probe3own']
    out, curves = [], {}
    for e in entries:
        att, M = monitor_rows(e)
        if not M:
            print('MON', e, 'no monitor yet', flush=True)
            continue
        its, g, peak = lineage(att[-1:])
        curves[e] = dict(iterations=its, gaussians=g)
        top = []
        for r in M:
            t1 = next(v | dict(key=k) for k, v in r['groups'].items() if k.startswith('top1:'))
            wsum = {k: v for k, v in r['groups'].items() if k.startswith('watch:')}
            top.append(dict(iteration=r['iteration'], n_total=r['n_before'], largest_family=t1['key'].split(':')[1], largest_n=t1['n'],
                            largest_clone=t1['clone'], largest_split=t1['split'], largest_pruned_est=t1['pruned_est'],
                            largest_grad_p50=(t1['grad_p50_p90'] or [None])[0], largest_max_scale_p50=(t1['max_scale_p50_p90'] or [None])[0],
                            largest_opacity_p50=(t1['opacity_p50'] or [None])[0], largest_denom_p50=(t1['denom_p50'] or [None])[0],
                            watch_max_n=max([v['n'] for v in wsum.values()] or [0]),
                            prior_n=r['groups']['prior_lineage']['n'], background_n=r['groups']['background_lineage']['n'],
                            clone_total=r['clone_total'], split_total=r['split_total'], clone_threshold_m=r['clone_scale_threshold'],
                            grad_threshold=r['max_grad'], monitor_s=r['monitor_seconds']))
        dump(D / f'tables/roof_monitor_{e}.json', dict(at=now(), entry=e, attempt=att[-1].name, rows=top, scientific_verdict=None))
        rec = json.loads((att[-1] / 'receipt.json').read_text()) if (att[-1] / 'receipt.json').exists() else {}
        ex = json.loads((att[-1] / 'extent_override.json').read_text()) if (att[-1] / 'extent_override.json').exists() else {}
        at = dict(zip(its, g))
        T = {r['iteration']: r for r in top}
        big = [r for r in top if r['largest_n'] >= 50000]
        out.append(dict(entry=e, status=rec.get('status', 'running'), attempt=att[-1].name, last_iteration=max(at) if at else None,
                        extent_used_m=ex.get('used_radius'), extent_fork_m=ex.get('fork_radius'), clone_threshold_m=M[-1]['clone_scale_threshold'],
                        gaussians_6000=at.get(6000), gaussians_7000=at.get(7000), gaussians_15000=at.get(15000),
                        max_gaussians=max(g) if g else None, peak_reserved_GiB=peak / 2**30 if peak else None,
                        largest_family_7000=T.get(7000, {}).get('largest_n'), largest_family_last=top[-1]['largest_n'], largest_family_id_last=top[-1]['largest_family'],
                        watched_max_last=top[-1]['watch_max_n'], first_step_largest_ge_50000=big[0]['iteration'] if big else None,
                        seconds=rec.get('attempts', [{}])[-1].get('seconds') if rec else None))
        print('MON', e, out[-1]['status'], out[-1]['last_iteration'], out[-1]['max_gaussians'], out[-1]['largest_family_last'], flush=True)
    write('roof_runs', out, 'runaway-roof probes (addenda 8/9): counts and largest prior family from the read-only monitor; no GT')
    # figure: totals and largest family vs iteration, with the cells and probe0
    R = {r['key']: r for r in cause_runs()}
    fig, ax = plt.subplots(1, 3, figsize=(15, 4.8))
    col = dict(probe3='#d62728', probe3own='#ff9896', probe4='#1f77b4', cell0='#8c564b', cell2='#bcbd22', cell3='#17becf', probe0='#7f7f7f')
    lab = dict(probe3='probe3 지붕 A (칸 0 장면 크기)', probe3own='probe3own 지붕 A (자기 장면 크기)', probe4='probe4 지붕 B (칸 3 장면 크기)',
               cell0='칸 0', cell2='칸 2', cell3='칸 3', probe0='probe0 대조 (B0)')
    for k in ['cell0', 'cell2', 'cell3', 'probe0']:
        its, g, _ = lineage(R[k]['atts'])
        ax[0].plot(its, np.array(g) / 1e6, color=col[k], lw=1, ls='--', label=lab[k])
    for e, c in curves.items():
        ax[0].plot(c['iterations'], np.array(c['gaussians']) / 1e6, color=col[e], lw=1.6, label=lab[e])
    ax[0].set(xlabel='반복', ylabel='가우시안 수 (백만)', title='판 전체 가우시안 수', xlim=(0, 15500))
    S = {r['run']: r for r in json.loads((D / 'tables/roof_summary.json').read_text())['rows']}   # run summary() first
    col |= dict(base_s0='#000000', probe1='#bdbdbd')
    lab |= dict(base_s0='기준 B0 ALS', probe1='probe1 (넓이 ×5)')
    for k in ['base_s0', 'probe0', 'probe1', 'cell0', 'cell2', 'cell3']:
        r = S[k]
        ax[1].plot(r['last_iteration'], r['largest_family'], ls='none', marker='o' if r['largest_family_lineage'] == '사전 정보' else 's', ms=6,
                   color=col[k], mec='k', mew=.5, label=f'{lab[k]} 마지막 1위 계보 ({r["largest_family_lineage"]})')
    for e in curves:
        M = json.loads((D / f'tables/roof_monitor_{e}.json').read_text())['rows']
        ax[1].plot([r['iteration'] for r in M], [r['largest_n'] for r in M], color=col[e], lw=1.6, label=f'{lab[e]} 1위 계보 (100회마다)')
    ax[1].set(yscale='log', xlabel='반복', ylabel='계보 크기 (개)', title='가장 큰 씨앗 계보 (사전 정보·배경 모두; ● 사전 정보, ■ 배경)', xlim=(0, 15500))
    for e in curves:
        M = json.loads((D / f'tables/roof_monitor_{e}.json').read_text())['rows']
        it = np.array([r['iteration'] for r in M]); n = np.maximum(1, np.array([r['largest_n'] for r in M]))
        ax[2].plot(it, np.array([r['largest_clone'] for r in M]) / n, color=col[e], lw=1.4, label=f'{lab[e]} 복제 선택 몫')
        ax[2].plot(it, np.array([r['largest_split'] for r in M]) / n, color=col[e], lw=1, ls=':', label=f'{lab[e]} 쪼개기 선택 몫')
    ax[2].set(xlabel='반복', ylabel='1위 계보 안 몫', title='1위 계보의 밀도 제어 선택(100회마다)', xlim=(0, 15500), ylim=(0, 1.02))
    for a in ax:
        a.grid(alpha=.3)
        a.legend(fontsize=7.5, loc='upper left')
    ax[1].legend(fontsize=7.5, loc='lower right')
    fig.tight_layout()
    p = D / 'figures/roof_runs.png'
    fig.savefig(p, dpi=170)
    dump(p.with_suffix('.json'), dict(at=now(), entries=list(curves), scientific_verdict=None))
    print('FIG', p, flush=True)


def families():
    """Three largest families (any lineage) per probe at 7,000 and the last saved state: seed, where the family sits, its shape."""
    from tu_cause import ply, state
    cfg()
    rows = []
    for e in ['probe3', 'probe4', 'probe3own']:
        att, M = monitor_rows(e)
        if not att:
            continue
        unit = e.replace('own', '')
        sd = loadz(TU / 'stage1' / f'{unit}__ALS/seeds.npz', ['xyz', 'origin', 'patch', 'sigma'])
        T = loadz(TU / 'targets' / f'{unit}__ALS.npz', ['building', 'region', 'kind'])
        m = att[-1] / 'model'
        saved = [int(p.name.split('_')[1]) for d in ['jbgs_complete', 'point_cloud'] for p in (m / d).glob('iteration_*')]
        for it in sorted({7000, max(saved)}):   # addendum 10: probe3 ends at its stop-file state, not 15,000
            try:
                p = state(m, it)
            except FileNotFoundError:
                continue
            l = ply(p, ('x', 'y', 'z', 'opacity', 'scale_0', 'scale_1', 'origin', 'init_id'))
            cnt = np.bincount(l['init_id'][l['init_id'] >= 0], minlength=len(sd['origin']))
            for rank, i in enumerate(np.argsort(cnt)[::-1][:3]):
                s = l['init_id'] == i
                x, y, z = l['x'][s], l['y'][s], l['z'][s]
                q = lambda a: [float(v) for v in np.quantile(a, [.01, .5, .99])]
                sc = np.exp(np.maximum(l['scale_0'][s], l['scale_1'][s]))
                key = np.round(np.c_[x, y, z] * 1000).astype(np.int64)
                uniq = len(np.unique(key, axis=0))
                pt = int(sd['patch'][i])
                rows.append(dict(entry=e, iteration=it, rank=rank + 1, init_id=int(i), lineage='사전 정보' if sd['origin'][i] == 1 else '배경(SfM)',
                                 family=int(cnt[i]), share_of_run=float(cnt[i] / len(l['x'])), seed_xyz=[float(v) for v in sd['xyz'][i]],
                                 seed_sigma_m=float(sd['sigma'][i]), building=str(T['building'][pt]) if pt >= 0 else None,
                                 x_p01_p50_p99=q(x), y_p01_p50_p99=q(y), z_p01_p50_p99=q(z), occupied_1m_cells=int(len(np.unique(np.c_[np.floor(x), np.floor(y)], axis=0))),
                                 distinct_positions_1mm=uniq, duplicate_share_1mm=1 - uniq / len(x),
                                 max_scale_m_p10_p50_p90=[float(v) for v in np.quantile(sc, [.1, .5, .9])],
                                 opacity_p10_p50_p90=[float(v) for v in np.quantile(1 / (1 + np.exp(-l['opacity'][s])), [.1, .5, .9])]))
                print('FAM', e, it, rank + 1, int(i), rows[-1]['lineage'], int(cnt[i]), rows[-1]['building'], flush=True)
    write('roof_families', rows, 'three largest seed families per runaway-roof probe at 7,000 and the last saved state (15,000; probe3 14,000 by addendum 10), any lineage; no GT')


def where():
    """Top view per probe at its last saved state: all Gaussians (grey), the three largest families (colour), the unit square,
    the roof where the cells ran away (cyan box = cell family xyz p01-p99 box)."""
    from tu_cause import ply, state
    cfg()
    P = {p['name']: p for p in json.loads((TU / 'probes/probes_add8.json').read_text())['probes']}
    fam = {(r['entry'], r['iteration'], r['rank']): r for r in json.loads((D / 'tables/roof_families.json').read_text())['rows']}
    entries = [e for e in ['probe3', 'probe3own', 'probe4'] if monitor_rows(e)[0]]
    fig, ax = plt.subplots(1, len(entries), figsize=(5.2 * len(entries), 5.4))
    colors3 = ['#d62728', '#ff7f0e', '#9467bd']
    for a, e in zip(np.atleast_1d(ax), entries):
        unit = e.replace('own', '')
        att, _ = monitor_rows(e)
        m = att[-1] / 'model'
        saved = [int(p.name.split('_')[1]) for d in ['jbgs_complete', 'point_cloud'] for p in (m / d).glob('iteration_*')]
        it = max(saved)
        l = ply(state(m, it), ('x', 'y', 'init_id'))
        lo, hi = np.array(P[unit]['region_min']), np.array(P[unit]['region_max'])
        c = (lo + hi) / 2
        R = 1.6 * (hi - lo).max() / 2
        H, xe, ye = np.histogram2d(l['x'], l['y'], bins=160, range=[[c[0] - R, c[0] + R], [c[1] - R, c[1] + R]])
        a.imshow(np.log10(1 + H.T), origin='lower', extent=(xe[0], xe[-1], ye[0], ye[-1]), cmap='Greys', alpha=.55)
        for rank in [1, 2, 3]:
            r = fam.get((e, it, rank))
            if r is None:
                continue
            s = np.flatnonzero(l['init_id'] == r['init_id'])
            s = s[:: max(1, len(s) // 4000)]
            a.scatter(l['x'][s], l['y'][s], s=1, color=colors3[rank - 1], alpha=.5,
                      label=f'{rank}위 {r["lineage"]} 계보 {r["family"] / 1e6:.2f} M ({100 * r["share_of_run"]:.0f} %)' + (f' {r["building"]}' if r['building'] else ''))
            a.plot(*r['seed_xyz'][:2], marker='x', color=colors3[rank - 1], ms=7, mew=1.6)
        a.add_patch(plt.Rectangle(lo, *(hi - lo), fill=False, ec='k', lw=1.2, ls='--', label='판 구역 (94 m 정사각형)'))
        roof = 'A' if unit == 'probe3' else 'B'
        blo, bhi = box(roof)
        a.add_patch(plt.Rectangle(blo[:2], *(bhi[:2] - blo[:2]), fill=False, ec='#00bcd4', lw=1.6, label=f'칸에서 폭주한 지붕 {roof} 자리'))
        a.set(xlim=(c[0] - R, c[0] + R), ylim=(c[1] - R, c[1] + R), aspect='equal', xlabel='x (m)', ylabel='y (m)')
        ext = json.loads((att[-1] / 'extent_override.json').read_text())
        a.set_title(f'{e}: {it:,}회, 전체 {len(l["x"]) / 1e6:.2f} M, 장면 크기 {ext["used_radius"]:.0f} m', fontsize=9.5)
        a.legend(fontsize=7, loc='upper left', markerscale=6)
    fig.suptitle('작은 판에서 커진 계보의 자리(위에서 봄; 회색 = 모든 가우시안 밀도, × = 계보의 씨앗)', fontsize=10.5)
    fig.tight_layout()
    p = D / 'figures/roof_where.png'
    fig.savefig(p, dpi=150)
    dump(p.with_suffix('.json'), dict(at=now(), entries=entries, scientific_verdict=None))
    print('FIG', p, flush=True)


def summary():
    """All runs of the cause check side by side: extent, count, largest family of any lineage and where it sits
    relative to the unit boundary (signed distance of the family's median xy to the nearest unit edge, negative = outside)."""
    from tu_cause import ply, state
    from tu_growth import extent
    cfg()
    P8 = {p['name']: p for p in json.loads((TU / 'probes/probes_add8.json').read_text())['probes']}
    cells = {f'cell{c["id"]}': c for c in json.loads((TU / 'cells/cells.json').read_text())['cells']}
    R = {r['key']: r for r in cause_runs()}
    spec = []
    for k in ['base_s0', 'probe0', 'probe1', 'cell0', 'cell2', 'cell3']:
        r = R[k]
        if k.startswith('cell'):
            lo, hi = cells[k]['expanded_min'], cells[k]['expanded_max']
        else:
            lo, hi = r['lo'], r['hi']
        sdp = FT / 'stage1/B0_b10__ALS/seeds.npz' if k == 'base_s0' else TU / f'stage1/{k}__ALS/seeds.npz'
        spec.append(dict(key=k, atts=r['atts'], late_att=r.get('late_att', r['atts'][-1]), late=r['late'], train=r['train'], lo=lo, hi=hi, seeds=sdp))
    for e in ['probe3', 'probe3own', 'probe4']:
        att, _ = monitor_rows(e)
        u = e.replace('own', '')
        m = att[-1] / 'model'
        late = max(int(p.name.split('_')[1]) for d in ['jbgs_complete', 'point_cloud'] for p in (m / d).glob('iteration_*'))
        spec.append(dict(key=e, atts=att[-1:], late_att=att[-1], late=late, train=P8[u]['images'], lo=P8[u]['region_min'], hi=P8[u]['region_max'],
                         seeds=TU / f'stage1/{u}__ALS/seeds.npz'))
    rows = []
    for s in spec:
        m0, m1 = s['atts'][0] / 'model', s['late_att'] / 'model'
        ext, ncam = extent(m0, s['train'])
        ex_file = s['late_att'] / 'extent_override.json'
        used = json.loads(ex_file.read_text())['used_radius'] if ex_file.exists() else ext
        its, g, peak = lineage(s['atts'])
        l = ply(state(m1, s['late']), ('x', 'y', 'init_id'))
        org = loadz(s['seeds'], ['origin'])['origin']
        cnt = np.bincount(l['init_id'][l['init_id'] >= 0], minlength=len(org))
        i = int(np.argmax(cnt))
        sel = l['init_id'] == i
        mx, my = float(np.median(l['x'][sel])), float(np.median(l['y'][sel]))
        lo, hi = np.maximum(np.array(s['lo'], float), -1e8), np.minimum(np.array(s['hi'], float), 1e8)
        d = min(mx - lo[0], hi[0] - mx, my - lo[1], hi[1] - my)
        rows.append(dict(run=s['key'], train_images=len(s['train']), scene_extent_used_m=float(used), clone_threshold_m=.01 * float(used),
                         last_iteration=s['late'], gaussians_last=len(l['x']), max_gaussians_7000_last=max(v for t, v in zip(its, g) if t >= 7000),
                         largest_family=int(cnt[i]), largest_family_share=float(cnt[i] / len(l['x'])), largest_family_lineage='사전 정보' if org[i] == 1 else '배경(SfM)',
                         largest_family_median_xy=[mx, my], distance_to_unit_edge_m=float(d),
                         second_family=int(np.sort(cnt)[-2])))
        print('SUM', s['key'], round(used), len(l['x']), int(cnt[i]), rows[-1]['largest_family_lineage'], round(d, 1), flush=True)
    write('roof_summary', rows, 'cause-check runs side by side: extent used, counts, largest seed family of any lineage at the last saved state and its signed distance to the nearest unit edge (negative = outside the unit; cells: expanded bounds); no GT')


if __name__ == '__main__':
    dict(images=images, prior=prior, monitor=monitor, families=families, where=where, summary=summary)[sys.argv[1]](*sys.argv[2:])
