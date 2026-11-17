"""Work na (order 4): what decides survival over an opacity reset. addendum6_b.json (locked). GPU (/source = r31); no parameter is changed (no optimizer step).
  grads <stem|run> <reset>  : the whole-scene dump <reset>_pre_reset; first the pre-reset values of a fixed sample of Gaussians (addendum 4/5 work na compositing at
                              the centre pixel: front accumulated opacity, own alpha*T, seeing views); then opacity reset with the training rule
                              (min(opacity, 0.01), no exemption: judgment off in TARGET runs) and, for every training view, the training photo loss
                              (0.8 L1 + 0.2 (1 - SSIM)) and depth loss (jbgs_target_lambda x target loss), each backpropagated alone to the opacity logits.
                              survival = uid present in the first whole-scene dump after the reset -> addendum6/na/grads_<run>_<reset>.npz
  tables                    : tables/na_bins, na_logistic, na_prereset_bins, na_record_sign (order 4.3), figures/na_survival.png"""
import sys, time
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum6')
from a6_common import *
NA6 = A6O/'na'; STAGE0 = PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1/fork_inputs/s61'

def bcfg6():
    p = R/'configs/phd/main_trainerr_v1/addendum6_b.json'; assert sha(p) == json.loads(p.with_name('addendum6_b.lock.json').read_text())['config_sha256'], 'addendum6_b changed after lock'
    return json.loads(p.read_text())

def resolve(x):
    c = cfg6()
    if x in c['runs']: return c['runs'][x]['run'], x
    return x, RUNS4[x]['stem']

def dump_names(m):
    names = [p.stem for p in (m/'trainlog/scene').glob('*.pt')]
    return sorted(names, key=lambda n: (int(n.split('_')[0]), 0 if n.endswith('pre_reset') else 1))

def patch_group(stem):
    """valid-patch index -> majority group of all addendum-2 points on the patch (ties: lower code); -1 no point."""
    z = loadz(O/'addendum2/points'/f'ra_{stem}__own.npz', ['patch_row', 'group']); T = Targets(stem); v = T.v_of_rows(z['patch_row']); ok = v >= 0
    cnt = np.zeros((len(T.valid), 4), 'i8'); np.add.at(cnt, (v[ok], z['group'][ok]), 1); return np.where(cnt.sum(1) > 0, cnt.argmax(1), -1)

def column_kind(stem, run, state, xyz, tag, tidx):
    """kind: 0 bound to the column patch at the centre, 1 bound to another patch, 2 released, 3 unbound (order 1.6)."""
    from s0_sets import columns
    core = loadz(JA/'core_points'/f'{stem}.npz'); own, _ = columns(np.asarray(xyz, 'f8'), core, A6O/'columns'/f'{run}_{state}')
    col = np.where(own >= 0, core['source_index'][np.clip(own, 0, None)], -1); T = Targets(stem); raw = np.where((tag == 1) & (tidx >= 0), T.valid[np.clip(tidx, 0, len(T.valid)-1)], -2)
    return np.where(tag == 1, np.where(raw == col, 0, 1), np.where(tag == 2, 2, 3)).astype('i1')

