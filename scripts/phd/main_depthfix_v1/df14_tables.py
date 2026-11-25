"""Report tables from score/, float/, surface/, points/ (CPU). usage: df14_tables.py
tables/res_51.csv        : 5.1 named values per scene × arm × seed × extraction (all points, without type-changed patches, switch points)
tables/res_51_cells.csv  : 4 cases × 판 0 target right/wrong cells
tables/res_51_type.csv   : main value by 판 0 target type
tables/res_52.csv        : completeness, accuracy (per case too), floating surface, Gaussians 15k / 30k, two-layer patches
tables/res_53.csv        : mechanism values: 판 1 right-target-half share and 판 2~4 pixel weight median, for lost / kept points (판 0 result, base extraction);
                           판 5~8 result-surface classes on split patches
tables/res_criteria.csv  : order 6 condition values only (no verdict)"""
import sys, glob
sys.path.insert(0, '/repo/scripts/phd/main_depthfix_v1')
from df_common import *
c = cfg(); ARM_KO = {'p0': '판 0', 'p1': '판 1', 'p2': '판 2', 'p3': '판 3', 'p4': '판 4', 'p5': '판 5', 'p6': '판 6', 'p7': '판 7', 'p8': '판 8', 'p9': '판 9', 'p10': '판 10', 'p11': '판 11'}
VK = {'base': '기준 추출', 'occl10': '가림 제외(10 m)', 'occlga': '가림 제외(가 지도)'}
S = {}; [S.__setitem__((d['stem'], d['run']), d) for d in (json.loads(Path(p).read_text()) for p in sorted(glob.glob(str(O/'score/*.json'))))]
FL = {(d['stem'], d['run']): d for d in (json.loads(Path(p).read_text()) for p in sorted(glob.glob(str(O/'float/*.json'))))}
SU = {(d['stem'], d['run']): d for d in (json.loads(Path(p).read_text()) for p in sorted(glob.glob(str(O/'surface/*.json'))))}
r51, cells, rtype, r52, r53 = [], [], [], [], []
for (stem, run), d in S.items():
    arm, seed = d['arm'], d['seed']; base = dict(scene=STEM_KO[stem], stem=stem, arm=ARM_KO[arm], arm_id=arm, seed=seed)
    for v, ex in d['extractions'].items():
        for key, lab in [('named', '모든 점'), ('named_without_type_changed', '종류 바뀐 패치 뺌'), ('named_split_points', '라 대상 패치의 점'), ('named_occl_half_points', '판 0에서 가린 화소 지시를 절반 넘게 받던 점'), ('named_split_p0_return', '라 대상 패치 가운데 판 0 되돌림'), ('named_split_p0_image', '라 대상 패치 가운데 판 0 영상 깊이')]:
            if ex.get(key): r51.append(dict(base, extraction=VK[v], points=lab, **ex[key]))
        for cl in ex['cells']: cells.append(dict(base, extraction=VK[v], **cl))
        for t, x in ex['main_lost_by_type'].items(): rtype.append(dict(base, extraction=VK[v], type=t, main_lost_n=x['n'], main_lost_pct=x['pct'], also_fixed_n=ex['fixed_also_by_type'][t]['n'], also_fixed_pct=ex['fixed_also_by_type'][t]['pct']))
    b = d['extractions']['base']; tl = (SU.get((stem, run)) or {}).get('two_layer') or {}
    r52.append(dict(base, completeness_pct=b['completeness_pct'], accuracy_pct=b['accuracy_pct'], **{f'completeness_{k}_pct': v for k, v in b['completeness_by_case_pct'].items()},
                    completeness_occl10_pct=d['extractions'].get('occl10', {}).get('completeness_pct'), accuracy_occl10_pct=d['extractions'].get('occl10', {}).get('accuracy_pct'),
                    completeness_occlga_pct=d['extractions'].get('occlga', {}).get('completeness_pct'), accuracy_occlga_pct=d['extractions'].get('occlga', {}).get('accuracy_pct'),
                    floating_pct=(FL.get((stem, run)) or {}).get('floating_pct'), gaussians_15000=d['gaussians'].get('15000', d['gaussians'].get(15000)),
                    gaussians_30000=d['gaussians'].get('30000', d['gaussians'].get(30000)), two_layer_area_pct=tl.get('two_layer_area_pct'), two_layer_patches=tl.get('two_layer_patches')))
