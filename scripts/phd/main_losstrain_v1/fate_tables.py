"""Unrounded seed-fate records with both region groups and readable counts."""
import json
import csv
from pathlib import Path
from inputs import save,sha

def main():
    rows=[]
    for p in sorted(Path('/docs/tables/fates').glob('*/*.json')):
        r=json.loads(p.read_text())
        if r['status']!='PASS':continue
        for group,x in r['regions'].items():
            for category,n in x['counts'].items():
                rows.append(dict(site=r['site'],prior=r['prior'],result=r['result'],group=group,category=category,
                    count=n,denominator=x['seeds_planted'],percent=100*x['shares'][category] if x['shares'][category] is not None else None,
                    region_patches=x['patches'],region_area_m2=x['area_m2'],source=str(p),source_sha256=sha(p),origin='[이 발주에서 냄]'))
    save('/docs/tables/fates_all.json',dict(rows=rows,scientific_verdict=None))
    if rows:
        with Path('/docs/tables/fates_all.csv').open('w') as f:
            w=csv.DictWriter(f,list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    lines=['# 심긴 점과 후손 묶음의 운명','',
        '각 처음 점과 후손을 한 묶음으로 센다. 지워짐 → 불투명도 0.5 이상 후손이 사전 면 0.25 m 안 → 그 밖에서 참값 면 0.2 m 안 → 둘 다 아님 순서다. 1단계 패치의 칸을 사용한다.','',
        '| 단위 | 사전 | 결과 | 칸 | 구분 | 수 | 처음 점 N | 비율 % |','|---|---|---|---|---|---:|---:|---:|']
    names=dict(removed='지워짐',old_place='옛 자리',current_surface='지금 면',neither='둘 다 아님')
    for r in rows:
        pct='확인 불가' if r['percent'] is None else f"{r['percent']:.5f}"
        lines.append(f"| {r['site']} | {r['prior']} | {r['result']} | {'1·3' if r['group']=='prior_wrong_1_3' else '0·2'} | {names[r['category']]} | {r['count']} | {r['denominator']} | {pct} |")
    Path('/docs/tables/fates_all.md').write_text('\n'.join(lines)+'\n');print('fate rows',len(rows),flush=True)

if __name__=='__main__':main()
