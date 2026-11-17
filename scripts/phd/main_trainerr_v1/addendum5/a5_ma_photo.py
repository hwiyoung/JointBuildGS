"""Work ma, last row of order 7: photo-loss difference with / without the seed at the reset before its deletion (config addendum5_c.json, locked). GPU (/source = r31).
  run <stem> [limit] : sample seeds per group (work ma groups), render every training view containing the seed centre with and without the seed,
                       training photo loss (0.8 L1 + 0.2 (1 - SSIM)) -> payload addendum5/ma/photo_<stem>.npz
  tables             : tables/ma_photo.csv (per scene x group), and the photo_loss_difference column of tables/ma_seeds is left as it is (this table replaces it)."""
import sys, time, hashlib
sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum5')
from a5_common import *
MA5 = A5O/'ma'
RESETS = [3000, 6000, 9000, 12000]
GROUPS = [('fixed', '틀린 목표 씨앗 · 제거됨', 'deleted'), ('kept', '대조: 지킨 점 씨앗 · 제거됨', 'deleted'), ('kept', '대조: 지킨 점 씨앗 · 살아남음', 'alive')]
STAGE0 = PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1/fork_inputs/s61'

def ccfg():
    p = R/'configs/phd/main_trainerr_v1/addendum5_c.json'; lk = json.loads(p.with_name('addendum5_c.lock.json').read_text())
    assert hashlib.sha256(p.read_bytes()).hexdigest() == lk['config_sha256'], 'addendum5_c.json changed after the lock'; return json.loads(p.read_text())

def pick(stem, c):
    """the work-ma rule: deleted -> last reset before deletion; surviving -> 3000; then a fixed-seed sample per group."""
    z = loadz(MA5/f'seeds_{stem}.npz'); rng = np.random.default_rng(c['sample_rng_seed']); out = []
    for name, grp, kind in GROUPS:
        o = {k.split('__', 1)[1]: z[k] for k in z if k.startswith(name+'__')}
        m = (o['del_it'] >= 0) if kind == 'deleted' else o['alive30']; idx = []
        for i in np.flatnonzero(m):
            di = int(o['del_it'][i]); cand = [x for x in RESETS if (di < 0 and x == 3000) or (di >= 0 and x < di)]
            if cand and np.isfinite(o.get(f'cw_{max(cand)}', np.full(len(m), np.nan))[i]): idx.append((i, max(cand)))
        sel = rng.choice(len(idx), size=min(c['sample_per_group'], len(idx)), replace=False) if idx else []
        for s in sorted(sel): i, rs = idx[s]; out.append(dict(group=grp, seed=int(o['seed'][i]), uid=int(o['uid'][i]), reset=rs, eligible=len(idx)))
    return out

