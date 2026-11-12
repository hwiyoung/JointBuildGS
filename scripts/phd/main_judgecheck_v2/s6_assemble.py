"""참값 점 표 조립 (평가 전용; 판정은 이미 저장됨). 사전 정보마다 analysis/gt_<prior>.npz.
열: 출처(0 나머지, 1 실험 지역 저장 행), 좌표, 법선, 참값 종류(1 지붕 2 벽 3 땅), s_P, s_M, τ, 상태(0 맞음 1 틀림 2 없음) 둘, 아홉 조합 번호, 지금 정의 경우,
짝 패치(구역, 차례), 건물, 탐색 지역, 묶음, 자리, 무늬 없음, 판(VARIANTS)마다 판정·목표 거리·목표 맞음, 민감도 판마다 본 방법 판정·목표 맞음, 넓이 칸 열쇠.
실험 지역 저장 행: 지금 판 판정·목표 맞음, FINALTRAIN 30,000회와 판단만으로 만든 면의 τ 안 여부."""
from common import *
import jc2_judge as J
from s4_truth_exp import plane_distance
SENS = ['ring_1.0', 'ring_3.0', 'z_1.645', 'z_2.576', 'centre_shift', 'building_r', 'same_face_ring']
def cases_nine(sP, sM, tau):
    stP = np.where(~np.isfinite(sP), 2, np.where(np.abs(sP) <= tau, 0, 1)).astype(np.int8); stM = np.where(~np.isfinite(sM), 2, np.where(np.abs(sM) <= tau, 0, 1)).astype(np.int8)
    nine = (3*stP + stM).astype(np.int8)
    p = stP == 0; m = stM == 0; cur = np.full(len(sP), 3, np.int8); cur[p & m] = 0; cur[~p & m] = 1; cur[p & ~m] = 2; cur[p & (stM == 2)] = 4   # GTJUDGE normal_line.cases
    return stP, stM, nine, cur
def cellkey(xyz, normal_patch, kind_wall, surf):
    """0.25 m 넓이 칸: 지붕·땅 수평 (x,y), 벽 = 면마다 (s,z)."""
    k = np.zeros(len(xyz), np.int64); r = ~kind_wall
    ix = np.floor(xyz[r, 0]/.25).astype(np.int64) + 4000; iy = np.floor(xyz[r, 1]/.25).astype(np.int64) + 4000; k[r] = ix*10000 + iy
    if kind_wall.any():
        nh = normal_patch[kind_wall, :2]; nh = nh/np.maximum(np.linalg.norm(nh, axis=1, keepdims=True), 1e-12); t = np.c_[-nh[:, 1], nh[:, 0]]
        s = (xyz[kind_wall, :2]*t).sum(1); iz = np.floor(xyz[kind_wall, 2]/.25).astype(np.int64) + 4000; isx = np.floor(s/.25).astype(np.int64) + 4000
        k[kind_wall] = (10**9 + surf[kind_wall].astype(np.int64))*10**8 + isx*10000 + iz
    return k
