"""Work da (order 3 + correction 1): code check table, depth differences of the addendum-2 'front' / 'behind' pixels, image 0013 walk-through, opacity gradients.
  pix <stem>   : every training view (own FINALTRAIN maps) -> addendum3/da/pix_<stem>.npz (front / behind pixels: owner row, view, diff; conf flag)
  view0013     : image 0013 south-wall target pixels through the map rules (owner disc, MVS point inside the GT view box, nearest target disc)
  grads        : correction 1: R1 floor band and control, |d photo / d opacity logit|, |d depth / ...|, |d gs2d / ...| of the bound Gaussians (record-run grads)
  tables       : tables/da_*.csv"""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum3')
from a3_common import *
import time
DA = A3O/'da'; THR = [1, 2, 3, 5, 10, 30]

def pix(stem):
    DA.mkdir(parents=True, exist_ok=True); t0 = time.monotonic(); site = stem.split('__')[0]; md = maps_dir(stem, 'own'); index = json.loads((md/'index.json').read_text())['views']
    S0dir = Path('/s0/fork_inputs/s61')/site/'maps'; names = sorted(index); out = {k: [] for k in ['f_owner', 'f_view', 'f_diff', 'f_conf', 'b_owner', 'b_view', 'b_diff', 'b_conf']}
    N = len(loadz(targets_of(stem, 'own'), ['area'])['area']); tgt = np.zeros(N, 'i8'); same = np.zeros(N, 'i8'); none = np.zeros(N, 'i8')
    for j, nm in enumerate(names):
        with np.load(md/index[nm]['file']) as z: own = z['owner']; dep = z['depth']
        mvs = np.load(S0dir/'mvs'/f'{nm}.npy'); conf = np.load(S0dir/'conf'/f'{nm}.npy'); k = own >= 0; o = own[k]; td = dep[k].astype('f8'); m = mvs[k].astype('f8'); cf = conf[k] > 0
        have = np.isfinite(m) & (m > 0); diff = np.where(have, m-td, np.nan)   # addendum2 a2_ga.stats classes (no confidence filter)
        f = have & (diff < -1.); b = have & (diff > 1.); s_ = have & ~f & ~b
        tgt += np.bincount(o, minlength=N); same += np.bincount(o[s_], minlength=N); none += np.bincount(o[~have], minlength=N)
        for p, sel, sign in [('f', f, -1.), ('b', b, 1.)]:
            out[f'{p}_owner'].append(o[sel].astype('i4')); out[f'{p}_view'].append(np.full(int(sel.sum()), j, 'i2')); out[f'{p}_diff'].append((sign*diff[sel]).astype('f4')); out[f'{p}_conf'].append(cf[sel].astype('u1'))
    savez(DA/f'pix_{stem}.npz', **{k: np.concatenate(v) for k, v in out.items()}, target_pixels=tgt, same_pixels=same, none_pixels=none, views=np.array(names))
    print('PIX', stem, {k: int(sum(len(x) for x in v)) for k, v in out.items() if k.endswith('owner')}, round(time.monotonic()-t0), flush=True)

def place_sets():
    """addendum3.json work_da.place_patch_sets -> list of (set name, stem, target rows)."""
    out = []; T = {}
    def rows_of(x): x = np.asarray(x, 'i8'); return np.unique(x[x >= 0])
    s = loadz(O/'sets/c2_own_lost.npz', ['patch_row']); out.append(('floor_band', 'R1rep_b10__ALS', rows_of(s['patch_row'])))
    s = loadz(O/'sets/c1_own_lost.npz', ['patch_row', 'xyz'])
    for nm, which in [('edge_back', 'back_wall_bottom'), ('edge_annex', 'annex_roof_edge')]: out.append((nm, 'B0_b10__LoD2', rows_of(s['patch_row'][place_mask(s['xyz'], which)])))
    out.append(('south_wall', 'B0_b10__LoD2', np.asarray(wall_zone_patches('B0_b10__LoD2', 'own')['south'], 'i8')))
    vis = np.r_[place_points('visible_low')['patch_row'], place_points('visible_high')['patch_row']]; out.append(('visible_wall', 'B0_b10__LoD2', rows_of(vis)))
    for stem in SCENES6:
        z = loadz(A2O/'points'/f'ra_{stem}__own.npz', ['case_id', 'group', 'judge', 'patch_row'])
        for jn, jc in [('보존', 1), ('일치', 0), ('보정', 2)]:
            out.append((f'fixed_{jn}', stem, rows_of(z['patch_row'][(z['case_id'] == 1) & (z['group'] == 2) & (z['judge'] == jc)])))
        out.append(('kept', stem, rows_of(z['patch_row'][z['group'] == 0])))
    return out

