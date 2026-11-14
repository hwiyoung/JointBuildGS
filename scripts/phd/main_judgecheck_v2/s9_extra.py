"""8절 열 덧붙이기(11/15): 내보낸 점 파일에 빠졌던 열을 같은 계산으로 다시 만들어 덧붙인다.
- gt_points/<탐색 지역>__<사전 정보>.npz: cluster_id·geometry_type(네 경우 밖인 점, 1 m2 미만 모임은 유형 빈칸), true_error·error_rule·patch_case_mixed(6.3, s8_checks.point_rules).
- core_points/<탐색 지역>__<사전 정보>.npz: nogt_cluster_id·nogt_geometry_type(기둥 안 참값이 없는 패치).
모임은 s7_clusters 와 같은 차례(건물 차례, 0.6 m 잇기)로 다시 만들고 analysis/clusters.csv 의 줄(건물·점 수·중심)과 하나씩 맞는지 확인한 뒤 번호를 붙인다. 맞지 않으면 멈춘다.
  s9_extra.py"""
from common import *
import pandas as pd
import jc2_judge as J
import s7_clusters as SC
import s8_checks as S8
from s7_tables import truth_hits
def check(rows, got, what):
    assert len(rows) == len(got), (what, len(rows), len(got))
    for r, (n, cx, cy) in zip(rows.itertuples(index=False), got):
        assert int(r.n) == n and abs(r.centre_x - cx) < 1e-6 and abs(r.centre_y - cy) < 1e-6, (what, r.cluster_id, r.n, n)
def main():
    cfg(); T = Timer(); C = pd.read_csv(O/'analysis/clusters.csv', usecols=['cluster_id', 'prior', 'cluster_source', 'building', 'n', 'centre_x', 'centre_y', 'geometry_type', 'size'], low_memory=False)
    C['geometry_type'] = C['geometry_type'].fillna(''); allv = ['base']; rec = {}
    for prior in ['LoD2', 'ALS']:
        d = loadz(O/'analysis'/f'gt_{prior}.npz'); N = len(d['src']); paired = d['paired']
        # 참값 점 모임
        cid = np.full(N, -1, np.int64); gtype = np.full(N, '', dtype='<U24'); Cg = C[(C.prior == prior) & (C.cluster_source == '참값 점')]
        out4 = np.flatnonzero(paired & (d['nine'] >= 4))
        for b in sorted(set(d['building'][out4])):
            ix = out4[d['building'][out4] == b]; k, lab = SC.components(d['xyz'][ix]); rows = Cg[Cg.building == b]
            got = [(int((lab == c).sum()), float(d['xyz'][ix[lab == c], 0].mean()), float(d['xyz'][ix[lab == c], 1].mean())) for c in range(k)]; check(rows, got, f'{prior} gt {b}')
            for c, r in zip(range(k), rows.itertuples(index=False)): m = ix[lab == c]; cid[m] = r.cluster_id; gtype[m] = r.geometry_type
        # 진짜 판정 오류와 생긴 규칙
        P = S8.patches(prior, allv); cols, ok = S8.gt_patch_cols(d, P, prior, ['base:geometry', 'base:photo_code', 'n', 'base:u_M'])
        nou = (cols['n'] >= 4) & (cols['base:geometry'] == 9) & ~np.isfinite(cols['base:u_M'])
        four, name_wrong, tgt_wrong, rule, mixed = S8.point_rules(d, cols, nou); te = four & name_wrong & tgt_wrong
        erule = np.where(four & name_wrong, rule, '')
        # 내보낸 참값 점 파일에 덧붙임
        nfile = 0
        for p in sorted((O/'gt_points').glob(f'*__{prior}.npz')):
            if p.name.startswith('unpaired__'): continue
            z = loadz(p); rn = z['row_number']
            z.update(cluster_id=cid[rn], geometry_type=gtype[rn], true_error=te[rn], error_rule=erule[rn], patch_case_mixed=(mixed & paired)[rn]); savez(p, **z); nfile += 1
        # 참값 없는 패치 모임
        PA = SC.patch_arrays(prior); look = {s: i for i, s in enumerate(PA['patch_id'])}; gpid = np.full(N, -1); gpid[paired] = [look[s] for s in d['patch_id'][paired]]
        has = np.zeros(len(PA['patch_id']), bool); has[np.unique(gpid[paired])] = True; has |= truth_hits(prior, PA['patch_id']); nog = np.flatnonzero(~has)
        pcid = np.full(len(PA['patch_id']), -1, np.int64); ptype = np.full(len(PA['patch_id']), '', dtype='<U24'); Cp = C[(C.prior == prior) & (C.cluster_source == '참값 없는 패치')]
        for b in sorted(set(PA['building'][nog])):
            ix = nog[PA['building'][nog] == b]; k, lab = SC.components(PA['centre'][ix]); rows = Cp[Cp.building == b]
            got = [(int((lab == c).sum()), float(PA['centre'][ix[lab == c], 0].mean()), float(PA['centre'][ix[lab == c], 1].mean())) for c in range(k)]; check(rows, got, f'{prior} patch {b}')
            for c, r in zip(range(k), rows.itertuples(index=False)): m = ix[lab == c]; pcid[m] = r.cluster_id; ptype[m] = r.geometry_type
        pl = {s: i for i, s in enumerate(PA['patch_id'])}; ncore = 0
        for p in sorted((O/'core_points').glob(f'*__{prior}.npz')):
            z = loadz(p); ii = np.array([pl[s] for s in z['patch_id']]); z.update(nogt_cluster_id=pcid[ii], nogt_geometry_type=ptype[ii]); savez(p, **z); ncore += 1
        rec[prior] = dict(gt_files=nfile, core_files=ncore, gt_points_in_cluster=int((cid >= 0).sum()), gt_clusters=int(len(np.unique(cid[cid >= 0]))), true_error_points=int(te.sum()),
                          nogt_patches=int(len(nog)), nogt_clusters=int(len(np.unique(pcid[pcid >= 0]))))
        print('EXTRA', prior, json.dumps(rec[prior], ensure_ascii=False), round(T.mark(prior)), flush=True)
    dump(O/'analysis/export_extra.json', dict(at=now(), seconds=T.mark('end'), records=rec, rule=__doc__, scientific_verdict=None))
if __name__ == '__main__': main()
