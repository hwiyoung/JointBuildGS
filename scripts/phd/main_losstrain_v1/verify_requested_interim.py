"""Verify the requested interim scope, without claiming all auxiliary work done."""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

DOC=Path('/docs');OUT=Path('/out')

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text())

def main():
    cfg=read(Path('/config/requested_interim_readout_v1.json'))
    variants=cfg['variants'];site=cfg['site'];prior=cfg['prior']
    values=read(DOC/'tables/interim_values.json')
    for v in variants:
        rows=[r for r in values['paired_patch_rows'] if r['variant']==v]
        assert len(rows)==10 and all(r['trained'] is not None for r in rows)
        fate=read(DOC/'tables/fate_cell_split'/site/f'{prior}__{v}_{prior}_s0.json')
        assert fate['status']=='PASS' and fate['partition_counts_equal_combined']
        assert set(fate['regions'])=={'cell_0','cell_2'}
    assert len(values['threshold_rows'])==21
    assert {r['variant'] for r in values['side_rows']}==set(variants)
    section=DOC/'figures/section_B173nb_b10_ALS_0.json'
    fig=read(section)
    assert set(fig['panels'])==set(variants) and fig['visual_review']=='PASS'
    assert fig['section']['start']==[146.68,96.32] and fig['section']['end']==[136.63,99.34]
    assert fig['section']['half_width']==.6
    for v,panel in fig['panels'].items():
        scored=read(OUT/'patch_z'/f'{site}__{prior}__{v}_{prior}_s0.json')
        assert panel['mesh_sha256']==scored['mesh_sha256'] and scored['status']=='PASS'
    report=DOC/'중간보고_v1.md'
    assert '![B173 날개 단면]' in report.read_text()
    files=[report,section,section.with_suffix('.png'),DOC/'tables/interim_values.json',DOC/'tables/interim_thresholds.json']
    record=dict(status='PASS_REQUESTED_INTERIM',at=datetime.now(timezone(timedelta(hours=9))).isoformat(),
                four_arm_patch_scores=True,side_tables=True,threshold_rows=21,separate_fate_cells=[0,2],
                wing_section_visual_review='PASS',section_and_score_mesh_hashes_equal=True,
                files=[dict(path=str(p),sha256=sha(p)) for p in files],
                full_measurement_complete=sum((OUT/'runs'/site/f'{v}_{prior}_s0'/'measure_PASS.json').exists() for v in variants),
                complete_training_program=False,scientific_verdict=None)
    for p in [OUT/'checks/requested_interim_readout_v1/verification.json',DOC/'tables/requested_interim_verification.json']:
        p.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(record,ensure_ascii=False))

if __name__=='__main__':main()
