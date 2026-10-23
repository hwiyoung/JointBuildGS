"""Compact execution receipt; no holdout outcome fields."""
import datetime as dt
import json
import os
from pathlib import Path
import sys
import numpy as np
import scipy
import laspy
from preflight import sha,dump
O=Path('/out');DOC=Path('/docs');R=Path(__file__).parent
def main():
    made=dt.datetime.now(dt.timezone(dt.timedelta(hours=9)))
    config=json.loads(Path('/cfg/widen0_v2.json').read_text())
    started=dt.datetime.fromisoformat(config['created_at'])
    groups={}
    for f in (O/'holdout/internal/work').glob('run_*.json'):
        if 'limit' in f.name:continue
        j=json.loads(f.read_text());key=j['data'];g=groups.setdefault(key,dict(jobs=0,total_seconds=0.,largest_parent_RSS_GiB=0.))
        g['jobs']+=1;g['total_seconds']+=j['seconds_loop'];g['largest_parent_RSS_GiB']=max(g['largest_parent_RSS_GiB'],j['peak_gb_parent'])
    exclusions=[]
    for prior in ['LoD2','ALS']:
        n=0;a=0.;outside=0;oa=0.
        for f in (O/'holdout/internal/patch_geometry').glob(f'*_{prior}.json'):
            j=json.loads(f.read_text());n+=j['unmatched_count'];a+=j['unmatched_area_m2'];outside+=j['matched_outside_scope_buildings_count'];oa+=j['matched_outside_scope_buildings_area_m2']
        exclusions.append(dict(prior=prior,unattached_patches=n,unattached_area_m2=a,attached_to_buildings_outside_scope_patches=outside,attached_to_buildings_outside_scope_area_m2=oa))
    from analysis_common import save_table
    save_table('건물에_붙지않은_패치',exclusions)
    result=dict(task_id='PHD-MAIN-WIDEN0-v2',made=made.isoformat(),
        first_config_created_at=started.isoformat(),elapsed_since_first_config_seconds=(made-started).total_seconds(),
        process_launch_commit=os.environ.get('WIDEN_COMMIT'),image_id=os.environ.get('WIDEN_IMAGE_ID'),
        preparation_commit=(O/'repository_head_at_pipeline_preparation.txt').read_text().strip(),
        versions=dict(python=sys.version,numpy=np.__version__,scipy=scipy.__version__,laspy=laspy.__version__),
        mvs=json.loads((O/'mvs/full/colmap_receipt.json').read_text()),cpu_measurement=groups,
        registration=json.loads((O/'gates/registration_runtime.json').read_text()),
        registration_runtime_scope='Successful resume only; initial failed attempt recorded separately below.',
        failed_registration_attempt=json.loads((O/'gates/continuation_register_geometry.py.json').read_text()),
        extra_normal_replay=json.loads((O/'gates/extra_normal_replay.json').read_text()),
        measurement_wall=json.loads((O/'gates/measurements_complete.json').read_text()),
        cpu_nice=19,container_total_memory_limit_GiB=32,patch_workers=64,cpu_quota=64,registration_tile_processes=4,training_executed=False,
        config_sha256=sha('/cfg/widen0_v2.json'),building_split_sha256=sha(O/'building_split.json'),image_split_sha256=sha(O/'image_split.json'),
        scripts_sha256={p.name:sha(p) for p in sorted(R.glob('*')) if p.is_file()},
        required_path_exception='An accidental empty repo-root interim.tmp was immediately removed; existing files unchanged. See issues.md.',
        scientific_verdict=None)
    dump(DOC/'execution_receipt.json',result);dump(O/'execution_receipt.json',result)
    print('execution receipt and exclusion counts written')
if __name__=='__main__':main()
