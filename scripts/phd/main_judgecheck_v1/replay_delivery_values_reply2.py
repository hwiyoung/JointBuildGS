"""Recompute all section 6/7 tables using only delivered per-core/per-photo values."""
import json,sys
import numpy as np
import metrics_reply2 as M
from export_reply2 import CORE_STACKED,PHOTO_STACKED
from geometry import loadz,savez
from preflight import C,D,O,Path,sha,dump,now

def main(source=None):
    source=Path(source) if source else O;replay=O/'r2/replay_delivery';outputs=replay/'reports';(outputs/'tables').mkdir(parents=True,exist_ok=True)
    inputs={}
    for folder,stacked in [('core_points',CORE_STACKED),('photo_points',PHOTO_STACKED)]:
        for path in sorted((source/folder).glob('*__*.npz')):
            g=loadz(path);inputs[str(path)]=sha(path)
            for kind in np.unique(g['kind']):
                keep=g['kind']==kind
                data={k:(v[:,keep] if k in stacked else v[keep]) for k,v in g.items()}
                savez(replay/folder/f'{path.stem}__{kind}.npz',**data)
    assert inputs,'No canonical delivery NPZ files found'
    M.BASE=replay;M.D=outputs
    for group in range(3):M.main(group)
    checks=[]
    reference_tables=source/'tables' if (source/'tables').exists() else D/'tables'
    for path in sorted((outputs/'tables').glob('*.json')):
        original=reference_tables/path.name;current=json.loads(path.read_text());expected=json.loads(original.read_text())
        assert current['rows']==expected['rows'],path.name
        assert current['excluded_shared_cores']==expected['excluded_shared_cores'],path.name
        checks.append(dict(table=path.name,rows=len(current['rows']),reference_sha256=sha(original)))
    assert len(checks)==30,len(checks)
    result=dict(at=now(),status='PASS_ALL_SECTION_6_7_TABLES_REPLAYED_FROM_DELIVERY_VALUES',tables=checks,input_files=inputs,
        raw_photos_or_point_clouds_read=False,original_curves_read=False,holdout_read=False,training=False,
        source_sha256={p.name:sha(p) for p in [Path(__file__),Path(M.__file__)]},scientific_verdict=None)
    dump(replay/'verification.json',result);dump(D/'replay_delivery_reply2.json',result);print(result['status'],len(checks),flush=True)

if __name__=='__main__':main(sys.argv[1] if len(sys.argv)>1 else None)
