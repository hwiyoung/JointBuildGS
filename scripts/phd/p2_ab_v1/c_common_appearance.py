"""Compare saved B renderings on fixed input-derived rays, without retraining.

Domain: union of unoptimized FIXED_IMAGE and FIXED_PRIOR alpha>=0.5 on the
same full-prism crops. This is an image evaluation domain, not area approval.
"""
import argparse
import json
from pathlib import Path
import time
import cv2
import numpy as np
from scripts.phd.p2_ab_v1.c_evaluate import read, write, sha, csv_write


def main(args):
    start=time.monotonic();args.output.mkdir(parents=True,exist_ok=False)
    im=args.image_root/'surface_texturing';pr=args.prior_root/'surface_texturing'
    hashes={};domains={};targets={};domain_meta=[]
    for path in sorted(im.glob('render_*.npz')):
        iid=int(path.stem.split('_')[-1]);other=pr/path.name
        target=im/f'target_{iid}.png'
        if sha(target)!=sha(pr/target.name):
            raise ValueError('Fixed input branches have different evaluation target crops')
        a=np.load(path)['alpha'].squeeze();b=np.load(other)['alpha'].squeeze()
        if a.shape!=b.shape:raise ValueError('Unmatched evaluation ray shape')
        mask=(a>=.5)|(b>=.5)
        domains[iid]=mask;targets[iid]=cv2.cvtColor(cv2.imread(str(target)),cv2.COLOR_BGR2RGB)/255.
        np.save(args.output/f'domain_mask_{iid}.npy',mask,allow_pickle=False)
        domain_meta.append(dict(image_id=iid,height=mask.shape[0],width=mask.shape[1],pixels=int(mask.sum()),
                                target_sha256=sha(target)))
        for p in [path,other,target]:hashes[str(p)]=sha(p)
    write(args.output/'PRE_EVALUATION_DOMAIN.json',dict(rule=__doc__,views=domain_meta,scientific_verdict=None))
    result=[]
    for root in args.b_root:
        receipt=read(root/'result.json')
        if receipt['status']=='ABSTAIN_NO_GEOMETRY':
            handoff=read(root/'handoff_receipt.json')
            result.append(dict(run=root.name,arm='no_geometry',decision_method=handoff['method'],
                condition=handoff['condition'],input_domain_pixels=sum(int(m.sum()) for m in domains.values()),
                covered_pixels=0,ray_coverage=0.,mae=None,psnr_db=None,per_view=[],
                missing_rgb_reason='no rendered geometry; do not fabricate an all-black RGB measurement',
                scientific_verdict=None))
            continue
        for arm in receipt['arms']:
            folder=root/arm['arm'];rows=[];sse=0.;abs_error=0.;n=0;covered=0
            for iid,mask in domains.items():
                target_path=folder/f'target_{iid}.png';render_path=folder/f'render_{iid}.npz'
                expected=next(x['target_sha256'] for x in domain_meta if x['image_id']==iid)
                if sha(target_path)!=expected:raise ValueError('Cross-A target crop identity mismatch')
                payload=np.load(render_path,allow_pickle=False);rgb=payload['rgb'];alpha=payload['alpha'].squeeze()
                if rgb.shape!=targets[iid].shape:raise ValueError('Cross-A render crop dimensions mismatch')
                count=int(mask.sum());error=rgb[mask]-targets[iid][mask]
                sq=float((error**2).sum());ab=float(np.abs(error).sum());valid=int((mask&(alpha>=.5)).sum())
                mse=sq/(3*count) if count else None
                rows.append(dict(image_id=iid,input_domain_pixels=count,covered_pixels=valid,
                    ray_coverage=valid/count if count else None,mae=ab/(3*count) if count else None,
                    psnr_db=float(-10*np.log10(max(mse,1e-12))) if mse is not None else None))
                sse+=sq;abs_error+=ab;n+=count;covered+=valid
                hashes[str(render_path)]=sha(render_path)
            result.append(dict(run=root.name,arm=arm['arm'],decision_method=arm['decision_method'],
                condition=arm['condition'],input_domain_pixels=n,covered_pixels=covered,
                ray_coverage=covered/n if n else None,mae=abs_error/(3*n) if n else None,
                psnr_db=float(-10*np.log10(max(sse/(3*n),1e-12))) if n else None,
                per_view=rows,scientific_verdict=None))
    write(args.output/'common_appearance.json',result)
    csv_write(args.output/'common_appearance.csv',[{k:v for k,v in r.items() if k not in ['per_view','scientific_verdict']} for r in result])
    if not all(sha(p)==h for p,h in hashes.items()):raise RuntimeError('Input changed')
    write(args.output/'technical_receipt.json',dict(status='MATCHED_INPUT_RAY_DIAGNOSTIC_COMPLETE',
        rule=__doc__,view_domain=domain_meta,input_sha256=hashes,elapsed_seconds=time.monotonic()-start,
        source_sha256=sha(__file__),scientific_verdict=None,
        caveats=['Fixed input alpha union is sample-derived evaluation rays, not physical surface area',
                 'No geometry generated at ABSTAIN; missing rays stay in color-error and coverage denominator',
                 'Target PNG quantization to 8-bit; predictions retained float32',
                 'All views remain historical development observations']))
    print(json.dumps({'status':'PASS','arms':len(result),'domain_pixels':sum(x['pixels'] for x in domain_meta)}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--image-root',type=Path,required=True);p.add_argument('--prior-root',type=Path,required=True)
    p.add_argument('--b-root',type=Path,action='append',required=True);p.add_argument('--output',type=Path,required=True)
    main(p.parse_args())
