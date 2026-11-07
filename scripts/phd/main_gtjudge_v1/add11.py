"""Ordered addendum11 continuation of add2_scores, using stored point arrays."""
from common import *
import sys,gc,zipfile,io,shutil,time
import numpy as np
from cylinder import Cylinder
from normal_line import cases
from add2_scores import metric_rows

A=json.loads((C/'addendum11.json').read_text());assert sha(C/'addendum11.json')==json.loads((C/'addendum11.lock.json').read_text())['config_sha256']
W=O/'addendum11';T=D/'tables/addendum11';F=D/'figures/addendum11'
for folder in [W,T,F,W/'interim_data',W/'final_data']:folder.mkdir(parents=True,exist_ok=True)
TAU=list(csv.DictReader((R/'docs/experiments/phd/main_release_v1/tables/stage0/tau_values.csv').open()))
SCORE_KEYS=['row_s','sample_s','sample_eligible','sample_reference_row','sample_tau']
TREES={};INPUTS={};TABLES=[];TAUTABLES=[];CHECKS=[];POOLS={};METHOD_RECEIPTS=[]

def proof(p):
 p=Path(p);key=str(p)
 if key not in INPUTS:INPUTS[key]=dict(path=key,sha256=sha(p),bytes=p.stat().st_size)
 return INPUTS[key]

def meta(**kw):return dict(at=now(),scientific_verdict=None,config_sha256=sha(C/'addendum11.json'),source_commit=os.environ.get('GTJUDGE_COMMIT'),container_image=os.environ.get('GTJUDGE_IMAGE'),python=sys.version,numpy=np.__version__,**kw)

def write_csv(path,rows):
 fields=list(dict.fromkeys(k for r in rows for k in r));path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');w.writeheader()
  for r in rows:w.writerow({k:json.dumps(v) if isinstance(v,(list,dict)) else v for k,v in r.items()})

def npz_arrays(z,arrays,prefix=''):
 for name,a in arrays.items():
  with z.open(prefix+name+'.npy','w',force_zip64=True) as f:np.lib.format.write_array(f,np.asarray(a),allow_pickle=False)

def sources(site,prior,m):
 root=O/'scenes'/f'{site}__{prior}';p=root/'distances'/f'{m}.npz';jpath=p.with_suffix('.json');j=json.loads(jpath.read_text());q=root/'distances'/f'{m}_samples.npz'
 if q.exists():xyz=q;norm=q
 else:xyz=Path(j['accuracy_sample_source']);norm=O/'shared'/site/j['mesh_sha256']/('cylinder_roof.npz' if prior=='ALS' else 'cylinder.npz')
 return p,jpath,xyz,norm,q.exists()

def get_tree(site):
 if site not in TREES:
  p=O/'reference'/site/'dense.npz';proof(p);ref=loadz(p,['xyz','wall','radius']);assert float(ref['radius'])==.05;tree=Cylinder(ref['xyz']);TREES[site]=(tree,ref['wall']);del ref
 return TREES[site]