def grads(x, reset):
    import torch
    sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1'); sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum4')
    import a4_da as D4, a4_na as NA4
    from PIL import Image
    camera = D4.gpu_setup(); from gaussian_renderer import render; from utils.loss_utils import l1_loss, ssim; from types import SimpleNamespace
    c = bcfg6()['work_na']; t0 = time.monotonic(); run, stem = resolve(x); m = RUNS4[run]['model']; site, prior = stem.split('__'); st = f'{reset}_pre_reset'
    names = dump_names(m); assert st in names, f'{run} has no {st} dump'; nxt = names[names.index(str(reset))+1]
    S = D4.load_pt(m, st); N = len(S['uid']); uid = S['uid'].numpy(); tag = S['target_tag'].numpy(); tidx = S['target_index'].numpy()
    nu = D4.load_pt(m, nxt)['uid'].numpy(); alive = np.isin(uid, nu)
    lk = load_events(m, ('link',))['link']; sp = (lk['how'] == 3) & (lk['iteration'] > reset) & (lk['iteration'] <= int(nxt.split('_')[0])); split = np.isin(uid, lk['parent_uid'][sp])
    kind = column_kind(stem, run, st, S['xyz'].double().numpy(), tag, tidx); pg = patch_group(stem); pgr = np.where((tag == 1) & (tidx >= 0), pg[np.clip(tidx, 0, len(pg)-1)], -1)
    md, mi = D4.views_of(stem); vn = sorted(mi); pipe = SimpleNamespace(convert_SHs_python=False, compute_cov3D_python=False, depth_ratio=0., debug=False); bg = torch.zeros(3, device='cuda')
    imgdir = STAGE0/site/f'scene_{prior}'/'images'; files = {p.stem: p for p in imgdir.iterdir()}
    # pre-reset values (sample, opacity as dumped)
    rng = np.random.default_rng(c['prereset_rng_seed']+reset); samp = np.sort(rng.choice(N, min(N, c['prereset_sample']), replace=False))
    g = D4.gmodel(S); tg = torch.as_tensor(tag.astype('i8'), device='cuda'); ti = torch.as_tensor(tidx.astype('i8'), device='cuda'); X = S['xyz'].double().numpy()[samp]
    fa_med = [[] for _ in samp]; cw = np.zeros(len(samp)); nv = np.zeros(len(samp), 'i4'); ov = np.zeros(len(samp), 'i4')
    with torch.no_grad():
        for j, nm in enumerate(vn):
            mm = mi[nm]; K = np.asarray(mm['K']); M = np.asarray(mm['W2C']); Xc = X@M[:3, :3].T+M[:3, 3]; z = Xc[:, 2]; okz = z > .2
            with np.load(md/mm['file']) as zz: H, W = zz['owner'].shape
            uu = K[0, 0]*Xc[:, 0]/np.where(okz, z, 1)+K[0, 2]; vv = K[1, 1]*Xc[:, 1]/np.where(okz, z, 1)+K[1, 2]; ins = np.flatnonzero(okz & (uu >= 0) & (uu < W) & (vv >= 0) & (vv < H))
            if not len(ins): continue
            FA, SW, FK, ACC = NA4.comp(g, tg, ti, camera(W, H, K, M, nm), np.floor(uu[ins]).astype('i8'), np.floor(vv[ins]).astype('i8'), z[ins], samp[ins])
            cw[ins] += SW; nv[ins] += 1; ov[ins] += (FA < .5)
            if j % 40 == 0: print('NA6_PRE', run, reset, j, len(vn), round(time.monotonic()-t0), flush=True)
    # reset and per-view gradients
    op = torch.sigmoid(g._opacity.detach()); g._opacity = torch.nn.Parameter(torch.log(torch.clamp(torch.minimum(op, torch.full_like(op, .01)), 1e-12)/(1-torch.minimum(op, torch.full_like(op, .01)))), requires_grad=True)
    lam = float(c['depth_lambda']); dss = float(c['lambda_dssim'])
    acc = {k: torch.zeros(N, device='cuda', dtype=torch.float64) for k in ['p_nz', 'p_up', 'p_sum', 'p_abs', 'd_nz', 'd_up', 'd_sum', 'd_abs', 'any_nz']}
    ins_rows = np.flatnonzero(S['inside'].numpy()) if 'inside' in S else np.zeros(0, 'i8'); keep_views = x in c['record_check_runs']; pv = {'p': [], 'd': []}
    for j, nm in enumerate(vn):
        mm = mi[nm]; K = np.asarray(mm['K']); Mw = np.asarray(mm['W2C'])
        with np.load(md/mm['file']) as zz: H, W = zz['owner'].shape; tdep = torch.from_numpy(zz['depth']).cuda(); w = torch.from_numpy(zz['weight']).cuda()
        im = Image.open(files[nm]).convert('RGB'); assert im.size == (W, H), (nm, im.size, (W, H)); gt = torch.from_numpy(np.asarray(im, 'f4')/255.).permute(2, 0, 1).cuda()
        pkg = render(camera(W, H, K, Mw, nm), g, pipe, bg); img = pkg['render']
        photo = (1-dss)*l1_loss(img, gt)+dss*(1-ssim(img, gt)); D = pkg['surf_depth'].squeeze(0)
        valid = torch.isfinite(tdep) & (tdep > 0) & torch.isfinite(D) & (D > 0) & (w > 0); depth = lam*(torch.abs(D[valid]-tdep[valid])*w[valid]).sum()/float(D.numel())
        gp = torch.autograd.grad(photo, g._opacity, retain_graph=True)[0][:, 0].double()
        gd = torch.autograd.grad(depth, g._opacity, allow_unused=True)[0] if depth.requires_grad else None
        gd = torch.zeros_like(gp) if gd is None else gd[:, 0].double()
        for k_, gg in [('p', gp), ('d', gd)]:
            acc[f'{k_}_nz'] += (gg != 0); acc[f'{k_}_up'] += (gg < 0); acc[f'{k_}_sum'] += gg; acc[f'{k_}_abs'] += gg.abs()
        acc['any_nz'] += (gp != 0) | (gd != 0)
        if keep_views and len(ins_rows): pv['p'].append(gp[ins_rows].float().cpu().numpy()); pv['d'].append(gd[ins_rows].float().cpu().numpy())
        if j % 40 == 0: print('NA6_GRAD', run, reset, j, len(vn), round(time.monotonic()-t0), flush=True)
    out = {k: v.cpu().numpy() for k, v in acc.items()}
    NA6.mkdir(parents=True, exist_ok=True)
    savez(NA6/f'grads_{run}_{reset}.npz', uid=uid, tag=tag, tidx=tidx, kind=kind, patch_group=pgr, alive=alive, split=split, size=torch.exp(S['scaling']).max(1).values.numpy(),
          opacity_pre=torch.sigmoid(S['opacity'][:, 0]).numpy(), views=np.int32(len(vn)), next_dump=nxt, **out,
          pre_rows=samp, pre_colour_weight=cw, pre_views=nv, pre_open_views=ov, inside_rows=ins_rows, view_names=np.array(vn),
          **({'pv_photo': np.stack(pv['p']), 'pv_depth': np.stack(pv['d'])} if pv['p'] else {}))
    dump(NA6/f'grads_{run}_{reset}.json', dict(at=now(), run=run, stem=stem, state=st, next_dump=nxt, gaussians=N, views=len(vn), alive_pct=pct(alive), split_pct=pct(split),
                                              depth_lambda=lam, lambda_dssim=dss, seconds=time.monotonic()-t0, scientific_verdict=None))
    print('NA6_DONE', run, reset, N, pct(alive), round(time.monotonic()-t0), flush=True)

