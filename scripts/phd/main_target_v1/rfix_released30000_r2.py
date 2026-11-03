"""Released provenance crossed with fixed spatial bins, camera distance and color contribution."""
import sys
import numpy as np
from scipy.spatial import cKDTree
from common import *
from cause_r8_spatial import bins
from rfix_continue_report import table,save,plt

def main():
 iteration=int(sys.argv[1]);assert iteration==30000
 cfg=json.loads((CFG/'rfix_released.json').read_text())
 for p,h in json.loads((CFG/'rfix_released30000_r2.lock.json').read_text())['files'].items():assert sha(p)==h,p
 binding=json.loads((OUT/'rfix_continue/validation/snapshot_binding_30000.json').read_text());assert binding['status']=='PASS_EXACT_CHECKPOINT_PLY_ROW_BINDING'
 for p,h in json.loads((CFG/'rfix_released.lock.json').read_text())['files'].items():assert sha(p)==h,p
 endpoint=OUT/'rfix_continue'/('endpoint' if iteration==15000 else 'final_endpoint')
 ep=CFG/('rfix_endpoint.json' if iteration==15000 else 'rfix_final.json');state=json.loads(ep.read_text())['state'];assert state['iteration']==iteration
 snap=Path(state['snapshot']);gpath=endpoint/'gaussians.npz';camera=Path(state['actual_training_model'])/'cameras.json'
 dest=OUT/'rfix_continue/released'/(str(iteration)+'_r2');dest.mkdir(parents=True,exist_ok=False)
 dump(dest/'inputs.lock.json',dict(at=stamp(),files={str(p):sha(p) for p in [ep,snap,gpath,camera]},scientific_verdict=None))
 g=np.load(gpath);s=np.load(snap);xyz=g['xyz'];tag=np.load(OUT/'rfix_continue/validation/complete_metadata_30000.npz')['target_tag'];assert np.array_equal(tag,s['target_tag']);assert np.array_equal(xyz[tag==2],s['xyz'][tag==2]);con=g['total_contribution'];assert np.isfinite(con).all() and (con>=0).all()
 names=set(cfg['training_views']);cameras=[v for v in json.loads(camera.read_text()) if v['img_name'] in names];assert len(cameras)==203 and {v['img_name'] for v in cameras}==names
 near=cKDTree(np.array([v['position'] for v in cameras])).query(xyz,workers=4)[0]<=30
 boundary=json.loads(Path(cfg['boundaries']).read_text());x,h=bins(xyz,boundary);released=tag==2;cc=np.where(con==0,0,np.where(con<.01,1,2));group=x.astype('i4')*24+h*6+near.astype('i4')*3+cc;count=np.bincount(group[released],minlength=96).reshape(4,4,2,3);assert count.sum()==released.sum()
 labels=['0','0 < contribution < 0.01','contribution >= 0.01'];rows=[]
 for xi in range(4):
  for hi in range(4):
   for ni in range(2):
    for ci in range(3):rows.append(dict(iteration=iteration,provenance='released',xy_bin=xi,xy_label=boundary['xy_labels'][xi],height_bin=hi,height_label=boundary['height_labels'][hi],within_camera30=bool(ni),contribution_bin=labels[ci],gaussians=int(count[xi,hi,ni,ci])))
 table('released_'+str(iteration),rows)
 fig,axes=plt.subplots(1,2,figsize=(16,5));xx=np.arange(16)
 for ni,ax in enumerate(axes):
  base=np.zeros(16)
  for ci,color in enumerate(['#666666','#dca452','#5c93ad']):
   y=count[:,:,ni,ci].reshape(-1);ax.bar(xx,y,bottom=base,color=color,label=labels[ci]);base+=y
  ax.set(title='카메라 30 m '+('안' if ni else '밖'),xticks=xx,xticklabels=[f'X{x}/Z{z}' for x in range(4) for z in range(4)],ylabel='풀림 출신 수');ax.tick_params(axis='x',rotation=50);ax.legend(fontsize=8)
 save(fig,'released_'+str(iteration),f'{iteration:,}회 풀림 출신 · 203장 총 색 기여',dict(rows=rows,boundaries=boundary['height_local_m'],contribution_definition='sum over all203 views and pixels of alpha*T; no numerical zero tolerance'))
 dump(dest/'result.json',dict(at=stamp(),status='PASS',iteration=iteration,released=int(released.sum()),total_gaussians=len(xyz),near30=int((released&near).sum()),contribution_counts=count.sum((0,1,2)).tolist(),rows=rows,scientific_verdict=None));print('RELEASED_TABLE_PASS',iteration,int(released.sum()))

if __name__=='__main__':main()