def process(site,prior,ms,phase):
 stem=f'{site}__{prior}';root=O/'scenes'/stem;row=loadz(root/'rows.npz');cell=loadz(root/'stage1_cells.npz');lab=cell['case_id'];source=[root/'rows.npz',root/'stage1_cells.npz',O/'reference'/site/'dense.npz']
 ps=loadz(root/'distances/prior.npz',['row_s'])['row_s'];vs=loadz(root/'distances/mvs.npz',['row_s'])['row_s'];source.extend([root/'distances/prior.npz',root/'distances/mvs.npz'])
 labels={f:cases(ps,vs,row['row_tau_m']*f)[0] for f in A['tau_multipliers']};assert np.array_equal(labels[1.],lab),'Inherited stage1 cells must equal normal-line tau1 labels'
 oldpath=D/'tables/addendum2/stage1'/f'{stem}.csv';source.append(oldpath);oldtable=list(csv.DictReader(oldpath.open()));oldlookup={(r['method'],r['surface'],str(r['case_id'])):r for r in oldtable}
 for m in ms:source.extend(sources(site,prior,m)[:4])
 for p in source:proof(p)
 dump(W/'locks'/f'{phase}_{stem}.json',meta(sources=[INPUTS[str(p)] for p in dict.fromkeys(source)]))
 tree,refwall=get_tree(site);dest=W/('interim_data' if phase=='interim' else 'final_data')/(stem+'.npz');parent=W/'interim_data'/dest.name
 if phase=='final' and parent.exists():shutil.copy2(parent,dest)
 new=not dest.exists();archive=zipfile.ZipFile(dest,'w' if new else 'a',compression=zipfile.ZIP_DEFLATED,compresslevel=4,allowZip64=True)
 if new:npz_arrays(archive,dict(point_id=np.arange(len(lab),dtype='i8'),xyz=row['xyz'].astype('f4'),normal=row['normal'].astype('f4'),case_id=lab.astype('i1'),wall=row['wall'].astype('u1'),tau_m=row['row_tau_m'].astype('f4'),eligible=np.ones(len(lab),'u1')),prefix='reference__')
 for m in ms:
  started=time.monotonic();p,jpath,xpath,npath,direct=sources(site,prior,m);z=loadz(p,SCORE_KEYS);old_s=z['sample_s'].copy();oldfinite=np.isfinite(old_s);oldeligible=z['sample_eligible'].astype(bool);N=len(old_s)
  if direct:q=loadz(xpath,['xyz','normal']);P=q['xyz'];normal=q['normal'];del q;nearest=None
  else:P=loadz(xpath,['sample_xyz'])['sample_xyz'];q=loadz(npath,['sample_normal','sample_nearest']);normal=q['sample_normal'];nearest=q['sample_nearest'];del q
  assert P.shape==normal.shape==(N,3);steep=(abs(normal[:,2])<.5) if prior=='ALS' else np.zeros(N,bool)
  if prior=='ALS':wall=np.zeros(N,bool)
  elif nearest is not None:wall=refwall[nearest]
  else:
   tau=next(t for t in TAU if t['site']==site and t['prior']==prior);wall=np.isclose(z['sample_tau'],float(tau['wall_tau_m']),rtol=0,atol=1e-6);assert np.all(wall|np.isclose(z['sample_tau'],float(tau['roof_tau_m']),rtol=0,atol=1e-6))
  normal_unit=normal.astype(float);normal_unit/=np.linalg.norm(normal_unit,axis=1)[:,None];observed=oldeligible.copy();missing=np.flatnonzero(~oldeligible);newcalc=0;large_hits=0
  for start in range(0,len(missing),100000):
   ids=missing[start:start+100000];limits=np.where(wall[ids],5.,10.);_,found=tree.query(P[ids],normal_unit[ids],limits,1.);hit=found>=0;observed[ids]=hit;large_hits+=int(hit.sum());need=ids[hit&~steep[ids]&~oldfinite[ids]]
   if len(need):s,_=tree.query(P[need],normal_unit[need],np.where(wall[need],5.,10.),.05);z['sample_s'][need]=s;newcalc+=len(need)
  assert np.array_equal(z['sample_s'][oldeligible|oldfinite],old_s[oldeligible|oldfinite],equal_nan=True);z['sample_observed_cylinder_1m']=observed
  # Small reusable cache permits reporting/repackaging without any geometry query.
  cache=W/'cache'/stem/(m+'.npz');savez(cache,sample_s=z['sample_s'],observed=observed,steep=steep,wall=wall)
  prepared=dict(row=row,cells=cell,scores={m:z},steep={m:steep});base=metric_rows(site,prior,[m],True,prepared=prepared,accuracy_rule='normal_cylinder_1m',extended=True)
  for r in base:
   key=(m,r['surface'],str(r['case_id']));old=oldlookup.get(key)
   if old:
    for newkey,oldkey in [('completeness_pct','completeness_pct'),('accuracy_old_pct','accuracy_pct')]:
     expected=float(old[oldkey]) if old[oldkey] else None;actual=r[newkey];diff=abs(actual-expected) if actual is not None and expected is not None else 0.;assert (actual is None)==(expected is None) and diff<=.1,(stem,key,newkey,diff);CHECKS.append(dict(scene=stem,method=m,surface=r['surface'],case_id=r['case_id'],metric=newkey,difference_pp=diff))
  TABLES.extend(base)
  for mode in ['fixed_cases','reclassified_cases']:
   for f in A['tau_multipliers']:
    rr=base if f==1 else metric_rows(site,prior,[m],True,prepared=prepared,accuracy_rule='normal_cylinder_1m',tau_multiplier=f,case_override=lab if mode=='fixed_cases' else labels[f],distance_statistics=False)
    for r in rr:TAUTABLES.append(dict(site=site,prior=prior,method=m,surface=r['surface'],case_id=r['case_id'],mode=mode,tau_multiplier=f,n_gt=r['gt_n'],n_result=r['result_n'],reference_in_n=round(r['completeness_pct']*r['gt_n']/100) if r['gt_n'] else 0,result_in_n=round(r['accuracy_pct']*r['result_n']/100) if r['result_n'] else 0,completeness_pct=r['completeness_pct'],accuracy_new_pct=r['accuracy_pct']))
  ix=z['sample_reference_row'];ok=ix>=0;qc=np.full(N,-1,'i1');qc[ok]=lab[ix[ok]];eligible=observed&~steep;hit=np.isfinite(z['sample_s']);state=np.zeros(N,'u1');state[~oldeligible&eligible]=1;state[eligible&~hit]=4;state[~observed]=2;state[steep]=3
  arrays=dict(point_id=np.arange(N,dtype='i8'),xyz=P.astype('f4'),normal=normal.astype('f4'),case_id=qc,wall=wall.astype('u1'),reference_row_id=ix.astype('i4'),tau_m=z['sample_tau'].astype('f4'),s_m=(-z['sample_s']).astype('f4'),state=state,eligible_old=(oldeligible&~steep).astype('u1'),eligible_new=eligible.astype('u1'),observed_old=oldeligible.astype('u1'),observed_new=observed.astype('u1'),steep=steep.astype('u1'),reference_found=hit.astype('u1'),distance_evaluated=(oldeligible|(observed&~steep)|oldfinite).astype('u1'),within_tau1=(hit&(abs(z['sample_s'])<=z['sample_tau'])).astype('u1'))
  npz_arrays(archive,dict(s_m=z['row_s'].astype('f4'),state=np.where(np.isfinite(z['row_s']),0,1).astype('u1'),within_tau1=(np.isfinite(z['row_s'])&(abs(z['row_s'])<=row['row_tau_m'])).astype('u1')),prefix='reference__'+m+'__');npz_arrays(archive,arrays,prefix='result__'+m+'__')
  if phase=='interim':
   group='ALS_pooled' if prior=='ALS' else 'B0_LoD2'
   for k in A['presentation_cases']:
    for direction,vals in [('reference',abs(z['row_s'][(lab==k)&np.isfinite(z['row_s'])])),('result',abs(z['sample_s'][(qc==k)&eligible&hit]))]:POOLS.setdefault((group,k,m,direction),[]).append(vals.copy())
  if stem=='B173nb_b10__ALS' and m in ['FINALTRAIN_30000','2DGS_30000']:
   pick=qc==1;savez(W/'figure_points'/(m+'.npz'),xyz=P[pick].astype('f4'),state=state[pick],old=arrays['eligible_old'][pick],new=arrays['eligible_new'][pick],steep=steep[pick],s=z['sample_s'][pick],tau=z['sample_tau'][pick])
   newly=pick&eligible&~oldeligible;both=pick&~eligible&~(oldeligible&~steep);bad=newly&(~hit|(abs(z['sample_s'])>z['sample_tau']));METHOD_RECEIPTS.append(dict(figure_method=m,newly_included_case1_n=int(newly.sum()),newly_included_case1_bad_pct=100*bad.sum()/newly.sum() if newly.any() else None,newly_included_case1_far_hit_pct=100*(newly&hit&(abs(z['sample_s'])>z['sample_tau'])).sum()/newly.sum() if newly.any() else None,newly_included_case1_none_pct=100*(newly&~hit).sum()/newly.sum() if newly.any() else None,both_excluded_case1_n=int(both.sum()),both_excluded_steep_pct=100*(both&steep).sum()/both.sum() if both.any() else None,both_excluded_window_pct=None))
  receipt=dict(scene=stem,method=m,points=N,old_excluded_query_n=len(missing),new_observed_n=large_hits,missing_thin_distances_computed_n=newcalc,stored_distances_preserved=True,mesh_read=False,seconds=round(time.monotonic()-started,1),sources=[INPUTS[str(x)] for x in [p,jpath,xpath,npath]])
  dump(W/'receipts'/stem/(m+'.json'),meta(**receipt));print('ADD11_METHOD',phase,stem,m,N,len(missing),newcalc,receipt['seconds'],flush=True)
  del arrays,prepared,z,P,normal,normal_unit,old_s,oldfinite,oldeligible,missing;gc.collect()
 archive.close();dump(W/'point_manifests'/(phase+'_'+stem+'.json'),meta(path=str(dest),sha256=sha(dest),methods=A['presentation_methods']+ms if phase=='final' and parent.exists() else ms,float_dtype='float32'))

