"""Whole largest tile estimate with fixed and variable costs kept separate."""
import json
from preflight import C,D,O,Path,sha,dump,now
from datetime import datetime
BASE=O/'r2'
def main():
    c=json.loads((BASE/'target_census.json').read_text());tile=c['benchmark_tile'];p=json.loads((BASE/'photo_prepared'/f'{tile}.complete.json').read_text());s=json.loads((BASE/'photo_scores'/tile/'complete.json').read_text());v=json.loads((BASE/'photo_scores'/tile/'numeric_parity.json').read_text());plane=json.loads((BASE/'photo_prepared/parity.json').read_text())
    assert v['status']=='PASS_WHOLE_TILE_PHOTO_PARITY' and plane['status']=='PASS_PACKED_PLANE_PARITY';assert p['target_count']==c['benchmark_tile_count'] and s['points']==p['target_count']
    point_ratio=c['total_targets']/p['target_count'];height_total=sum(r['height_hypotheses_both_planes'] for r in c['rows']);height_tile=sum(r['height_hypotheses_both_planes'] for r in c['rows'] if r['tile']==tile);height_ratio=height_total/height_tile;ntiles=len(c['tile_targets'])
    shared_p=p['shared_load_and_tree_seconds'];variable_p=p['per_point_geometry_seconds']+p['visibility_seconds'];other_p=max(0,p['total_seconds']-shared_p-variable_p)
    # Ordered prior/kind passes reuse decoded image files but can incur a cache
    # read/upload per pass. Charge every nonempty tile/group conservatively.
    image_passes=sum(r['target_count']>0 for r in c['rows'])
    def score_components(measured,prefix):
        shared=measured['image_cache_total_seconds']+measured['upload_seconds']+max(0,measured['total_seconds']-measured['image_cache_total_seconds']-measured['arithmetic_and_reduction_seconds'])
        variable=max(0,measured['arithmetic_and_reduction_seconds']-measured['upload_seconds'])
        return {prefix+'_image_cache_read_and_upload_seconds':shared*image_passes,prefix+'_packed_arithmetic_seconds':variable*height_ratio}
    components=dict(tile_load_and_tree_seconds=shared_p*ntiles,per_point_plane_and_visibility_seconds=variable_p*point_ratio,prepared_output_seconds=other_p*point_ratio,
        **score_components(s,'gpu'))
    cpu=json.loads((BASE/'cpu_benchmark'/tile/'complete.json').read_text())
    cpu_components={k:v for k,v in components.items() if not k.startswith('gpu_')};cpu_components.update(score_components(cpu,'cpu'))
    cpu_estimate=sum(cpu_components.values())*1.25
    pauses=[];waitlog=BASE/'resources/jbgs-judgecheck-maxdirect_gpu_wait.tsv';pending=None
    if waitlog.exists():
        for line in waitlog.read_text().splitlines():
            fields=line.split('\t')
            if fields[1]=='pause':pending=fields[0]
            elif fields[1]=='resume' and pending:
                pauses.append((datetime.fromisoformat(fields[0])-datetime.fromisoformat(pending)).total_seconds());pending=None
    total=sum(components.values());estimate=total*1.25
    result=dict(at=now(),status='PASS_CONTINUE_STAGE_A' if estimate<=48*3600 else 'STOP_REVISED_TIME_GATE',benchmark_tile=tile,benchmark_points=p['target_count'],
        all_targets=c['total_targets'],group_targets=c['group_targets'],target3_included=True,point_ratio=point_ratio,height_hypothesis_ratio=height_ratio,
        measured_preparation=p,measured_scoring=s,components_seconds=components,subtotal_hours=total/3600,reserve_factor=1.25,estimated_hours=estimate/3600,
        report_breakdown_required=estimate>10*3600,gpu_limit_hours=48,image_passes=image_passes,benchmark_recorded_pause_seconds=sum(pauses),benchmark_clock_note='Measured phases exclude all pre-start GPU queue waiting. Any pauses during measurement remain in measured wall costs and are explicitly listed as a conservative overestimate; no unobserved allocation of a pause to arithmetic is inferred.',cpu_limit_hours=72,cpu_estimated_hours=cpu_estimate/3600,cpu_components_seconds=cpu_components,measured_cpu_scoring=cpu,cpu_extrapolation='whole tile, 2 CPU quota, float64; measured during other research GPU activity; conservative shared image/read/upload cost per nonempty tile/group',
        model='shared tile/tree once per tile; geometry by target count; cache read/upload once per nonempty tile/group pass; arithmetic by pre-counted two-plane height hypotheses; 25% scheduling/IO reserve. Reuse may reduce shared image costs. Already-spent one-time cache trials and GPU queue waits are logged separately.',
        inputs_sha256={str(q):sha(q) for q in [BASE/'target_census.json',BASE/'photo_prepared'/f'{tile}.complete.json',BASE/'photo_scores'/tile/'complete.json',BASE/'photo_scores'/tile/'numeric_parity.json',BASE/'cpu_benchmark'/tile/'complete.json']},
        scientific_verdict=None)
    dump(BASE/'timing_estimate.json',result);dump(D/'tables/reply2_time_estimate.json',result);dump(C/'timing.reply2.lock.json',dict(at=now(),source_sha256=sha(Path(__file__)),result_sha256=sha(BASE/'timing_estimate.json'),scientific_verdict=None))
    with (D/'progress.md').open('a') as f:f.write(f"\n- {now()}: 최대 구역 {p['target_count']:,}점 전체를 계산한 시간 어림 {estimate/3600:.3f}시간, {result['status']}. 대상 3 포함.\n")
    print('REVISED_TIME_ESTIMATE',json.dumps({k:v for k,v in result.items() if k not in ['measured_preparation','measured_scoring','inputs_sha256']}),flush=True)
    if result['status']!='PASS_CONTINUE_STAGE_A':raise SystemExit(48)
if __name__=='__main__':main()
