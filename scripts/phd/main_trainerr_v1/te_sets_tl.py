"""Record-run point sets (order 3.4 lost-point overlap, 5: lost points redefined on the record 30000 mesh) with the stage-0 rule.
argv: <run>. Reads te/meshes/<stem>__tl_<arm>_30000/points.npz (full scorer output) and the stored target-surface distances.
Writes sets_tl/<cell>_<arm>_<lost|control>.npz and tables/record_lost_overlap rows (overlap with the original run's lost points)."""
import importlib.util
from common import *
sys.path.insert(0, '/repo')
from src.phd.metrics_v3.surface import MeshScene
from s0_sets import NL, columns, subsample, write_set
RUNS = {'tl_R1_ALS_gt': ('R1rep_b10__ALS', 'gt'), 'tl_B0_LoD2_gt': ('B0_b10__LoD2', 'gt'), 'tl_R1_ALS_own': ('R1rep_b10__ALS', 'own'), 'tl_B0_LoD2_own': ('B0_b10__LoD2', 'own')}

def main(run):
    c = cfg(); stem, arm = RUNS[run]; fam = f'tl_{arm}_30000'; t = Timer(f'sets_tl_{run}')
    T = loadz(O/'meshes'/f'{stem}__{fam}'/'points.npz'); A11 = np.load(GT/'addendum11/final_data'/f'{stem}.npz')
    base = {k: A11[f'reference__{k}'] for k in ['point_id', 'xyz', 'normal', 'case_id', 'wall', 'tau_m']}; tm = TARGET_METHOD[arm]
    tw = A11[f'reference__{tm}__within_tau1'].astype(bool); ts_ref = A11[f'reference__{tm}__s_m']; A11.close()
    rows = loadz(GT/'scenes'/stem/'rows.npz', ['row_owner']); core = loadz(JA/'core_points'/f'{stem}.npz'); out = []
    tg = loadz(arm_paths(stem, arm)['targets'], ['patch_id', 'region'])
    def pc(owner):
        prow = np.where(owner >= 0, core['source_index'][np.clip(owner, 0, None)], -1)
        return dict(core_owner=owner.astype('i4'), patch_row=prow.astype('i8'), patch_id=np.where(prow >= 0, tg['patch_id'][np.clip(prow, 0, None)], ''))
    for cell, cs in c['cells'].items():
        if f"{cs['site']}__{cs['prior']}" != stem: continue
        orig_lost = loadz(O/'sets'/f'{cell}_{arm}_lost.npz', ['point_id'])['point_id']
        if cs['metric'] == 'completeness':
            sel = base['case_id'] == cs['case_id']; rw = T['reference__within_tau1'].astype(bool)
            lost = np.flatnonzero(sel & tw & ~rw); ctrl_all = np.flatnonzero(sel & tw & rw); ctrl, sub = subsample(ctrl_all, c)
            for setname, idx in [('lost', lost), ('control', ctrl)]:
                write_set(f'../sets_tl/{cell}_{arm}_{setname}', dict(point_id=base['point_id'][idx], xyz=base['xyz'][idx].astype('f8'), normal=base['normal'][idx].astype('f8'),
                          wall=base['wall'][idx].astype('u1'), tau_m=base['tau_m'][idx].astype('f8'), **pc(rows['row_owner'][base['point_id'][idx]]),
                          target_s_m=ts_ref[idx], trained_s_m=T['reference__s_m'][idx], trained_state=T['reference__state'][idx], set=np.full(len(idx), 0 if setname == 'lost' else 1, 'i1')))
            new_lost = base['point_id'][lost]; ov = np.intersect1d(new_lost, orig_lost)
            value = 100*float(rw[sel].mean())
        else:
            e = T['result__eligible_new'].astype(bool) & (T['result__case_id'] == cs['case_id']); w = T['result__within_tau1'].astype(bool)
            cand = np.flatnonzero(e & ~w); ctrl_all = np.flatnonzero(e & w); ctrl, sub = subsample(ctrl_all, c); idx = np.r_[cand, ctrl]
            sc = MeshScene.from_ply(str(arm_paths(stem, arm)['target_mesh'])); st, _ = NL.measure(sc, T['result__xyz'][idx].astype('f8'), T['result__normal'][idx].astype('f8'), T['result__wall'][idx].astype(bool)); del sc
            tsd = np.full(len(w), np.nan); tsd[idx] = st; lost = cand[~(np.abs(tsd[cand]) <= T['result__tau_m'][cand])]
            for setname, ii in [('lost', lost), ('control', ctrl)]:
                write_set(f'../sets_tl/{cell}_{arm}_{setname}', dict(point_id=ii.astype('i8'), xyz=T['result__xyz'][ii].astype('f8'), normal=T['result__normal'][ii].astype('f8'),
                          wall=T['result__wall'][ii], tau_m=T['result__tau_m'][ii].astype('f8'), **pc(T['result__owner'][ii]), reference_row_id=T['result__reference_row_id'][ii],
                          target_s_m=tsd[ii], trained_s_m=T['result__s_m'][ii], trained_state=T['result__state'][ii], set=np.full(len(ii), 0 if setname == 'lost' else 1, 'i1')))
            # result samples differ between meshes: overlap = share of new lost points within 0.05 m of an original lost point
            from scipy.spatial import cKDTree
            ol = loadz(O/'sets'/f'{cell}_{arm}_lost.npz', ['xyz'])['xyz']; d, _ = cKDTree(ol).query(T['result__xyz'][lost].astype(float)); ov = np.flatnonzero(d <= .05); new_lost = lost
            value = 100*float((e & w).sum())/max(1, int(e.sum()))
        out.append(dict(run=run, cell=cell, arm=arm, metric=cs['metric'], record_value=value, original_trained=cs['expected'][arm][1], diff_pp=value-cs['expected'][arm][1],
                        record_lost=len(new_lost), original_lost=len(orig_lost), overlap=len(ov), overlap_pct_of_record=100*len(ov)/max(1, len(new_lost)),
                        overlap_pct_of_original=(100*len(ov)/max(1, len(orig_lost))) if cs['metric'] == 'completeness' else None,
                        same_value=abs(value-cs['expected'][arm][1]) <= c['record_runs']['comparison']['value_tolerance_pp']))
    dump(O/'sets_tl'/f'{run}.json', dict(at=now(), run=run, rows=out, seconds=t.done(), scientific_verdict=None)); print('SETS_TL', out, flush=True)

if __name__ == '__main__': main(*sys.argv[1:])
