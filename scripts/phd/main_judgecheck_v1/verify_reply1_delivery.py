"""Verify the partial-report delivery boundary and final config/benchmark hashes."""
import ast,csv,hashlib,json,zipfile
import numpy as np
from preflight import C,D,O,Path,dump,sha,now

def main():
    base=O/'r1';p=base/'photo_benchmark';receipt=json.loads((D/'delivery_reply1_receipt.json').read_text())
    archive=D/receipt['archive'];assert sha(archive)==receipt['sha256'];assert archive.stat().st_size==receipt['bytes']<400_000_000
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None;lines=z.read('SHA256SUMS').decode().splitlines()
        for line in lines:
            h,n=line.split('  ',1);assert hashlib.sha256(z.read(n)).hexdigest()==h
        assert all(not n.startswith(('inputs/','photo_inputs/','source_snapshots/','holdout/')) for n in z.namelist())
    cfg=json.loads((C/'judgecheck_v1.json').read_text());lock=json.loads((C/'judgecheck_v1.reply1.lock.json').read_text())
    assert sha(C/'judgecheck_v1.json')==lock['config_sha256'];assert cfg['scientific_verdict'] is None
    for device in ['cpu','cuda']:
        a=json.loads((C/f'photo_score.{device}.lock.json').read_text())
        assert a['config_sha256']==sha(C/'judgecheck_v1.json');assert a['planes_sha256']==sha(p/'planes.npz')
        for name,h in a['source_sha256'].items():assert sha(Path(__file__).parent/name)==h
    with np.load(p/'planes.npz') as z:
        excluded={r['point_id'] for r in json.loads((base/'scope_audit.json').read_text())['rows']}
        assert not set(z['point_id'])&excluded and len(z['point_id'])==200
    for path in (D/'tables').glob('reply1_*.csv'):
        rows=list(csv.DictReader(path.open()));ex=[r for r in rows if r['row_type']=='excluded_shared_photo_cores']
        assert len(ex)==1 and int(ex[0]['excluded_core_count'])==73 and float(ex[0]['excluded_area_m2'])==5.442552935831812
    report=(D/'판단검증_보고가_v1.md').read_text();assert len(report)<20000 and '부분 보고' in report and '22개' in report and '미완료' in report
    assert not (O/'core_points').exists() and not (O/'photo_points').exists() and not (O/'holdout').exists()
    for path in Path(__file__).parent.glob('*.py'):ast.parse(path.read_text())
    result=dict(at=now(),status='PASS_REPLY1_FINAL_DELIVERY_AUDIT',config_sha256=sha(C/'judgecheck_v1.json'),
        archive_sha256=receipt['sha256'],files_checked=len(lines),report_characters=len(report),
        initial_preparation_absent=True,excluded_shared_points_absent=True,all_current_csv_tables_exclusion_row=True,
        report_a_complete=False,holdout_values_opened=False,scientific_verdict=None)
    dump(D/'delivery_reply1_verification.json',result);print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
