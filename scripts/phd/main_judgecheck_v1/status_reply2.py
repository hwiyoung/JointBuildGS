"""Completion receipts only; no scores, reference values or holdout data opened."""
import json
from preflight import C,D,O,Path,dump,now
BASE=O/'r2';GROUPS=['ALS_1','LoD2_1','LoD2_2']
def main():
    census=json.loads((BASE/'target_census.json').read_text());done={g:0 for g in GROUPS};devices={};files=[]
    for tile in census['tile_targets']:
        root=BASE/'photo_scores'/tile
        if (root/'complete.json').exists():
            prepared=json.loads((BASE/'photo_prepared'/f'{tile}.complete.json').read_text());scored=json.loads((root/'complete.json').read_text())
            for k,count in prepared['group_counts'].items():done[GROUPS[int(k)]]+=count
            files.append(str(root/'complete.json'));devices[scored['device']]=devices.get(scored['device'],0)+scored['points']
        else:
            for i,g in enumerate(GROUPS):
                p=root/f'group{i}/complete.json'
                if not p.exists():continue
                scored=json.loads(p.read_text());done[g]+=scored['points'];files.append(str(p));devices[scored['device']]=devices.get(scored['device'],0)+scored['points']
    result=dict(at=now(),stage='A',prepared_tiles=len(list((BASE/'photo_prepared').glob('*.complete.json'))),total_tiles=len(census['tile_targets']),
        processed_points=done,target_points=census['group_targets'],completed_by_device=devices,
        metric_groups=[g for g in GROUPS if (BASE/'metrics'/f'{g}.json').exists()],roof_report_committed=(BASE/'reports/roof_commit.json').exists(),
        benchmark_includes_all_three_groups=True,completed_point_processing_does_not_imply_finite_score=True,holdout_opened=False,scientific_verdict=None)
    dump(BASE/'status.json',result);dump(D/'status_reply2.json',result);print(json.dumps(result,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
