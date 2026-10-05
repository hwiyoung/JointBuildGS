"""Full-native source review: RGB, metric depth, discrete partition and weights.

Consumes already sealed annotation output; does not modify or train on it.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

import matplotlib
matplotlib.use('Agg')
from matplotlib import font_manager
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Patch
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

from mvs_depth import read_colmap_depth, checked_bytes


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--annotations', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not Path('/.dockerenv').exists():
        raise RuntimeError('Docker required')
    receipt = json.loads((args.annotations / 'receipt.json').read_text())
    cfg = receipt['config']; region = cfg['region']
    bindings = json.loads(checked_bytes('/mvs_input/bindings.json', cfg['binding_sha256']))
    font_manager.fontManager.addfont('/font/NotoSansCJK-Regular.ttc')
    plt.rcParams.update({'font.family':font_manager.FontProperties(fname='/font/NotoSansCJK-Regular.ttc').get_name(), 'axes.unicode_minus':False})
    args.output.mkdir(exist_ok=False)
    lut = np.zeros((7,3), np.uint8)
    for key, color in cfg['colors'].items():
        lut[int(key)] = [int(color[i:i+2],16) for i in (1,3,5)]
    source_rows = []
    with PdfPages(args.output / f'{region}_manual_sources_native_weights.pdf') as pdf:
        for manual in cfg['manual_sources']:
            index = manual['train_index']; view = bindings['train'][index]
            row = receipt['views'][index]; folder = args.annotations / row['folder']
            checked_bytes(Path('/prior_input/scene/images')/view['name'], view['sha256'])
            rgb = np.asarray(Image.open(Path('/prior_input/scene/images')/view['name']).convert('RGB'))
            depth = read_colmap_depth(Path('/mvs_input')/view['local_depth'], view['maps']['depth'])
            with np.load(folder/'native_masks.npz', allow_pickle=False) as data:
                labels = data['region_id']; valid = data['valid']
            limits = np.percentile(depth[valid], [2,98])
            fig, axes = plt.subplots(2,3,figsize=(18,10.8))
            fig.suptitle(f'{region} · R1–R4 수동 영역과 전체 native depth 가중치\n{view["name"]} · 학습 시점 {index} · 검토용 초안', x=.025, ha='left', fontsize=17,y=.975)
            axes[0,0].imshow(rgb); axes[0,0].set_title('현재 RGB · 전체 1400×1013',loc='left')
            cmap = matplotlib.colormaps['viridis'].copy(); cmap.set_bad('#DCDCE0')
            im=axes[0,1].imshow(np.ma.masked_where(~valid, depth),cmap=cmap,vmin=limits[0],vmax=limits[1],interpolation='nearest')
            axes[0,1].set_title('원본 MVS · 전체 1024×741 · 색은 깊이',loc='left')
            cb=fig.colorbar(im,ax=axes[0,1],fraction=.027,pad=.01); cb.set_label('camera-Z (m)',fontsize=9)
            axes[0,2].imshow(lut[labels],interpolation='nearest'); axes[0,2].set_title('영역 분류도 · 전체 픽셀 R1–R6',loc='left')
            for axis, alpha in zip(axes[1],cfg['candidate_alpha_values']):
                weights = np.zeros(labels.shape,np.float32)
                weights[np.isin(labels,[2,3])] = 1; weights[labels==1] = alpha
                colors=np.full((*labels.shape,3),[53,58,64],np.uint8)
                colors[weights==1]=[72,163,125]
                colors[weights>1]=[230,159,0]
                axis.imshow(colors,interpolation='nearest')
                axis.set_title(f'R1 가중치 α={alpha} · 나머지 R2/R3=1, 제외=0',loc='left',fontsize=11)
                np.save(args.output/f'{region}_{index:03d}_native_weight_alpha{alpha}.npy',weights,allow_pickle=False)
                Image.fromarray(colors).save(args.output/f'{region}_{index:03d}_native_weight_alpha{alpha}.png')
            for axis in axes.flat: axis.axis('off')
            handles=[Patch(facecolor=cfg['colors'][str(i)],label=f'R{i} {cfg["region_labels"][str(i)]}') for i in range(1,7)]
            fig.legend(handles=handles,ncol=3,loc='lower center',bbox_to_anchor=(.49,.062),frameon=False,fontsize=11)
            fig.text(.025,.043,'가중치 도면: 진회색=0 · 초록=1 · 주황=4. R4·R5·R6 및 depth 결측은 모두 0. 원본 depth의 파란색은 가중치 영역이 아닙니다.',fontsize=11)
            fig.text(.025,.022,'R1은 수동 보정 시험 대상이며 MVS 정확성·실제 변화 판정이 아닙니다. 결측과 경계는 제외. P2/P3 학습에는 아직 연결하지 않았습니다.',fontsize=10)
            fig.subplots_adjust(left=.025,right=.985,top=.865,bottom=.15,hspace=.2,wspace=.1)
            target=args.output/f'{region}_{index:03d}_native_regions_weights.png'
            fig.savefig(target,dpi=115); pdf.savefig(fig,dpi=110); plt.close(fig)
            source_rows.append(dict(train_index=index,name=view['name'],native_counts=row['native_counts'],rgb_counts=row['rgb_counts'],image=target.name))
    # Lightweight gallery includes every generated view, keeping full-frame context.
    frame_dir=args.output/'frames'; frame_dir.mkdir()
    for row in receipt['views']:
        with Image.open(args.annotations/row['folder']/'full_frame.png') as im:
            im.convert('RGB').save(frame_dir/f'{row["train_index"]:03d}.jpg',quality=91)
    shutil.copyfile(args.annotations/f'{region}_all_{len(receipt["views"])}_views.pdf',args.output/f'{region}_all_views.pdf')
    result=dict(status='PASS_NATIVE_SOURCE_REVIEW',scientific_verdict=None,training_executed=False,
                annotations_receipt_sha256=sha(args.annotations/'receipt.json'),config_sha256=receipt['config_sha256'],
                region=region,sources=source_rows,views=receipt['views'],
                note='Source polygons manually inspected by assistant; remaining views receive correspondence-checked transfer. No all-pixel semantic accuracy or calibrated confidence claim.',
                outputs=[dict(path=str(p.relative_to(args.output)),sha256=sha(p)) for p in sorted(args.output.rglob('*')) if p.is_file()])
    (args.output/'review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k not in ('views','outputs')},ensure_ascii=False),flush=True)


if __name__=='__main__': main()