# mechanism: lost / kept by 판 0 (seed 0, base extraction)
for stem in c['stems']:
    pp = O/'points'/f'pix_{stem}.npz'; rp = O/'points_out'/f'res_{stem}.npz'
    if not (pp.exists() and rp.exists()): continue
    P = loadz(O/'points'/f'pts_{stem}.npz', ['case_id', 'target_ok']); X = loadz(pp); R = loadz(rp)
    if 'p0_s0' not in R: continue
    w0 = (R['p0_s0'] & 1).astype(bool); tgt = (P['case_id'] == 2) & P['target_ok']; lost = tgt & ~w0; kept = tgt & w0
    for arm in ['p0', 'p1', 'p2', 'p3', 'p4']:
        for g, m in [('잃은 점(판 0)', lost), ('지킨 점(판 0)', kept)]:
            r53.append(dict(scene=STEM_KO[stem], stem=stem, map=ARM_KO[arm], group=g, points=int(m.sum()), right_target_half_pct=100*float(X[f'right_half_{arm}'][m].mean()) if m.any() else None,
                            w_median=float(np.nanmedian(X[f'w_median_{arm}'][m])) if m.any() else None,
                            w_median_nonzero=(float(np.nanmedian(X[f'w_median_pos_{arm}'][m])) if f'w_median_pos_{arm}' in X and m.any() else None),
                            right_target_half_visible_pct=(100*float(X[f'right_half_visible_{arm}'][m].mean()) if f'right_half_visible_{arm}' in X and m.any() else None), occluded_instr_half_p0_pct=100*float(X['occluded_instr_half_p0'][m].mean()) if m.any() else None))
for (stem, run), d in SU.items():
    for row in d['classes']: r53.append(dict(scene=STEM_KO[stem], stem=stem, map=ARM_KO[run.rsplit('_s', 1)[0]], run=run, group='라 대상 패치 결과 면', **row))
crit = []
def val(stem, run, v='base'):
    d = S.get((stem, run)); return d['extractions'][v] if d else None
for arm, refs in c['criteria']['compare'].items():
    for ref in refs:
        for stem in c['stems']:
            a, b = val(stem, f'{arm}_s0'), val(stem, f'{ref}_s0')
            if not (a and b): continue
            s0, s1 = val(stem, 'p0_s0'), val(stem, 'p0_s1')
            na, nb = a['named'], b['named']; sd = lambda k: (abs(s0['named'][k] - s1['named'][k]) if (s0 and s1 and s0['named'][k] is not None and s1['named'][k] is not None) else None)
            ga = S[(stem, f'{arm}_s0')]['gaussians']; gb = S[(stem, f'{ref}_s0')]['gaussians']; g = lambda x: x.get('30000', x.get(30000))
            fa, fb = (FL.get((stem, f'{arm}_s0')) or {}).get('floating_pct'), (FL.get((stem, f'{ref}_s0')) or {}).get('floating_pct')
            dd = lambda k: (na[k] - nb[k]) if (na[k] is not None and nb[k] is not None) else None
            crit.append(dict(scene=STEM_KO[stem], arm=ARM_KO[arm], against=ARM_KO[ref], main_lost_pct=na['main_lost_pct'], against_main_lost_pct=nb['main_lost_pct'],
                             main_rel_change_pct=(100*(na['main_lost_pct'] - nb['main_lost_pct'])/nb['main_lost_pct'] if (na['main_lost_pct'] is not None and nb['main_lost_pct']) else None),
                             main_abs_change_pp=dd('main_lost_pct'), p0_seed_diff_main_pp=sd('main_lost_pct'),
                             keep1_change_pp=dd('keep1_fixed_pct'), accuracy_change_pp=a['accuracy_pct'] - b['accuracy_pct'], completeness_change_pp=a['completeness_pct'] - b['completeness_pct'],
                             also_fixed_change_pp=dd('also_fixed_pct'), p0_seed_diff_also_fixed_pp=sd('also_fixed_pct'),
                             floating_ratio=(fa/fb if (fa is not None and fb) else None), gaussians_ratio=(g(ga)/g(gb) if g(ga) and g(gb) else None),
                             main_lost_switch_points_pct=(a['named_split_points']['main_lost_pct'] if arm in ('p5', 'p6', 'p7', 'p8') else (a['named_occl_half_points'] or {}).get('main_lost_pct') if arm == 'p1' else None),
                             against_main_lost_switch_points_pct=(b['named_split_points']['main_lost_pct'] if arm in ('p5', 'p6', 'p7', 'p8') else (b['named_occl_half_points'] or {}).get('main_lost_pct') if arm == 'p1' else None),
                             note='조건마다의 값만 싣는다(판정은 사람이 한다). 씨앗 차이는 판 0 씨앗 0·1이 모두 있을 때만'))
for name, rows in [('res_51', r51), ('res_51_cells', cells), ('res_51_type', rtype), ('res_52', r52), ('res_53', r53), ('res_criteria', crit)]:
    if rows: table(name, rows)
print('TABLES', len(r51), len(r52), len(r53), len(crit), flush=True)
