"""세 실험 지역의 참값 행 (발주 2.3: 저장된 GTJUDGE 사전 정보 면·MVS 면·거리 다시 씀). 참값은 평가에만.
- 행: GTJUDGE scenes/<site>__<prior>/rows.npz (xyz, normal, row_kind, row_owner = JUDGEAPPLY 핵심점 차례), distances/prior.npz·mvs.npz row_s.
- 본값 패치와의 짝: RESCORE 기둥 규칙(prism.cpp) - 벽 행 ↔ 벽 패치, 지붕 행 ↔ 지붕 패치 (s4_truth_rest 와 같음).
- 지금 판: row_owner → JUDGEAPPLY patch_id → FINALTRAIN targets (judge_region, target_height_m, centre, normal).
- 학습 뒤: distances/FINALTRAIN_30000.npz, judgment_mesh.npz row_s 의 |s| <= τ."""
from common import *
import s4_truth_rest as TR
SITE_REGION = {'B0_b10': 'B0', 'B173nb_b10': 'R2', 'R1rep_b10': 'R1'}
def plane_distance(x, g, c, n, h, wall):
    """참값 점 x 에서 법선 g 를 따라 목표 면(c + h n 을 지나고 n 에 수직)까지의 부호 있는 거리; 범위 밖·평행·목표 없음 = NaN."""
    p0 = c + h[:, None]*n; den = np.einsum('ij,ij->i', g, n)
    with np.errstate(divide='ignore', invalid='ignore'): t = np.einsum('ij,ij->i', p0 - x, n)/den
    lim = np.where(wall, 5., 10.); t[~np.isfinite(h) | (np.abs(den) < 1e-9) | (np.abs(t) > lim)] = np.nan
    return t
def main():
    cfg(); T = Timer(); Dg = dict(np.load(TR.SURVEY/'derived.npz')); dtm = Dg['dtm'].astype(float)
    for site in SITES:
        for prior in ['LoD2', 'ALS']:
            dest = O/'truth/exp'/f'{site}__{prior}.npz'
            if dest.exists(): continue
            sc = GJ/'scenes'/f'{site}__{prior}'; r = loadz(sc/'rows.npz', ['xyz', 'normal', 'row_kind', 'row_owner', 'row_tau_m', 'wall'])
            cell = loadz(sc/'stage1_cells.npz', ['case_id', 'prior_absent']); X = r['xyz']; Nm = r['normal']; wall = r['row_kind'] == 2
            sP = loadz(sc/'distances/prior.npz', ['row_s'])['row_s']; sM = loadz(sc/'distances/mvs.npz', ['row_s'])['row_s']
            ft = loadz(sc/'distances/FINALTRAIN_30000.npz', ['row_s'])['row_s']; jm = loadz(sc/'distances/judgment_mesh.npz', ['row_s'])['row_s']
            E = X[:, 0] + 690953.0; N = X[:, 1] + 5336071.0; ix = np.floor((E - 690700.0)/0.5).astype(int); iy = np.floor((N - 5335820.0)/0.5).astype(int)
            ok = (ix >= 0) & (iy >= 0) & (ix < dtm.shape[1]) & (iy < dtm.shape[0]); zd = np.full(len(X), np.nan); zd[ok] = dtm[iy[ok], ix[ok]] - 604.0; hag = X[:, 2] - zd
            gk = np.where(wall, 2, np.where(np.isfinite(hag) & (hag <= .5), 3, 1)).astype(np.int8)
            # 본값 패치(모든 구역)와 기둥 규칙
            lo = X[:, :2].min(0); hi = X[:, :2].max(0); P = []
            for q in sorted((O/'geometry_raw').glob(f'*__{prior}.npz')):
                z = loadz(q, ['patch_id', 'centre', 'normal', 'tangent1', 'tangent2', 'kind', 'prior_height_m', 'building', 'region'])
                m = ((z['centre'][:, :2] >= lo - 12) & (z['centre'][:, :2] <= hi + 12)).all(1)
                if m.any(): P.append({k: v[m] for k, v in z.items()})
            p = {k: np.concatenate([x[k] for x in P]) for k in P[0]}; n = p['normal'].astype(float); a = p['tangent1'].astype(float); b = p['tangent2'].astype(float)
            if prior == 'ALS':
                for i in np.flatnonzero(np.isfinite(n).all(1)):
                    e = np.array([1., 0., 0.]) if abs(n[i, 0]) < .9 else np.array([0., 1., 0.]); e = e - n[i]*(e@n[i]); e /= np.linalg.norm(e); a[i] = e; b[i] = np.cross(n[i], e)
            c = p['centre'] + np.nan_to_num(p['prior_height_m'])[:, None]*n; length = np.where(p['kind'] == 1, 10., 5.)
            owner = np.full(len(X), -1, np.int64); hits = np.zeros(len(X), np.int32)
            for kind, gm in [(1, ~wall), (2, wall)]:
                pm = np.flatnonzero(p['kind'] == kind); qi = np.flatnonzero(gm)
                if not len(pm) or not len(qi): continue
                o, h = TR.prism(X[qi], c[pm], a[pm], b[pm], n[pm], length[pm], O/'tmp'/f'prism_exp_{site}_{prior}_{kind}')
                owner[qi[o >= 0]] = pm[o[o >= 0]]; hits[qi] = h
            pid = np.where(owner >= 0, p['patch_id'][np.maximum(owner, 0)], '')
            # 지금 판
            core = loadz(JA/'core_points'/f'{site}__{prior}.npz', ['patch_id']); f = loadz(FT/'targets'/f'{site}__{prior}.npz', ['patch_id', 'judge_region', 'reason', 'target_height_m', 'centre', 'normal', 'in_eval'])
            pos = {s: i for i, s in enumerate(f['patch_id'])}; ro = r['row_owner']; has = (ro >= 0) & (ro < len(core['patch_id']))
            fi = np.full(len(X), -1); fi[has] = [pos[s] for s in core['patch_id'][ro[has]]]
            cur_reg = np.where(fi >= 0, f['judge_region'][np.maximum(fi, 0)], -1).astype(np.int8)
            cur_t = np.full(len(X), np.nan); m = fi >= 0
            cur_t[m] = plane_distance(X[m], Nm[m], f['centre'][fi[m]], f['normal'][fi[m]], f['target_height_m'][fi[m]], wall[m])
            tau = r['row_tau_m']
            savez(dest, xyz=X, normal=Nm, row_kind=r['row_kind'], gt_kind=gk, hag=hag, s_P=sP, s_M=sM, tau=tau, case_stored=cell['case_id'], prior_absent_stored=cell['prior_absent'],
                  patch_id=pid, building=np.where(owner >= 0, p['building'][np.maximum(owner, 0)], ''), region=np.where(owner >= 0, p['region'][np.maximum(owner, 0)], SITE_REGION[site]), hits=hits,
                  current_patch_id=np.where(has, core['patch_id'][np.where(has, ro, 0)], ''), current_region=cur_reg, current_target_distance=cur_t,
                  finaltrain_s=ft, judgment_mesh_s=jm, site=np.full(len(X), site))
            print('TRUTH_EXP', site, prior, len(X), int((owner >= 0).sum()), int((fi >= 0).sum()), round(T.mark(site+prior)), flush=True)
    dump(O/'truth/exp/complete.json', dict(at=now(), seconds=T.mark('end'), scientific_verdict=None))
if __name__ == '__main__': main()
