"""Short, fixed-geometry appearance probe and final-state gradient diagnostic."""
import math
import os
from pathlib import Path
import time
import traceback
from types import SimpleNamespace
import json

import numpy as np
from PIL import Image, ImageDraw
import torch
import rgb_radius_probe as p
from rgb_final_gradient_probe import analyze


def objective(pred, target):
    return .8*(pred-target).abs().mean() + .2*(1-p.ssim(pred[None], target[None]))


def main():
    started = time.time()
    torch.set_num_threads(2)
    cfg = p.read('/config.json')
    assert cfg['scientific_verdict'] is None and cfg['steps'] == 100
    diagnostic = p.TASK / 'viewer_rgb_v1/rgb_diagnostic_v1' / cfg['diagnostic_attempt']
    assert p.sha(diagnostic / 'manifest.json') == cfg['diagnostic_manifest_sha256']
    manifest = p.read(diagnostic / 'manifest.json')
    pipe = SimpleNamespace(compute_cov3D_python=False, convert_SHs_python=False, depth_ratio=0.)
    records = []
    for item in cfg['cases']:
        tick = time.time()
        case = next(v for v in manifest['cases'] if v['id'] == item['case'])
        condition = next(v for v in case['conditions'] if v['id'] == item['condition'])
        assert case['split'] == 'train'
        folder = p.OUT / (item['case']+'__'+item['condition'])
        folder.mkdir()
        args_path = Path(condition['cfg_args']['path'])
        assert p.sha(args_path) == condition['cfg_args']['sha256']
        values = p.cfg_args(args_path)
        ply = args_path.parent / 'point_cloud/iteration_30000/point_cloud.ply'
        pc = p.GaussianModel(3)
        pc.load_ply(str(ply))
        assert p.sha(diagnostic / case['photo_full_url']) == case['photo_full_sha256']
        photo = p.rgb(diagnostic / case['photo_full_url'])
        k = np.asarray(case['K'])
        cam = p.Camera(colmap_id=case['camera_id'], R=np.asarray(case['R']).T, T=np.asarray(case['t']),
            FoVx=2*math.atan(case['full_width']/(2*k[0,0])), FoVy=2*math.atan(case['full_height']/(2*k[1,1])),
            image=p.image_tensor(photo), gt_alpha_mask=None, image_name=Path(case['name']).stem, uid=case['index'])
        p.apply_projection(cam, {'K': case['K'], 'width': case['full_width'], 'height': case['full_height']})
        bg = torch.full((3,), 1. if values['white_background'] else 0., device='cuda')
        x0,y0,x1,y1 = case['bbox']
        sl = np.s_[y0:y1,x0:x1]
        gt = cam.original_image.cuda()[:, y0:y1,x0:x1]
        with torch.no_grad():
            before = p.render(cam, pc, pipe, bg)
            baseline = p.u8(before['render'])
            assert p.sha(diagnostic / condition['render_full_url']) == condition['render_full_sha256']
            parity = np.abs(baseline.astype(np.int16)-p.rgb(diagnostic / condition['render_full_url']).astype(np.int16))
            assert parity.max() <= 1
            baseline_alpha = before['rend_alpha'].clone()
            baseline_metric = p.metrics(photo[sl], baseline[sl], baseline_alpha.squeeze().cpu().numpy()[sl])
        del before
        gradients = analyze(pc, cam, pipe, bg, case, condition, model=args_path.parent)
        p.write(folder / 'gradients.json', gradients)
        print(json.dumps({'case': item, 'stage': 'gradient_probe_complete'}), flush=True)
        fixed = {name: getattr(pc,name).detach().clone() for name in ['_xyz','_rotation','_scaling','_opacity']}
        saved_sh = [pc._features_dc.detach().clone(), pc._features_rest.detach().clone()]
        for name in fixed:
            getattr(pc,name).requires_grad_(False)
        parameters = [pc._features_dc, pc._features_rest]
        optimizer = torch.optim.Adam(parameters, lr=cfg['learning_rate'])
        trace = []
        Image.fromarray(photo[sl]).save(folder / 'photo.png')
        Image.fromarray(baseline[sl]).save(folder / 'before.png')
        for step in range(cfg['steps']+1):
            optimizer.zero_grad(set_to_none=True)
            package = p.render(cam, pc, pipe, bg)
            loss = objective(package['render'][:,y0:y1,x0:x1], gt)
            if step % 25 == 0:
                rendered = p.u8(package['render'])[sl]
                with torch.no_grad():
                    measured = p.metrics(photo[sl], rendered, package['rend_alpha'].squeeze().detach().cpu().numpy()[sl])
                    alpha_delta = float((package['rend_alpha']-baseline_alpha).abs().max())
                assert alpha_delta == 0
                row = {'step': step, 'objective': float(loss.detach()), 'alpha_max_delta': alpha_delta, **measured}
                trace.append(row)
                Image.fromarray(rendered).save(folder / f'step_{step:03d}.png')
                print(json.dumps({'case':item, **row}), flush=True)
            if step == cfg['steps']:
                final = rendered
                del package, loss
                break
            loss.backward()
            assert all(torch.isfinite(v.grad).all() for v in parameters)
            optimizer.step()
            del package, loss
        for name, tensor in fixed.items():
            assert torch.equal(getattr(pc,name), tensor), name
        with torch.no_grad():
            for parameter, original in zip(parameters, saved_sh):
                parameter.copy_(original)
            restored = p.u8(p.render(cam, pc, pipe, bg)['render'])
            assert np.array_equal(restored, baseline)
        h,w = photo[sl].shape[:2]
        canvas=Image.new('RGB',(3*w,h+32),'#eeeeee')
        draw=ImageDraw.Draw(canvas)
        for index,(label,array) in enumerate([('Photo',photo[sl]),('30k original',baseline[sl]),('100-step SH-only diagnostic',final)]):
            draw.text((index*w+6,8),label,fill='black')
            canvas.paste(Image.fromarray(array),(index*w,32))
        canvas.save(folder/'montage.png')
        record={'case':item,'photo':case['name'],'bbox':case['bbox'],'ply_path':str(ply),'ply_sha256':p.sha(ply),
            'baseline':baseline_metric,'trace':trace,'gradients':gradients,'geometry_opacity_unchanged':True,
            'restored_rgb_exact':True,'native_parity_max_u8':int(parity.max()),'wall_seconds':time.time()-tick}
        p.write(folder/'result.json',record)
        records.append(record)
        del pc,optimizer,parameters,fixed,saved_sh,cam,gt,baseline_alpha
        torch.cuda.empty_cache()
    receipt={'status':'PASS_SHORT_DIAGNOSTIC','scientific_verdict':None,'config':cfg,'results':records,
        'wall_seconds':time.time()-started,'diagnostic_color_optimizer_steps':cfg['steps']*len(records),
        'new_full_training_runs':0,'runtime_image_id':os.environ['DIAGNOSTIC_IMAGE_ID'],
        'operator_head':(p.OUT/'operator_head.txt').read_text().strip(),'torch_version':torch.__version__,
        'gpu':torch.cuda.get_device_name(),'script_sha256':{v.name:p.sha(v) for v in p.OUT.glob('*.py')},
        'config_sha256':p.sha('/config.json')}
    p.write(p.OUT/'receipt.json',receipt)


if __name__=='__main__':
    try:
        main()
    except Exception:
        p.write(p.OUT/'failure.json',{'status':'FAIL','scientific_verdict':None,'traceback':traceback.format_exc()})
        raise