def presentation():
 rows=[];metrics=['completeness_pct','accuracy_old_pct','accuracy_new_pct','reference_mean_abs_m','reference_median_abs_m','reference_p95_abs_m','result_mean_abs_m','result_median_abs_m','result_p95_abs_m','reference_none_pct','result_none_pct']
 for group in ['ALS_pooled','B0_LoD2']:
  for k in A['presentation_cases']:
   current=[]
   for m in A['presentation_methods']:
    selected=[r for r in TABLES if r['surface']=='all' and r['case_id']==k and r['method']==m and (r['prior']=='ALS' if group=='ALS_pooled' else r['site']=='B0_b10' and r['prior']=='LoD2')];assert len(selected)==(3 if group=='ALS_pooled' else 1)
    r=dict(group=group,case_id=k,method=m,n_gt=sum(x['n_gt'] for x in selected),n_result_old=sum(x['result_old_n'] for x in selected),n_result_new=sum(x['result_new_n'] for x in selected),excluded_old_n=sum(x['excluded_old_n'] for x in selected),excluded_new_n=sum(x['excluded_new_n'] for x in selected))
    for metric,weight in [('completeness_pct','n_gt'),('accuracy_old_pct','result_old_n'),('accuracy_new_pct','result_new_n'),('reference_none_pct','n_gt'),('result_none_pct','result_new_n')]:
     n=sum(x[weight] for x in selected);r[metric]=sum((x[metric] or 0)*x[weight] for x in selected)/n if n else None
    for direction in ['reference','result']:
     vals=np.concatenate(POOLS[(group,k,m,direction)]);n=len(vals);r[direction+'_distance_n']=n;r[direction+'_mean_abs_m']=float(vals.mean()) if n else None;q=np.quantile(vals,[.5,.95]) if n else [None,None];r[direction+'_median_abs_m']=float(q[0]) if n else None;r[direction+'_p95_abs_m']=float(q[1]) if n else None
    current.append(r)
   for metric in metrics:
    vals=[r[metric] for r in current if r[metric] is not None];high=metric in ['completeness_pct','accuracy_old_pct','accuracy_new_pct'];best=(max(vals) if high else min(vals)) if vals else None
    for r in current:r[metric+'_gap_to_best']=None if r[metric] is None else best-r[metric] if high else r[metric]-best
   rows.extend(current)
 write_csv(T/'presentation.csv',rows);dump(T/'presentation.json',meta(rows=rows,weighting='completeness: reference N; accuracy: eligible result N separately per rule; means: finite-hit point N; medians/p95: pooled point arrays, not averages of scene quantiles; differences high-is-better for completeness/accuracy, low-is-better for distance and absence percentages; counts are denominators, not ranked scores'))
 return rows