def group_median(key, val):
    o = np.lexsort((val, key)); k = key[o]; v = val[o]; b = np.r_[0, np.flatnonzero(np.diff(k))+1, len(k)]
    meds = np.array([np.median(v[b[i]:b[i+1]]) for i in range(len(b)-1)]); cnt = np.diff(b); return k[b[:-1]], meds, cnt

def tables():
    c = ccfg(); rows = []; dist = []; cons = []; cache = {}
    for name, stem, prow in place_sets():
        if stem not in cache: cache[stem] = loadz(DA/f'pix_{stem}.npz')
        z = cache[stem]; tp = z['target_pixels']
        for side, pre in [('front', 'f'), ('behind', 'b')]:
            own = z[f'{pre}_owner']; m = np.isin(own, prow); o = own[m]; d = z[f'{pre}_diff'][m].astype('f8'); v = z[f'{pre}_view'][m]; cf = z[f'{pre}_conf'][m].astype(bool)
            N = len(tp); n = np.bincount(o, minlength=N); has = np.flatnonzero(n > 0)
            r = dict(set=name, stem=stem, side=side, patches=len(prow), patches_with_pixels=len(has), target_pixels=int(tp[prow].sum()), side_pixels=int(len(o)),
                     side_pixels_pct_of_target=100*len(o)/max(1, int(tp[prow].sum())), side_conf_pass_pct=100*float(cf.mean()) if len(cf) else None)
            for t in THR:
                share = np.bincount(o[d > t], minlength=N)[has]/n[has]; q = qs(100*share, (10, 50, 90))
                r[f'gt{t}m_patch_median_pct'] = q['p50']; r[f'gt{t}m_patch_p10_pct'] = q['p10']; r[f'gt{t}m_patch_p90_pct'] = q['p90']; r[f'gt{t}m_pixel_pct'] = 100*float((d > t).mean()) if len(d) else None
            rows.append(r); dist.append(dict(set=name, stem=stem, side=side, pixels=len(d), **qs(d, (5, 10, 25, 50, 75, 90, 95))))
            if side == 'front' and len(o):
                key = o.astype('i8')*1000+v; k, mv, cnt = group_median(key, d); pat = k//1000; ok = cnt >= 5
                views_per_patch = np.bincount(pat, minlength=N)[has]
                sd = [np.std(mv[ok & (pat == p_)]) for p_ in np.unique(pat[ok]) if (ok & (pat == p_)).sum() >= 2]
                cons.append(dict(set=name, stem=stem, patches=len(has), views_per_patch_median=med(views_per_patch), views_per_patch_p90=qs(views_per_patch, (90,))['p90'],
                                 patches_with_2plus_views_of_5px=len(sd), per_view_median_diff_std_median_m=med(sd), per_view_median_diff_std_p90_m=qs(sd, (90,))['p90']))
    ctable('da_threshold_shares', rows); ctable('da_diff_distribution', dist); ctable('da_consistency', cons)
    code = [dict(item='화소에 어느 패치의 목표를 적는가', where='scripts/phd/main_finaltrain_v1/prepare_inputs.py:59-67; scripts/phd/main_target_v1/prepare_maps_r7.py:19-25; scripts/phd/main_target_v1/target_discs.cpp:6-26',
                 record='목표 원판(패치 목표점·법선·반지름 sqrt(area/pi), surface_exists인 패치만) z-버퍼: 화소마다 가장 가까운 원판의 행 번호가 owner, 그 깊이가 목표. 가림은 그 원판끼리만 계산; 영상 깊이는 쓰지 않음; 원판 목록 밖(패치가 없는 물체, 장면 상자 밖)의 것은 가림에 들어가지 않음'),
            dict(item='영상 깊이와 목표 깊이를 비교해 목표를 빼거나 무게를 줄이는 규칙', where='prepare_inputs.py:67-70; src/phd/forks/GeoGS-conf-guided-v1-r27/jbgs_target.py:116-122',
                 record='없음. 무게는 owner 화소 clip(sigma_ref/sigma, 0.1, 10), 배경 1. 학습 손실의 유효 화소 조건은 목표 유한·>0, 렌더 깊이 유한·>0, 무게 >0뿐'),
            dict(item='영상 깊이가 없는 화소', where='prepare_inputs.py:69', record='owner 화소는 영상 깊이와 상관없이 목표를 그대로 적음. owner가 없는 화소만 영상 깊이가 유한·>0·conf>0일 때 배경 목표(무게 1)'),
            dict(item='영상 0013 남쪽 끝 벽 화소', where='tables/da_view0013.csv', record='원판 z-버퍼에서 남쪽 끝 벽 패치가 가장 가까움 → owner; 비교 규칙 없음 → 통과; 영상 깊이 점의 자리와 가장 가까운 원판까지 거리는 표'),
            dict(item='깊이 손실의 렌더 깊이와 불투명도 기울기(고침 1)', where='gaussian_renderer/__init__.py:132,144-146,155; arguments/__init__.py:104; jbgs_target.py:116-122; train.py:902; rfix_speed builds/target/source/cuda_rasterizer/backward.cu:367,370,381,443',
                 record='surf_depth = (Σ w_i z_i)/(Σ w_i) (depth_ratio 0; render_alpha로 나눔, detach 없음). 손실 = Σ|D−목표|·화소무게 / 화소 수, 총손실에 jbgs_target_lambda 0.05를 곱함(train.py:902). CUDA 역전파: 깊이 채널(367)과 누적 불투명도 채널(370)이 dL_dalpha에 더해지고 T를 곱한 뒤(381) dL_dopacity += G·dL_dalpha(443)')]
    ctable('da_code_check', code); print('DA_TABLES', len(rows), flush=True)

