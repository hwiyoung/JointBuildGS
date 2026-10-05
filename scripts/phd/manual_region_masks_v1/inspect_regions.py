"""Rank current train depths by actual regional support; render input-only sheets."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib import font_manager
from mvs_depth import checked_bytes, read_colmap_depth, load_view_depth
from manual_region_masks_v1 import unproject, resample_nearest
from mvs_evidence_v1 import sample_prior


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inside(xyz, bounds):
    mask = np.isfinite(xyz).all(-1)
    for axis, key in enumerate('xyz'):
        mask &= (xyz[..., axis] >= bounds[key][0]) & (xyz[..., axis] <= bounds[key][1])
    return mask


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--region', choices=['P2','P3'], required=True)
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    started = time.time()
    args.output.mkdir(exist_ok=False)
    cfg = json.loads(args.config.read_text())
    if not Path('/.dockerenv').exists() or Path('/reference').exists():
        raise RuntimeError('Isolated input-only Docker required')
    binding = json.loads(checked_bytes('/mvs/bindings.json', cfg['binding_sha256']))
    manifest = json.loads(checked_bytes('/input/input_manifest.json', binding['parent_input_manifest_sha256']))
    ledger = {r['path']:r['sha256'] for r in manifest['files']}
    rows = []
    for index, view in enumerate(binding['train']):
        depth = read_colmap_depth(Path('/mvs')/view['local_depth'], view['maps']['depth'])
        xyz = unproject(depth, view['maps']['depth']['K'], view['R'], view['t'])
        roi = inside(xyz, cfg['evaluation_roi'])
        context = inside(xyz, cfg['training_context'])
        tilt = float(np.degrees(np.arccos(np.clip(-np.asarray(view['R'])[2,2], -1, 1))))
        rows.append(dict(train_index=index, name=view['name'], valid_roi_native=int(roi.sum()),
                         valid_context_native=int(context.sum()), tilt_to_local_z_deg=tilt,
                         depth_sha256=view['maps']['depth']['sha256'], rgb_sha256=view['sha256']))
    ranking = sorted(rows, key=lambda r:(-r['valid_roi_native'], r['train_index']))
    # Include coverage leaders, near-vertical views and contrasting oblique coverage.
    selected = ranking[:5]
    for group in [sorted(rows, key=lambda r:r['tilt_to_local_z_deg'])[:3],
                  [r for r in ranking if r['tilt_to_local_z_deg']>35][:3]]:
        for row in group:
            if row not in selected:
                selected.append(row)
    font_manager.fontManager.addfont('/font/NotoSansCJK-Regular.ttc')
    plt.rcParams.update({'font.family':font_manager.FontProperties(fname='/font/NotoSansCJK-Regular.ttc').get_name(), 'axes.unicode_minus':False})
    font = ImageFont.truetype('/font/NotoSansCJK-Regular.ttc', 18)
    thumbs = []
    with PdfPages(args.output / f'{args.region}_input_inspection.pdf') as pdf:
        for rank, row in enumerate(selected):
            view = binding['train'][row['train_index']]
            rgb_path = Path('/input/scene/images')/view['name']
            rgb = np.asarray(Image.open(rgb_path).convert('RGB'))
            md, valid, _ = load_view_depth(view, depth_path=Path('/mvs')/view['local_depth'], rgb_path=rgb_path)
            native = read_colmap_depth(Path('/mvs')/view['local_depth'], view['maps']['depth'])
            xyz = unproject(native,view['maps']['depth']['K'],view['R'],view['t'])
            roi = resample_nearest(inside(xyz,cfg['evaluation_roi']),view['maps']['depth']['K'],view['K'],view['width'],view['height'],False)
            prior_rel = 'prior/raw_depth/'+Path(view['name']).stem+'.npy'
            checked_bytes(Path('/input')/prior_rel, ledger[prior_rel])
            prior_raw = np.load(Path('/input')/prior_rel, allow_pickle=False)
            yy,xx=np.indices(md.shape)
            pd,pvalid=sample_prior(prior_raw,np.stack((xx,yy),-1))
            low,high=np.quantile(md[valid],[.02,.98])
            fig,axes=plt.subplots(2,2,figsize=(18,13),constrained_layout=True)
            axes[0,0].imshow(rgb)
            axes[0,0].set_title('현재 RGB · 좌표는 전체 RGB 픽셀')
            a=axes[0,1].imshow(np.ma.masked_where(~valid,md),cmap='viridis',vmin=low,vmax=high)
            axes[0,1].set_title('현재 MVS depth · camera-Z (m)');fig.colorbar(a,ax=axes[0,1])
            a=axes[1,0].imshow(np.ma.masked_where(~pvalid,pd),cmap='viridis',vmin=low,vmax=high)
            axes[1,0].set_title('기존 prior depth · 같은 깊이 색상 범위');fig.colorbar(a,ax=axes[1,0])
            a=axes[1,1].imshow(np.ma.masked_where(~(valid&pvalid),pd-md),cmap='RdBu_r',vmin=-5,vmax=5)
            axes[1,1].set_title('Prior − MVS (m) · 불일치이며 정오 판정 아님');fig.colorbar(a,ax=axes[1,1])
            for ax in axes.flat:
                ax.contour(roi.astype(float),levels=[.5],colors=['#00d7e8'],linewidths=1)
                ax.set_xticks(range(0,1401,200));ax.set_yticks(range(0,1014,200));ax.grid(alpha=.16)
            fig.suptitle(f'{args.region} · train index {row["train_index"]} · {row["name"]}\n원래 ROI 내 native 표본 {row["valid_roi_native"]:,} · local Z 기준 경사 {row["tilt_to_local_z_deg"]:.1f}° · 청록선은 평가 범위',fontsize=16)
            filename=f'{args.region}_{row["train_index"]:03d}_inputs.png'
            fig.savefig(args.output/filename,dpi=105);pdf.savefig(fig,dpi=90);plt.close(fig)
            row['figure']=filename
            thumb=Image.fromarray(rgb).resize((560,405))
            canvas=Image.new('RGB',(560,453),'white');canvas.paste(thumb,(0,48))
            draw=ImageDraw.Draw(canvas);draw.text((6,3),f'{args.region} idx {row["train_index"]} | ROI {row["valid_roi_native"]:,} | {row["tilt_to_local_z_deg"]:.1f}°',font=font,fill='black')
            draw.text((6,25),view['name'],font=font,fill='black');thumbs.append(canvas)
            print(json.dumps(dict(region=args.region, inspected_index=row['train_index']),ensure_ascii=False),flush=True)
    sheet=Image.new('RGB',(1680,453*((len(thumbs)+2)//3)),'#eeeeee')
    for i,thumb in enumerate(thumbs):sheet.paste(thumb,((i%3)*560,(i//3)*453))
    sheet.save(args.output/f'{args.region}_contact.png')
    result=dict(status='PASS_INPUT_ONLY_VIEW_INSPECTION',region=args.region,scientific_verdict=None,
                config=cfg,config_sha256=sha(args.config),all_train_ranking=ranking,inspected=selected,
                elapsed_seconds=time.time()-started,versions=dict(python=platform.python_version(),numpy=np.__version__,matplotlib=matplotlib.__version__),
                source_sha256={p.name:sha(p) for p in Path(__file__).parent.glob('*.py')})
    (args.output/'receipt.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
