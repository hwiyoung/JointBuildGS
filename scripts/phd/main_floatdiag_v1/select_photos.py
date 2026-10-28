"""Select source photos from original patch centres, using cached baseline depths."""
import argparse
import json
import numpy as np
from common import *
from recount import load_eval

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--site',required=True);ap.add_argument('--prior',default='ALS');a=ap.parse_args()
    cfg=config();e,_=load_eval(a.site,a.prior)
    cases=[c for c in json.loads((CFG/f'cases_{a.prior}.json').read_text())['cases'] if c['site']==a.site]
    root=OUT/'renders'/a.site/f'nojudge_{a.prior}_s0/iteration_30000'
    quality=json.loads((root/'quality.json').read_text());out=[]
    for case in cases:
        ids=np.asarray(case['patch_indices'],int);xyz=e['centre'][ids];weights=e['area'][ids];candidates=[]
        for cam in quality['train']:
            ext=np.array(cam['world_to_camera']);K=np.array(cam['intrinsic']);H,W=cam['height'],cam['width']
            pc=xyz@ext[:3,:3].T+ext[:3,3];proj=pc@K.T;uv=proj[:,:2]/proj[:,2,None]
            xy=np.rint(np.nan_to_num(uv,nan=-1e6)).astype(int)
            on=(pc[:,2]>0)&np.isfinite(uv).all(1)&(xy[:,0]>=0)&(xy[:,0]<W)&(xy[:,1]>=0)&(xy[:,1]<H)
            vis=np.zeros(len(ids),bool);idx=np.flatnonzero(on)
            with np.load(root/'train'/(cam['view']+'.npz')) as f:depth=f['depth']
            dd=depth[xy[idx,1],xy[idx,0]]
            vis[idx]=np.isfinite(dd)&(dd>0)&(pc[idx,2]<=dd+.25)
            candidates.append(dict(view=cam['view'],coverage=float(weights[vis].sum()/weights.sum()),
                angle_from_vertical_deg=float(np.rad2deg(np.arccos(np.clip(abs(ext[2,2]),0,1)))),
                visible_patches=int(vis.sum()),total_patches=len(ids)))
        main=sorted([x for x in candidates if x['coverage']>.9],key=lambda x:(x['angle_from_vertical_deg'],x['view']))
        oblique=sorted([x for x in candidates if x['coverage']>.5],key=lambda x:(-x['angle_from_vertical_deg'],x['view']))
        out.append(dict(case=case['id'],main=main[0] if main else None,oblique=oblique[0] if oblique else None,candidates=candidates,
            unavailable_reason=None if main and oblique else 'No camera passes the locked visible-area threshold'))
    dest=CFG/f'photos_{a.site}_{a.prior}.json'
    if dest.exists():
        prior=json.loads(dest.read_text())
        assert 'reference surface' in prior['rule'],'already uses original centres; refuse to overwrite'
        old=CFG/'history'/('pre_original_centres_'+dest.name);assert not old.exists();dest.rename(old)
    save(dest,dict(frozen_at=now(),visibility_result=f'nojudge_{a.prior}_s0',iteration=30000,cases=out,
        rule='area-weighted original stage-1 patch centres; baseline rendered camera-depth visibility; ties by filename; no GT in camera selection',scientific_verdict=None))
    with (DOC/'issues.md').open('a') as f:f.write('\nFD-004: R1 실사 선택 초안에서 패치 중심을 참값 면으로 옮겨 투영한 오류를 발견했다. 3.4의 원래 패치 중심으로 수정했다. 초안은 history/pre_original_centres_photos_R1rep_b10_ALS.json에 보존했다. 저장 모델, 렌더, PSNR, 사례 선택과 메시 캡처는 변경하지 않았다.\n')
    print([(x['case'],x['main'],x['oblique'],max(v['coverage'] for v in x['candidates'])) for x in out])

if __name__=='__main__':main()
