"""Run the isolated CPU audit and publish one full-RGB boolean R1 mask."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Patch
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mask_audit import audit_mask, array_stats
from mvs_depth import checked_bytes, read_colmap_depth, load_view_depth
from manual_region_masks_v1 import unproject, polygon_mask, resample_nearest


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_json(path, data):
    with Path(path).open('x') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--runtime-image-id', required=True)
    args = parser.parse_args()
    if not Path('/.dockerenv').exists() or Path('/reference').exists() or Path('/artifacts/JointBuildGS').exists():
        raise RuntimeError('Use the isolated CPU Docker command with narrow inputs')
    cfg = json.loads(args.config.read_text())
    out = args.output
    out.mkdir(parents=True, exist_ok=False)
    try:
        binding = json.loads(checked_bytes('/mvs_input/bindings.json', cfg['binding_sha256']))
        view = binding['train'][cfg['train_index']]
        if view['name'] != cfg['camera_name'] or view['name'] in binding['evaluation_names']:
            raise ValueError('Expected only frozen training camera 0100_D')
        prior_manifest = json.loads(checked_bytes('/prior_input/input_manifest.json', binding['parent_input_manifest_sha256']))
        ledger = {row['path']: row['sha256'] for row in prior_manifest['files']}
        parent = Path('/parent_masks')
        parent_receipt = json.loads(checked_bytes(parent/'receipt.json', cfg['parent_mask_receipt_sha256']))
        checked_bytes('/parent_config.json', cfg['parent_manual_config_sha256'])
        manual_cfg = json.loads(Path('/parent_config.json').read_text())
        folder = parent/'views'/('000_'+Path(view['name']).stem)
        checked_bytes(folder/'native_masks.npz', cfg['parent_native_masks_sha256'])
        checked_bytes(folder/'rgb_masks.npz', cfg['parent_rgb_masks_sha256'])
        native_masks = np.load(folder/'native_masks.npz', allow_pickle=False)
        rgb_masks = np.load(folder/'rgb_masks.npz', allow_pickle=False)
        depth_path = Path('/mvs_input')/view['local_depth']
        rgb_path = Path('/prior_input/scene/images')/view['name']
        rgb_depth, _, loader = load_view_depth(view, depth_path=depth_path, rgb_path=rgb_path)
        native = read_colmap_depth(depth_path, view['maps']['depth'])
        rgb = np.asarray(Image.open(rgb_path).convert('RGB'))
        source = next(item for item in manual_cfg['manual_sources'] if item['name'] == view['name'])
        semantic_rgb = polygon_mask(1400, 1013, source['polygons'], source['default_region'])
        semantic_native = resample_nearest(semantic_rgb, view['K'], view['maps']['depth']['K'], 1024, 741, 5)
        exclusions_rgb = polygon_mask(1400, 1013, cfg['extra_exclusion_polygons_rgb'], 0) > 0
        exclusions_native = resample_nearest(exclusions_rgb, view['K'], view['maps']['depth']['K'], 1024, 741, False)
        arrays, diagnostic, stats = audit_mask(native, rgb_depth, view, native_masks, rgb_masks,
                                               semantic_native, exclusions_native, cfg, unproject, resample_nearest)
        prior_rel = 'prior/raw_depth/'+Path(view['name']).stem+'.npy'
        prior_path = Path('/prior_input')/prior_rel
        checked_bytes(prior_path, ledger[prior_rel])
        prior = np.load(prior_path, allow_pickle=False)
        r1 = arrays['r1_mask']; valid = arrays['valid_rgb']; use_mask = arrays['use_mask']
        common = r1 & np.isfinite(prior) & (prior > 0)
        stats['r1_rgb_prior_depth_m'] = array_stats(prior[common])
        stats['r1_rgb_mvs_minus_prior_m'] = array_stats((rgb_depth-prior)[common])
        np.savez_compressed(out/'r1_mask.npz', **arrays)
        Image.fromarray(r1.astype(np.uint8)*255).save(out/'r1_mask_rgb.png')
        font_manager.fontManager.addfont(cfg['font_path'])
        plt.rcParams.update({'font.family':font_manager.FontProperties(fname=cfg['font_path']).get_name(), 'axes.unicode_minus':False})
        overlay = rgb.astype(float)
        overlay[r1] = .7*overlay[r1]+.3*np.array([230,159,0])
        overlay = overlay.astype(np.uint8)
        xyz = diagnostic['xyz_rgb']
        mask_extent = np.zeros(r1.shape, np.uint8)
        mask_extent[r1 & diagnostic['evaluation_rgb']] = 1
        mask_extent[r1 & ~diagnostic['evaluation_rgb']] = 2
        limits = np.percentile(rgb_depth[valid],[2,98])
        depth_masked = np.ma.masked_where(~valid, rgb_depth)
        cmap=matplotlib.colormaps['viridis'].copy();cmap.set_bad('#dddddd')
        with PdfPages(out/'0100_D_mask_audit.pdf') as pdf:
            fig, axes = plt.subplots(2,2,figsize=(15,11))
            axes[0,0].imshow(overlay);axes[0,0].set_title('전체 RGB 1400×1013 · R1 경계 유지')
            im=axes[0,1].imshow(depth_masked,cmap=cmap,vmin=limits[0],vmax=limits[1]);fig.colorbar(im,ax=axes[0,1],label='camera Z (m)')
            axes[0,1].contour(r1,levels=[.5],colors=['#e69f00'],linewidths=.8);axes[0,1].set_title('전체 MVS · native 1024×741에서 같은 nearest 조회')
            palette=matplotlib.colors.ListedColormap(['#eeeeee','#0072b2','#e69f00'])
            axes[1,0].imshow(mask_extent,cmap=palette,vmin=0,vmax=2,interpolation='nearest')
            axes[1,0].set_title('R1 범위 · 파랑=기존 30×30m 안 / 주황=밖·80×80m 안')
            selected=np.ma.masked_where(~r1,xyz[...,2]);im=axes[1,1].imshow(selected,cmap=cmap)
            fig.colorbar(im,ax=axes[1,1],label='local Z (m)');axes[1,1].set_title('R1의 current MVS 파생 높이 · 정확도/GT 아님')
            for ax in axes.flat:ax.set_xlabel('전체영상 x pixel');ax.set_ylabel('전체영상 y pixel')
            fig.suptitle('0100_D 수동 판단 영역만 감독신호 사용 · 기존 R1 유지',fontsize=17)
            fig.text(.06,.018,'0100_D만: R1=α, R2/R3=1, R4/R5/R6/결측=0 · 다른 97개 카메라의 기존 감독신호 정책 유지',fontsize=11)
            fig.tight_layout(rect=[0,.04,1,.96]);fig.savefig(out/'0100_D_full_frame_audit.png',dpi=140);pdf.savefig(fig);plt.close(fig)
            x0,y0,x1,y1=stats['r1_rgb_bbox_xyxy'];pad=25;x0=max(0,x0-pad);y0=max(0,y0-pad);x1=min(1400,x1+pad);y1=min(1013,y1+pad)
            sl=np.s_[y0:y1,x0:x1]
            fig,axes=plt.subplots(2,2,figsize=(13,11))
            extent=[x0,x1,y1,y0]
            axes[0,0].imshow(rgb[sl],extent=extent);axes[0,0].set_title('R1 주변 확대 RGB · 원본 좌표')
            axes[0,1].imshow(overlay[sl],extent=extent);axes[0,1].set_title('같은 확대 · R1 주황/제외부 원색')
            im=axes[1,0].imshow(depth_masked[sl],extent=extent,cmap=cmap,vmin=limits[0],vmax=limits[1]);fig.colorbar(im,ax=axes[1,0],label='camera Z (m)');axes[1,0].set_title('MVS 원값·결측 보존')
            pp=np.ma.masked_where(~(np.isfinite(prior)&(prior>0)),prior)
            im=axes[1,1].imshow(pp[sl],extent=extent,cmap=cmap,vmin=limits[0],vmax=limits[1]);fig.colorbar(im,ax=axes[1,1],label='camera Z (m)');axes[1,1].set_title('ALS prior 입력 깊이 · 같은 색 범위')
            for ax in axes.flat:ax.grid(alpha=.2);ax.set_xlabel('전체영상 x pixel');ax.set_ylabel('전체영상 y pixel')
            fig.text(.04,.015,'확대 그림만 crop이며 학습 마스크는 전체 1400×1013 boolean · prior 반 픽셀/nearest MVS ray 차이 유지',fontsize=10)
            fig.tight_layout(rect=[0,.04,1,1]);fig.savefig(out/'0100_D_r1_zoom_audit.png',dpi=150);pdf.savefig(fig);plt.close(fig)
            region_colors = ['#E69F00','#267DB3','#6F8C62','#BD5C86','#B8B8BE','#353A40']
            region_names = ['A → R1 보정 시험 지면: α','C → R2 현재 건물 표면: 1',
                            'B → R3 기타 정적 지면: 1','D → R4 관측 제외 대상: 0',
                            'R5 미분류·판단 유보: 0','R6 80m 문맥 범위 밖: 0']
            rgb_labels=arrays['region_id']; native_labels=arrays['region_id_native']
            palette_rgb=(matplotlib.colors.to_rgba_array(region_colors)[:,:3]*255).astype(np.uint8)
            semantic_overlay=(.62*rgb+.38*palette_rgb[rgb_labels-1]).astype(np.uint8)
            fig,axes=plt.subplots(1,2,figsize=(17,8))
            axes[0].imshow(semantic_overlay);axes[0].set_title('전체 RGB 위 기존 수동 분류 · 색=영역 ID')
            im=axes[1].imshow(np.ma.masked_where(~arrays['valid_native'],native),cmap=cmap,vmin=limits[0],vmax=limits[1])
            for region,color in zip(range(1,7),region_colors):
                axes[1].contour(native_labels==region,levels=[.5],colors=[color],linewidths=.65)
            axes[1].set_title('전체 native MVS 원값 위 영역 윤곽 · 결측만 회색')
            fig.colorbar(im,ax=axes[1],label='camera Z (m)',shrink=.8)
            axes[0].set_xlabel('RGB x pixel');axes[0].set_ylabel('RGB y pixel')
            axes[1].set_xlabel('native x pixel');axes[1].set_ylabel('native y pixel')
            fig.legend(handles=[Patch(facecolor=c,label=n) for c,n in zip(region_colors,region_names)],loc='lower center',ncol=3,bbox_to_anchor=(.5,.035))
            fig.text(.035,.01,'A/B/C/D는 최초 의미 구분이며 저장된 R1/R3/R2/R4에 대응합니다. 유효한 R1/R2/R3만 use_mask=True입니다.',fontsize=11)
            fig.tight_layout(rect=[0,.13,1,1]);fig.savefig(out/'0100_D_manual_region_support.png',dpi=140);pdf.savefig(fig);plt.close(fig)
            weights={}
            fig,axes=plt.subplots(1,3,figsize=(18,6.5))
            wcmap=matplotlib.colors.ListedColormap(['#e0e0e0','#56b4e9','#e69f00'])
            wnorm=matplotlib.colors.BoundaryNorm([-.5,.5,2.5,4.5],3)
            for ax,alpha in zip(axes,cfg['alpha_values']):
                weight=use_mask.astype(np.float32);weight[r1]=alpha;weights['alpha'+str(alpha)]=weight
                im=ax.imshow(weight,cmap=wcmap,norm=wnorm,interpolation='nearest')
                ax.contour(r1,levels=[.5],colors=['#d55e00'],linewidths=.7)
                ax.set_title('α='+str(alpha)+' · 수동 판단 영역만 사용');ax.set_xlabel('RGB x pixel');ax.set_ylabel('RGB y pixel')
            fig.colorbar(im,ax=list(axes),ticks=[0,1,4],label='depth-loss multiplier',shrink=.85)
            fig.text(.025,.05,'회색=0: 제외 객체 R4 / 미분류 R5 / 범위 밖 R6 / 결측 (+ α=0일 때 R1). 파랑=1, 주황=4.',fontsize=11)
            fig.text(.025,.014,'0100_D의 R1만 α=0/1/4, R2/R3는 항상 1. 다른 97개 카메라의 depth 감독신호는 기존 합의를 유지합니다.',fontsize=11)
            fig.savefig(out/'0100_D_actual_manual_support_alpha0_1_4.png',dpi=140);pdf.savefig(fig);plt.close(fig)
            np.savez_compressed(out/'audit_weight_maps.npz',**weights)
        receipt={'task_id':cfg['task_id'],'status':'PASS_SINGLE_VIEW_MANUAL_SUPPORT_AUDIT','scientific_verdict':None,
                 'created_utc':datetime.now(timezone.utc).isoformat(),'camera_name':view['name'],'image_id':view['image_id'],
                 'train_index':cfg['train_index'],'mask_npz':'r1_mask.npz','mask_key':'r1_mask','mask_sha256':sha(out/'r1_mask.npz'),
                 'mask_dtype':'bool','mask_shape':[1013,1400],'native_mask_key':'r1_native','native_shape':[741,1024],
                 'use_mask_key':'use_mask','use_mask_dtype':'bool','use_mask_shape':[1013,1400],
                 'binding_sha256':cfg['binding_sha256'],'parent_input_manifest_sha256':binding['parent_input_manifest_sha256'],
                 'rgb_sha256':view['sha256'],'mvs_depth_sha256':view['maps']['depth']['sha256'],'prior_depth_sha256':ledger[prior_rel],
                 'parent_mask_receipt_sha256':cfg['parent_mask_receipt_sha256'],'parent_native_masks_sha256':cfg['parent_native_masks_sha256'],
                 'parent_rgb_masks_sha256':cfg['parent_rgb_masks_sha256'],'config':cfg,'config_sha256':sha(args.config),
                 'source_snapshot_hashes':{p.name:sha(p) for p in Path(__file__).parent.iterdir() if p.is_file()},
                 'commit':args.commit,'runtime_image_id':args.runtime_image_id,'python':platform.python_version(),'numpy':np.__version__,
                 'stats':stats,'loader':loader,'crs':prior_manifest['crs'],
                 'pdf_scope':'Pages 1, 3, 4 use full-frame coordinates; page 2 is a labeled zoom. Pages 3 and 4 document the user-confirmed manual-only support revision.',
                 'weight_policy':cfg['weight_policy'],'training_executed':False,'gpu_exposed':False,'reference_accessed':False,
                 'semantic_accuracy_certified':False,
                 'limitations':['Manual input inspection cannot certify every subpixel object or true geometry.',
                                'Height and disagreement statistics derive from training inputs, not independent truth.',
                                'R1 retains the whole approved 80m-context mask, including parts outside the old 30m prism.'],
                 'outputs':[{'path':p.name,'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(out.iterdir()) if p.is_file()]}
        save_json(out/'receipt.json',receipt)
        print(json.dumps({'status':receipt['status'],'mask_sha256':receipt['mask_sha256'],'stats':stats},ensure_ascii=False),flush=True)
    except Exception as exc:
        save_json(out/'failure.json',{'status':'FAILED','error':repr(exc),'scientific_verdict':None})
        raise


if __name__=='__main__':
    main()
