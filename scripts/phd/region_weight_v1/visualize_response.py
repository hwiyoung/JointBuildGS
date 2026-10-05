"""Locate final depth residuals; all masks and training outputs remain immutable."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

import cv2
import numpy as np
from PIL import Image
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path): return json.loads(Path(path).read_text())


def stats(values):
    a=np.abs(np.asarray(values,dtype=np.float64))
    if not a.size: return dict(n=0)
    total=a.sum()
    return dict(n=int(a.size),mae_m=float(a.mean()),median_m=float(np.median(a)),
                p90_m=float(np.quantile(a,.90)),p95_m=float(np.quantile(a,.95)),
                le_01_fraction=float((a<=.1).mean()),gt_1_fraction=float((a>1).mean()),
                gt_10_count=int((a>10).sum()),gt_10_fraction=float((a>10).mean()),
                gt_10_share_of_abs_error=float(a[a>10].sum()/total) if total else 0.)


def main():
    if not Path('/.dockerenv').exists(): raise RuntimeError('Docker required')
    ap=argparse.ArgumentParser(); ap.add_argument('--config',required=True)
    ap.add_argument('--payload',default='/payload');ap.add_argument('--out',default='/out')
    args=ap.parse_args();cfg=read(args.config);p=Path(args.payload);out=Path(args.out)
    sys.path.insert(0,'/repo/src/phd/geogs_mvs_pgsr_v1')
    from mvs_depth import load_view_depth
    v=p/cfg['viewer_root'];manifest=read(v/cfg['destination']/'manifest.json')
    font_manager.fontManager.addfont(cfg['font'])
    plt.rcParams.update({'font.family':font_manager.FontProperties(fname=cfg['font']).get_name(),'axes.unicode_minus':False})
    result=dict(schema='weight_response_v1',scientific_verdict=None,training_changed=False,
                definition='Full valid R1 image pixels; camera-Z residual, not vertical roof displacement or independent accuracy.',
                thresholds='0.1/1/10m are descriptive diagnostic bins only; not new confidence thresholds or masks.',
                regions={},inputs={},config_sha256=sha(args.config),script_sha256=sha(__file__),runtime=cfg['runtime_image'])
    def bind(path): result['inputs'][str(path)]=sha(path);return read(path)
    for region in ['P1','P2','P3']:
        run=p/cfg['P1'] if region=='P1' else p/cfg['P2P3']/region
        rcfg=bind(run/'config.json'); bp=p/cfg['mvs_root']/region;binding=bind(bp/'bindings.json')
        assert sha(bp/'bindings.json')==rcfg['binding_sha256']
        masks=None if region=='P1' else bind(run/'mask/manifest.json')
        display=next(x for x in manifest['regions'] if x['id']==region)
        views=[x for x in display['views'] if x['split']=='train']; rr=dict(views=[],exposure={})
        for a in [0,1,4]:
            prefix='p1_weight' if region=='P1' else 'region_weight'
            trace=run/f'train/alpha_{a}/model/{prefix}_camera_trace.jsonl'
            result['inputs'][str(trace)]=sha(trace)
            counts=Counter(json.loads(line)['camera'] for line in trace.read_text().splitlines())
            supported={rcfg['target_camera']} if region=='P1' else {x['camera'] for x in masks['views'] if x['r1_pixels']>0}
            rr['exposure'][str(a)]=dict(total_steps=sum(counts.values()),train_cameras=len(counts),r1_cameras=len(supported),
                r1_steps=sum(counts[x] for x in supported),selected_view_visits={x['image_name']:counts[Path(x['image_name']).stem] for x in views})
        for view in views:
            name=view['image_name']; cam=next(x for x in binding['train'] if x['name']==name)
            target,valid,_=load_view_depth(cam,verify_rgb=False,depth_path=bp/cam['local_depth'])
            result['inputs'][str(bp/cam['local_depth'])]=cam['maps']['depth']['sha256']
            rgb_path=v/view['original']['url'].removeprefix('/data/'); assert sha(rgb_path)==view['original']['sha256']
            rgb=np.asarray(Image.open(rgb_path).convert('RGB')); result['inputs'][str(rgb_path)]=sha(rgb_path)
            if region=='P1': mp=run/'mask/r1_mask.npz'
            else:
                m=next(x for x in masks['views'] if x['camera']==Path(name).stem);mp=run/'mask'/m['path'];assert sha(mp)==m['sha256']
            result['inputs'][str(mp)]=sha(mp)
            with np.load(mp,allow_pickle=False) as m: r1=m['region_id']==1
            prior_path=p/f'geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/inputs/{region}/prior/raw_depth/{Path(name).stem}.npy'
            prior=cv2.resize(np.load(prior_path),(cam['width'],cam['height']),interpolation=cv2.INTER_LINEAR)
            result['inputs'][str(prior_path)]=sha(prior_path)
            predictions={}
            for a in [0,1,4]:
                item=view['conditions'][f'alpha_{a}'];rgb_file=v/item['rgb']['url'].removeprefix('/data/')
                file=rgb_file.parent.parent/'vis'/('depth_'+rgb_file.stem+'.tiff')
                assert sha(file)==item['source_depth_sha256'];result['inputs'][str(file)]=sha(file)
                predictions[a]=np.asarray(Image.open(file),dtype=np.float32)
            common=r1&valid&np.logical_and.reduce([np.isfinite(x)&(x>0) for x in predictions.values()])
            errors={a:predictions[a]-target for a in predictions}
            yy,xx=np.indices(target.shape)
            rays=np.stack([xx,yy,np.ones_like(xx)],-1)@np.linalg.inv(cam['K']).T
            xyz=(rays*target[...,None]-np.asarray(cam['t']))@np.asarray(cam['R'])
            in_roi=((xyz>=np.asarray(display['bounds']['min']))&(xyz<np.asarray(display['bounds']['max']))).all(-1)
            report=dict(name=name,id=view['id'],figure=f'{region}_{view["id"]}.png',
                stats={str(a):stats(errors[a][common]) for a in predictions},
                roi_stats={str(a):stats(errors[a][common&in_roi]) for a in predictions},
                outside_roi_stats={str(a):stats(errors[a][common&~in_roi]) for a in predictions},
                difference_1_to_4=stats((predictions[4]-predictions[1])[common]),
                native_valid=int(valid.sum()),r1_pixels=int(common.sum()),roi_pixels=int((common&in_roi).sum()),
                probes=[])
            if region=='P3' and view['id']=='source_4':
                selections=[('A','대부분의 작은 잔차',common&(np.abs(errors[4])<=.1)),
                            ('B','큰 잔차 표본',common&(np.abs(errors[4])>10))]
            else:
                selections=[('A','0→1에서 줄어든 잔차',common&(np.abs(errors[0])>1)&(np.abs(errors[1])<.1)),
                            ('B','1→4에서 추가 감소',common&(np.abs(errors[1])>.2)&(np.abs(errors[4])<.1))]
            for label,meaning,mask in selections:
                ys,xs=np.where(mask)
                if not len(ys): continue
                center=np.array([np.median(ys),np.median(xs)])
                i=np.argmin((ys-center[0])**2+(xs-center[1])**2);y,x=int(ys[i]),int(xs[i])
                report['probes'].append(dict(label=label,meaning=meaning,x=x,y=y,MVS=float(target[y,x]),
                    prior=float(prior[y,x]) if np.isfinite(prior[y,x]) and prior[y,x]>0 else None,GS={str(a):float(z[y,x]) for a,z in predictions.items()},
                    current_mvs_xyz=xyz[y,x].tolist(),in_viewer_roi=bool(in_roi[y,x]),
                    selection='Nearest pixel to component-wise median of the stated residual group; illustration only.'))
            fig,axes=plt.subplots(2,3,figsize=(17,11)); axes=axes.ravel()
            axes[0].imshow(rgb); axes[0].contour(common,levels=[.5],colors=['#ffbe33'],linewidths=.65)
            axes[0].set_title('원사진 · 노란 경계 = R1 유효 감독\nA/B는 아래에 수치를 적은 예시 픽셀')
            vmax=45 if region=='P3' and view['id']=='source_4' else 6
            cmap=matplotlib.colormaps['magma'].copy();cmap.set_bad('#dfe3e8')
            for ax,a in zip(axes[1:4],[0,1,4]):
                im=ax.imshow(np.ma.masked_where(~common,np.abs(errors[a])),cmap=cmap,vmin=0,vmax=vmax,interpolation='nearest')
                ax.set_title(f'가중치 {a} · |GS depth − MVS depth|\n평균 {report["stats"][str(a)]["mae_m"]:.3f}m / 중앙값 {report["stats"][str(a)]["median_m"]:.3f}m')
                fig.colorbar(im,ax=ax,fraction=.03,pad=.015,label='m')
            im=axes[4].imshow(np.ma.masked_where(~common,np.abs(predictions[4]-predictions[1])),cmap=cmap,vmin=0,vmax=.5,interpolation='nearest')
            axes[4].set_title('가중치 1↔4의 최종 depth 차이\n0–0.5m 확대 색상 범위');fig.colorbar(im,ax=axes[4],fraction=.03,pad=.015,label='m')
            for a in [0,1,4]:
                values=np.sort(np.abs(errors[a][common]));idx=np.unique(np.linspace(0,len(values)-1,min(3000,len(values))).astype(int))
                axes[5].plot(values[idx],100*(idx+1)/len(values),label=f'가중치 {a}')
            axes[5].set_xscale('symlog',linthresh=.01);axes[5].set_ylim(0,101);axes[5].grid(alpha=.25)
            axes[5].set_xlabel('절대 depth 잔차 (m, 0.01m 이후 로그 축)');axes[5].set_ylabel('이 잔차 이하인 R1 픽셀 (%)');axes[5].legend()
            axes[5].set_title('잔차 분포 · 평균과 함께 확인')
            for ax in axes[:5]:
                ax.set_xticks([]);ax.set_yticks([])
                for probe in report['probes']:
                    x,y=probe['x'],probe['y'];ax.plot(x,y,'o',ms=5,mfc='none',mec='#24e8df',mew=1.2)
                    ax.annotate(probe['label'],(x,y),xytext=(7,-10),textcoords='offset points',color='black',weight='bold',bbox=dict(fc='white',alpha=.85,pad=1))
            fig.suptitle(f'{region} · {name}\n입력 적합도 변화의 위치 — 표면 높이 변화나 독립 정확도가 아님',fontsize=17)
            lines=[]
            for q in report['probes']:
                prior_text=f'{q["prior"]:.2f}' if q['prior'] is not None else 'invalid'
                lines.append(f'{q["label"]} ({q["x"]}, {q["y"]}) · MVS {q["MVS"]:.2f} / prior {prior_text} / GS 0: {q["GS"]["0"]:.2f}, 1: {q["GS"]["1"]:.2f}, 4: {q["GS"]["4"]:.2f} m (camera-Z)')
            fig.text(.03,.055,'\n'.join(lines),fontsize=11,va='center')
            fig.text(.03,.012,f'R1 전체 {common.sum():,}px 중 기존 3D 평가 범위 안의 MVS 표본 {(common&in_roi).sum():,}px. 회색은 이 잔차 집계 밖이며 0m가 아닙니다.',fontsize=10)
            fig.subplots_adjust(top=.86,bottom=.13,left=.02,right=.96,hspace=.22,wspace=.28)
            fig.savefig(out/report['figure'],dpi=140);plt.close(fig)
            report['figure_sha256']=sha(out/report['figure']);rr['views'].append(report)
        result['regions'][region]=rr
    result['mvs_helper_sha256']=sha('/repo/src/phd/geogs_mvs_pgsr_v1/mvs_depth.py')
    with (out/'response.json').open('x') as f: json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False)
    print(json.dumps({r:[dict(name=x['name'],stats=x['stats'],roi_stats=x['roi_stats'],probes=x['probes']) for x in rr['views']] for r,rr in result['regions'].items()},ensure_ascii=False))


if __name__=='__main__': main()
