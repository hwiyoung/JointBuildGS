"""Freeze v1.1 display-only definitions and immutable source receipts before build."""
import os
import sys
sys.path.insert(0, '/repo/scripts/phd/main_uncert_view_v1')
from common import *

DR = Path('/ph/main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1/s02_box')

def main():
    p = CFG / 'view_v1_1.json'
    if p.exists():
        assert sha(p) == load(CFG / 'view_v1_1.lock.json')['sha256']
        print('Existing lock preserved', sha(p)); return
    for site, _ in U.CASES:
        assert (DR/site/'lod2_surfaces.json').is_file(), 'STOP: LoD2 surfaces missing'
        assert (DR/site/'lod2_mesh.npz').is_file(), 'STOP: LoD2 mesh missing'
    config = dict(task_id='PHD-MAIN-UNCERT-VIEW-v1.1', made=now(), scientific_verdict=None,
        source_config_sha256=sha(CFG/'view_v1.json'), seed=20261023,
        calibration=dict(bins_cm=[0,2,5,10,20,40,None], interval='left inclusive, right exclusive',
            axes_cm=[.5,100], axes_scale='log10', min_patches=30,
            statistics=['n','u_median_cm','e_median_cm','e_p25_cm','e_p75_cm','median_e_over_u'],
            overflow='triangles at clipped chart boundary with unrounded value in tooltip and table',
            lod2='20 cm; current case: roof type and wall; pooled: site roof/wall, optional site roof type/wall'),
        population=dict(scope='eval by default; obey sidebar filters; only finite uncertainty and actual error',
            current_radius='top selector', pool_radii={'B0_b10':1.,'B173nb_b10':1.5,'R1rep_b10':1.5},
            exclusion_cell='c_corr4p', exclusion_applies='prior only, charts only; off by default',
            exclusion_warning='참값으로 뺀 것. 불확실도가 4τ에 가까운 구간은 실제 오차가 작게 나올 수 있음.'),
        sparsification=dict(remove_percent=list(range(0,91,5)), remove_count='floor(n * percent / 100)',
            uncertainty_order='descending uncertainty, ascending patch index, then site order',
            ideal_order='descending actual error, ascending patch index, then site order',
            normalized='remaining error mean / initial error mean; zero baseline unavailable',
            integration='trapezoid over removed fraction 0..0.9', random=1,
            lod2='unavailable: constant uncertainty has no ordering'),
        faces=dict(source=str(DR/'<site>/lod2_surfaces.json'), triangles='lod2_mesh.npz V,F,tri_surface; no caps',
            lod2='exact regions_ext_v3 surf_ext, cross-check patch surf and centre',
            als_roof='XY triangle containment including boundary 1e-9; nearest interpolated Z; tie surface ext ascending',
            als_wall='minimum Euclidean point-to-triangle distance <= 1 m; tie surface ext ascending',
            fallback='floor(local x/2), floor(local y/2); 2 m XY grid; Z median for display',
            aggregation='current scope and sidebar/map drill-down filters; continuous finite median; missed area fraction; categories count majority and share',
            insufficient=dict(min_valid=10,min_valid_fraction=.3,denominator='filtered patches of the face'),
            roof_type='LoD2 building attribute; ALS face view inherits matched LoD2 attribute; patch source unchanged',
            verification='10 LoD2 faces per case; numpy default_rng(seed + case index); independent source patch medians'),
        pairs=[dict(id='mvs',label='MVS 정밀도',left='mvs_u',right='mvs_e'),
               dict(id='prior',label='사전 정보 정밀도',left='prior_u',right='prior_e'),
               dict(id='sources',label='자료끼리',left='mvs_u',right='prior_u')],
        pair_range_cm=[0,50], pair_statistics='LoD2 faces only, both medians finite and both sufficiently sampled; Spearman and median(right/left); constant rank unavailable; grids excluded',
        signed=dict(layers=['difference','gt_p'],range_cm=[-50,50],zero='#ffffff',negative='#3b63a2',positive='#ba4432',label='+ 바깥, − 안쪽'),
        validation=dict(length_tolerance_cm=.1,count_tolerance=0,record_both_on_difference=True),
        output=dict(web='web_v1_1',tables='tables_v1_1',screens='screens_v1_1',port=8912), amendments=[])
    dump(p,config)
    dump(CFG/'view_v1_1.lock.json',dict(made=now(),sha256=sha(p),before_first_build=True,commit=os.environ.get('VIEW_COMMIT'),scientific_verdict=None))
    sources = list((SRC/'patch_values').glob('*.npz'))
    sources += list((ROOT/'scripts/phd/main_uncert_v1').glob('*'))
    sources += list((ROOT/'docs/experiments/phd/main_uncert_v1').rglob('*'))
    sources += list((OUT/'web').rglob('*'))
    sources += [OUT/'PHD-MAIN-UNCERT-VIEW-v1_web.zip',CFG/'view_v1.json',CFG/'view_v1.lock.json']
    for site in config['population']['pool_radii']:
        sources += [DR/site/'lod2_surfaces.json',DR/site/'lod2_mesh.npz']
        for prior in ['ALS','LoD2']:
            sources += [Path('/s1/regions_v3')/f'regions_ext_v3_{site}_{prior}.npz']
    receipt=[dict(path=str(f),bytes=f.stat().st_size,sha256=sha(f)) for f in sorted(set(sources)) if f.is_file()]
    dump(DOC/'tables_v1_1/input_receipt.json',dict(made=now(),files=receipt,config_sha256=sha(p),scientific_verdict=None))
    progress('v1.1 일 1: 세 지역 LoD2 면·삼각형 확인. 첫 빌드 전 설정 잠금과 v1 웹·ZIP·원본 값·보고·방법 코드 SHA-256 기록 완료.')
    print('v1.1 config locked',sha(p),'inputs',len(receipt))

if __name__ == '__main__': main()
