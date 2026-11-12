"""50 cm 사진 점 (2x2 패치 묶음). 지붕 PHOTOCHECK-v1, LoD2 벽 WALLPHOTO-v1 의 대응(geometry/*__mapping.npz, 개발용+확인용)을 잇고,
잇지 못한 패치만 PHOTOCHECK-v1 prepare.group (상속, 바이트 같음)으로 새로 묶는다. 묶음은 WIDEN0 좌표에서 하고, 사진 점 중심은
구성 패치의 (이 작업 중심 - WIDEN0 중심)만큼 옮긴다. 참값 읽지 않음."""
from common import *
from inherit import functions
ROOT = {1: PC, 2: WP}
def group_fn(tile):
    env = dict(np=np, W=W, sigmas=lambda d, p: (np.zeros(len(d['centre'])), np.zeros(len(d['centre']))))
    functions('main_photocheck_v1__prepare.py', ['group'], env); return env['group']
def main(tile):
    cfg(); T = Timer()
    for prior in ['LoD2', 'ALS']:
        src = O/'geometry_raw'/f'{tile}__{prior}.npz'; dest = O/'photo_groups'/f'{tile}__{prior}.npz'
        if not src.exists() or dest.exists(): continue
        d = loadz(src, ['patch_id', 'kind', 'surf', 'building', 'area', 'centre', 'widen0_centre', 'normal', 'old_normal', 'tangent1', 'tangent2', 'source_extra', 'holdout', 'region'])
        N = len(d['kind']); owner = np.full(N, -1, np.int64); rows = []; srcs = []
        for kind in [1, 2]:
            if prior == 'ALS' and kind == 2: continue
            for split in ['', 'holdout/']:
                mp = ROOT[kind]/f'{split}geometry'/f'{tile}__{prior}__mapping.npz'; gp = ROOT[kind]/f'{split}geometry'/f'{tile}__{prior}.npz'
                if not mp.exists(): continue
                m = loadz(mp, ['patch_id', 'point_index', 'kind']); g = loadz(gp, ['point_id', 'kind', 'surf', 'building', 'centre', 'normal', 'tangent1', 'tangent2', 'geometry_valid'])
                pos = {s: i for i, s in enumerate(d['patch_id'])}
                sel = (m['kind'] == kind); pids = m['patch_id'][sel]; pidx = m['point_index'][sel]
                have = np.array([s in pos for s in pids], bool); pids, pidx = pids[have], pidx[have]
                ix = np.array([pos[s] for s in pids], np.int64)
                ok = (d['kind'][ix] == kind) & (owner[ix] < 0); ix, pidx = ix[ok], pidx[ok]
                uniq, inv = np.unique(pidx, return_inverse=True); base = len(rows)
                for j, q in enumerate(uniq):
                    rows.append(dict(point_id=str(g['point_id'][q]), kind=int(g['kind'][q]), surf=int(g['surf'][q]), building=str(g['building'][q]), centre=g['centre'][q], normal=g['normal'][q],
                                     tangent1=g['tangent1'][q], tangent2=g['tangent2'][q], geometry_valid=bool(g['geometry_valid'][q]), source=f'{ROOT[kind].name}/{split}geometry'))
                owner[ix] = base + inv; srcs.append(dict(path=str(mp), sha256=sha(mp), patches=int(len(ix)), points=int(len(uniq))))
        miss = np.flatnonzero(owner < 0); created = 0
        if len(miss):
            inp = {k: d[k][miss] for k in ['kind', 'surf', 'building', 'area', 'tangent1', 'tangent2', 'source_extra', 'holdout']}
            inp['centre'] = d['widen0_centre'][miss]; inp['normal'] = d['old_normal'][miss]
            grp, own, audit = group_fn(tile)(inp, prior, tile); base = len(rows)
            for i in range(len(grp['point_id'])):
                rows.append(dict(point_id=f'new:{prior}:{tile}:{i}', kind=int(grp['kind'][i]), surf=int(grp['surf'][i]), building=str(grp['building'][i]), centre=grp['centre'][i], normal=grp['normal'][i],
                                 tangent1=grp['tangent1'][i], tangent2=grp['tangent2'][i], geometry_valid=bool(grp['geometry_valid'][i]), source='[이 발주에서 냄] PHOTOCHECK-v1 group rule'))
            owner[miss] = base + own; created = len(grp['point_id'])
        P = len(rows); off = d['centre'] - d['widen0_centre']
        g = {k: np.array([r[k] for r in rows]) for k in rows[0]}
        osum = np.zeros((P, 3)); np.add.at(osum, owner, off); cnt = np.bincount(owner, minlength=P); g['offset_m'] = osum/cnt[:, None]
        g['centre_widen0'] = g['centre']; g['centre'] = g['centre'] + g['offset_m']
        g['area'] = np.bincount(owner, weights=d['area'], minlength=P); g['patch_count'] = cnt
        fi = np.full(P, -1); fi[owner[::-1]] = np.arange(N)[::-1]; g['region'] = d['region'][fi]
        sf = d['surf'][fi]; g['mixed_member_surface'] = np.bincount(owner, weights=(d['surf'] != sf[owner]).astype(float), minlength=P) > 0
        g['point_uid'] = np.array([f'{prior}:{tile}:{k}:{s}:{p}' for k, s, p in zip(g['kind'], g['source'], g['point_id'])])
        savez(dest, patch_point=owner, patch_id=d['patch_id'], **g)
        rec = dict(at=now(), tile=tile, prior=prior, patches=N, points=P, created_points=created, created_patches=int(len(miss)), mixed_member_surface=int(g['mixed_member_surface'].sum()), sources=srcs, seconds=T.mark(prior), GT_read=False, scientific_verdict=None)
        dump(dest.with_suffix('.json'), rec); print('PHOTO_GROUPS', json.dumps({k: rec[k] for k in ['tile', 'prior', 'patches', 'points', 'created_points', 'created_patches', 'mixed_member_surface']}), flush=True)
if __name__ == '__main__':
    for t in sys.argv[1:]: main(t)
