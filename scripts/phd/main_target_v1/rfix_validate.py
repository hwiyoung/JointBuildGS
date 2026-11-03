"""Independent CPU checks of saved measurements, aggregates and archived row evidence."""
import numpy as np
from common import *
ROOT=OUT/'rfix';DEST=DOC/'rfix'

def main():
 cfg=json.loads((CFG/'rfix.json').read_text());summary=json.loads((DEST/'tables/state_summary.json').read_text())['rows'];assert len(summary)==8
 checks=[]
 for state in cfg['states']:
  key=state['key'];d=json.loads((ROOT/'states'/key/'result.json').read_text());g=json.loads((ROOT/'gradients'/key/'result.json').read_text());s=next(x for x in summary if x['state']==key)
  assert [r['camera'] for r in d['records']]==cfg['views'] and len(d['records'])==203
  assert [r['camera'] for r in g['rows']]==state['gradient_views'] and len(g['rows'])==30
  assert set(state['original_top5']+['DJI_20241217102535_0020_D','DJI_20241217091133_0109_D'])<=set(state['gradient_views'])
  assert d['optimization_steps']==g['optimization_steps']==0
  before=sum(r['performance'][1]['overlaps'] for r in d['records']);after=sum(r['performance'][2]['overlaps'] for r in d['records'])
  assert before==s['original_overlaps_sum']==d['original_overlaps'] and after==s['fixed_overlaps_sum']==d['fixed_overlaps']
  burst_n=0;burst_ov=0;contrib=0;raw_files=[]
  for row in d['records']:
   assert len(row['performance'])==3 and row['performance'][0]['overlaps']==row['performance'][1]['overlaps']
   assert row['performance'][2]['overlaps']<=row['performance'][1]['overlaps']
   for name,m in row['comparison'].items():
    assert m['pass_']==(m.get('nonfinite_masks_equal',True) and m['max_abs']<=m['jitter_max_abs'])
    assert m.get('nonfinite_count',0)==0,(key,row['camera'],name,'nonfinite')
   assert row['pass_']==all(m['pass_'] for m in row['comparison'].values())
   p=ROOT/'states'/key/'bursts'/(row['camera']+'.npz')
   with np.load(p) as z:
    n=len(z['id']);assert n==row['pairs'];assert len(np.unique(z['id']))==n
    assert (z['radius']>np.hypot(row['width'],row['height'])).all()
    assert all(len(z[k])==n for k in z.files)
    overlaps=int(z['tiles'].astype('i8').sum());positive=int((z['sum_w']>0).sum())
    assert overlaps==row['burst_overlaps'] and positive==row['burst_color_contributors']
    assert np.array_equal(z['max_w']>0,z['sum_w']>0)
    assert (z['disc_nearest_depth']<=z['disc_farthest_depth']).all()
    burst_n+=n;burst_ov+=overlaps;contrib+=positive
   raw_files.append(dict(path=str(p),sha256=sha(p)))
  failed=0;max_delta=0.;saved_rows=0
  for row in g['rows']:
   assert len(row['parameters'])==7 and row['radii_equal']
   assert row['pass_']==all(m['pass_'] for m in row['parameters'].values())
   for m in row['parameters'].values():
    assert m['pass_']==(m['nonfinite_masks_equal'] and m['fixed_max_abs']<=m['jitter_max_abs'])
    failed+=not m['pass_'];max_delta=max(max_delta,m['fixed_max_abs'])
   p=ROOT/'gradients'/key/(row['camera']+'_differing_rows.npz')
   if p.exists():
    with np.load(p) as z:
     assert len(z['ids'])==len(z['xyz']) and len(np.unique(z['ids']))==len(z['ids']);saved_rows+=len(z['ids'])
     for name,m in row['parameters'].items():
      delta=float(np.abs(z['original_a_'+name].astype('f8')-z['fixed_'+name]).max())
      assert delta==m['fixed_max_abs'],(key,row['camera'],name,delta,m['fixed_max_abs'])
  assert failed==s['gradient_comparisons_failed'] and max_delta==s['max_gradient_abs']
  grouped=json.loads((DEST/'tables/burst_groups.json').read_text())['rows'];ours=[r for r in grouped if r['state']==key]
  assert sum(r['pairs'] for r in ours)==burst_n and sum(r['color_contributing'] for r in ours)==contrib
  checks.append(dict(state=key,views=203,gradient_views=30,raw_burst_files=len(raw_files),burst_pairs=burst_n,burst_overlaps=burst_ov,actual_color_pairs=contrib,gradient_failed_comparisons=failed,saved_differing_rows=saved_rows,original_overlaps=before,fixed_overlaps=after,records_match_tables=True,scientific_verdict=None))
  dump(ROOT/'validation'/('raw_'+key+'.json'),dict(files=raw_files,scientific_verdict=None));print('VERIFIED',key,flush=True)
 for label in ['target','imageonly','geogs']:
  u=json.loads((ROOT/'units'/label/'result.json').read_text());assert u['status']=='PASS' and len(u['rows'])==4
  assert all(r['pass_'] and r['radii_equal'] and r['fixed_overlaps']==r['exact_visible_tiles'] for r in u['rows'])
 done=json.loads((DEST/'completion.json').read_text());assert done['forward_pairs']==1624 and done['gradient_pairs']==240
 expected=all(s['render_pass']==203 and s['gradient_pass']==30 and s['radii_all_equal'] and s['fixed_overlaps_sum']<s['original_overlaps_sum'] for s in summary)
 assert done['formal_pass']==expected
 status=json.loads((DEST/'report_status.json').read_text());assert status['training_started']==False and status['other_six_started']==False
 # Every scientific figure must have the requested three formats.
 pngs=list((DEST/'figures').glob('*.png'));assert pngs
 for p in pngs:
  assert p.with_suffix('.pdf').is_file() and p.with_suffix('.json').is_file()
 for p in (DEST/'tables').glob('*.csv'):
  assert p.with_suffix('.md').is_file() and p.with_suffix('.json').is_file()
 receipt=dict(at=stamp(),status='PASS_EVIDENCE_CONSISTENCY',acceptance_pass=expected,states=checks,figure_triplets=len(pngs),table_triplets=len(list((DEST/'tables').glob('*.csv'))),raw_gradient_recheck='saved differing rows only; full gradients compared during original GPU measurement',scientific_verdict=None)
 dump(DEST/'validation.json',receipt);dump(ROOT/'validation/result.json',receipt);print('RFIX_VALIDATION_PASS',flush=True)

if __name__=='__main__':main()