def tau_summary():
 cells=[];summary=[]
 for mode in ['fixed_cases','reclassified_cases']:
  for f in A['tau_multipliers']:
   current=[]
   for group in ['ALS_pooled','B0_LoD2']:
    for k in A['presentation_cases']:
     rs=[]
     for m in A['presentation_methods']:
      ss=[r for r in TAUTABLES if r['mode']==mode and r['tau_multiplier']==f and r['surface']=='all' and r['case_id']==k and r['method']==m and (r['prior']=='ALS' if group=='ALS_pooled' else r['site']=='B0_b10' and r['prior']=='LoD2')];ng=sum(x['n_gt'] for x in ss);nr=sum(x['n_result'] for x in ss);rs.append(dict(mode=mode,tau_multiplier=f,group=group,case_id=k,method=m,n_gt=ng,n_result=nr,completeness_pct=100*sum(x['reference_in_n'] for x in ss)/ng if ng else None,accuracy_new_pct=100*sum(x['result_in_n'] for x in ss)/nr if nr else None))
     for metric in ['completeness_pct','accuracy_new_pct']:
      best=max((r[metric] for r in rs if r[metric] is not None),default=None)
      for r in rs:r[metric+'_gap_pp']=best-r[metric] if r[metric] is not None else None
     current+=rs
   cells+=current
   for m in A['presentation_methods']:
    rr=dict(mode=mode,tau_multiplier=f,method=m)
    for metric in ['completeness_pct','accuracy_new_pct']:
     available=[r for r in current if r['method']==m and r[metric+'_gap_pp'] is not None];worst=max(available,key=lambda r:r[metric+'_gap_pp']) if available else None;rr[metric+'_worst_gap_pp']=worst[metric+'_gap_pp'] if worst else None;rr[metric+'_worst_cell']=worst['group']+':'+str(worst['case_id']) if worst else '';rr[metric+'_available_cells']=len(available)
    summary.append(rr)
 write_csv(T/'tau_presentation_cells.csv',cells);write_csv(T/'tau_summary.csv',summary);dump(T/'tau_summary.json',meta(rows=summary));return summary