def view0013():
    stem = 'B0_b10__LoD2'; nm = 'DJI_20241217094933_0013_D'; md = maps_dir(stem, 'own'); mi = json.loads((md/'index.json').read_text())['views'][nm]
    with np.load(md/mi['file']) as z: own = z['owner']; dep = z['depth']
    mvs = np.load(Path('/s0/fork_inputs/s61/B0_b10/maps/mvs')/f'{nm}.npy'); conf = np.load(Path('/s0/fork_inputs/s61/B0_b10/maps/conf')/f'{nm}.npy')
    south = np.asarray(wall_zone_patches(stem, 'own')['south']); k = np.isin(own, south); v, u = np.nonzero(k); td = dep[k].astype('f8'); m = mvs[k].astype('f8'); have = np.isfinite(m) & (m > 0)
    K = np.asarray(mi['K']); E = np.asarray(mi['W2C']); Rm, t = E[:3, :3], E[:3, 3]
    ray = np.c_[(u-K[0, 2])/K[0, 0], (v-K[1, 2])/K[1, 1], np.ones(len(u))]
    P = ((ray*np.where(have, m, np.nan)[:, None])-t)@Rm   # camera -> world (W2C rows), z = depth
    box = np.asarray(json.loads((GT/'views/B0_b10.json').read_text())['box']); inbox = np.all((P >= box[0]) & (P <= box[1]), 1) & have
    tg = loadz(targets_of(stem, 'own'), ['target', 'surface_exists']); cen = tg['target'][tg['surface_exists']]; dmin = np.full(len(P), np.nan)
    if have.any(): dmin[have] = cKDTree(cen).query(P[have])[0]
    front = have & (m < td-1)
    rows = [dict(view=nm, south_target_pixels=int(k.sum()), image_depth_present=int(have.sum()), front=int(front.sum()), conf_pass_of_front=int((front & (conf[k] > 0)).sum()),
                 target_depth_median_m=med(td), image_depth_median_front_m=med(m[front]), front_points_inside_view_box=int((front & inbox).sum()),
                 front_point_to_nearest_target_disc_centre_median_m=med(dmin[front]), front_point_to_nearest_target_disc_centre_p10_m=qs(dmin[front], (10,))['p10'],
                 rule_1_owner='nearest target disc = south-wall patch (z-buffer among target discs only)', rule_2_compare='none', rule_3_no_image_depth='target kept', passed=int(k.sum()))]
    ctable('da_view0013', rows); print('VIEW0013', rows, flush=True)