KIND_KO6 = ['같은 목표에 묶인 것', '다른 목표에 묶인 것', '풀린 것', '묶이지 않은 것']
PG_KO = {-1: '묶인 조각 없음', 0: '지킨 점의 조각', 1: '잃은 점의 조각', 2: '고친 점의 조각', 3: '목표도 결과도 틀린 점의 조각'}

def values(z):
    V = int(z['views']); nzp = z['p_nz']; nzd = z['d_nz']
    with np.errstate(invalid='ignore', divide='ignore'):
        return dict(views_with_gradient_share=z['any_nz']/V, up_share_photo=np.where(nzp > 0, z['p_up']/nzp, np.nan), up_share_depth=np.where(nzd > 0, z['d_up']/nzd, np.nan),
                    sum_photo=z['p_sum'], sum_depth=z['d_sum'], abs_photo=z['p_abs'], abs_depth=z['d_abs'],
                    consistency_photo=np.where(z['p_abs'] > 0, z['p_sum']/z['p_abs'], np.nan), consistency_depth=np.where(z['d_abs'] > 0, z['d_sum']/z['d_abs'], np.nan))

def prank(x):
    x = np.asarray(x, 'f8'); out = np.full(len(x), .5); ok = np.isfinite(x)
    if ok.any():
        from scipy.stats import rankdata
        out[ok] = (rankdata(x[ok])-.5)/ok.sum()
    return out

def auc(y, s):
    from scipy.stats import rankdata
    r = rankdata(s); n1 = int(y.sum()); n0 = len(y)-n1
    return float((r[y == 1].sum()-n1*(n1+1)/2)/(n1*n0)) if n1 and n0 else None

def logit_fit(X, y, l2=1e-3, it=50):
    X = np.c_[np.ones(len(X)), X]; w = np.zeros(X.shape[1])
    for _ in range(it):
        p = 1/(1+np.exp(-np.clip(X@w, -30, 30))); W = p*(1-p); H = X.T@(X*W[:, None])+l2*np.eye(X.shape[1]); w -= np.linalg.solve(H, X.T@(p-y)+l2*w)
    return w
