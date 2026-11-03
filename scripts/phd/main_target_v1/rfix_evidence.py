"""Supplementary factual tables/figures; no new acceptance rule or optimization."""
from rfix_tables import *
from matplotlib import font_manager

def main():
 for p in Path('/fonts').glob('*Regular.ttc'):
  font_manager.fontManager.addfont(str(p));plt.rcParams['font.family']=FontProperties(fname=str(p)).get_name();break
 plt.rcParams['axes.unicode_minus']=False
 cfg=json.loads((CFG/'rfix.json').read_text());summ=json.loads((TAB/'state_summary.json').read_text())['rows'];assert len(summ)==8
 # All differing row IDs and coordinates, all measured parameters, all locked views.
 worst=[];output=[];loss=[]
 for s in cfg['states']:
  key=s['key'];d=json.loads((ROOT/'states'/key/'result.json').read_text());g=json.loads((ROOT/'gradients'/key/'result.json').read_text())
  for name in d['records'][0]['comparison']:
   vals=[r['comparison'][name] for r in d['records']]
   output.append(dict(state=key,output=name,views=len(vals),maximum_fixed_difference=max(v['max_abs'] for v in vals),maximum_repeat_difference=max(v['jitter_max_abs'] for v in vals),pass_count=sum(v['pass_'] for v in vals)))
  for row in g['rows']:
   loss.append(dict(state=key,camera=row['camera'],original_a=row['losses'][0],original_b=row['losses'][1],fixed=row['losses'][2],radii_equal=row['radii_equal']))
   p=ROOT/'gradients'/key/(row['camera']+'_differing_rows.npz')
   if not p.exists():continue
   with np.load(p) as z:
    positions={int(i):xyz.tolist() for i,xyz in zip(z['ids'],z['xyz'])}
    for name,m in row['parameters'].items():
     for rank,(delta,i) in enumerate(m['worst_rows'],1):
      worst.append(dict(state=key,camera=row['camera'],parameter=name,rank=rank,gaussian_row_id=i,xyz_local_m=positions[i],row_maximum_difference=delta,parameter_repeat_maximum=m['jitter_max_abs'],parameter_gate_pass=m['pass_']))
 table('all_render_outputs',output);table('same_losses',loss);table('differing_gaussians',worst)
 boundaries=json.loads((OUT/'r8_lod2_cause/boundaries.json').read_text());groups=json.loads((TAB/'burst_groups.json').read_text())['rows'];names={}
 for state in cfg['states']:
  with np.load(OUT/'screen_sim/states'/state['key']/'groups.npz') as z:names[state['key']]=z['provenance_names'].tolist()
 table('burst_groups_labeled',[dict(state=r['state'],provenance=names[r['state']][r['tag']],xy=boundaries['xy_labels'][r['xy_bin']],height=boundaries['height_labels'][r['height_bin']],**{k:v for k,v in r.items() if k!='state'}) for r in groups])
 dump(DEST/'spatial_legend.json',dict(height_local_m=boundaries['height_local_m'],height_labels=boundaries['height_labels'],xy_labels=boundaries['xy_labels'],frame=boundaries['frame'],provenance=names,scientific_verdict=None))
 # Observation-only atomic addend probe. Its camera/rows were selected after a failure.
 p=ROOT/'gradient_probe/measurement';result=json.loads((p/'result.json').read_text());probe=[]
 with np.load(p/'original.npz') as a,np.load(p/'fixed.npz') as b:
  for i,row in enumerate(result['rows']):
   metrics={}
   for k in a.files:
    if k in ['ids','terms','per_pixel_terms']:continue
    if a[k].shape==b[k].shape and a[k].shape[0]==len(result['rows']):metrics[k]=float(np.abs(a[k][i].astype('f8')-b[k][i]).max())
   probe.append(dict(camera=result['camera'],gaussian_row_id=row['id'],per_pixel_terms_equal=row['per_pixel_terms_exact_equal'],per_pixel_maximum_difference=row['max_abs_term_difference'],per_pixel_differing_values=row['differing_terms'],summed_parameter_differences=metrics,used_for_acceptance=False))
 table('atomic_addend_probe',probe)
 provenance=json.loads((ROOT/'provenance.json').read_text());table('renderer_build_bindings',[dict(implementation=r['implementation'],original_sha256=r.get('original_extension_sha256'),fixed_sha256=r.get('fixed_extension_sha256'),patch=r.get('fixed_patch'),status=r.get('status','BUILT_SEPARATELY'),training_source_changed=r.get('training_source_changed',False),screen_pruning_changed=r.get('screen_pruning_changed',False)) for r in provenance['rows']])
 units=[]
 for label in ['target','imageonly','geogs']:
  rows=json.loads((ROOT/'units'/label/'result.json').read_text())['rows']
  for r in rows:units.append(dict(build=label,case=r['case']['name'],original_tiles=r['original_overlaps'],fixed_tiles=r['fixed_overlaps'],pixel_reference_tiles=r['exact_visible_tiles'],radii=r['radii'],radii_equal=r['radii_equal'],maximum_output_difference=r['max_abs'],repeat_maximum=r['jitter_max_abs'],pass_=r['pass_']))
 table('unit_comparison',units);extra=json.loads((ROOT/'extra_units/target/result.json').read_text());table('extra_near_plane_units',extra['rows'])
 hist=json.loads((ROOT/'mesh_history.json').read_text());table('mesh_history_summary',[dict(prior=r['prior'],result=r['result'],old_all_R=r['old_all_R'],new_all_R=r['new_all_R'],old_all_P_E=r['old_all_P_E'],new_all_P_E=r['new_all_P_E'],old_views=r['old_tsdf']['views'],old_voxel_m=r['old_tsdf']['voxel_m'],virtual_cells=[c['cell'] for c in r['cells'] if '가상' in c['old_status']],different_cells=[c['cell'] for c in r['cells'] if not c['same']]) for r in hist['rows']])
 # Same axes for all states. Values are observed, never normalized to a passing gate.
 f,axes=plt.subplots(1,3,figsize=(17,5));x=np.arange(8);labels=[LABEL[s['state']] for s in summ]
 for ax,ka,kb,title,scale in [(axes[0],'original_overlap_max','fixed_overlap_max','영상별 겹침 최댓값 (백만)',1e6),(axes[1],'original_buffer_max_bytes','fixed_buffer_max_bytes','정렬 버퍼 최댓값 (GiB)',2**30),(axes[2],'original_render_median_s','fixed_render_median_s','렌더 시간 중앙값 (ms)',.001)]:
  ax.bar(x-.18,[s[ka]/scale for s in summ],.36,label='원본');ax.bar(x+.18,[s[kb]/scale for s in summ],.36,label='타일 등록 고침');ax.set_xticks(x,labels,rotation=65,ha='right',fontsize=8);ax.set_title(title);ax.legend();ax.grid(axis='y',alpha=.2)
 fig('all_states_load',f,dict(rows=summ,original_timing='second original run without accounting'))
 f,ax=plt.subplots(figsize=(12,4));ax.bar(x,[s['gradient_comparisons_failed'] for s in summ],color='#b44e4e');ax.set_xticks(x,labels,rotation=35,ha='right');ax.set_ylim(0,210);ax.set_ylabel('기준을 넘은 비교 수 / 210');ax.set_title('상태마다 30장 × 매개변수 7종 · 추가 허용 오차 없음');fig('all_states_gradient_gate',f,dict(rows=summ,comparisons_per_state=210))
 u=units[:4];f,ax=plt.subplots(figsize=(9,4));xx=np.arange(4);ax.bar(xx-.18,[r['original_tiles'] for r in u],.36,label='원본');ax.bar(xx+.18,[r['fixed_tiles'] for r in u],.36,label='타일 등록 고침');ax.set_xticks(xx,['렌즈 앞 기울임','화면 밖','앞 평면 걸침','보통']);ax.set_ylabel('등록 타일 수');ax.legend();ax.set_title('단위 점검: 화소 출력과 radii 동일');fig('unit_tile_counts',f,dict(rows=units,extra=extra['rows']))
 dump(DEST/'supplement.json',dict(at=stamp(),tables=['all_render_outputs','same_losses','differing_gaussians','atomic_addend_probe','renderer_build_bindings','unit_comparison','extra_near_plane_units','mesh_history_summary'],scientific_verdict=None));print('RFIX_EVIDENCE_DONE',flush=True)

if __name__=='__main__':main()