def snapshot(phase):
 write_csv(T/('full_'+phase+'.csv'),[r for r in TABLES if r['case_id']!='prior_absent']);write_csv(T/('tau_all_'+phase+'.csv'),[r for r in TAUTABLES if r['case_id']!='prior_absent']);write_csv(T/'old_rule_checks.csv',CHECKS);dump(T/'rule_diagnostic_numbers.json',meta(rows=METHOD_RECEIPTS));dump(W/(phase+'_input_lock.json'),meta(sources=list(INPUTS.values())));dump(W/(phase+'_state.json'),meta(tables=TABLES,tau=TAUTABLES,checks=CHECKS,method_receipts=METHOD_RECEIPTS))

def main():
 for p in [C/'addendum11.json',Path(__file__),Path(__file__).with_name('add2_scores.py'),Path(__file__).with_name('normal_line.py'),Path(__file__).with_name('cylinder.cpp')]:proof(p)
 for site,prior in A['presentation_scenes']:process(site,prior,A['presentation_methods'],'interim')
 presentation();tau_summary();snapshot('interim')
 import add11_figures,add11_publish
 add11_figures.main();add11_publish.deliver('interim')
 print('ADD11_INTERIM_DELIVERED',flush=True)
 # No remaining-scene/method computation precedes the sealed interim artifact.
 for site,prior in A['presentation_scenes']:process(site,prior,[m for m in A['methods'] if m not in A['presentation_methods']],'final')
 for site,prior in A['remaining_scenes']:process(site,prior,A['methods'],'final')
 snapshot('final');add11_publish.deliver('final')
 for tree,_ in TREES.values():tree.close()
 print('ADD11_FINAL_DELIVERED',flush=True)

if __name__=='__main__':main()