def logit_pred(w, X): return 1/(1+np.exp(-np.clip(np.c_[np.ones(len(X)), X]@w, -30, 30)))

FAMILIES = {'기울기를 받는 영상의 비율': ['views_with_gradient_share'], '올리는 쪽 영상의 비율': ['up_share_photo', 'up_share_depth'],
            '기울기의 합과 절댓값의 합': ['sum_photo', 'sum_depth', 'abs_photo', 'abs_depth'], '부호 일관성': ['consistency_photo', 'consistency_depth'], '종류': ['kind']}

def tables():
    c = bcfg6()['work_na']; bins, logi, pre, sign = [], [], [], []
    for f in sorted(NA6.glob('grads_*.npz')):
        z = loadz(f); run, reset = f.stem[6:].rsplit('_', 1); reset = int(reset); stem = RUNS4[run]['stem']; V = values(z); y = z['alive'].astype(float); N = len(y)
        base = dict(run=run, stem=stem, reset=reset, next_dump=str(z['next_dump']), gaussians=N, views=int(z['views']), alive_pct=pct(z['alive']), split_parent_pct=pct(z['split']))
        groups = [('전체', np.ones(N, bool))]+[(f'종류: {k}', z['kind'] == i) for i, k in enumerate(KIND_KO6)]+[(f'조각: {PG_KO[k]}', z['patch_group'] == k) for k in [0, 1, 2, 3, -1]]
        for vn, x in V.items():
            ok = np.isfinite(x); edges = np.unique(np.quantile(x[ok], np.linspace(0, 1, c['bins']+1))) if ok.any() else np.array([0., 1.])
            b = np.where(ok, np.clip(np.searchsorted(edges, x, 'right')-1, 0, len(edges)-2), -1)
            for gn, gm in groups:
                for k in range(-1, len(edges)-1):
                    m = gm & (b == k); n = int(m.sum())
                    if not n: continue
                    bins.append(dict(base, value=vn, subset=gn, bin=k, bin_range='값 없음(nan)' if k < 0 else f'[{edges[k]:.4g}, {edges[k+1]:.4g}]', n=n, small=n < 30, alive_pct=pct(z['alive'][m])))
        # logistic
        F = {k: prank(v) for k, v in V.items()}; kd = z['kind']; KD = np.stack([(kd == i).astype(float) for i in (1, 2, 3)], 1)
        rng = np.random.default_rng(20261117); tr = rng.random(N) < .5; te = ~tr
        def fit(drop=()):
            cols = [F[k] for k in c['logistic']['features'] if not any(k in FAMILIES[d] for d in drop)]
            X = np.stack(cols, 1) if cols else np.zeros((N, 0))
            if '종류' not in drop: X = np.c_[X, KD]
            mu, sd = X[tr].mean(0), X[tr].std(0)+1e-9; X = (X-mu)/sd; w = logit_fit(X[tr], y[tr]); p = logit_pred(w, X[te])
            return dict(accuracy_pct=pct((p >= .5) == (y[te] == 1)), auc=auc(y[te], p))
        full = fit(); logi.append(dict(base, model='네 값 + 종류', **full, test_n=int(te.sum()), always_alive_accuracy_pct=pct(y[te] == (y[tr].mean() >= .5))))
        for d in FAMILIES:
            r = fit((d,)); logi.append(dict(base, model=f'{d} 뺌', **r, auc_change=(r['auc']-full['auc']) if (r['auc'] is not None and full['auc'] is not None) else None))
        for k in c['logistic']['features']:
            a1 = auc(y, np.nan_to_num(V[k], nan=np.nanmedian(V[k]) if np.isfinite(V[k]).any() else 0)); logi.append(dict(base, model=f'{k} 하나만(전체 점, 순위)', auc=a1))
        # pre-reset values (sample)
        r_ = z['pre_rows']; PV = dict(seeing_views=z['pre_views'].astype(float), open_views=z['pre_open_views'].astype(float), colour_weight=z['pre_colour_weight'], size=z['size'][r_])
        for vn, x in PV.items():
            edges = np.unique(np.quantile(x, np.linspace(0, 1, c['bins']+1))); b = np.clip(np.searchsorted(edges, x, 'right')-1, 0, len(edges)-2)
            for gn, gm in [('전체', np.ones(len(r_), bool))]+[(f'종류: {k}', z['kind'][r_] == i) for i, k in enumerate(KIND_KO6)]+[(f'조각: {PG_KO[k]}', z['patch_group'][r_] == k) for k in [0, 1, 2, 3, -1]]:
                for k in range(len(edges)-1):
                    m = gm & (b == k); n = int(m.sum())
                    if n: pre.append(dict(base, value=vn, subset=gn, sample=len(r_), bin=k, bin_range=f'[{edges[k]:.4g}, {edges[k+1]:.4g}]', n=n, small=n < 30, alive_pct=pct(z['alive'][r_][m])))
        if 'pv_photo' in z:
            sign.extend(record_sign(run, z))
    table6('na_bins', bins); table6('na_logistic', logi); table6('na_prereset_bins', pre); table6('na_record_sign', sign or [dict(note='no record-check run computed')])
    print('NA6_TABLES', len(bins), len(logi), len(pre), len(sign), flush=True)

