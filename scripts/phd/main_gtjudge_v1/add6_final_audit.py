"""Check final archive integrity and that later work preserves the first delivery."""
from add6_common import *

protected=json.loads((W6/'previous_figures_sha256.json').read_text())
for name,h in protected.items():assert sha(R/name)==h,name
archives=[]
for kind in ['sections','precision']:
 receipt=json.loads((D/'verification'/f'addendum6_{kind}_archive.json').read_text());p=Path(receipt['path']);assert sha(p)==receipt['sha256']
 with zipfile.ZipFile(p) as z:
  assert z.testzip() is None;manifest=json.loads(z.read('manifest.json'))
  for item in manifest['files']:
   assert hashlib.sha256(z.read(item['member'])).hexdigest()==item['sha256']
   # The first archive intentionally contains the report as of its early delivery.
   if not (kind=='sections' and item['member']=='보고_덧붙임6.md'):assert sha(D/item['member'])==item['sha256']
 archives.append(receipt)
with (T6/'precision_where.csv').open() as f:rows=list(csv.DictReader(f))
assert len(rows)==144
for key in {(r['case'],r['method'],r['accuracy_version']) for r in rows}:
 part=[r for r in rows if (r['case'],r['method'],r['accuracy_version'])==key];whole=next(r for r in part if r['dimension']=='all')
 for dimension in ['LGDM_absence','stage2_quadrant','LGDM_absence_x_stage2']:
  group=[r for r in part if r['dimension']==dimension];assert sum(int(r['group_bad_n']) for r in group)==int(whole['bad_total_n']);assert sum(int(r['group_eligible_n']) for r in group)==int(whole['eligible_total_n']);assert abs(sum(float(r['pct_of_all_bad']) for r in group)-100)<1e-8
for p in F6.glob('*_precision_map.png'):
 j=json.loads(p.with_suffix('.json').read_text());im=Image.open(p);im.load();assert list(im.size)==j['size_px'] and im.info.get('icc_profile');assert j['text_in_figure'] is False and j['line_drawn'] is False
 for source in j['sources']:assert proof(source['path'])['sha256']==source['sha256']
lock=json.loads((C/'addendum6_building_execution.lock.json').read_text());selector=R/'scripts/phd/main_gtjudge_v1/add6_select.py';assert sha(selector)==lock['source_sha256'][str(selector.relative_to(R))];assert sha(C/'addendum6.json')==lock['config_sha256']
assert sha(W6/'c3_camera.json')==json.loads((C/'addendum6_camera.lock.json').read_text())['camera_sha256']
report=D/'보고_덧붙임6.md';assert len(report.read_text())<=3000
receipt=dict(at=now(),status='PASS_INTEGRITY_WITH_DISPLAY_LIMITATIONS',old_figure_files_preserved=len(protected),first_delivery_figure_and_table_bytes_preserved=True,archive_receipts=archives,precision_csv_rows=len(rows),report_characters=len(report.read_text()),visual_review='Section maps, four input/result check plots, twelve c3 MVS camera candidates, all primary panels and both precision maps inspected.',display_limitations='New c2 line is outside inherited frames; c3/c4 some inherited crops are partial. Source ortho depth unavailable; top annotations use explicitly recorded MVS proxy.',training_started=False,training_interrupted=False,scientific_verdict=None,code=[proof(p) for p in sorted((R/'scripts/phd/main_gtjudge_v1').glob('add6_*.py'))])
dump(D/'verification/addendum6_final.json',receipt);print('ADD6_FINAL_AUDIT',receipt['status'],receipt['precision_csv_rows'],receipt['report_characters'],flush=True)
