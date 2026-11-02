"""Lock the read-only twelve-state diagnosis before any model measurements."""
import shutil
from common import *

ROOT = OUT / 'r8_lod2_cause'

def main():
    ROOT.mkdir(exist_ok=False)
    rows = []
    for name in ['scoring_continue_r7.r1.json', 'scoring_r8.json']:
        for r in json.loads((CFG/name).read_text())['rows']:
            if r['family'] == 'r6': continue
            if r['family'] == 'r7' and r['prior'] == 'ALS' and r['iteration'] != 7000: continue
            if r['family'] == 'r8' and r['prior'] == 'LoD2' and r['iteration'] != 7000: continue
            m = Path(r['model']); it = r['iteration']
            row = {k:r[k] for k in ['key','family','prior','iteration','model']}
            row['ply'] = str(m/f'point_cloud/iteration_{it}/point_cloud.ply')
            row['snapshot'] = str(m/f'target_monitor/snapshot_{it}.npz') if r['family'] != 'base' else None
            cp = m/f'jbgs_complete/iteration_{it}/checkpoint.pth'
            row['checkpoint'] = str(cp) if cp.exists() else None
            row['gradient_requested'] = it == 7000 and r['key'] in ['r8_LoD2_7000','r8_ALS_7000','r7_LoD2_7000','base_LoD2_7000']
            row['renders'] = str(OUT/'r5/baselines'/f'depth_{r["prior"]}/renders') if r['family']=='base' and it==30000 else str(m/f'check{it}/renders')
            row['source'] = '/repo/src/phd/forks/GeoGS-conf-guided-v1-' + ('r15' if r['family']=='base' else 'r21' if r['family']=='r7' else 'r22')
            rows.append(row)
    assert len(rows)==12
    config = dict(task_id='PHD-MAIN-TARGET-v1',at=stamp(),authority='2026-11-02 user r8 LoD2 cause diagnosis',
        rows=rows,training=False,optimization_steps=0,gpu_use='rendering only',scientific_verdict=None,
        spatial_height_status='PENDING_USER_DEFINITION; no spatial aggregation until separately locked',
        spatial_xy='distance in metres from frozen eval_u/eval_v rectangle in original orthonormal BASIS; inside inclusive, outside (0,50],(50,200],(200,infinity)',
        provenance='baseline origin.npy[PLY init_id], assert stored origin equality; r7/r8 current target_tag; r8 LoD2 released_at==100 is inherited by all children',
        longest_axis='max(exp(PLY scale_0), exp(PLY scale_1)), same activated scale as training; not diameter',
        opacity='sigmoid(PLY opacity)',gradient='model tuple indices 8 / 9; NaN -> 0 as original densify_and_prune; >= saved densify_grad_threshold; additionally report observed denominator and actual exemption if available',
        render=dict(views=203,order='lexicographic image_name',resolution=1,shuffle=False,depth_ratio=0,
            method='unmodified rasterizer forward; read returned num_rendered and GeometryState.tiles_touched; return original tuple unchanged',
            parity='all depth and alpha arrays exactly equal previous saved render; total tiles equals sum per Gaussian',
            buffers='record returned geom, binning, image bytes and live CUDA peak allocation; counts include pre-alpha, occluded bounding-box tiles'))
    files = {}
    for row in rows:
        paths=[row['ply'],row['snapshot']]
        if row['gradient_requested']: paths.append(row['checkpoint'])
        paths.append(str(S0/'fork_inputs/s61/B173nb_b10'/f'scene_{row["prior"]}/sparse/0/origin.npy'))
        paths.append(str(OUT/'r7/stage1'/f'B173nb_b10_{row["prior"]}/maps/index.json'))
        for p in filter(None,paths):
            if p not in files: files[p]=sha(p)
        for p in Path(row['source']).rglob('*.py'):
            if '__pycache__' not in p.parts: files[str(p)]=sha(p)
    src=Path('/opt/geogs-source/submodules/diff-surfel-rasterization')
    shutil.copytree(src, ROOT/'rasterizer_source',ignore=shutil.ignore_patterns('build','*.so','__pycache__','.git'))
    for p in (ROOT/'rasterizer_source').rglob('*'):
        if p.is_file():files[str(p)]=sha(p)
    for p in Path(__file__).parent.glob('cause_r8_*.py'):files[str(p)]=sha(p)
    for p in [CFG/'scoring_continue_r7.r1.json',CFG/'scoring_r8.json',REPO/'configs/phd/main_prep_measure_v1/prep_v5.json',
              PH/'main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1/s02_box/B173nb_b10/range.json']:
        files[str(p)]=sha(p)
    dump(CFG/'cause_r8_lod2.json',config)
    dump(CFG/'cause_r8_lod2.lock.json',dict(at=stamp(),config_sha256=sha(CFG/'cause_r8_lod2.json'),files=files,
        image_id='sha256:ff4eba02c450573e3258ec4946b9c536f32c213dde9abc83ee2969aaf18384be',scientific_verdict=None))
    print('LOCKED',len(rows),len(files),flush=True)

if __name__=='__main__':main()