def record_sign(run, z):
    """order 4.3: recorded signed opacity gradients in (3000, 3100] vs the computed values (same view, all-view sum); opacity at saved states by survival."""
    m = RUNS4[run]['model']; rows = []; ins = z['inside_rows']; uid = z['uid'][ins]; vn = [str(x) for x in z['view_names']]
    cam = {}
    for l in (m/'trainlog/curve.jsonl').read_text().splitlines():
        if l.strip(): r = json.loads(l); cam[int(r['iteration'])] = r.get('camera')
    for gf in sorted((m/'trainlog/grads').glob('*.npz'), key=lambda p: int(p.stem)):
        it = int(gf.stem)
        if not (3000 < it <= 3100): continue
        gz = loadz(gf); o = np.argsort(uid); pos = np.clip(np.searchsorted(uid[o], gz['uid']), 0, len(uid)-1); ok = uid[o][pos] == gz['uid']; j = o[pos]
        for term, key in [('광도', 'photo'), ('깊이', 'depth')]:
            rec = gz[f'{key}_opacity_signed']; nz = ok & (rec != 0); cv = cam.get(it); vi = vn.index(cv) if cv in vn else -1
            same = z['pv_photo' if key == 'photo' else 'pv_depth'][vi][j] if vi >= 0 else np.full(len(j), np.nan)
            allv = z['p_sum' if key == 'photo' else 'd_sum'][ins][j]
            for lab, comp in [('같은 영상(그 반복의 학습 영상)', same), ('모든 영상의 합', allv)]:
                q = nz & np.isfinite(comp) & (comp != 0)
                rows.append(dict(run=run, iteration=it, camera=cv, term=term, compare=lab, recorded_nonzero=int(nz.sum()), compared=int(q.sum()),
                                 sign_agree_pct=pct(np.sign(rec[q]) == np.sign(comp[q])) if q.any() else None,
                                 alive_sign_agree_pct=pct((np.sign(rec[q]) == np.sign(comp[q]))[z['alive'][ins][j][q]]) if q.any() else None))
    # opacity at the saved in-range states by survival
    for st in ['3000_pre_reset', '3000', '3020', '3040', '3060', '3080', '3100']:
        p = m/'trainlog/states'/f'{st}.npz'
        if not p.exists(): rows.append(dict(run=run, state=st, note='저장 없음')); continue
        s = loadz(p, ['uid', 'opacity']); o = np.argsort(uid); pos = np.clip(np.searchsorted(uid[o], s['uid']), 0, len(uid)-1); ok = uid[o][pos] == s['uid']; al = z['alive'][ins][o][pos]
        for lab, mm in [('살아남음', ok & al), ('지워짐', ok & ~al)]:
            rows.append(dict(run=run, state=st, survival=lab, n=int(mm.sum()), opacity_q=q4(s['opacity'][mm]), above_0_05_pct=pct(s['opacity'][mm] >= .05) if mm.any() else None))
    return rows

if __name__ == '__main__':
    a = sys.argv[1:]
    {'grads': lambda: grads(a[1], int(a[2])), 'tables': tables}[a[0]]()
