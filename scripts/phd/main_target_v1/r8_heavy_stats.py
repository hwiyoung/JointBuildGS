"""CPU-only heavy-view rankings, distributions, original-seed ancestry and count deltas."""
import csv,gzip,gc,math
import numpy as np
import torch
from common import *
from cause_r8_spatial import writecsv,bins
ROOT=OUT/'r8_recorded_continue';H=ROOT/'heavy'
NAMES=['배경','패치','풀림: 100회 자손','풀림: 그 밖']
def read(p):return json.loads(Path(p).read_text())
def dist(v,c,field):
 assert np.isfinite(v).all()
 edges=np.array([np.inf if x is None else x for x in c['histogram_edges'][field]],float);hist=np.histogram(v,edges)[0]
 assert int(hist.sum())==len(v),(field,float(v.min()),float(v.max()))
 return dict(n=len(v),quantiles=dict(zip(map(str,c['quantiles']),map(float,np.percentile(v,c['quantiles'])))) if len(v) else None,histogram_edges=c['histogram_edges'][field],histogram_counts=hist.tolist())
def main():
 lock=read(CFG/'r8_heavy_stats.lock.json')
 for p,h in lock['files'].items():assert sha(p)==h,p
 c=read(CFG/'r8_heavy.json');b=read(c['boundaries']);out=H/'tables';out.mkdir(exist_ok=False);summ=[];cross=[];dists=[];seed_rows=[]
 stopped=H/'states/r8_14031_stop';sa=dict(np.load(stopped/'arrays.npz'));sv=dict(np.load(stopped/(c['heavy_camera']+'.npz')));order=np.lexsort((np.arange(len(sa['xyz'])),-sv['tiles'].astype('i8')));cohorts={str(q):np.unique(sa['init_id'][order[:math.ceil(q*len(order))]]) for q in c['top_fractions']};del sa,sv,order;gc.collect();fixed=[]
 for row in c['rows']:
  d=H/'states'/row['key'];a=dict(np.load(d/'arrays.npz'));render=read(d/'render.json');n=len(a['xyz']);names=NAMES if row['family']=='r8' else ['SfM 출신','사전 정보 출신'];ng=len(names)*16
  for view in render['views']:
   name=view['camera'];v=dict(np.load(d/(name+'.npz')));tiles=v['tiles'].astype('i8');assert len(tiles)==n and tiles.sum()==view['overlaps'];order=np.lexsort((np.arange(n),-tiles));ntop=math.ceil(.1*n);top=order[:ntop];metrics=dict(camera_distance_m=np.linalg.norm(a['xyz'].astype('f8')-v['camera_center'],axis=1),longest_axis_m=a['longest_axis'],opacity=a['opacity'],radius_pixels=v['radius']);assert np.isfinite(np.concatenate([x[top] for x in metrics.values()])).all()
   for q in c['top_fractions']:
    k=math.ceil(q*n);ix=order[:k];total=int(tiles[ix].sum());assert k<=n
    sr=dict(state=row['key'],iteration=row['iteration'],stage=row['stage'],camera=name,top_fraction=q,population=n,selected=k,positive_selected=int(np.count_nonzero(tiles[ix])),selected_overlap=total,total_overlap=int(tiles.sum()),overlap_share=total/int(tiles.sum()),cutoff_tiles=int(tiles[ix[-1]]),distinct_initial_seeds=len(np.unique(a['init_id'][ix])),binning_bytes=view['binning_bytes']);summ.append(sr)
    for field,val in metrics.items():dists.append(dict(state=row['key'],camera=name,top_fraction=q,metric=field,**dist(val[ix],c,field)))
    for j in range(ng):
     jj=ix[a['group'][ix]==j];ct=len(jj);ov=int(tiles[jj].sum());r=dict(state=row['key'],camera=name,top_fraction=q,provenance=names[j//16],tag=j//16,xy_bin=j%16//4,height_bin=j%4,count=ct,count_fraction_of_selected=ct/k,overlaps=ov,overlap_fraction_of_selected=ov/total,overlap_fraction_of_all=ov/int(tiles.sum()))
     for field,val in metrics.items():r[field+'_median']=float(np.median(val[jj])) if ct else None
     cross.append(r)
    assert sum(r['count'] for r in cross[-ng:])==k and sum(r['overlaps'] for r in cross[-ng:])==total
   # Every selected row includes the original seed ID and immutable source, not inferred parents.
   filename=f'{row["key"]}__{name}__top10.csv.gz';fields=['row','rank','top1','tiles','init_id','initial_source','provenance','xy_bin','height_bin','x','y','z',*metrics]
   with gzip.open(out/filename,'wt',encoding='utf8',newline='') as f:
    w=csv.writer(f);w.writerow(fields)
    for rank,j in enumerate(top,1):
     gp=int(a['group'][j]);w.writerow([int(j),rank,int(rank<=math.ceil(.01*n)),int(tiles[j]),int(a['init_id'][j]),'SfM' if a['origin'][j]==0 else 'prior_patch',names[gp//16],gp%16//4,gp%4,*map(float,a['xyz'][j]),*[float(val[j]) for val in metrics.values()]])
   # Summarize initial ancestors for each of the two nested top groups.
   for q in c['top_fractions']:
    ix=order[:math.ceil(q*n)];ids,inv=np.unique(a['init_id'][ix],return_inverse=True);counts=np.bincount(inv);ov=np.bincount(inv,weights=tiles[ix]).astype('i8');unique_origins=np.zeros(len(ids),dtype='i1');unique_origins[inv]=a['origin'][ix]
    ap=out/f'{row["key"]}__{name}__top{int(q*100)}_ancestors.csv.gz'
    with gzip.open(ap,'wt',encoding='utf8',newline='') as f:
     w=csv.writer(f);w.writerow(['initial_seed_id','initial_source','descendants_selected','overlaps'])
     for ii in np.lexsort((ids,-ov)):w.writerow([int(ids[ii]),'SfM' if unique_origins[ii]==0 else 'prior_patch',int(counts[ii]),int(ov[ii])])
    seed_rows.append(dict(state=row['key'],camera=name,top_fraction=q,initial_seeds=len(ids),descendants=int(counts.sum()),overlaps=int(ov.sum()),file=ap.name))
   if row['family']=='r8' and name==c['heavy_camera']:
    for q,ids in cohorts.items():
     mask=np.isin(a['init_id'],ids);fixed.append(dict(state=row['key'],iteration=row['iteration'],stage=row['stage'],final_top_fraction=float(q),initial_seeds=len(ids),present_initial_seeds=len(np.unique(a['init_id'][mask])),gaussians=int(mask.sum()),overlaps=int(tiles[mask].sum()),overlap_share=float(tiles[mask].sum()/tiles.sum()),definition='all descendants sharing initial seed IDs of stopped top group; not exact intermediate parents'))
   print('HEAVY_STATS',row['key'],name,summ[-2]['overlap_share'],summ[-1]['overlap_share'],flush=True)
   del v,tiles,order,top,metrics;gc.collect()
  del a;gc.collect()
 for name,rr in [('top_summary',summ),('top_cells',cross),('ancestor_index',seed_rows),('fixed_initial_seed_cohorts',fixed)]:dump(out/(name+'.json'),dict(rows=rr,scientific_verdict=None));writecsv(out/(name+'.csv'),rr)
 dump(out/'distributions.json',dict(rows=dists,scientific_verdict=None))
 # Flatten distributions for tabular inspection.
 dr=[]
 for r in dists:
  for quant,val in r['quantiles'].items():dr.append(dict(state=r['state'],camera=r['camera'],top_fraction=r['top_fraction'],metric=r['metric'],percentile=quant,value=val))
 writecsv(out/'distribution_quantiles.csv',dr)
 # Count change uses post-iteration records; initial boundary is the full original7000.
 cfg=read(CFG/'r8_record_continue.json');model=Path(cfg['model']);cp=torch.load(cfg['checkpoint'],map_location='cpu');xyz=cp['model'][1].detach().numpy();meta=cp['target_r6']['meta'];tag=meta['target_tag'].numpy().copy();release=meta['target_released_at'].numpy();tag[(tag==2)&(release!=100)]=3;x,z=bins(xyz,b);g=tag.astype('i4')*16+x*4+z;first=np.bincount(g,minlength=64);del cp,meta,xyz,tag,release,g;gc.collect()
 after=[json.loads(x) for x in (model/'recording/after_iteration_100.jsonl').read_text().splitlines()];records={r['iteration']:np.asarray(r['counts'],dtype='i8').reshape(-1) for r in after};records[7000]=first;growth=[]
 for end in range(8000,14001,1000):
  start=end-1000;aa=records[start];zz=records[end];steps=list(range(start+100,end+1,100));assert all(i in records for i in steps)
  prev=aa;net=np.zeros(64,dtype='i8')
  for i in steps:net+=records[i]-prev;prev=records[i]
  assert np.array_equal(net,zz-aa)
  for j in range(64):growth.append(dict(start=start,end=end,provenance=NAMES[j//16],tag=j//16,xy_bin=j%16//4,height_bin=j%4,start_count=int(aa[j]),end_count=int(zz[j]),net_change=int(zz[j]-aa[j]),end_start_ratio=float(zz[j]/aa[j]) if aa[j] else None,observed_100_step_records=len(steps)))
 dump(out/'growth_1000.json',dict(rows=growth,interpretation='net population change; includes movement between bins, cloning/splitting and deletion',scientific_verdict=None));writecsv(out/'growth_1000.csv',growth)
 gr=[r for r in read(ROOT/'stop_diagnostic/gradient.json')['rows'] if 8000<=r['iteration']<=14000];assert len(gr)==7*64;dump(out/'pre_density_gradients.json',dict(rows=gr,scientific_verdict=None));writecsv(out/'pre_density_gradients.csv',gr)
 dump(H/'stats_verification.json',dict(at=stamp(),status='PASS',render_states=len(c['rows']),ranked_views=len(summ)//2,all_rank_count_and_overlap_sums_equal=True,all_histograms_conserve_counts=True,initial_seed_source_asserted_during_render=True,counts_from_100_steps_telescope=True,gradient_rows=len(gr),optimization_steps=0,scientific_verdict=None))
if __name__=='__main__':main()
