"""Early Gaussian populations from main-view rendered patch heights."""
import argparse
import json
import numpy as np
from scipy.spatial import cKDTree
from scipy.special import expit
from plyfile import PlyData
from common import *
from recount import load_eval
from reduce_diagnostics import table

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--site',required=True);ap.add_argument('--prior',default='ALS')
    ap.add_argument('--result',required=True);a=ap.parse_args()
    model=OUT/'runs'/a.site/a.result/'model' if a.result.startswith('fd_') else model_path(a.site,a.result)
    e,_=load_eval(a.site,a.prior);cases={c['id']:c for c in json.loads((CFG/f'geometry_{a.site}_{a.prior}.json').read_text())['cases']}
    rows=[];pixelrows=[]
    for receipt in sorted((OUT/'formation'/a.site/a.result).glob('iteration_*/receipt.json')):
        rec=json.loads(receipt.read_text());it=rec['iteration'];pixelrows+=rec['rows']
        path=model/f'point_cloud/iteration_{it}/point_cloud.ply';data=PlyData.read(str(path),mmap='r')['vertex'].data
        xyz=np.column_stack([data[k] for k in ['x','y','z']]);op=expit(data['opacity'].astype(float))
        scale=np.exp(np.column_stack([data[k] for k in data.dtype.names if k.startswith('scale_')])).max(1)
        origin=data['origin'].astype(int);lineage=np.full(len(xyz),3,np.int8);births=None
        side=path.with_name('floatdiag_birth.npz')
        if not side.exists():side=model/f'monitor/losstrain_birth_{it}.npz'
        if side.exists():
            with np.load(side) as f:
                survivor=f['initial_survivor'];assert len(survivor)==len(xyz)
                if 'birth_iteration' in f.files:births=f['birth_iteration']
            lineage[~survivor]=0;lineage[survivor&(origin==1)]=1;lineage[survivor&(origin==0)]=2
        for r in rec['rows']:
            c=cases[r['case']]
            with np.load(receipt.parent/(r['view']+'.npz')) as f:
                ids=f['patch_id'];valid=f['valid'];delta=f['vertical_delta_m'];world=f['world'];gtz=f['gt_world_z']
            xy=e['centre'][ids,:2];b=np.array(c['bbox']);valid&=((xy>=b[:2]-3)&(xy<=b[2:]+3)).all(1)
            selected_pixels=np.flatnonzero(valid);order=np.argsort(ids[selected_pixels],kind='stable');ordered=selected_pixels[order]
            patch_ids,starts=np.unique(ids[ordered],return_index=True)
            groups=np.split(ordered,starts[1:]);median_delta=np.array([np.median(delta[ix]) for ix in groups])
            median_height=np.array([np.median(world[ix,2]) for ix in groups])
            crop=((xyz>=c['crop_min'])&(xyz<=c['crop_max'])).all(1)&(op>=.1)
            candidates=np.flatnonzero(crop);gx=xyz[candidates]
            for kind,pm in [('floating',median_delta>e['tau'][patch_ids]),('roof',np.abs(median_delta)<=e['tau'][patch_ids])]:
                pi=patch_ids[pm];height=median_height[pm];hit=np.zeros(len(candidates),bool)
                gt=e['centre'][pi,2]+e['p_gt'][pi]*e['normal'][pi,2]
                bot=gt+e['tau'][pi] if kind=='floating' else gt-e['tau'][pi]
                top=height+.25 if kind=='floating' else gt+e['tau'][pi]
                tree=cKDTree(e['centre'][pi,:2]);neigh=tree.query_ball_point(gx[:,:2],np.sqrt(2)*.125+1e-8,workers=2)
                for gi,local in enumerate(neigh):
                    if not local:continue
                    k=np.array(local,int);hit[gi]=bool(((np.abs(e['centre'][pi[k],:2]-gx[gi,:2])<=.125+1e-8).all(1)&(gx[gi,2]>=bot[k])&(gx[gi,2]<=top[k])).any())
                selected=candidates[hit];weight=op[selected];total=float(weight.sum())
                row=dict(site=a.site,result=a.result,iteration=it,case=c['id'],kind=kind,patches=len(pi),count=len(selected),
                    opacity_median=float(np.median(weight)) if len(selected) else None,
                    max_axis_median_m=float(np.median(scale[selected])) if len(selected) else None,
                    birth_iteration_q25_q50_q75_q90=np.quantile(births[selected],[.25,.5,.75,.9]).tolist() if births is not None and len(selected) else None,
                    birth_iteration_status='기록 있음' if births is not None else '기록 없음',
                    sample_status='표본 부족' if len(pi)<100 else 'PASS',source=str(path),main_view=r['view'])
                for i,label in enumerate(['densified','initial_prior','initial_image','unrecorded']):
                    row[label+'_opacity_fraction']=float(weight[lineage[selected]==i].sum()/total) if total and (i==3 or side.exists()) else None
                rows.append(row)
                np.savez_compressed(receipt.parent/(c['id']+'__'+kind+'_gaussians.npz'),index=selected,xyz=xyz[selected],opacity=op[selected],
                    max_axis_m=scale[selected],lineage=lineage[selected],birth_iteration=births[selected] if births is not None else np.full(len(selected),-1,np.int32))
        del data,xyz,op,scale
        print(a.site,a.result,it,'early Gaussian population PASS',flush=True)
    assert rows
    table(DOC/'tables'/f'formation_gaussians_{a.site}_{a.result}',rows,'앞 반복 가우시안 · 주 시점 패치별 렌더 높이 중앙값')
    table(DOC/'tables'/f'formation_pixels_{a.site}_{a.result}',pixelrows,'앞 반복 화소와 깊이 항의 힘')

if __name__=='__main__':main()
