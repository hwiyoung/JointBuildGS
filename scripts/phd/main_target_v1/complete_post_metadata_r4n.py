"""Add two omitted reporting fields required by streamed_tsdf.merge; geometry unchanged."""
import sys,shutil
import numpy as np
from common import *

def main():
    prior=sys.argv[1];run=OUT/'r4n/runs'/f'tg_B173nb_b10_{prior}_s0';folder=run/'post7000/inputs'
    meta=json.loads((folder/'meta.json').read_text());binding=json.loads((folder/'binding.json').read_text())
    assert 'mean_share_of_pixels_with_depth' not in meta and 'seconds' not in meta
    assert sha(folder/'meta.json')==binding['files']['meta.json']
    shares=[];cover=json.loads((run/'model/check7000/coverage.json').read_text())
    for row in cover['views']:
        with np.load(run/'model/check7000/renders'/f"{row['camera']}.npz") as z:shares.append(float((z['depth']>0).mean()))
    original=folder/'metadata_before_completion';original.mkdir(exist_ok=False)
    shutil.copy2(folder/'meta.json',original/'meta.json');shutil.copy2(folder/'binding.json',original/'binding.json')
    meta.update(mean_share_of_pixels_with_depth=float(np.mean(shares)),seconds=None,
        seconds_unavailable_reason='original preparation did not record elapsed duration; no invented replacement')
    dump(folder/'meta.json',meta);binding['files']['meta.json']=sha(folder/'meta.json');dump(folder/'binding.json',binding)
    record=dict(at=stamp(),status='COMPLETED_REPORT_METADATA',reason='task prepare omitted two fields read only for merge reporting',
        old_meta_sha256=sha(original/'meta.json'),new_meta_sha256=sha(folder/'meta.json'),changed_fields=['mean_share_of_pixels_with_depth','seconds','seconds_unavailable_reason'],
        geometry_arrays_changed=False,tsdf_parameters_changed=False,training_steps=0,scientific_verdict=None)
    dump(folder/'metadata_completion.json',record);print('POST_METADATA_COMPLETED',prior,flush=True)

if __name__=='__main__':main()
