"""Freeze direct reply 2 without changing the existing geometry/calibration."""
import json,shutil,os
from preflight import C,D,O,Path,sha,dump,now

def main():
    dest=C/'judgecheck_v1.reply2.lock.json'
    if dest.exists():assert sha(C/'judgecheck_v1.json')==json.loads(dest.read_text())['config_sha256'];return
    p=C/'judgecheck_v1.json';before=sha(p);assert before=='4d6bbe79fcc68023382b1e77cc59cf1be7915dda5b191057a97a0524c09d0d32'
    rev=C/'revisions/r2';rev.mkdir(parents=True)
    shutil.copy2(p,rev/p.name);shutil.copy2(C/'judgecheck_v1.reply1.lock.json',rev/'judgecheck_v1.reply1.lock.json')
    cfg=json.loads(p.read_text());at=now();cfg['amendments'].append(dict(at=at,authority='reply_2.txt',authority_at='2026-11-03T10:20:00+09:00',
        authority_sha256=sha(C/'reply_2.txt'),previous_config_sha256=before,reason='User authorizes tile/image batching, all target types and conditional continuation after revised 48h estimate',full_text=(C/'reply_2.txt').read_text()))
    cfg['execution'].update(current_payload='/out/r2',input_payload='/out/r1',
        stage_a_order=['ALS_roof','LoD2_roof','roof_interim_report_commit_then_continue','LoD2_wall'],
        revised_benchmark='whole tile with largest target 1/2/3 count; shared tile/image costs separated from per-point work',
        gpu_continue_if_estimated_hours_le=48,report_cost_breakdown_if_hours_gt=10,
        old_200point_linear_stop_superseded=True,stage_b_requires_new_user_reply=True)
    cfg['reply2_diagnostics']=dict(missing_u_overlap_with_n_lt4=True,geometry_unknown_cause_counts_and_areas=True,
        als_normal_fallback_edge_proximity=True,accuracy_split_by_normal_fallback=True,
        missing_values_remain_unavailable=True,do_not_stop_for_these=True)
    dump(p,cfg);dump(dest,dict(at=at,config_sha256=sha(p),authority_sha256=sha(C/'reply_2.txt'),
        inherited_geometry_sha256=sha(O/'r1/geometry_calibration.json'),before_resumed_calculation=True,scientific_verdict=None))
    (O/'r2').mkdir(exist_ok=True)
    with (D/'progress.md').open('a') as f:f.write(f'\n- {at}: 회신 2에 따라 시간 중단을 해제하고 대상 3을 포함한 최대 구역 단위의 새 시간 점검을 시작한다. 48시간 안이면 지붕 중간 보고를 커밋하고 벽까지 계속한다. 확인용 미개방.\n')
    print('REPLY2_LOCK',sha(p))

if __name__=='__main__':main()
