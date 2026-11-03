"""Freeze execution/report sources before the full photo census; syntax and imports."""
import ast,json,subprocess
import numpy,scipy,torch,cv2,matplotlib,open3d,shapely
from preflight import C,D,O,Path,sha,dump,now
from record_setting_reply2 import record

def main():
    root=Path(__file__).parent
    record('figures','photo_camera_selection','largest projected component bounding-box area among selected photos of every point in the component; exact union of projected core cells for outlines','Resolve photo montage implementation before outcomes or component selection; include every component point, preserve roof/wall and tile identity')
    record('sources','source_roles','Widen reference cells and reference heights are evaluation-only, including target 3 and figure selection; geometry calibration, agreement sample, photo views, thresholds and honest judgments do not use reference cells','Clarify source-role metadata to match implemented GT separation; no numerical or membership change')
    record('execution','delivery_subdirectory','delivery_reply2','Keep large delivery ZIP payloads inside the authorized external task folder; commit reports, figures, source, configuration and archive receipts in the three authorized repository folders')
    record('execution','cpu_preparation_workers',dict(main_cpus=4,auxiliary_cpus=2,max_memory_gib_each=32,nice=19,per_tile_lock=True),'Record the operational parallel preparation introduced during the census; both workers reuse the same frozen numerical preparation code and skip completed tiles; prior source locks and runner failures retained')
    record('execution','core_stacked_axes',['photo_code','new_photo_code','region','reason','arm_region','arm_height_m'],'Before the first section 6/7 census aggregation, static review found new_photo_code missing from the stacked-array list. Metrics now share the canonical export schema; no score, target, threshold or numerical decision changed')
    files=sorted(root.glob('*.py'))+sorted(root.glob('*.sh'))
    for p in files:
        if p.suffix=='.py':ast.parse(p.read_text(),filename=str(p))
        else:subprocess.run(['bash','-n',str(p)],check=True)
    result=dict(at=now(),status='PASS_SOURCE_SYNTAX_AND_IMPORTS',files={p.name:sha(p) for p in files},config_sha256=sha(C/'judgecheck_v1.json'),
        versions={k:v.__version__ for k,v in dict(numpy=numpy,scipy=scipy,torch=torch,cv2=cv2,matplotlib=matplotlib,open3d=open3d,shapely=shapely).items()},scientific_verdict=None)
    lock=C/'sources.reply2.lock.json';first=not lock.exists()
    if not first:
        previous=sha(lock);(C/'revisions/r2'/f'sources.{previous[:16]}.json').write_bytes(lock.read_bytes());result['previous_lock_sha256']=previous
    dump(lock,result);dump(D/'tables/reply2_source_audit.json',result)
    with (D/'progress.md').open('a') as f:
        f.write(f"\n- {now()}: 회신 2 실행·표·그림 스크립트 {len(files)}개의 문법과 환경을 확인하고 소스 SHA-256을 잠갔다. 이전 잠금은 보존한다. 단계 나 미시작.\n")
    print(result['status'],len(files),flush=True)

if __name__=='__main__':main()