def grads():
    """record-run grads (tl_R1_ALS_own): bound Gaussians of the place patches at every gradient iteration (uid join with the same-iteration state)."""
    run = 'tl_R1_ALS_own'; model = RUNS[run]['model']; out = []
    for place in ['floor_band', 'floor_control']:
        P = place_points(place); Sp = np.unique(P['v'][P['v'] >= 0])
        for f in sorted((model/'trainlog/grads').glob('*.npz'), key=lambda p: int(p.stem)):
            g = loadz(f); it = int(g['iteration']); S = load_state(model, str(it), 'states'); b = (S['tag'] == 1) & np.isin(S['tidx'], Sp); uid = S['uid'][b]
            pos = {int(x): i for i, x in enumerate(g['uid'])}; ii = np.array([pos[x] for x in uid if x in pos], 'i8')
            r = dict(place=place, iteration=it, bound=int(b.sum()), joined=len(ii))
            for term in ['photo', 'depth', 'gs2d']:
                a = g[f'{term}_opacity'][ii].astype('f8') if len(ii) else np.zeros(0); nz = a[a > 0]
                r[f'{term}_nonzero'] = len(nz); r[f'{term}_median_nonzero'] = med(nz); r[f'{term}_sum'] = float(a.sum()); r[f'{term}_loss_value'] = float(g[f'{term}_value'])
            r['depth_over_photo_sum'] = r['depth_sum']/r['photo_sum'] if r['photo_sum'] > 0 else None; out.append(r)
    ctable('da_opacity_gradients', out)
    pooled = []
    for place in ['floor_band', 'floor_control']:
        for lo, hi in [(0, 3000), (3000, 7000), (7000, 15000), (15000, 30000)]:
            q = [r for r in out if r['place'] == place and lo < r['iteration'] <= hi]
            pooled.append(dict(place=place, window=f'{lo}-{hi}', iterations=len(q), **{f'{t}_sum': float(sum(r[f'{t}_sum'] for r in q)) for t in ['photo', 'depth', 'gs2d']},
                               depth_over_photo=(sum(r['depth_sum'] for r in q)/sum(r['photo_sum'] for r in q)) if sum(r['photo_sum'] for r in q) > 0 else None,
                               photo_median_of_medians=med([r['photo_median_nonzero'] for r in q if r['photo_median_nonzero'] is not None]),
                               depth_median_of_medians=med([r['depth_median_nonzero'] for r in q if r['depth_median_nonzero'] is not None])))
    ctable('da_opacity_gradients_windows', pooled); print('GRADS', pooled, flush=True)

def figure():
    """cumulative share of front (and behind) pixel differences per place set (B0 / R1 places and the scene 'kept' sets), log x."""
    plt = korean_plt(); FIG = A3D/'figures'; FIG.mkdir(parents=True, exist_ok=True); cache = {}; fig, axs = plt.subplots(1, 2, figsize=(14, 5.5), dpi=110, sharey=True); used = []
    sets = [(n, s_, r) for n, s_, r in place_sets() if n in ('floor_band', 'edge_back', 'edge_annex', 'south_wall', 'visible_wall') or (n == 'kept' and s_ in ('B0_b10__LoD2', 'R1rep_b10__ALS'))]
    cols = {'floor_band': '#2CA02C', 'edge_back': '#8E44AD', 'edge_annex': '#E67E22', 'south_wall': '#D62728', 'visible_wall': '#1F5FD6'}
    for ax, (side, pre) in zip(axs, [('front', 'f'), ('behind', 'b')]):
        for n, s_, r in sets:
            if s_ not in cache: cache[s_] = loadz(DA/f'pix_{s_}.npz')
            z = cache[s_]; d = np.sort(z[f'{pre}_diff'][np.isin(z[f'{pre}_owner'], r)].astype('f8'))
            if not len(d): continue
            lab = {'floor_band': 'R1 바닥 띠', 'edge_back': 'B0 가장자리 띠: 뒤쪽 벽 아랫단', 'edge_annex': 'B0 가장자리 띠: 별채 평지붕 가장자리', 'south_wall': 'B0 남쪽 끝 벽', 'visible_wall': 'B0 잘 보이는 벽'}.get(n, f"장면 지킴 ({s_.replace('_b10__', ' × ')})"); ax.plot(d, 100*np.arange(1, len(d)+1)/len(d), color=cols.get(n, '#7F8C8D'), ls='-' if n != 'kept' else ('--' if 'B0' in s_ else ':'), lw=1.4, label=lab)
            used.append(dict(set=n, stem=s_, side=side, pixels=len(d)))
        for t in THR: ax.axvline(t, color='#BDBDBD', lw=.6)
        ax.set_xscale('log'); ax.set_xlim(1, 300); ax.grid(alpha=.25); ax.set_xlabel(('목표 깊이 − 영상 깊이 (m)' if side == 'front' else '영상 깊이 − 목표 깊이 (m)')+', 화소 누적', fontsize=9)
        ax.set_title('앞에 다른 것 화소 (영상 깊이가 목표보다 1 m 넘게 앞)' if side == 'front' else '영상 깊이가 목표보다 1 m 넘게 뒤인 화소', fontsize=10)
    axs[0].set_ylabel('누적 화소 비율 (%)'); axs[0].legend(fontsize=7, loc='lower right'); fig.tight_layout(); p = FIG/'da_diff_cumulative.png'; fig.savefig(p, facecolor='white'); plt.close(fig)
    dump(p.with_suffix('.json'), dict(at=now(), figure=p.name, source=[str(DA/f'pix_{s}.npz') for s in cache], sets=used, vertical_lines_m=THR, arm='own', scientific_verdict=None)); print('DA_FIGURE', flush=True)

if __name__ == '__main__':
    a = sys.argv[1:]
    {'pix': lambda: pix(a[1]), 'tables': tables, 'view0013': view0013, 'grads': grads, 'figure': figure}[a[0]]()