def run(stem, limit=None):
    import torch
    from PIL import Image
    sys.path.insert(0, '/repo/scripts/phd/main_trainerr_v1/addendum4'); import a4_ra as RA, a4_da as D4
    camera = D4.gpu_setup(); from gaussian_renderer import render; from utils.loss_utils import l1_loss, ssim
    from types import SimpleNamespace
    c = ccfg(); t0 = time.monotonic(); m_ = RA.RECORD[stem][0]; site, prior = stem.split('__'); imgdir = STAGE0/site/f'scene_{prior}'/'images'
    seeds = pick(stem, c)
    if limit: seeds = [s for k, s in enumerate(seeds) if k % max(1, len(seeds)//int(limit)) == 0][:int(limit)]
    md, mi = D4.views_of(stem); names = sorted(mi); pipe = SimpleNamespace(convert_SHs_python=False, compute_cov3D_python=False, depth_ratio=0., debug=False); bg = torch.zeros(3, device='cuda')
    photos = {}
    def photo(nm, W, H):
        if nm not in photos:
            f = next(p for p in imgdir.iterdir() if p.stem == nm); im = Image.open(f).convert('RGB')
            assert im.size == (W, H), f'image {nm} {im.size} != maps {(W, H)}'
            photos[nm] = torch.from_numpy(np.asarray(im, 'f4')/255.).permute(2, 0, 1).cuda().clamp(0, 1)
        return photos[nm]
    def loss(img, gt): return float((1-.2)*l1_loss(img, gt).mean()+.2*(1-ssim(img, gt)))
    rec = {k: [] for k in ['k', 'view', 'dL_pix', 'L_with', 'HW']}
    for rs in sorted({s['reset'] for s in seeds}):
        S = D4.load_pt(m_, f'{rs}_pre_reset'); ix = {int(x): i for i, x in enumerate(S['uid'].numpy())}; g = D4.gmodel(S); X = S['xyz'].double().numpy(); base = {}
        for k, s in enumerate(seeds):
            if s['reset'] != rs: continue
            row = ix.get(s['uid']); s['alive_in_dump'] = row is not None
            if row is None: continue
            x = X[row]
            for nm in names:
                mm = mi[nm]; K = np.asarray(mm['K']); M = np.asarray(mm['W2C']); xc = M[:3, :3]@x+M[:3, 3]
                if xc[2] <= .2: continue
                with np.load(md/mm['file']) as zz: H, W = zz['owner'].shape
                u = K[0, 0]*xc[0]/xc[2]+K[0, 2]; v = K[1, 1]*xc[1]/xc[2]+K[1, 2]
                if not (0 <= u < W and 0 <= v < H): continue
                cam = camera(W, H, K, M, nm); gt = photo(nm, W, H)
                with torch.no_grad():
                    if nm not in base: base[nm] = loss(render(cam, g, pipe, bg)['render'].clamp(0, 1), gt)
                    keep = g._opacity.data[row].clone(); g._opacity.data[row] = -30.
                    Lw = loss(render(cam, g, pipe, bg)['render'].clamp(0, 1), gt); g._opacity.data[row] = keep
                rec['k'].append(k); rec['view'].append(names.index(nm)); rec['dL_pix'].append((Lw-base[nm])*H*W); rec['L_with'].append(base[nm]); rec['HW'].append(H*W)
        print('MA_PHOTO', stem, rs, len(rec['k']), round(time.monotonic()-t0), flush=True)
        del g; torch.cuda.empty_cache()
    MA5.mkdir(parents=True, exist_ok=True)
    savez(MA5/f'photo_{stem}{"_test" if limit else ""}.npz', **{k: np.asarray(v) for k, v in rec.items()}, seed_group=np.array([s['group'] for s in seeds]), seed=np.array([s['seed'] for s in seeds]),
          seed_uid=np.array([s['uid'] for s in seeds]), seed_reset=np.array([s['reset'] for s in seeds]), seed_eligible=np.array([s['eligible'] for s in seeds]),
          seed_alive=np.array([s.get('alive_in_dump', False) for s in seeds]), seconds=np.float64(time.monotonic()-t0))
    print('MA_PHOTO_DONE', stem, len(seeds), len(rec['k']), round(time.monotonic()-t0), flush=True)

def tables():
    rows = []
    for stem in ['B0_b10__LoD2', 'B173nb_b10__ALS']:
        p = MA5/f'photo_{stem}.npz'
        if not p.exists(): continue
        z = loadz(p); k = z['k']; d = z['dL_pix']
        for grp in [g[1] for g in GROUPS]:
            sk = np.flatnonzero((z['seed_group'] == grp) & z['seed_alive'])
            per_seed = np.array([d[k == i].sum() for i in sk if (k == i).any()]); per_view = d[np.isin(k, sk)]
            rows.append(dict(stem=stem, group=grp, eligible=int(z['seed_eligible'][sk[0]]) if len(sk) else 0, sampled=int(((z['seed_group'] == grp)).sum()), seeds_with_views=len(per_seed), small_group=len(per_seed) < 30,
                             views=int(len(per_view)), reset_used={str(r): int((z['seed_reset'][sk] == r).sum()) for r in sorted(set(z['seed_reset'][sk].tolist()))},
                             dL_pix_per_view_q=q4(per_view), view_removal_worse_pct=pct(per_view > 0) if len(per_view) else None, view_removal_better_pct=pct(per_view < 0) if len(per_view) else None,
                             view_no_change_pct=pct(per_view == 0) if len(per_view) else None, dL_pix_per_seed_sum_q=q4(per_seed), seed_removal_worse_pct=pct(per_seed > 0) if len(per_seed) else None,
                             rule='dL = loss(seed removed) - loss(as dumped), training photo loss 0.8 L1 + 0.2 (1-SSIM), x H*W; > 0: removing the seed moves the render away from the photo'))
    table5('ma_photo', rows); print('MA_PHOTO_TABLE', len(rows), flush=True)

if __name__ == '__main__':
    a = sys.argv[1:]
    {'run': lambda: run(*a[1:]), 'tables': tables}[a[0]]()
