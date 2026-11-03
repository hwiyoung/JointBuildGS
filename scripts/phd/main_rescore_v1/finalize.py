"""One final required acceptance check, final lock, and byte-verified delivery ZIP."""
import hashlib,zipfile
from common import *
from PIL import Image
def main():
 cfg();assert not (C/'rescore_v1.final.lock.json').exists(),'Final lock is written only once'
 checks=[];tables={n:json.loads((D/'tables'/f'{n}.json').read_text())['rows'] for n in ['table1_tau','table2_cells',*[f'table{i}' for i in range(3,10)]]};checks.append(dict(check='nine_tables_json_csv_md',status='PASS',rows={k:len(v) for k,v in tables.items()}))
 for name in tables:
  assert (D/'tables'/f'{name}.csv').exists() and (D/'tables'/f'{name}.md').exists()
 assert len(tables['table1_tau'])==9 and all(r['old_matches_printed_0p1_cm'] for r in tables['table1_tau'])
 assert len(list(CELLS.glob('*.npz')))==6 and len(list((O/'targets_v2').glob('*.npz')))==6
 for p in (O/'targets_v2').glob('*.npz'):
  z=loadz(p,['patch_id','region','target_height_m','target_sigma_m','undecided_before']);assert len(z['patch_id'])==len(np.unique(z['patch_id']));assert np.isnan(z['target_sigma_m'][z['undecided_before']&(z['region']==2)]).all()
 mesh_hashes={}
 for r in tables['table3']:
  if r.get('completeness') is None:assert r.get('status')=='확인 불가';continue
  assert r['n_gt']>0 and r['n_result']>0 and 0<=r['completeness']<=1 and 0<=r['accuracy']<=1
  p=O/'scores'/r['key']/'values.json';v=json.loads(p.read_text());assert v['scientific_verdict'] is None and v['provenance']['sampling_density_m2']==400
  if v['prior']=='LoD2':assert v['provenance']['tau_assignment']=='reference_surface_kind_v1'
  if v['mesh'] not in mesh_hashes:mesh_hashes[v['mesh']]=sha(v['mesh'])
  assert mesh_hashes[v['mesh']]==v['mesh_sha256']
  if any(x in r['key'] for x in ['baseline_','GeoGS_','2DGS_','CDGS_','r8_','__fusion','__judgment_mesh','__oracle']):
   meta=Path(v['mesh']).with_suffix('.json');m=json.loads(meta.read_text());assert m['voxel_m']==.05 and m['trunc_m']==.25
   assert m.get('cluster_to_keep',50)==50
   views=json.loads((O/'views'/f"{r['site']}.json").read_text())['views'];assert sum(x['virtual'] for x in views)==16
 checks.append(dict(check='source_hashes_final_mesh_settings_sampling_and_new_wall_tau',status='PASS'))
 membership=[]
 for site in SITES:
  frozen=json.loads((O/'views'/f'{site}.json').read_text());split=S0/'fork_inputs/s61'/site/'split.json';expected=sorted(json.loads(split.read_text())['train']);actual=[v['name'] for v in frozen['views'] if not v['virtual']];assert actual==expected,site
  membership.append(dict(site=site,training_views=len(actual),split_sha256=sha(split),views_sha256=sha(O/'views'/f'{site}.json')))
 checks.append(dict(check='exact_training_camera_names_and_order_against_original_split',status='PASS',rows=membership))
 repro=json.loads((D/'tables/reproduction_full_replay.json').read_text())['rows'];assert len(repro)==2 and all(r['pass_tolerance'] for r in repro);checks.append(dict(check='existing_actual_geometry_reproduction',status='PASS',rerun=False))
 required=['그림6_2']+[f'그림7_{n}_{prior}' for n in [3,5] for prior in ['ALS','LoD2']]+[f'그림7_{n}_ALS' for n in [4,6,7]]
 for stem in required:
  p=D/'figures'/f'{stem}.png';meta=json.loads(p.with_suffix('.json').read_text());assert meta['dpi']==300
  with Image.open(p) as im:assert all(abs(d-300)<.1 for d in im.info['dpi']);assert im.width>1000 and im.height>1000
 assert (O/'early_figures_review.json').exists() and (O/'remaining_figures_review.json').exists()
 checks.append(dict(check='required_figures_300dpi_metadata_and_once_visual_review',status='PASS',figures=required))
 assert len((D/'다시채점_보고_v1.md').read_text())<=15000
 # Reuse receipts and generated final meshes carry exact model provenance.
 for p in (O/'jobs').glob('*__*.json'):
  j=json.loads(p.read_text())
  if 'model' in j and not j['key'].endswith('__freeze_views'):assert (O/'meshes'/j['key']/'train.json').exists(),j['key']
 checks.append(dict(check='training_mesh_present_for_each_trained_checkpoint',status='PASS'))
 unavailable=[r for r in tables['table3'] if r.get('completeness') is None]
 dump(D/'final_validation.json',dict(at=now(),status='PASS_AVAILABLE_ARTIFACTS_WITH_EXPLICIT_UNAVAILABLE_RESULTS',unavailable_scene_rows=len(unavailable),checks=checks,optimization_steps=0,writes='only task cfg/scripts/docs/external payload; enforced by read-only Docker mounts',scientific_verdict=None))
 dump(C/'rescore_v1.final.lock.json',dict(at=now(),phase='after_all_calculations',config_sha256=sha(C/'rescore_v1.json'),initial_lock_sha256=sha(C/'rescore_v1.initial.lock.json'),scripts={str(p.relative_to(R)):sha(p) for p in sorted((R/'scripts/phd/main_rescore_v1').glob('*')) if p.is_file()},validation_sha256=sha(D/'final_validation.json'),scientific_verdict=None))
 progress('모든 셈과 최종 점검 완료. 설정 두 번째 잠금. 묶음에 메시를 넣지 않음. scientific_verdict: null.')
 entries=[]
 for folder,prefix in [(D,'docs'),(C,'configs'),(R/'scripts/phd/main_rescore_v1','scripts'),(CELLS,'cells_v2'),(O/'targets_v2','targets_v2'),(O/'targets_oracle','targets_oracle')]:
  for p in sorted(folder.rglob('*')):
   if p.is_file() and p.name!='package_receipt.json':entries.append((p,prefix+'/'+p.relative_to(folder).as_posix()))
 sums=''.join(f'{sha(p)}  {name}\n' for p,name in entries);(O/'SHA256SUMS').write_text(sums);dest=O/'PHD-MAIN-RESCORE-v1.zip'
 with zipfile.ZipFile(dest,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  for p,name in entries:z.write(p,name)
  z.writestr('SHA256SUMS',sums)
 assert dest.stat().st_size<=400*1024**2,'Archive exceeds 400 MiB; split into bounded ZIPs before delivery'
 with zipfile.ZipFile(dest) as z:
  assert z.testzip() is None
  for line in sums.splitlines():
   digest,name=line.split('  ',1);assert hashlib.sha256(z.read(name)).hexdigest()==digest
 receipt=dict(at=now(),archive=str(dest),bytes=dest.stat().st_size,sha256=sha(dest),members=len(entries)+1,zip_crc='PASS',entry_sha256='PASS',meshes_included=False,scientific_verdict=None);dump(D/'package_receipt.json',receipt);dump(O/'package_receipt.json',receipt);print('PACKAGE_COMPLETE',receipt)
if __name__=='__main__':main()
