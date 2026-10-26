"""Verify completed tile receipts before resuming with an equivalent image cache."""
from common import *
def main():
    rows=[]
    for f in sorted((O/'work/full').glob('*.npz')):
        if f.stem.endswith('_selection'):continue
        rec=load(f.with_suffix('.json'));assert rec['file_sha256']==sha(f);p=npz(f)
        assert len(p['point_id'])==rec['points']+rec.get('reused_pilot_points',0)
        rows.append(dict(file=f.name,points=len(p['point_id']),sha256=sha(f)))
    assert load(O/'gates/ram_cache.json')['status']=='PASS'
    dump(O/'gates/checkpoint_restart.json',dict(status='PASS',at=now(),reason='Intentional own-container stop after durable tile receipt to enable byte-identical original-JPEG RAM cache; exit 137 is an intentional restart, not a numerical failure.',files=rows,scientific_verdict=None));print('checkpoint verified',len(rows),sum(r['points'] for r in rows))
if __name__=='__main__':main()
