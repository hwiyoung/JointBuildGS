"""Training/model handoff only: no reference geometry, meshes, scoring or figures."""
import sys
from common import *
from scope_policy import training_only, POLICY

HOST_OUT=Path('/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1')
NAMES={'B0_b10':'B0','R1rep_b10':'R1'}
PRIORS={'ALS':'항공LiDAR','LoD2':'LoD2'}

def main(site,prior):
    assert training_only(site);cfg()
    from report import table,monitor
    stem=f'{site}__{prior}';run=O/'runs'/site/f'ft_{prior}_s0'
    receipt=json.loads((run/'receipt.json').read_text());attempts=[];models=[]
    for attempt in receipt['attempts']:
        model=Path(attempt['model']);launch=json.loads((model.parent/'launch.json').read_text())
        attempts.append(dict(site=site,prior=prior,attempt=attempt['attempt'],status=attempt['status'],gpu=launch['gpu'],
            start=launch['at'],finish=attempt['at'],seconds=attempt['seconds'],hours=attempt['seconds']/3600,
            model_directory=str(HOST_OUT/model.relative_to(O)),training_log=str(HOST_OUT/(model.parent/'train.log').relative_to(O))))
        for iteration in [7000,15000,30000]:
            checkpoint=model/f'jbgs_complete/iteration_{iteration}/checkpoint.pth'
            gaussian=model/f'point_cloud/iteration_{iteration}/point_cloud.ply'
            if not checkpoint.exists() and not gaussian.exists():continue
            assert checkpoint.is_file() and gaussian.is_file(),(checkpoint,gaussian)
            models.append(dict(site=site,prior=prior,attempt=attempt['attempt'],iteration=iteration,
                checkpoint=str(HOST_OUT/checkpoint.relative_to(O)),gaussian_ply=str(HOST_OUT/gaussian.relative_to(O)),
                checkpoint_bytes=checkpoint.stat().st_size,gaussian_ply_bytes=gaussian.stat().st_size))
    if receipt['status']=='TRAINING_COMPLETE_30000':assert any(x['iteration']==30000 for x in models)
    releases,alerts=monitor(site,prior,run)
    table('training_summary_'+stem,attempts);table('model_paths_'+stem,models)
    prior_post=O/'post'/f'{stem}.json'
    if prior_post.exists():
        archive=O/'post_history'/f'{stem}_{now().replace(":","-")}.json';archive.parent.mkdir(exist_ok=True);prior_post.rename(archive)
    report=D/f'결과_{NAMES[site]}_{PRIORS[prior]}.md'
    text=[f'# {NAMES[site]} {PRIORS[prior]} 학습 기록','','FINALTRAIN 덧붙임 적용. 메시·채점·그림: RESCORE 덧붙임 3에서 수행. scientific_verdict: null.','']
    text+=['**풀림 기록: '+x+'**' for x in alerts]
    for label,name in [('학습 시간과 GPU','training_summary_'),('저장 모델 경로','model_paths_'),('7,000·15,000·30,000회 영역별 풀림','release_')]:
        text+=['',label,'',(D/'tables'/f'{name}{stem}.md').read_text().rstrip()]
    report.write_text('\n'.join(text)+'\n')
    record=dict(at=now(),status=receipt['status'],scope='TRAINING_AND_MODEL_SAVE_ONLY',postprocessing='RESCORE_ADDENDUM_3',
        report=str(report),figures=[],scored=False,attempts=attempts,models=models,release_table=str(D/'tables'/f'release_{stem}.json'),
        policy_sha256=sha(POLICY),scientific_verdict=None)
    dump(O/'reports'/f'{stem}.json',record)
    dump(O/'verification'/f'delivery_{stem}.json',dict(at=now(),status='PASS_TRAINING_HANDOFF',training_status=receipt['status'],
        saved_models=len(models),score_table_binding=None,exported_figures=[],policy_sha256=sha(POLICY),scientific_verdict=None))
    print('TRAINING_REPORT',stem,receipt['status'],flush=True)

if __name__=='__main__':main(*sys.argv[1:])
