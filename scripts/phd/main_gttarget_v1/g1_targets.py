"""Stage 1 (order 3.2-3.3): GT target file (FINALTRAIN schema) and seeds per scene.
usage (CPU container): g1_targets.py <stem>
writes /gt/targets/<stem>.npz (+ .json) and /gt/stage1/<stem>/seeds.npz (+ seed_receipt.json)"""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_gttarget_v1'); sys.path.insert(0, '/repo')
from gt_common import *
from scipy.spatial import cKDTree
from plyfile import PlyData
from src.phd.prior_propagation_v6.orientation import quat_from_normal

def main(stem):
    c = cfg(1); site, prior = stem.split('__'); p = loadz(O/'surface'/site/'patches.npz'); N = len(p['area'])
    ft = loadz(FT/'targets'/f'{stem}.npz'); ref = float(ft['sigma_ref']); ft_keys = set(ft)
    sig = np.full(N, ref); z = np.zeros(N)
    t = dict(centre=p['centre'], normal=p['normal'], kind=p['kind'].astype('i1'), area=p['area'], in_eval=np.ones(N, bool),
             source_index=np.arange(N), patch_id=np.array([f'GT:{site}:{i}' for i in range(N)]), n=np.full(N, -1), u_mvs=np.full(N, np.nan),
             sigma_P_m=np.full(N, np.nan), prior_height_m=z.copy(), mvs_mean_m=np.full(N, np.nan), photo_code=np.full(N, 9, 'i1'),
             judge_region=np.full(N, c['targets']['judge_region_code'], 'i1'), reason=np.full(N, 9, 'i1'), region=np.full(N, c['targets']['region_code'], 'i1'),
             h=z.copy(), sigma=sig, target=p['centre'].copy(), target_height_m=z.copy(), target_sigma_m=sig.copy(), undecided_before=np.zeros(N, bool),
             sigma_replaced=np.zeros(N, bool), surface_exists=np.ones(N, bool), sigma_ref=np.asarray(ref), correction_u_median=np.asarray(np.nan),
             any_replaced=np.zeros(N, bool), gt_surface=p['surf'], gt_extra=p['extra'])
    assert ft_keys <= set(t), ft_keys-set(t)
    for k in ft_keys: assert np.asarray(t[k]).dtype.kind == np.asarray(ft[k]).dtype.kind or k in ('n',), (k, t[k].dtype, ft[k].dtype)
    tp = O/'targets'/f'{stem}.npz'; savez(tp, **t)
    active = t['surface_exists']; check_ref = float(t['area'][active].sum()/np.sum(t['area'][active]/t['sigma'][active])); assert abs(check_ref-ref) < 1e-12
    dump(tp.with_suffix('.json'), dict(at=now(), stem=stem, title=TITLE, patches=N, sigma_ref=ref, sigma_ref_source=str(FT/'targets'/f'{stem}.npz'),
        sha256=sha(tp), surface_receipt=json.loads((O/'surface'/site/'receipt.json').read_text()), region_code=c['targets']['region_code'],
        GT_used_as_target=True, scientific_verdict=None))
    # seeds: GT patch seeds first (origin 1; scale/colour/opacity of the nearest prior SfM row, r8 keep_original rule), then FINALTRAIN background as is
    fs = loadz(FT/'stage1'/stem/'seeds.npz'); bgm = fs['origin'] == 0
    src = S0/'fork_inputs/s61'/site/f'scene_{prior}/sparse/0'; v = PlyData.read(str(src/'points3D.ply'))['vertex']; xyz = np.c_[v['x'], v['y'], v['z']].astype('f4')
    assert np.array_equal(xyz, fs['original_xyz'])
    origin = np.load(src/'origin.npy'); seat = np.load(S0/'fork_inputs/s61'/site/f'seat_{prior}.npy'); prior_rows = np.flatnonzero((origin == 1) & (seat >= 0))
    d, j = cKDTree(xyz[prior_rows].astype('f8')).query(p['centre'], workers=16); keep = prior_rows[j]
    q = quat_from_normal(p['normal']).astype('f4')
    seeds = dict(original_xyz=fs['original_xyz'], keep_original=keep.astype('i8'),
                 xyz=np.r_[p['centre'].astype('f4'), fs['xyz'][bgm]], target=np.r_[p['centre'].astype('f4'), fs['target'][bgm]],
                 normal=np.r_[p['normal'].astype('f4'), fs['normal'][bgm]], sigma=np.r_[sig.astype('f4'), fs['sigma'][bgm]],
                 quaternion=np.r_[q, fs['quaternion'][bgm]], origin=np.r_[np.ones(N, 'i1'), fs['origin'][bgm]],
                 region=np.r_[t['region'], fs['region'][bgm]], patch=np.r_[np.arange(N), fs['patch'][bgm]],
                 background_rgb=fs['background_rgb'], background_original=fs['background_original'],
                 uncertainty_replaced=np.r_[np.zeros(N, bool), fs['uncertainty_replaced'][bgm]])
    assert int(bgm.sum()) == len(fs['background_rgb']) and np.all(np.flatnonzero(bgm) == np.arange(len(fs['origin'])-int(bgm.sum()), len(fs['origin'])))
    root = O/'stage1'/stem; savez(root/'seeds.npz', **seeds)
    bgxyz = fs['xyz'][bgm].astype('f8'); dn, _ = cKDTree(p['centre']).query(bgxyz, distance_upper_bound=c['seeds']['near_background_m'], workers=16); near = np.isfinite(dn)
    rec = dict(at=now(), stem=stem, title=TITLE, gt_seeds=N, background_seeds=int(bgm.sum()), seeds_total=len(seeds['origin']),
        seedless_valid_patches=int(N-len(np.unique(seeds['patch'][seeds['origin'] == 1]))), prior_sfm_rows=int(len(prior_rows)),
        donor_distance_m_q10_q50_q90_max=np.r_[np.quantile(d, [.1, .5, .9]), d.max()].tolist(), donor_rows_unique=int(len(np.unique(keep))),
        background_within_0p3m_of_gt_patch=int(near.sum()), background_within_0p3m_fraction=float(near.mean()),
        rule=c['seeds'], seeds_sha256=sha(root/'seeds.npz'), target_sha256=sha(tp), scientific_verdict=None)
    dump(root/'seed_receipt.json', rec); print('TARGETS_SEEDS', stem, json.dumps({k: rec[k] for k in ['gt_seeds', 'background_seeds', 'seedless_valid_patches', 'donor_distance_m_q10_q50_q90_max', 'background_within_0p3m_fraction']}), flush=True)

if __name__ == '__main__': main(sys.argv[1])
