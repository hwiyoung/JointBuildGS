"""Required low-cell0 diagnostics, using one original training view per model."""
from common import *
import sys
BASE=Path('/out')
def setup(site):
    import diagnostics
    diagnostics.main(site)
    p=O/'diagnostics'/f'{site}_jobs.json';record=json.loads(p.read_text());rows=[]
    for j in record['jobs']:
        key=j['key'];j.update(mesh=str(O/'meshes'/key/'primary.ply'),score_key=key)
        source=BASE/'jobs'/f"{j['render_key']}.json";job=json.loads(source.read_text())
        # Keep the pre-existing shared 2DGS render key and exact model implementation.
        job.update(diagnostic_only=True,source_job=str(source),source_job_sha256=sha(source))
        dump(O/'diagnostics/jobs'/source.name,job)
        primary=O/'scores'/key/'values.json';v=json.loads(primary.read_text());old=BASE/'scores'/key/'values.json'
        ov=json.loads(old.read_text()) if old.exists() else None
        rows.append(dict(site=site,prior=j['prior'],key=key,training_mesh_source=str(primary),training_mesh_sha256=v['mesh_sha256'],training_scene=v['scene'],final_mesh_source=str(old) if ov else None,final_scene=ov['scene'] if ov else None,comparison_note='덧붙임 3에서 학습 시점 메시가 최종 제출 메시이므로 두 값 동일; 옛 값은 있으면 출처만 보존',submitted_final_scene=v['scene'],scientific_verdict=None))
    dump(p,record);table(site+'__low_cell0_mesh_comparison',rows);print('DIAGNOSTICS',site,[j['key'] for j in record['jobs']],flush=True)
def draw(key):
    import figures
    figures.draw_diagnostic(key)
if __name__=='__main__':
    if sys.argv[1]=='setup':setup(sys.argv[2])
    else:draw(sys.argv[2])
