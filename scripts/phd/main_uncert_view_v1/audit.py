"""Task 1: inventory and original table comparison. No source writes."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_uncert_view_v1')
from common import *

def main():
    records = []
    inventory = []
    keys = {}
    for site, prior in U.CASES:
        for r in (1., 1.5, 3.):
            p = SRC / 'patch_values' / f'{site}__{prior}__R{r:.1f}.npz'
            if not p.is_file(): raise SystemExit(f'STOP: missing patch values {p}')
            z = pv(site, prior, r)
            inventory.append(dict(path=str(p), bytes=p.stat().st_size, sha256=sha(p)))
            keys[f'{site}__{prior}'] = {k: dict(dtype=str(v.dtype), shape=v.shape) for k,v in z.items()}
            report = load(ROOT / f'docs/experiments/phd/main_uncert_v1/tables/R{r:.1f}/t1_value_share.json')['values']
            for d in L.DATAS[prior]:
                row = next(x for x in report if x['case']==U.case_ko(site,prior) and x['data']==U.DATA_KO[d] and x.get('face')=='전체')
                ev = z['in_eval'].astype(bool)
                got = float((z[d+'_status'][ev]==0).mean())
                records.append(dict(case=U.case_ko(site,prior), R=r, data=d, total=len(ev), eval=int(ev.sum()), band=int((~ev).sum()),
                    reported_eval=row['patches'], reported_value=row['value'], recounted_value=got,
                    match=int(ev.sum())==row['patches'] and abs(got-row['value'])<=.01))
    inputs = [ROOT/'configs/phd/main_uncert_v1/uncert_v1.json']
    inputs += sorted((ROOT/'scripts/phd/main_uncert_v1').glob('*'))
    inputs += sorted((ROOT/'docs/experiments/phd/main_uncert_v1').rglob('*'))
    inputs += sorted((SRC/'points').rglob('*.npy'))
    inputs += sorted((SRC/'work').glob('patches_*.npz')) + [SRC/'work/places.npz',SRC/'work/places.json',SRC/'work/ring_choice.json']
    inputs += sorted(Path('/s1/regions_v3').glob('regions_ext_v3_*.npz'))
    for p in inputs:
        if p.is_file(): inventory.append(dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p)))
    dump(DOC/'tables/input_audit.json', dict(made=now(), rows=records, keys=keys, inputs=inventory,scientific_verdict=None))
    progress('일 1 완료: 18개 패치 파일, 여섯 경우, 세 고리 크기와 원본 표 1 확인. 입력 파일 SHA-256 기록. 학습·GPU 사용 없음.')
    print(json.dumps(clean(dict(rows=records[::3], keys=keys['B0_b10__LoD2'], inputs=len(inventory))),ensure_ascii=False,indent=2))

if __name__=='__main__': main()
