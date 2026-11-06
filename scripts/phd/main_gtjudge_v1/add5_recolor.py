"""Addendum 5 changes eight top-view images only; verify every other figure byte."""
from add4_common import *
from add4_figures import tops

def main():
 cfg=json.loads((C/'addendum5.json').read_text());assert sha(C/'addendum5.json')==json.loads((C/'addendum5.lock.json').read_text())['config_sha256']
 target=[AF/f"{c['id']}_{tag}{suffix}" for c in AC['cases'] for tag in ['top','top_crop'] for suffix in ['.png','.json']];target_set=set(target)
 protected={p:sha(p) for p in AF.rglob('*') if p.is_file() and p not in target_set};old={p:json.loads(p.read_text()) for p in target if p.suffix=='.json'}
 dump(AW/'verification/addendum5_before.json',dict(protected={str(p):h for p,h in protected.items()},top_metadata={str(p):j for p,j in old.items()},scientific_verdict=None))
 for c in AC['cases']:tops(c['id'])
 preserved=['case_point_counts','point_diameter_m','point_alpha','A_px','Aprime_px','box_corners_px','bounds_uv','size_px']
 checks=[]
 for p,before in old.items():
  after=json.loads(p.read_text())
  for k in preserved:assert after[k]==before[k],(str(p),k)
  assert after['case_colors']==cfg['case_colors'];assert after['paint_order_case_ids']==[0,3,1,2,4]
  im=Image.open(p.with_suffix('.png'));assert im.info.get('icc_profile') and im.width>=1600;assert not after['text_in_figure']
  checks.append(dict(path=str(p),coordinates_counts_dimensions_opacity_unchanged=True,colors=after['case_colors'],paint_order=after['paint_order_case_ids']))
 changed=[str(p) for p,h in protected.items() if sha(p)!=h];assert not changed,changed
 files=sorted(target);dest=O/'delivery/PHD-MAIN-GTJUDGE-v1_사례사진색고침.zip';rows=[dict(member=str(p.relative_to(D)),sha256=sha(p),bytes=p.stat().st_size) for p in files]
 with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  for p,r in zip(files,rows):z.write(p,r['member'])
  z.writestr('manifest.json',json.dumps(dict(task_id='PHD-MAIN-GTJUDGE-v1',addendum=5,files=rows,configuration=cfg,scope='eight top/top_crop PNGs and their JSONs only',scientific_verdict=None),ensure_ascii=False,indent=2))
 with zipfile.ZipFile(dest) as z:
  assert z.testzip() is None
  assert len(z.namelist())==17
  for r in rows:assert hashlib.sha256(z.read(r['member'])).hexdigest()==r['sha256']
 out=dict(at=now(),status='PASS_EIGHT_TOP_IMAGES_ONLY',protected_figure_files=len(protected),other_figure_bytes_unchanged=True,checks=checks,archive=dict(path=str(dest),sha256=sha(dest),bytes=dest.stat().st_size,members=17),training_started=False,training_interrupted=False,presentation_name_only={'fusion':'LGDM'},scientific_verdict=None)
 dump(D/'verification/addendum5_recolor.json',out);print('ADD5_DELIVERED',json.dumps(out['archive'],ensure_ascii=False),flush=True)
if __name__=='__main__':main()
