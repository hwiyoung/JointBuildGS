"""Final payload consistency across the presentation and palette-only deliveries."""
from add4_common import *

def main():
 recolor=json.loads((D/'verification/addendum5_recolor.json').read_text());before=json.loads((AW/'verification/addendum5_before.json').read_text())
 assert recolor['other_figure_bytes_unchanged']
 for p,h in before['protected'].items():assert sha(p)==h,p
 names=['발표사례그림','발표실험대상','늘보존','사례사진색고침'];archives=[]
 for name in names:
  p=O/'delivery'/f'PHD-MAIN-GTJUDGE-v1_{name}.zip'
  with zipfile.ZipFile(p) as z:
   assert z.testzip() is None;j=json.loads(z.read('manifest.json'))
   for row in j['files']:
    assert hashlib.sha256(z.read(row['member'])).hexdigest()==row['sha256'];assert sha(D/row['member'])==row['sha256'],row['member']
   archives.append(dict(path=str(p),sha256=sha(p),members=len(z.namelist()),bytes=p.stat().st_size))
 for c in AC['cases']:
  for tag in ['top','top_crop']:
   j=json.loads((AF/f"{c['id']}_{tag}.json").read_text());assert j['paint_order_case_ids']==[0,3,1,2,4];assert j['case_colors']=={'0':'#7FA7D9','1':'#1D9E75','2':'#D85A30','3':'#8C95A3','4':'#F0A07F'}
 c=case('c3');camera=getcase(c)['camera']
 for tag in ['context_MVS_cutaway','wrong_gray','wrong_dist','truth_gray','prior_gray']:
  p=AF/f"{c['id']}_{tag}.json";j=json.loads(p.read_text());assert j['camera']==camera
  for src in j['sources']:assert proof(src['path'])['sha256']==src['sha256'],src['path']
 detail=json.loads((AF/f"{c['id']}_input_section_detail.json").read_text());l,t,r,b=detail['plot_bounds_px'];x0,x1,z0,z1=detail['axis_bounds'];assert abs((r-l)/(x1-x0)-(b-t)/(z1-z0))<1e-9;assert detail['reference_points_total']==237
 for src in detail['sources']:assert proof(src['path'])['sha256']==src['sha256'],src['path']
 dump(D/'verification/addendum45_delivery.json',dict(at=now(),status='PASS_CURRENT_FILES_ARCHIVES_AND_PALETTE_SCOPE',archives=archives,addendum5_protected_figure_bytes_unchanged=True,c3_camera_clip_and_detail_axes_match=True,scientific_verdict=None))
 print('ADD45_FINAL_VERIFIED',json.dumps(archives,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
