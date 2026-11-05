"""Inspect exact inherited reference schemas without inventing a GT surface."""
import zipfile
import sys
import numpy as np
from common import *

def schema(path):
    rows = []
    with zipfile.ZipFile(path) as archive:
        for member in archive.infolist():
            if not member.filename.endswith('.npy'):
                continue
            with archive.open(member) as f:
                version = np.lib.format.read_magic(f)
                shape, fortran, dtype = np.lib.format._read_array_header(f, version)
            rows.append(dict(name=member.filename[:-4], shape=list(shape), dtype=str(dtype),
                             crc32=f'{member.CRC:08x}', uncompressed_bytes=member.file_size))
    return dict(path=str(path), bytes=path.stat().st_size, arrays=rows,
                triangle_index_fields=[x['name'] for x in rows if x['name'].lower() in
                    ['f','faces','triangles','face_indices','triangle_indices']],
                payload_sha256_verified=False)

def main():
    c = cfg()
    stamp = O / 'first_inspection.json'
    if not stamp.exists():
        dump(stamp, dict(at=now(), config_sha256=sha(C/'gtjudge_v1.json'),
            stage0_lock_sha256=sha(C/'stage0.initial.lock.json'),
            image=os.environ['GTJUDGE_IMAGE'], python=sys.version, numpy=np.__version__,
            numerical_scoring_started=False, scientific_verdict=None))
    inventory, scenes, method_rows, training = [], [], [], []
    paths = set()
    for site in SITES:
        references = [S1/'defs'/site/'gt_classes.npz', S1/'v3/box_gt'/site/'gt_points.npz',
            S1/'v3/box_gt'/site/'gt_primary.npz',
            PH/'main_axes71_v2/PHD-MAIN-AXES71-v2/work'/f'normals_{site}.npz']
        for p in references:
            if p.exists(): inventory.append(schema(p))
        defs = json.loads((S1/'defs'/site/'defs.json').read_text())
        paths.update([S1/'defs'/site/'defs.json', S1/'v3/box_gt'/site/'gt_summary.json'])
        for prior in PRIORS:
            stem = f'{site}__{prior}'
            cells = RL/'stage0'/stem/'cells.npz'
            with np.load(cells) as z:
                cell = z['score_cell_1p0']
                counts = {int(k):int((cell==k).sum()) for k in np.unique(cell)}
            reference = next(x for x in inventory if x['path']==str(references[0]))
            scenes.append(dict(site=site, prior=prior, n_reference_rows=len(cell),
                n_old_both_correct=counts.get(0,0), min_1000_eligible=counts.get(0,0)>=1000,
                gt_triangle_fields=len(reference['triangle_index_fields']),
                reference_normals='PCA radius 0.5 m, KNN 10 fallback, sign unset',
                required_normal='nearest GT triangle; roof up/wall outward',
                reference_surface_status='확인 불가: 상속 참값 삼각형 면 없음',
                normal_prior_within_tau_pct=None, normal_mvs_within_tau_pct=None,
                anomaly_signal=None, correction_attempts=0, fallback_authorized=False))
            for method in METHODS:
                folder = score_dir(site,prior,method)
                value_path = folder/'values.json'
                value = json.loads(value_path.read_text())
                p = Path(value['mesh'])
                method_rows.append(dict(site=site, prior=prior, method=method,
                    score_path=str(value_path), points_path=str(folder/'points.npz'), mesh_path=str(p),
                    mesh_exists=p.is_file(), saved_points_exists=(folder/'points.npz').is_file(),
                    inherited_mesh_sha256=value['mesh_sha256'], mesh_sha256_reverified=False,
                    normal_completeness_status='확인 불가: 참값 삼각형 법선 미확인',
                    normal_accuracy_status='확인 불가: 광선을 교차할 참값 면 미확인'))
                paths.add(value_path)
            receipt = FT/'runs'/site/f'ft_{prior}_s0/receipt.json'
            value=json.loads(receipt.read_text())
            training.append(dict(site=site,prior=prior,status=value['status'],
                target_exists=(FT/'targets'/f'{stem}.npz').is_file(),receipt=str(receipt)))
            paths.add(receipt)
    p = PH/'geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/native_example/evaluation_reference/r1_b1_sub002_transformed.ply'
    header=[]
    with p.open('rb') as f:
        for _ in range(200):
            line=f.readline().decode('ascii').strip();header.append(line)
            if line=='end_header':break
        else:raise ValueError('No PLY header terminator')
    dump(D/'provenance/B0_primary_ply_header.json',dict(path=str(p),header=header,
        vertex_only=not any(x.startswith('element face ') for x in header),scientific_verdict=None))
    scopes=[R/'scripts/phd'/name for name in ['main_recount_v1','main_release_v1','main_rescore_v1',
        'main_stage1_v1','main_axes71_v2','main_dist71_v1']]
    refs=[]
    for root in scopes:
        for path in root.glob('*.py'):
            for i,line in enumerate(path.read_text().splitlines(),1):
                if any(token in line for token in ['gt_classes.npz','normals_full','estimate_point_covariances',
                    'gt_primary.npz','r1_b1_sub002_transformed.ply','normal_wall_distance','ctx[\'ref\'].query(sample)']):
                    refs.append(dict(path=str(path),line=i,text=line))
    for rel in ['scripts/phd/main_axes71_v2/a1_normals.py','scripts/phd/main_axes71_v2/a2x_sample.py',
        'scripts/phd/main_dist71_v1/dm_common.py','scripts/phd/main_stage1_v1/defs_s1.py',
        'scripts/phd/main_stage1_v1/s04_gt_v7.py','scripts/phd/main_rescore_v1/geometry.py',
        'scripts/phd/main_rescore_v1/score_mesh.py','scripts/phd/main_release_v1/stage0.py',
        'configs/phd/main_prep_measure_v1/prep_v5.json',
        'configs/phd/main_recount_v1/recount_v1.json','configs/phd/main_finaltrain_v1/finaltrain_v1.json',
        'docs/experiments/phd/main_release_v1/tables/stage0/tau_values.csv']:
        paths.add(R/rel)
    paths.update((R/'scripts/phd/main_gtjudge_v1').glob('*.py'))
    paths.update((R/'src/phd/forks/GeoGS-conf-guided-v1-r23').rglob('*.py'))
    dump(D/'provenance/inspected_source_lock.json',dict(at=now(),
        files={str(p):sha(p) for p in sorted(paths)},scientific_verdict=None))
    dump(D/'provenance/reference_schemas.json',dict(at=now(),files=inventory,
        note='ZIP member headers and CRC metadata inspected; not full payload SHA validation',scientific_verdict=None))
    dump(D/'provenance/reference_source_lines.json',dict(rows=refs,scientific_verdict=None))
    table('reference_preflight',scenes);table('saved_method_inputs',method_rows);table('finaltrain_inputs',training)
    status=dict(at=now(),status='UNAVAILABLE_REFERENCE_TRIANGLE_SURFACE',
        stage0_complete=False, measured_anomaly_signal=None, implementation_retry_count=0,
        nearest_fallback_applied=False, fallback_reason='No measured 90-percent signal; missing input is not that signal',
        scenes=scenes, scientific_verdict=None)
    dump(D/'단계0_판정.json',status);dump(O/'stage0_status.json',status)
    print('REFERENCE_PREFLIGHT',len(scenes),'scenes;',len(method_rows),'saved methods;',
          sum(x['mesh_exists'] and x['saved_points_exists'] for x in method_rows),'inputs available;',status['status'])

if __name__=='__main__':main()
