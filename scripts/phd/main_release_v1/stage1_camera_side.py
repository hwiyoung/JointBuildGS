"""Orient wall front/back by an actual contributing training camera."""
from common import *
import sys
def main(site,prior):
 root=O/'stage1'/f'{site}__{prior}';r=loadz(root/'rows.npz');a=loadz(root/'attribution.npz');lineage=root/'lineage';meta=json.loads((lineage/'receipt.json').read_text());rr=Path(meta['render_root']);views=[v for v in json.loads((rr/'receipt.json').read_text())['views'] if not v['virtual']];ids=loadz(lineage/'gaussian_lineage.npz')['full_gaussian_index'];source=loadz(S1/'defs'/site/f'rows_{prior}.npz',['thin','kind']);wall=source['kind'][source['thin'].astype(bool)]==2
 needed=wall&np.isin(r['result_type'],[1,2]);camera=np.full(len(wall),-1,'i4');typ=r['result_type'].copy();signed=np.full(len(wall),np.nan)
 for v in views:
  ii=np.flatnonzero(needed&(camera<0)&(a['selected_gaussian']>=0))
  if not len(ii):break
  E=np.array(v['W2C']);K=np.array(v['K']);q=r['surface_xyz'][ii]@E[:3,:3].T+E[:3,3];keep=q[:,2]>0;ii=ii[keep];q=q[keep];u=np.rint(K[0,0]*q[:,0]/q[:,2]+K[0,2]).astype(int);w=np.rint(K[1,1]*q[:,1]/q[:,2]+K[1,2]).astype(int);keep=(u>=0)&(w>=0)&(u<v['width'])&(w<v['height']);ii=ii[keep];q=q[keep];u=u[keep];w=w[keep]
  dep=loadz(rr/v['file'],['depth'])['depth'][w,u];index=loadz(lineage/'views'/v['file'],['max_gaussian'])['max_gaussian'][w,u];keep=(index>=0)&(dep>0)&(abs(dep-q[:,2])<=.25);keep[keep]&=ids[index[keep]]==a['selected_gaussian'][ii[keep]];take=ii[keep]
  if not len(take):continue
  # Positive means result is closer to this camera than the GT point.
  gtdepth=r['xyz'][take]@E[2,:3]+E[2,3];value=gtdepth-q[keep,2];signed[take]=value;typ[take]=np.where(value>=0,1,2);camera[take]=v['index']
 unknown=needed&(camera<0);typ[unknown]=4;a.update(result_type_camera=typ,wall_side_training_camera_index=camera,wall_signed_camera_depth_m=signed);savez(root/'attribution.npz',**a)
 rows=[];modes=[('original',r['old_cell']),('score',loadz(O/'stage0'/f'{site}__{prior}'/'cells.npz',['score_cell_1p0'])['score_cell_1p0'])]
 for mode,cells in modes:
  for cell in [0,1,2,4]:
   for region in [-1,0,1,2,3,4,9] if cell in [2,4] else [-1]:
    base=(cells==cell)&((r['judge_region']==region) if region>=0 else True);den=int(base.sum())
    for result_type in range(5):
     num=int((base&(typ==result_type)).sum())
     for tag in range(5):
      count=int((base&(typ==result_type)&(a['current_binding']==tag)).sum());rows.append(dict(site=site,prior=prior,cell_basis=mode,cell=cell,judgment_region=region,result_type=result_type,binding=tag,n_gt=count,cell_n_gt=den,cell_fraction=count/den if den else None,result_type_fraction=count/num if num else None,small='적음' if den<1000 else ''))
 table('stage1/'+f'{site}__{prior}'+'_attribution',rows)
 dump(root/'wall_side.json',dict(status='PASS_WITH_EXPLICIT_UNAVAILABLE',wall_outside_points=int(needed.sum()),oriented_from_modal_contributor_view=int((needed&(camera>=0)).sum()),camera_side_unavailable=int(unknown.sum()),camera_rule='first frozen training view supporting the modal max-alpha*T contributor with exact inherited 0.25 m depth match; sign is GT camera depth minus result camera depth',result_type_4='outside tau, wall camera side unavailable; never imputed from arbitrary normal',roof_rule='positive local Z means above',scientific_verdict=None))
 print('WALL_SIDE',prior,int(needed.sum()),int(unknown.sum()),flush=True)
if __name__=='__main__':main(*sys.argv[1:])
