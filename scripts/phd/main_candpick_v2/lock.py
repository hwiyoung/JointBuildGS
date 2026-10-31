"""Final pre-training configuration, exact diagnostic views, and implementation lock."""
import torch
from frozen_engine import cameras,project
from cp2_common import *

def main():
    cfg=json.loads((CFG/'plan_before_views.json').read_text())
    cfg['locked_at']=now();cfg['optimizer_steps_before_lock']=0
    cfg['commit_at_lock']=os.environ.get('CANDPICK_COMMIT')
    cfg['depth_preflight']=bind(OUT/'preflight/depth_rule.json')
    assert json.loads((OUT/'preflight/depth_rule.json').read_text())['status']=='PASS'
    cfg['photo']['peak_identity']='Reuse stored peak_mask, which is range-independent and was computed before float16 curve storage; do not regenerate peaks from quantized values.'
    for unit in UNITS:
        v=OUT/'depth_views'/unit
        complete=json.loads((v/'complete.json').read_text());assert complete['status']=='PASS_EXACT_V1_MASK_UNION'
        cfg['units'][unit]['depth_views']=bind(v/'selected_pixels.npz')
        cfg['units'][unit]['depth_view_check']=bind(v/'complete.json')
        site={'B173':'B173nb_b10','R1':'R1rep_b10'}[unit.split('_')[0]];prior=unit.split('_')[1]
        p=PH/'main_stage3_v1/PHD-MAIN-STAGE3-v1/runs'/site/f'nojudge_{prior}_s0/model/jbgs_complete/iteration_30000/checkpoint.pth'
        state=torch.load(p,map_location='cpu',weights_only=False,mmap=True)
        cfg['units'][unit]['spatial_lr_scale']=float(state['model'][11]);del state
        cfg['units'][unit]['spatial_lr_scale_source']=str(p)+':model[11]'
        checks={}
        for variant in 'abcd':
            for start in ['equal','right']:
                arm=f'cp2_{variant}_{start}_{unit}';check=OUT/'preflight'/(arm+'.json')
                r=json.loads(check.read_text());checks[arm]=dict(status=r['status'],reason=r.get('reason'),receipt=bind(check))
        cfg['units'][unit]['unit_checks']=checks
        data=arrays(v/'selected_pixels.npz');d=arrays(CP1/'places'/(unit+'.npz'));cams=cameras(unit)
        for rep in cfg['representatives']:
            if rep['unit']!=unit or not rep['selection']:continue
            ids=np.flatnonzero(np.isin(d['point_id'],rep['selection']['point_ids']))
            choices=sorted(set(data['chosen_view_index'][ids].ravel())-{-1})
            scores=[]
            for j in choices:
                member=(data['chosen_view_index'][ids]==j).any(1)
                scores.append((-int(data['counts'][ids[member],j].sum()),cams[j]['name'],j))
            _,_,j=min(scores);cam=cams[j]
            sel=np.isin(data['point_index'],ids)&(data['view_index']==j)
            pixels=data['pixel_index'][sel];x=pixels%cam['width'];y=pixels//cam['width']
            crop=[max(0,int(x.min())-32),max(0,int(y.min())-32),min(cam['width'],int(x.max())+33),min(cam['height'],int(y.max())+33)]
            rep['render_view']=dict(name=cam['name'],view_index=j,crop=crop,selected_point_pixels=len(pixels),
                rule='Among point-selected top-three views, largest sum of selected representative point-pixel support; lexical view tie.')
    scripts=['cp2_common.py','frozen_engine.py','engine.py','train.py','preflight.py','prepare_views.py','depth_rule.py','run.sh']
    cfg['training_implementation_sha256']={str(Path('/repo/scripts/phd/main_candpick_v2')/s):sha(Path(__file__).with_name(s)) for s in scripts}
    cfg['depth']['native_gsplat_depth']='RGB+ED uses center Z; diagnostic only. Primary uses ray-plane depth s.x*Tw.x+s.y*Tw.y+Tw.z, then the same expected-depth normalization as GeoGS.'
    cfg['depth']['source']='GeoGS arguments depth_ratio=0.0; gaussian_renderer accumulated depth / alpha; mesh_utils surf_depth; diff-surfel forward.cu ray-plane depth. Retain gsplat1.4 alpha cap .999 and its frozen v1 contributor ordering, without swapping rasterizers.'
    cfg['depth']['nonpositive_or_near_ray']='Any contributing ray depth below GeoGS near_n=0.2m or nonfinite makes that pixel unavailable; recorded explicitly.'
    save(CFG/'candpick_v2.json',cfg)
    save(CFG/'candpick_v2.lock.json',dict(locked_at=cfg['locked_at'],sha256=sha(CFG/'candpick_v2.json'),optimizer_steps=0,source=SOURCE,scientific_verdict=None))
    save(DOC/'tables/pretraining_lock.json',dict(status='LOCKED',at=cfg['locked_at'],config_sha256=sha(CFG/'candpick_v2.json'),
        unit_status={u:{k:v['status'] for k,v in cfg['units'][u]['unit_checks'].items()} for u in UNITS},scientific_verdict=None))
    print('LOCKED',sha(CFG/'candpick_v2.json'),flush=True)

if __name__=='__main__':main()
