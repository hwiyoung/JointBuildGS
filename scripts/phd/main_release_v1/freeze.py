"""Host filesystem setup only; all numerical work runs in Docker."""
import datetime as dt, hashlib, json, shutil, subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[3]
C=R/'configs/phd/main_release_v1'; D=R/'docs/experiments/phd/main_release_v1'
PH=R.parent/'JointBuildGS-artifacts/phase-payloads/phd'
O=PH/'main_release_v1/PHD-MAIN-RELEASE-v1'
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(8<<20),b''):h.update(b)
    return h.hexdigest()
def dump(p,v):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def main():
    assert subprocess.check_output(['git','branch','--show-current'],cwd=R,text=True).strip()=='exp/main-experiment'
    assert not (C/'release_v1.initial.lock.json').exists()
    for p in [D,O/'tmp',O/'logs',O/'verification',O/'stage0',O/'stage1',O/'bin']:p.mkdir(parents=True,exist_ok=True)
    old=R/'src/phd/forks/GeoGS-conf-guided-v1-r23';new=old.with_name('GeoGS-conf-guided-v1-r24')
    shutil.copytree(old,new,ignore=shutil.ignore_patterns('__pycache__','*.pyc','.git'))
    ft=R/'configs/phd/main_finaltrain_v1/finaltrain_v1.json';base=json.loads(ft.read_text())
    cfg=dict(task_id='PHD-MAIN-RELEASE-v1',order_version=2,scientific_verdict=None,
      created_at=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(),
      source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip(),
      order_sha256=sha(C/'order_v2.md'),parent_config=str(ft.relative_to(R)),parent_config_sha256=sha(ft),
      parent_fork=str(old.relative_to(R)),fork=str(new.relative_to(R)),V0='FINALTRAIN r23 30000',
      sites=base['sites'],priors=['ALS','LoD2'],seed=0,renderer=base['renderer'],docker_images=base['docker_images'],
      inherited={k:base[k] for k in ['frozen_judgment','targets','weights','unchanged','health','retry']},
      stage0=dict(tau_multipliers=[.5,.75,1.,1.5,2.],cell_ids=[0,1,2,4],small_n=1000,
        methods=['prior','mvs','fusion','baseline_30000','GeoGS_30000','2DGS_30000','CDGS_30000','judgment_mesh','FINALTRAIN_30000'],
        best_excludes=['judgment_mesh'],match_tolerance_pp=.1,scorer='unchanged RESCORE score_mesh.py'),
      stage1=dict(sites=['R1rep_b10'],checkpoint=30000,simulations=['delete_released','pull_released','delete_background'],
        lineage='inherited max alpha*T, modal depth-matched 0.25m train-view attribution',GT_selects_interventions=False),
      stage2=dict(iterations=30000,stop_after=15000,rules=['release'],release_log='on',gpus={'0':'ALS','1':'LoD2'}),
      stage3=dict(iterations=30000,rules=['pull','delete','mix'],gate='order_v2 section 5; original cells',
        selection='order_v2 section 6.5; original cells n>=1000',initially_authorized=False),
      output_paths=['configs/phd/main_release_v1','scripts/phd/main_release_v1','docs/experiments/phd/main_release_v1',str(new.relative_to(R)),str(O)],
      cpu_nice=19,cpu_memory_gib=32,crs='EPSG:25832')
    dump(C/'release_v1.json',cfg)
    protected={str(p):sha(p) for folder in [old,R/'configs/phd/main_rescore_v1',R/'scripts/phd/main_rescore_v1',R/'docs/experiments/phd/main_rescore_v1',R/'configs/phd/main_finaltrain_v1'] for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'}
    dump(C/'inherited_files.lock.json',protected)
    dump(C/'release_v1.initial.lock.json',dict(at=cfg['created_at'],config_sha256=sha(C/'release_v1.json'),inputs_lock_sha256=sha(C/'inherited_files.lock.json'),scientific_verdict=None))
    dump(O/'initial_git_status.json',dict(status=subprocess.check_output(['git','status','--porcelain'],cwd=R,text=True),scientific_verdict=None))
    (D/'progress.md').write_text('# 진행\n\n- '+cfg['created_at']+': v2 원문 저장; 설정 첫 잠금; r23→r24 복사. 계산 전.\n')
    (D/'issues.md').write_text('# 실행 문제·정의 적용 기록\n\n- v2가 v1과 덧붙임 1을 대체. 모의의 결과 면 생성은 3.3의 명시 지시 적용.\n- 단계 2는 iterations=30000 일정과 학습률을 유지하고 --jbgs_stop_after 15000으로 정지한다.\n')
    print(json.dumps(dict(config_sha256=sha(C/'release_v1.json'),protected_files=len(protected),output=str(O))))
if __name__=='__main__':main()