def main(prior):
    cfg(); T = Timer(); tau = json.loads((O/'stage0/tau.json').read_text())['values']
    B = {r['building']: r for r in json.loads((O/'stage0/buildings.json').read_text())['rows'] if r['in_scope']}
    # 패치 찾기표
    tiles_ = [p.stem.split('__')[0] for p in sorted((O/'geometry_raw').glob(f'*__{prior}.npz'))]; look = {}; PT = {}
    for t in tiles_:
        g = loadz(O/'geometry_raw'/f'{t}__{prior}.npz', ['patch_id', 'centre', 'normal', 'kind', 'surf', 'area', 'building', 'region', 'prior_height_m', 'mvs_mean_m', 'n', 'roof_type'])
        jb = loadz(O/'judge/base'/f'{t}__{prior}.npz', ['region', 'reason', 'target_h', 'photo_code', 'photo_point']); jb['j_region'] = jb.pop('region'); jb['j_reason'] = jb.pop('reason')
        pl = loadz(O/'place'/f'{t}__{prior}.npz', ['place', 'face']); tx = loadz(O/'texture'/f'{t}__{prior}.npz', ['textureless'])
        g.update(jb); g['place'] = pl['place']; g['face'] = pl['face']; g['textureless'] = tx['textureless']
        for v in SENS:
            p = O/'judge'/v/f'{t}__{prior}.npz'
            if p.exists(): z = loadz(p, ['region', 'target_h']); g[f'sens_{v}_region'] = z['region'][J.VARIANTS.index('method')]; g[f'sens_{v}_h'] = z['target_h'][J.VARIANTS.index('method')]
        PT[t] = g
        for i, s in enumerate(g['patch_id']): look[s] = (t, i)
    rows = []
    # 나머지
    for t in tiles_:
        p = O/'truth/rest'/f'{t}.npz'
        if not p.exists(): continue
        z = loadz(p); k = f'{prior}__'
        if k + 'xyz' not in z: continue
        n = len(z[k + 'xyz']); rows.append(dict(src=np.zeros(n, np.int8), site=np.full(n, ''), tile=np.full(n, t), xyz=z[k + 'xyz'], normal=z[k + 'normal'], gt_kind=z[k + 'gt_kind'], hag=z[k + 'hag'], s_P=z[k + 's_P'], s_M=z[k + 's_M'],
                                    patch_id=z[k + 'patch_id'], current_region=np.full(n, -1, np.int8), current_target_distance=np.full(n, np.nan), finaltrain_s=np.full(n, np.nan), judgment_mesh_s=np.full(n, np.nan), tau_stored=np.full(n, np.nan), case_stored=np.full(n, -1, np.int8)))
    # 실험 지역
    for site in SITES:
        z = loadz(O/'truth/exp'/f'{site}__{prior}.npz'); n = len(z['xyz'])
        rows.append(dict(src=np.ones(n, np.int8), site=np.full(n, site), tile=np.full(n, ''), xyz=z['xyz'], normal=z['normal'], gt_kind=z['gt_kind'], hag=z['hag'], s_P=z['s_P'].astype(float), s_M=z['s_M'].astype(float), patch_id=z['patch_id'],
                         current_region=z['current_region'], current_target_distance=z['current_target_distance'], finaltrain_s=z['finaltrain_s'].astype(float), judgment_mesh_s=z['judgment_mesh_s'].astype(float), tau_stored=z['tau'], case_stored=z['case_stored'].astype(np.int8)))
    d = {k: np.concatenate([r[k] for r in rows]) for k in rows[0]}; N = len(d['xyz'])
    pt = np.array([look.get(s, ('', -1))[0] for s in d['patch_id']]); pi = np.array([look.get(s, ('', -1))[1] for s in d['patch_id']], np.int64); paired = pi >= 0
    def col(name, fill, dtype=None):
        out = np.full(N, fill, dtype=dtype or np.asarray(fill).dtype if not isinstance(fill, str) else '<U40')
        for t in tiles_:
            m = paired & (pt == t)
            if m.any(): out[m] = PT[t][name][pi[m]]
        return out
    d['paired'] = paired; d['patch_tile'] = pt; d['patch_index'] = pi
    d['building'] = col('building', ''); d['region'] = col('region', ''); pk = col('kind', 0, np.int8); d['patch_kind'] = pk
    d['group'] = np.array([B[b]['group'] if b in B else '' for b in d['building']]); d['old_split'] = np.array([B[b]['old_split'] if b in B else '' for b in d['building']])
    d['place'] = col('place', -1, np.int8); d['textureless'] = col('textureless', -1, np.int8); d['photo_code'] = col('photo_code', 9, np.int8); d['roof_type'] = col('roof_type', '')
    d['surf'] = col('surf', -1, np.int64); d['face'] = col('face', -1, np.int64)
    key = np.where(pk == 2, '_wall', '_roof'); tv = np.array([tau.get(r if r else 'none', tau['none'])[prior + kk] if paired[i] else np.nan for i, (r, kk) in enumerate(zip(d['region'], key))]) if prior == 'LoD2' else \
        np.array([tau.get(r if r else 'none', tau['none'])['ALS_roof'] if paired[i] else np.nan for i, r in enumerate(d['region'])])
    tv = np.where((d['src'] == 1) & np.isfinite(d['tau_stored']), d['tau_stored'], tv)   # 세 실험 지역 저장 행은 저장된 τ (덱과 같은 값)
    d['tau'] = tv
    d['state_P'], d['state_M'], d['nine'], d['case'] = cases_nine(d['s_P'], d['s_M'], tv)
    pc = np.full((N, 3), np.nan); pn = pc.copy()
    for t in tiles_:
        m = paired & (pt == t)
        if m.any(): pc[m] = PT[t]['centre'][pi[m]]; pn[m] = PT[t]['normal'][pi[m]]
    wall = d['gt_kind'] == 2
    reg = np.full((len(J.VARIANTS), N), -1, np.int8); why = reg.copy(); tdist = np.full((len(J.VARIANTS), N), np.nan)
    for t in tiles_:
        m = np.flatnonzero(paired & (pt == t))
        if not len(m): continue
        g = PT[t]; reg[:, m] = g['j_region'][:, pi[m]]; why[:, m] = g['j_reason'][:, pi[m]]
        for j in range(len(J.VARIANTS)): tdist[j, m] = plane_distance(d['xyz'][m], d['normal'][m], pc[m], pn[m], g['target_h'][j, pi[m]], wall[m])
    d['region_v'] = reg; d['reason_v'] = why; d['target_distance_v'] = tdist
    d['target_ok_v'] = np.abs(tdist) <= tv[None, :]
    for v in SENS:
        if f'sens_{v}_region' not in PT[tiles_[0]]: continue
        r2 = np.full(N, -1, np.int8); td = np.full(N, np.nan)
        for t in tiles_:
            m = np.flatnonzero(paired & (pt == t))
            if len(m): r2[m] = PT[t][f'sens_{v}_region'][pi[m]]; td[m] = plane_distance(d['xyz'][m], d['normal'][m], pc[m], pn[m], PT[t][f'sens_{v}_h'][pi[m]], wall[m])
        d[f'sens_{v}_region'] = r2; d[f'sens_{v}_target_ok'] = np.abs(td) <= tv
    d['current_target_ok'] = np.abs(d['current_target_distance']) <= np.where(np.isfinite(d['tau_stored']), d['tau_stored'], tv)
    d['finaltrain_ok'] = np.abs(d['finaltrain_s']) <= d['tau_stored']; d['judgment_mesh_ok'] = np.abs(d['judgment_mesh_s']) <= d['tau_stored']
    d['cell'] = cellkey(d['xyz'], pn, pk == 2, d['surf'])
    # 패치 다수결 (지금 정의 경우)
    gid = np.full(N, -1, np.int64); off = {}; base = 0
    for t in tiles_: off[t] = base; base += len(PT[t]['patch_id'])
    gid[paired] = np.array([off[t] for t in pt[paired]]) + pi[paired]
    Mreg = np.concatenate([PT[t]['j_region'][J.VARIANTS.index('method')] for t in tiles_]); U = np.concatenate([loadz(O/'geometry/base'/f'{t}__{prior}.npz', ['u_M'])['u_M'] for t in tiles_]); HM = np.concatenate([PT[t]['mvs_mean_m'] for t in tiles_])
    orc, counts = J.oracle(Mreg, d['case'], gid, U, HM)
    j = J.VARIANTS.index('oracle'); reg[j, paired] = orc[gid[paired]]
    Hp = np.concatenate([PT[t]['prior_height_m'] for t in tiles_]); SP = np.concatenate([loadz(O/'geometry/base'/f'{t}__{prior}.npz', ['sigma_P'])['sigma_P'] for t in tiles_]); SW = float(json.loads((O/'calib/base.json').read_text())['sigma_W_m'])
    Ho = J.target_height(orc, Hp, HM, U, SP, np.full(len(U), SW))
    tdist[j, paired] = plane_distance(d['xyz'][paired], d['normal'][paired], pc[paired], pn[paired], Ho[gid[paired]], wall[paired]); d['target_ok_v'][j] = np.abs(tdist[j]) <= tv
    maj = np.full(len(Mreg), -1, np.int8); has = counts.sum(1) > 0; maj[has] = counts[has].argmax(1); d['patch_majority_case'] = np.where(paired, maj[np.maximum(gid, 0)], -1)
    d['gid'] = gid; d['region_v'] = reg; d['target_distance_v'] = tdist
    savez(O/'analysis'/f'gt_{prior}.npz', **d)
    savez(O/'analysis'/f'patches_{prior}.npz', gid_offset_tiles=np.array(tiles_), gid_offsets=np.array([off[t] for t in tiles_]), oracle_region=orc, majority_counts=counts)
    dump(O/'analysis'/f'gt_{prior}.json', dict(at=now(), prior=prior, rows=N, paired=int(paired.sum()), by_src={str(s): int((d['src'] == s).sum()) for s in [0, 1]}, seconds=T.mark('end'), scientific_verdict=None))
    print('ASSEMBLE', prior, N, int(paired.sum()), round(T.mark('end')), flush=True)
if __name__ == '__main__': main(sys.argv[1])
