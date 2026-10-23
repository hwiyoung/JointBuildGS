"""Readable Markdown companions; complete precision stays in JSON/CSV."""
import csv
import json
from pathlib import Path
from analysis_common import DOC,csvwrite
def cell(v):
    if v is None:return '확인 불가'
    if isinstance(v,float):return f'{v:,.6g}'
    return str(v).replace('|',' / ').replace('\n',' ')
def main():
    # Supplementary input/audit JSONs also receive CSV and Markdown companions.
    # Nested values remain exact JSON cells; the source JSON is unchanged.
    for p in sorted((DOC/'tables').glob('*.json')):
        if p.with_suffix('.csv').exists():continue
        obj=json.loads(p.read_text())
        rows=obj.get('rows') if isinstance(obj,dict) else obj
        if not isinstance(rows,list) or not all(isinstance(r,dict) for r in rows):
            rows=[dict(field=k,value=v) for k,v in obj.items()] if isinstance(obj,dict) else [dict(value=obj)]
        csvwrite(p.with_suffix('.csv'),rows)
    sections=[
        ('맞는쪽칸_넓이',['prior','cell_ko','patches','area_m2','fraction','difference_missing_area_m2']),
        ('차의크기_비율',['prior','scope','cell','shape','valid_patches','difference_area_m2','fraction_abs_gt_0.5m','fraction_abs_gt_1m','fraction_abs_gt_2m','fraction_positive']),
        ('시험자리_요약',['prior','cell_ko','patches','area_m2','components','components_under_1m2','area_under_1m2','radius_m']),
        ('건물에_붙지않은_패치',['prior','unattached_patches','unattached_area_m2','attached_to_buildings_outside_scope_patches']),
        ('계산_어림',['site','result','training_seconds','gpu_peak_minus_idle_GiB','final_gaussians','full_area_hours_linear','full_images_hours_linear','all_buffered_tiles_hours_linear']),
        ('확인용_봉인',['prior','buildings_with_assigned_patches','patches','area_m2','fraction_patches_with_GT'])]
    L=['# 핵심 표 [이 발주에서 냄]','','표시만 유효숫자 6자리로 줄였다. 반올림 전 값·각 열의 출처·생성 스크립트는 같은 이름의 JSON/CSV에 있다. scientific_verdict: null.','']
    for name,keys in sections:
        p=DOC/'tables'/f'{name}.json';j=json.loads(p.read_text());L += [f'## {name}','',f'[JSON]({name}.json) · [CSV]({name}.csv)','', '| '+' | '.join(keys)+' |','| '+' | '.join(['---']*len(keys))+' |']
        for r in j['rows']:L.append('| '+' | '.join(cell(r.get(k)) for k in keys)+' |')
        L += ['']
    (DOC/'tables/핵심표.md').write_text('\n'.join(L)+'\n')
    # Every CSV table also has a complete Markdown companion. Read the CSV
    # strings directly so this full version preserves its unrounded values.
    for p in sorted((DOC/'tables').glob('*.csv')):
        with p.open(encoding='utf-8-sig',newline='') as f:
            reader=csv.DictReader(f);keys=reader.fieldnames or [];rows=list(reader)
        lines=[f'# {p.stem} [이 발주에서 냄]','',
            f'출처·정의·생성 스크립트: [{p.stem}.json]({p.stem}.json). scientific_verdict: null.','',
            '| '+' | '.join(keys)+' |','| '+' | '.join(['---']*len(keys))+' |']
        for row in rows:lines.append('| '+' | '.join(cell(row.get(k,'')) for k in keys)+' |')
        p.with_suffix('.md').write_text('\n'.join(lines)+'\n')
    entries=[]
    for p in sorted((DOC/'tables').glob('*.json')):
        j=json.loads(p.read_text());n=len(j['rows']) if isinstance(j,dict) and isinstance(j.get('rows'),list) else None
        entries.append(f"- [{p.stem}]({p.name})"+(f' · {n}행' if n is not None else '')+(f' · [CSV]({p.stem}.csv)' if p.with_suffix('.csv').exists() else ''))
    (DOC/'tables/표_목록.md').write_text('# 표 목록\n\n'+ '\n'.join(entries)+'\n')
    print('Markdown table companions written')
if __name__=='__main__':main()
