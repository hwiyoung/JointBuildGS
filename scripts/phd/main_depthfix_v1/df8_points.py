"""Order 5: GT point groups, fixed once from the 판 0 target and used for every arm (CPU). usage: df8_points.py <stem>
Points = WRONGTARGET-v1 / TRAINERR addendum 2 set (ra_<stem>__own: addendum11 eligible rows, 300,000 fixed sample for the large LoD2 scenes).
case = addendum11 reference__case_id (0 both right, 1 prior wrong, 2 image wrong, 4 image missing; 3 both wrong kept apart).
판 0 target right = |GT point − 판 0 target plane of its patch| along the patch normal <= τ (WRONGTARGET second definition 'target-plane distance';
no target / no patch -> wrong). type = 판 0 target type of the patch. changed = patch whose type changes when re-judged with scene heights (reply 1 §2).
writes /df/points/pts_<stem>.npz"""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_depthfix_v1')
from df_common import *
TE = PH/'main_trainerr_v1/PHD-MAIN-TRAINERR-v1'; WT = PH/'main_wrongtarget_v1/PHD-MAIN-WRONGTARGET-v1'; GT = PH/'main_gtjudge_v1/PHD-MAIN-GTJUDGE-v1'

def main(stem):
    ra = loadz(TE/'addendum2/points'/f'ra_{stem}__own.npz', ['point_id', 'xyz', 'case_id', 'patch_raw']); w = loadz(WT/'points'/f'wt_{stem}.npz', ['point_id', 'tau', 'wall', 's_prior', 's_mvs', 'group', 'method_target_ok'])
    assert np.array_equal(ra['point_id'], w['point_id'])
    a11 = loadz(GT/'addendum11/final_data'/f'{stem}.npz', ['reference__normal', 'reference__case_id']); pid = ra['point_id']
    assert np.array_equal(a11['reference__case_id'][pid], ra['case_id'])
    tb = loadz(O/'families/base/targets'/f'{stem}.npz', ['target', 'normal', 'surface_exists']); pi = loadz(O/'patchinfo'/f'{stem}.npz'); rj = loadz(O/'patchinfo'/f'{stem}_rejudge.npz')
    pr = ra['patch_raw']; has = pr >= 0; q = np.maximum(pr, 0); act = has & tb['surface_exists'][q]
    n = tb['normal'][q]/np.linalg.norm(tb['normal'][q], axis=1)[:, None]; dist = np.where(act, ((ra['xyz'].astype('f8') - tb['target'][q])*n).sum(1), np.nan)
    tok = act & (np.abs(dist) <= w['tau'])
    typ = np.where(act, pi['type'][q], -1).astype('i1'); split = act & pi['split'][q]; changed = act & rj['changed'][q]
    out = dict(point_id=pid, xyz=ra['xyz'], normal=a11['reference__normal'][pid].astype('f4'), case_id=ra['case_id'], tau=w['tau'], wall=w['wall'], patch=pr, target_distance=dist.astype('f4'),
               target_ok=tok, type=typ, split=split, type_changed=changed, c_kA=np.where(split, pi['c_kA'][q], np.nan), c_k1=np.where(split, pi['c_k1'][q], np.nan),
               s_prior=w['s_prior'], s_mvs=w['s_mvs'], finaltrain_group=w['group'], finaltrain_target_ok=w['method_target_ok'])
    savez(O/'points'/f'pts_{stem}.npz', **out)
    rows = []
    for cs in [0, 1, 2, 4, 3]:
        for t_ in [True, False]:
            m = (ra['case_id'] == cs) & (tok == t_); rows.append(dict(stem=STEM_KO[stem], case=int(cs), target_ok=bool(t_), points=int(m.sum()), finaltrain_target_ok_pct=100*float(w['method_target_ok'][m].mean()) if m.any() else None))
    table(f'points_{stem}', rows, D/'tables/pre'); print('POINTS', stem, len(pid), flush=True)

if __name__ == '__main__': main(sys.argv[1])
