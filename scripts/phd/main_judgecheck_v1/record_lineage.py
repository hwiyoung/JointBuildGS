"""Final hashes for resumed payloads and raw neighbourhood sources; no GT reads."""
import json,os,time
from preflight import C,O,Path,sha,dump,now
BASE=O/'r1'

def main():
    started=time.monotonic();cfg=json.loads((C/'judgecheck_v1.json').read_text());W=Path(cfg['sources']['widen']);rows=[]
    tiles=sorted({p.stem.split('__')[0] for p in (BASE/'inputs').glob('*.npz')})
    for t in tiles:
        for name in ['mvs_a_xyz.npy','mvs_a_view.npy','mvs_a_key.npy','als_xyz.npy']:
            p=W/'holdout/internal/points'/t/name;s=p.stat();rows.append(dict(path=str(p),bytes=s.st_size,mtime_ns=s.st_mtime_ns,sha256=sha(p),role='raw_neighbourhood_no_building_outcomes'))
        print('LINEAGE',t,flush=True)
    local=[]
    for sub in ['inputs','photo_inputs','ring_recompute','geometry','photo_targets']:
        for p in sorted((BASE/sub).glob('*.npz')):local.append(dict(path=str(p.relative_to(BASE)),bytes=p.stat().st_size,sha256=sha(p)))
    dump(BASE/'resumed_lineage_final_hashes.json',dict(at=now(),timing='post-calculation integrity binding; not claimed to be a pre-calculation raw-byte lock',
        config_precalculation_lock=json.loads((C/'judgecheck_v1.reply1.lock.json').read_text()),
        raw_sources=rows,resumed_payloads=local,seconds=time.monotonic()-started,
        initial_preparation_included=False,GT_sources_read=False,scientific_verdict=None))
    print('LINEAGE_COMPLETE',len(rows),len(local),time.monotonic()-started)

if __name__=='__main__':main()
