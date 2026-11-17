"""표 쓰기 (JC s7_tables.write 옮김): docs tables/ 에 csv, json(반올림 전), md(요약)."""
from common import *
import pandas as pd
TAB = D/'tables'
def write(name, df, md_cols=None, note='', md_filter=None):
    TAB.mkdir(parents=True, exist_ok=True); df.to_csv(TAB/f'{name}.csv', index=False)
    (TAB/f'{name}.json').write_text(json.dumps(dict(rows=json.loads(df.to_json(orient='records', force_ascii=False)), note=note, scientific_verdict=None), ensure_ascii=False, indent=0))
    m = df if md_filter is None else md_filter(df)
    if md_cols: m = m[md_cols]
    lines = ['| ' + ' | '.join(map(str, m.columns)) + ' |', '|' + '---|'*len(m.columns)]
    for r in m.itertuples(index=False): lines.append('| ' + ' | '.join('' if (isinstance(x, float) and not np.isfinite(x)) else (f'{x:.4g}' if isinstance(x, float) else str(x).replace('|', '/')) for x in r) + ' |')
    (TAB/f'{name}.md').write_text((note + '\n\n' if note else '') + '\n'.join(lines) + '\n')
