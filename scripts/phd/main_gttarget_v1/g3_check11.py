"""Stage 3 order 11 checks that need the payload (CPU, read only):
 - the occlusion map used by the occl / occl_median extractions (O/stage1/<stem>/occl, read directly by g3_render_model.py) is the one stage 1 (order 4) saved:
   order-2 pixel count over every view = stage-1 ready.json totals.order2, and no occl file is newer than ready.json 'at'; a sha256 manifest of the files is written;
 - every table json in /docs/tables carries the title TITLE (rows or top level).
table check11 (+ payload checks/occl_manifest_<stem>.json)."""
import sys, datetime as dt_
sys.path.insert(0, '/repo/scripts/phd/main_gttarget_v1')
from gt_common import *
rows = []
for stem in STEMS:
    root = O/'stage1'/stem; rd = json.loads((root/'ready.json').read_text()); at = dt_.datetime.fromisoformat(rd['at']).timestamp()
    n2 = 0; newest = 0.; man = {}
    for f in sorted((root/'occl').glob('*.npz')):
        with np.load(f) as z: n2 += int((z['code'] == 2).sum())
        newest = max(newest, f.stat().st_mtime); man[f.name] = sha(f)
    dump(O/'checks'/f'occl_manifest_{stem}.json', dict(at=now(), stem=stem, files=man, scientific_verdict=None))
    rows.append(dict(title=TITLE, check='추출에 쓴 가림 지도 = 4절에서 저장한 것', stem=stem, files=len(man), order2_pixels_now=n2, order2_pixels_stage1=rd['totals']['order2'],
                     equal=n2 == rd['totals']['order2'], newest_file_not_after_stage1=newest <= at+1, manifest=f'payload checks/occl_manifest_{stem}.json'))
for p in sorted((D/'tables').glob('*.json')):
    d = json.loads(p.read_text()); ok = d.get('title') == TITLE if isinstance(d, dict) else False
    if isinstance(d, dict) and 'rows' in d and d['rows'] and isinstance(d['rows'][0], dict) and 'title' in d['rows'][0]: ok = ok and all(r.get('title') == TITLE for r in d['rows'] if 'title' in r)
    rows.append(dict(title=TITLE, check='표 제목에 참값 목표 판(진단용)', stem=p.name, equal=ok))
table('check11', rows); print('CHECK11', sum(1 for r in rows if not r.get('equal')), 'not equal', flush=True)
