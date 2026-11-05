"""Record the final delivery boundary, versions, and source preservation."""
from common import *
import importlib.metadata as md
import shutil

cfg()
assert os.environ['PRES_IMAGE']==json.loads((C/'realbldg_v1.initial.lock.json').read_text())['image']
raw=D/'provenance/workspace_before.zlist'
if raw.exists():
    target=O/'provenance/workspace_before.zlist';target.parent.mkdir(parents=True,exist_ok=True);shutil.move(raw,target)
shutil.copyfile(O/'first_calculation.json',D/'provenance/first_calculation.json')
photo=json.loads((D/'provenance/photo_inputs.json').read_text())['files']
for x in photo:
    p=Path(x['path']);assert p.stat().st_size==x['bytes'] and p.stat().st_mtime_ns==x['mtime_ns'],str(p)
    if 'sha256' in x:assert sha(p)==x['sha256']
dependencies=[
    R/'scripts/phd/main_judgecheck_v1/photo_cameras.py',
    R/'scripts/phd/main_judgeapply_v1/cameras.py',
    R/'scripts/phd/main_recount_v1/recount.py',
    R/'scripts/phd/main_stage1_v1/defs_s1.py',
    R/'docs/evidence/p0-audit/w3-quality-integration/tables/W3_failure_surface_cause_thresholds.csv',
]
versions={p:md.version(p) for p in ['numpy','scipy','shapely','matplotlib','Pillow','open3d']}
import cv2
versions['opencv']=cv2.__version__
report=(D/'보고.md').read_text();assert len(report)<=3000
for word in ['판정','언저리','가르다','갈리다','갈래','가져온다','계승','새로움','우리','꼴','층','견주다','몫']:
    assert word not in report,word
for word in ['TODO','FIXME','TBD','{{','}}']:assert word not in report,word
rank=json.loads((O/'ranking.json').read_text());figures=json.loads((D/'provenance/figure_decode.json').read_text())['figures']
assert len(figures)==10
assert json.loads((D/'validation.json').read_text())['status']=='PASS_NUMERICAL_CHECKS'
population=json.loads((D/'provenance/saved_population.json').read_text())['scenes']
assert all(p['ground_rows']==0 for p in population)
assert rank['all_five_full_spatial_scope'] is None
dump(D/'provenance/delivery_audit.json',dict(at=now(),status='PASS_DELIVERY_CHECKS_WITH_DECLARED_SCOPE_LIMIT',
    versions=versions,dependency_sources=[source(p) for p in dependencies],
    task_code=[source(p) for p in sorted((R/'scripts/phd/pres_realbldg_v1').glob('*')) if p.is_file()],
    photo_inputs_unchanged=True,reference_scope='saved roof and wall cases; ground unavailable',
    full_spatial_all_five=None,report_characters=len(report),
    visual_review=dict(method='One contact sheet containing all ten images was opened once',
        result='No visible broken image, clipped title, or overlapping label found at contact-sheet scale',
        png_decode_and_dpi='Separately verified all ten PNG files at 3000 x 2400 and 300 dpi',
        source_sha256='Verified all figure source sidecars after unassigned-point correction'),
    generation=dict(training=False,mesh_generation=False,GS_render=False,GPU=False,
        photo_projection='CPU projection onto existing prior geometry, as requested'),
    payload_path='../JointBuildGS-artifacts/phase-payloads/phd/pres_realbldg_v1/PHD-PRES-REALBLDG-v1',
    scientific_verdict=None))
print('DELIVERY_AUDIT_PASS',len(report),versions)
