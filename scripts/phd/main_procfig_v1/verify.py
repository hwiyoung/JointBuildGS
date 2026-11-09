"""Independent direct checkpoint recount plus output/schema/figure audits."""
from common import *
import torch
from shapely.geometry import shape,Point
from shapely.prepared import prep
from PIL import Image,ImageOps
def main():
 c=cfg();p=Path(c['sources']['checkpoint_30000']);state=torch.load(p,map_location='cpu',weights_only=False);xyz=state['model'][1].detach().numpy();poly=prep(shape(c['scope']['buffered_footprint']));b=shape(c['scope']['buffered_footprint']).bounds
 rough=(xyz[:,0]>=b[0])&(xyz[:,0]<=b[2])&(xyz[:,1]>=b[1])&(xyz[:,1]<=b[3])&(xyz[:,2]>=c['scope']['z_min'])&(xyz[:,2]<=c['scope']['z_max']);ids=np.flatnonzero(rough);ids=ids[np.fromiter((poly.contains(Point(float(x),float(y))) for x,y in xyz[ids,:2]),bool,len(ids))]
 saved=loadz(O/'gaussians/30000.npz');assert np.array_equal(saved['full_gaussian_index'],ids);assert np.array_equal(saved['xyz'],xyz[ids]);assert np.array_equal(saved['init_id'],state['init_id'].numpy()[ids]);assert np.array_equal(saved['opacity'],torch.sigmoid(state['model'][6].detach()).numpy()[ids].ravel());assert np.array_equal(saved['scale'],torch.exp(state['model'][4].detach()).numpy()[ids])
 snap=loadz(MODEL/'target_monitor/snapshot_30000.npz',['xyz','init_id','target_tag','target_index']);assert np.array_equal(snap['init_id'],state['init_id'].numpy());assert np.array_equal(snap['target_tag'],state['target_r6']['meta']['target_tag'].numpy());assert np.array_equal(snap['target_index'],state['target_r6']['meta']['target_index'].numpy());phase=json.loads((D/'saved_phase_audit.json').read_text());del state
 checks=dict(direct_checkpoint_building_count=len(ids),checkpoint_equals_export=True,final_snapshot_equals_complete_checkpoint=False,final_snapshot_lineage_and_binding_equal_checkpoint=True,saved_phase_audit=phase,configuration_locked=True,scientific_verdict=None)
 rows=list(csv.DictReader((D/'tables/filling_intervals.csv').open()));totals=list(csv.DictReader((D/'tables/building_counts.csv').open()));lineage=list(csv.DictReader((D/'tables/wrong_patch_lineage.csv').open()));group=loadz(O/'work/patch_groups.npz')['group'];seed=loadz(c['sources']['seeds'],['patch','origin']);base=loadz(O/'gaussians/0.npz');base_by_group={gp:set(base['init_id'][base['group33']==gp].tolist()) for gp in [1,2]};findings=[]
 for total in totals:
  it=int(total['iteration']);g=loadz(O/'gaussians'/f'{it}.npz');assert len(g['xyz'])==int(total['building_gaussians']);assert np.isfinite(g['xyz']).all();assert np.isfinite(g['scale']).all();assert (g['scale']>0).all();assert ((g['opacity']>=0)&(g['opacity']<=1)).all();assert abs(np.linalg.norm(g['normal'],axis=1)-1).max()<1e-5
  subtotal=sum(int(r['n']) for r in rows if int(r['iteration'])==it and r['judgment']=='전체');assert subtotal==len(g['xyz'])
  for gp,name in [(1,'틀린 판정'),(2,'보정 비교')]:
   take=np.isin(g['init_id'],list(base_by_group[gp]));r=next(r for r in lineage if int(r['iteration'])==it and r['group']==name);assert int(take.sum())==int(r['descendants']);assert len(set(g['init_id'][take]))==int(r['live_init_ids']);area=float(sum(float(alpha)*np.pi*float(ax[0])*float(ax[1]) for alpha,ax in zip(g['opacity'][take],g['scale'][take])));assert abs(area-float(r['coverage_sum_m2']))<1e-7*max(area,1)
  findings.append(dict(iteration=it,count=len(g['xyz']),group_sums_equal=True,lineage_count_and_coverage_recomputed=True))
 allpng=sorted((O/'figures').glob('*.png'));assert len(allpng)==48,len(allpng);frames={};zoomframes=[]
 for p in allpng:
  with Image.open(p) as im:
   im.load();assert im.width>=1600;assert im.mode=='RGB';assert im.info.get('icc_profile');a=np.asarray(im);assert np.any(a!=[252,252,250]);assert not np.all(a==a[0,0]);
  meta=json.loads(p.with_suffix('.json').read_text());assert meta['text_in_figure'] is False
  if 'camera' in meta:
   cam=meta['camera'];key='zoom' if cam['zoom'] else str(cam['azimuth']);h=hashlib.sha256(json.dumps(cam,sort_keys=True).encode()).hexdigest();frames.setdefault(key,set()).add(h)
 for key,hashes in frames.items():assert len(hashes)==1,(key,hashes)
 checks.update(gaussian_checks=findings,figures=len(allpng),all_png_decoded=True,all_srgb_and_minimum_width=True,same_camera_across_all_states_and_styles=True,scope=c['scope'],stage3='not executed optional; main stage1+2 delivery',training_steps=0,attribution=json.loads((D/'attribution_receipt.json').read_text())['status'])
 dump(D/'verification.json',checks)
 # One visual inspection sheet: all products + large representative zooms.
 sheet=Image.new('RGB',(1800,2400),'#FCFCFA')
 for j,p in enumerate(allpng):
  with Image.open(p) as im:tile=ImageOps.contain(im,(225,180));sheet.paste(tile,((j%8)*225,(j//8)*180))
 for j,p in enumerate([O/'figures/proc_zoom_0_a.png',O/'figures/proc_zoom_30000_a.png',O/'figures/proc_30000_1_c.png']):
  with Image.open(p) as im:tile=ImageOps.contain(im,(600,600));sheet.paste(tile,(j*600,1120))
 with Image.open(O/'figures/proc_section_check.png') as im:tile=ImageOps.contain(im,(1800,650));sheet.paste(tile,((1800-tile.width)//2,1730))
 sheet.save(O/'work/qa_contact.png',icc_profile=ImageOps.exif_transpose(Image.open(allpng[0])).info.get('icc_profile'))
 print('VERIFY_PASS',len(ids),len(allpng),flush=True)
if __name__=='__main__':main()
