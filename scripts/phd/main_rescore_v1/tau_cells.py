"""Only disable the inherited single 3-NMAD trim; retain residual lineage."""
import ast,difflib
from common import *
def main():
 start=time.monotonic();c=cfg();src=R/'src/phd/prior_propagation_v5/tolerance.py';before=src.read_text()
 oldline='    keep = np.abs(x - m1) <= clip * s1 if s1 > 0 else np.ones(x.size, bool)'
 assert before.count(oldline)==1
 after=before.replace(oldline,'    keep = np.ones(x.size, bool)  # RESCORE: retain every finite residual')
 dest=Path(__file__).parent/'inherited/tolerance.py';assert dest.read_text()==after
 old={};new={};exec(compile(before,str(src),'exec'),old);exec(compile(after,str(dest),'exec'),new)
 root=PH/'main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1/s52/s03';rows=[];taus={}
 for region in ['B0','R2','R1']:
  taus[region]={}
  for prior in ['LoD2','ALS']:
   path=root/region/prior/'residual_samples.npz';z=loadz(path);summary=json.loads(path.with_name('summary.json').read_text())
   for kind in ['roof','wall'] if prior=='LoD2' else ['roof']:
    x=z[kind].astype(float);a=old['robust_width'](x);b=new['robust_width'](x);oldpaper=c['tau']['old_m'][region][0 if prior=='LoD2' and kind=='roof' else 1 if prior=='LoD2' else 2]
    assert b['n_kept']==b['n'] and b['clipped_share']==0
    key=prior+'_'+kind;taus[region][key]=b['width']
    rows.append(dict(search_region=region,prior=prior,kind=kind,old_table_tau_m=oldpaper,old_recomputed_tau_m=a['width'],old_source_tau_m=summary['tolerance'][kind]['tau'],new_tau_m=b['width'],n_pixels=a['n'],median_m=b['median_before'],old_clipped_fraction=a['clipped_share'],old_matches_printed_0p1_cm=round(a['width']*100,1)==round(oldpaper*100,1),old_minus_source_m=a['width']-summary['tolerance'][kind]['tau'],source=str(path),source_sha256=sha(path),sample_rule='inherited confidence-valid building pixels; max 20000 pixels/view/kind; roof vertical and wall normal residual',signed_residual='inherited (MVS depth - prior depth) * surface factor; sign has no effect on NMAD',source_tag='[이 발주에서 냄]'))
   if prior=='ALS':taus[region]['ALS_wall']=taus[region]['ALS_roof']
 table('table1_tau',rows);dump(O/'tau_v2.json',dict(values=taus,scientific_verdict=None))
 cellrows=[];bindings=[]
 for site in SITES[:3]:
  for prior in ['LoD2','ALS']:
   p=JA/'core_points'/f'{site}__{prior}.npz';z=loadz(p);t=np.array([taus[c['tau']['search_regions'][site]][prior+('_roof' if k==1 else '_wall')] for k in z['kind']]);N=len(t)
   cell=np.full(N,6,np.int8);usable=(z['gt_status']==0)&np.isfinite(z['gt_p'])&np.isfinite(z['prior_height_m'])&np.isfinite(z['normal']).all(1)
   pg=abs(z['prior_height_m']-z['gt_p'])<=t;observed=(z['n']>=4)&np.isfinite(z['mvs_mean_m']);mg=abs(z['mvs_mean_m']-z['gt_p'])<=t
   for mask,v in [(observed&pg&mg,0),(observed&~pg&mg,1),(observed&pg&~mg,2),(observed&~pg&~mg,3),(~observed&pg,4),(~observed&~pg,5)]:cell[usable&mask]=v
   invalid=~np.isfinite(z['prior_height_m'])|~np.isfinite(z['normal']).all(1);cell[invalid]=9
   out=O/'cells_v2'/f'{site}__{prior}.npz';savez(out,patch_id=z['patch_id'],source_index=z['source_index'],cell_v2=cell,tau_v2_m=t)
   bindings.append(dict(site=site,prior=prior,n=N,source=str(p),source_sha256=sha(p),output=str(out),output_sha256=sha(out),changed_count=int((cell!=z['cell']).sum()),invalid_count=int(invalid.sum())))
   for k in [1,2]:
    m=z['kind']==k;den=float(z['area'][m].sum())
    if not m.any():continue
    for j in range(7):
     oldm=m&(z['cell']==j);newm=m&(cell==j)
     cellrows.append(dict(site=site,prior=prior,kind='roof' if k==1 else 'wall',cell=j,old_patches=int(oldm.sum()),new_patches=int(newm.sum()),old_area_m2=float(z['area'][oldm].sum()),new_area_m2=float(z['area'][newm].sum()),old_fraction=float(z['area'][oldm].sum()/den),new_fraction=float(z['area'][newm].sum()/den),total_area_m2=den,core_sha256=sha(p),source_tag='[이 발주에서 냄]'))
 table('table2_cells',cellrows);dump(D/'tables/cell_bindings.json',dict(rows=bindings,scientific_verdict=None))
 changes=dict(source=str(src),source_sha256=sha(src),copy=str(dest),copy_sha256=sha(dest),changed_original_lines=[27],diff=list(difflib.unified_diff(before.splitlines(),after.splitlines(),fromfile=str(src),tofile=str(dest))),residual_source='scripts/phd/main_prep_discard_rule_v1/s03_stage1.py:243-299',cell_source='scripts/phd/main_judgeapply_v1/truth.py:38-48; same rules with tau replaced',scientific_verdict=None)
 dump(D/'provenance/stage1_changes.json',changes);timing('stage1',start)
 progress('stage1 스크립트 추가, CSV 신규 출력 줄 끝 LF로 변경. 설정 재잠금 없음. τ 원본은 DISCARD s52/s03; PREP step03은 다른 값이므로 사용하지 않음.')
 print('TAU_COMPLETE',json.dumps(taus));print('OLD_MATCH',sum(x['old_matches_printed_0p1_cm'] for x in rows),len(rows));print('CELL_COUNTS',[(x['site'],x['prior'],x['n'],x['invalid_count']) for x in bindings])
if __name__=='__main__':main()
