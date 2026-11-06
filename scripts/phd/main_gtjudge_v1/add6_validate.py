"""Verify selection arithmetic, saved scoring populations, sources, frames and preservation."""
from add6_common import *
from add6_render import camera

def main(stage='sections'):
 protected=json.loads((W6/'previous_figures_sha256.json').read_text())
 for name,h in protected.items():assert sha(R/name)==h,name
 checks=[]
 for c in AC['cases']:
  key=c['id'].split('_')[0];rec=selected(c);s=rec['section'];root=root_of(c);row=loadz(root/'rows.npz');lab=loadz(root/'stage1_cells.npz')['case_id'];take=section_mask(row['xyz'],s);target=take&(lab==c['case_id']);data=json.loads((F6/f"{c['id']}_section_data.json").read_text())
  with (T6/f"section_candidates_{c['id']}.csv").open() as f:candidates=list(csv.DictReader(f))
  for r in candidates:
   if not int(r['n_case_points']):continue
   ordered=list(A6['targets'][key]);rank=all(float(r[a+'_completeness_pct'])+1>=float(r[b+'_completeness_pct'])-1e-10 for i,a in enumerate(ordered) for b in ordered[i+1:]);assert rank==(r['condition2_pass']=='True')
   assert abs(float(r['score_sum_abs_pp'])-sum(abs(float(r[m+'_completeness_pct'])-v) for m,v in A6['targets'][key].items()))<1e-9
   for m in methods(c):assert abs(sum(float(r[m+'_'+k]) for k in ['completeness_pct','far_pct','none_pct'])-100)<1e-8
  eligible=[r for r in candidates if int(r['n_case_points'])>=A6['minimum_points'][key]];ranked=[r for r in eligible if r['condition2_pass']=='True'];pool=ranked or eligible;expected=min(pool,key=lambda r:(float(r['score_sum_abs_pp']),-int(r['n_case_points']),r['candidate_id']));assert rec['selection']['candidate_id']==expected['candidate_id'];assert rec['rank_fallback']==(not bool(ranked));assert int(target.sum())==data['reference_points_target_case']==rec['selection']['n_case_points'];assert len(data['gt_points'])==int(take.sum())
  for m in methods(c):
   z=loadz(root/'distances'/f'{m}.npz',['row_s'])['row_s'];v=values(z[target],row['row_tau_m'][target]);assert v==data['strip_metrics'][m]
   for i,p in zip(np.flatnonzero(take),data['gt_points']):
    assert p['row_id']==int(i) and p['case_id']==int(lab[i]);assert p['scores'][m]['status']==str(status(np.array([z[i]]),np.array([row['row_tau_m'][i]]))[0]);assert (p['scores'][m]['signed_distance_m'] is None and not np.isfinite(z[i])) or p['scores'][m]['signed_distance_m']==float(z[i])
  for source in data['sources']:assert proof(source['path'])['sha256']==source['sha256']
  for panel in data['section_check']['panels']:assert abs(panel['vertical_exaggeration']-3)<.01
  if key=='c1':assert rec['selection']['direction']=='perpendicular';assert abs(np.dot(np.array(data['line']['direction_unit_xy']),rec['principal_axis_xy']))<1e-10
  frames=[]
  if stage!='sections':
   cam=camera(c)
   for method in ['FINALTRAIN_30000','fusion','GeoGS_30000']:
    j=json.loads((F6/f"{c['id']}_result_dist_{method}.json").read_text());assert j['camera']==cam;assert j['method']==method;assert j['line_drawn'] is False;frames.append(dict(method=method,line_inside_fraction=float(np.mean(j['line_points_inside_image'])),removed_triangles=len(j['removed_original_triangle_ids'])))
   if key=='c3':assert 45<=cam['elevation_deg']<=70 and cam['output_size_px']==[1600,2000];assert json.loads((F6/f"{c['id']}_wrong_dist_v2.json").read_text())['camera']==cam
   else:assert cam==getcase(c)['camera']
   for p in F6.glob(c['id']+'*.json'):
    if p.name.endswith(('_section_data.json','_section_check.json','_precision_map.json')) or '_result_dist_' in p.name:continue
    j=json.loads(p.read_text());line=j['line_polyline_px'];assert len(line)==len(j['line_occluded'])==len(j['line_points_inside_image'])==257;assert j['A_px']==line[0] and j['Aprime_px']==line[-1];assert j['line_drawn'] is False
    frames.append(dict(method=p.stem.removeprefix(c['id']+'_'),line_inside_fraction=float(np.mean(j['line_points_inside_image'])),removed_triangles=len(j.get('removed_original_triangle_ids',[]))))
  checks.append(dict(case=c['id'],selected_candidate=expected['candidate_id'],target_case_n=int(target.sum()),all_strip_n=int(take.sum()),rank_condition=rec['selection']['condition2_pass'],rank_fallback=rec['rank_fallback'],source_scores_reused=True,frames=frames))
 if stage!='sections':
  for p in F6.glob('*.png'):
   j=json.loads(p.with_suffix('.json').read_text());im=Image.open(p);im.load();assert im.info.get('icc_profile');assert list(im.size)==j['size_px'];assert j['text_in_figure'] is False and j['scientific_verdict'] is None
   assert j['config_sha256']==sha(C/'addendum6.json')
   for source in j['sources']:assert proof(source['path'])['sha256']==source['sha256'],source['path']
 dump(D/'verification'/f'addendum6_{stage}.json',dict(at=now(),status='PASS_SELECTION_SAVED_SCORES_AND_PRESERVATION',old_figure_files_preserved=len(protected),checks=checks,training_started=False,training_interrupted=False,scientific_verdict=None));print('ADD6_VERIFIED',stage,json.dumps(checks,ensure_ascii=False),flush=True)

if __name__=='__main__':main(*sys.argv[1:])
