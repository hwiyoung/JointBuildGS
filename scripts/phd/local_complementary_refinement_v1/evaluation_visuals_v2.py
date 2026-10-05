"""Matched real-camera and fixed-band sections from sealed v2 evaluation.

Chart contract: compare the same source photograph, Anchor8k, matched global G,
and LC; compare observed UAS and sampled raw TSDF512 geometry in common 0.5m
central X/Y bands. Axes, crop, pixels, sample size and missingness stay explicit.
Neutral reference dots and blue method crosses distinguish series without color
alone. Figures are standalone PNG evidence; no viewer/service changes occur.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import resource
import time

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageDraw

from evaluation_utils_v2 import read_json, write_json, sha, require_membership, safe_child
from evaluate_v2 import Evidence, GEOMETRY_DIR, PARENT_SEAL_SHA, load_module, load_split, snapshot_implementation


def section_figure(path, reference, candidates, bounds, width=.5, title='Matched raw TSDF512 sections'):
    """All samples in fixed midpoint bands; no residual-driven point filtering."""
    bounds=np.asarray(bounds,dtype=float)
    if bounds.shape!=(3,2) or not np.isfinite(bounds).all() or width<=0:
        raise ValueError('Finite 3D bounds and positive band width required')
    figure,axes=plt.subplots(2,3,figsize=(15,9),sharex='row',sharey=True,layout='constrained')
    records=[]
    try:
        for row,dimension in enumerate((0,1)):
            center=float(bounds[dimension].mean());horizontal=1-dimension
            selected_ref=reference[np.abs(reference[:,dimension]-center)<width/2]
            for col,(label,points) in enumerate(candidates):
                selected=points[np.abs(points[:,dimension]-center)<width/2]
                ax=axes[row,col]
                ax.scatter(selected_ref[:,horizontal],selected_ref[:,2],s=2,c='#555555',marker='.',
                           label='Observed UAS',rasterized=True)
                ax.scatter(selected[:,horizontal],selected[:,2],s=4,c='#2E6FBB',marker='x',linewidths=.35,
                           label=label,rasterized=True)
                ax.set(xlim=bounds[horizontal],ylim=bounds[2],xlabel=('Y' if horizontal else 'X')+' (m)',ylabel='Z (m)')
                ax.set_title(f'{label}\n{"X" if dimension==0 else "Y"}={center:.2f} m; UAS n={len(selected_ref):,}; surface n={len(selected):,}',fontsize=10)
                ax.set_aspect('equal',adjustable='box');ax.grid(color='#DDDDDD',linewidth=.5)
                if not len(selected_ref):ax.text(.03,.96,'No observed UAS in this band',transform=ax.transAxes,va='top',fontsize=8)
                if not len(selected):ax.text(.03,.87,'No candidate samples in this band',transform=ax.transAxes,va='top',fontsize=8)
                records.append(dict(candidate=label,axis='XY'[dimension],center_m=center,width_m=width,
                    reference_samples=len(selected_ref),prediction_samples=len(selected),
                    horizontal_bounds_m=bounds[horizontal].tolist(),z_bounds_m=bounds[2].tolist()))
        axes[0,0].legend(loc='lower left',fontsize=8)
        figure.suptitle(title+'\n0.5 m sample bands, not mesh-plane intersections; common axes; reference gaps remain unassessed.',fontsize=12)
        if Path(path).exists():raise FileExistsError(path)
        figure.savefig(path,dpi=160)
    finally:plt.close(figure)
    return records


def photo_figure(path, arrays, labels, bbox):
    if len(arrays)!=4 or len(labels)!=4 or any(a.shape!=arrays[0].shape or a.dtype!=np.uint8 for a in arrays):
        raise ValueError('Four equal-size original uint8 RGB arrays required')
    x0,y0,x1,y1=bbox
    if not (0<=x0<x1<=arrays[0].shape[1] and 0<=y0<y1<=arrays[0].shape[0]):
        raise ValueError('Fixed half-open image bounds required')
    crops=[a[y0:y1,x0:x1] for a in arrays]
    height,width=crops[0].shape[:2];panel=max(width,260)
    canvas=Image.new('RGB',(panel*4,height+56),'white');draw=ImageDraw.Draw(canvas)
    for index,(crop,label) in enumerate(zip(crops,labels)):
        canvas.paste(Image.fromarray(crop),(index*panel,56))
        draw.text((index*panel+6,8),label,fill='#222222')
        draw.text((index*panel+6,27),f'Original pixels; common crop {width} x {height}',fill='#555555')
    if Path(path).exists():raise FileExistsError(path)
    canvas.save(path)
    return dict(bbox=list(bbox),pixel_resize=False,exposure_fit=False,alpha_filter=False,
                black_pixels_included=True,panel_padding_only=panel-width,crop_shape=list(crops[0].shape))


def _sealed_candidate(seal,region,condition,variant):
    matches=[c for c in seal['candidates'] if c['region']==region and c['condition']==condition
             and c['variant']==variant and c['mesh_kind']=='raw']
    if len(matches)!=1:raise ValueError('Expected one sealed candidate render identity')
    return matches[0]


def _load_arrays(path, expected, evidence):
    evidence.bind(path,expected)
    with np.load(path,allow_pickle=False) as data:
        return {key:data[key] for key in ('prediction_surface_samples','reference_points','reference_original_indices')}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evaluation',type=Path)
    parser.add_argument('--task',type=Path,default=Path('/task/main_v2'))
    parser.add_argument('--parent',type=Path,default=Path('/parent'))
    parser.add_argument('--config',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--self-test',action='store_true')
    args=parser.parse_args()
    if not Path('/.dockerenv').is_file():raise RuntimeError('Docker required')
    output=safe_child(args.output,'attempt_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'))
    output.mkdir(parents=True,exist_ok=False)
    if args.self_test:
        points=np.array([[.5,.4,.1],[.5,.6,.2],[.4,.5,.1],[.6,.5,.2]])
        section_figure(output/'synthetic_sections.png',points,[(n,points) for n in ('Anchor8k','Global G','Local LC')],[[0,1],[0,1],[0,1]])
        arrays=[np.full((180,300,3),v,np.uint8) for v in (80,110,160,200)]
        photo_figure(output/'synthetic_photo.png',arrays,['Actual photograph','Anchor8k','Global G','Local LC'],[10,10,290,170])
        print(json.dumps(dict(status='PASS_SYNTHETIC_FIGURES',output=str(output),scientific_verdict=None)));return
    if args.evaluation is None or args.config is None:raise ValueError('--evaluation and --config required')
    parent=args.parent.resolve();task=args.task.resolve();evaluation=args.evaluation.resolve()
    if output.is_relative_to(parent) or parent.is_relative_to(output):raise ValueError('Output overlaps parent')
    evidence=Evidence();started=time.time();records=[]
    from run_selection_v2 import run_from_evaluation
    implementation=(Path(__file__),Path(__file__).with_name('evaluation_utils_v2.py'),Path(__file__).with_name('evaluate_v2.py'),Path(__file__).with_name('run_selection_v2.py'))
    snapshots=snapshot_implementation(output,implementation,evidence);evidence.bind(args.config)
    cfg=read_json(args.config);receipt_path=evaluation/'receipt.json';evidence.bind(receipt_path)
    receipt=read_json(receipt_path)
    if receipt['status'] not in ('COMPLETE_DEVELOPMENT_EVALUATION','PARTIAL_DEVELOPMENT_EVALUATION') or receipt['scientific_verdict'] is not None:
        raise ValueError('Completed v2 technical evaluation required')
    config_digests=[r['sha256'] for r in receipt['inputs'] if r['path'].endswith('/experiment_v2.json')]
    if not config_digests or set(config_digests)!={sha(args.config)}:raise ValueError('Evaluation configuration differs')
    outputs={r['path']:r['sha256'] for r in receipt['outputs']}
    sealed_path=parent/'contracts/candidates_sealed_v1.json';evidence.bind(sealed_path,PARENT_SEAL_SHA);seal=read_json(sealed_path)
    quality=load_module('lc_visual_render_quality',GEOMETRY_DIR/'render_quality.py');evidence.bind(GEOMETRY_DIR/'render_quality.py')
    try:
        for region in receipt['selected_regions']:
            _,views=load_split(parent,region,evidence)
            for condition in cfg['conditions']:
                base=Path(region)/condition['id'];new_key=str(base/'raw_distances.npz')
                if new_key not in outputs:continue
                case=output/base;case.mkdir(parents=True)
                new=_load_arrays(evaluation/new_key,outputs[new_key],evidence)
                metrics_path=evaluation/base/'raw_metrics.json';evidence.bind(metrics_path,outputs[str(base/'raw_metrics.json')]);metrics=read_json(metrics_path)
                bounds=metrics['bounds_half_open'];width=cfg['evaluation']['section_width_m']
                sets=[]
                for label,name in [('Anchor8k','D005_Pnative.anchor_512.raw'),('Matched Global G',condition['parent_condition']+'.mesh_512.raw')]:
                    path=parent/'evaluation/geometry'/region/name/'sample0.1_reference0.1.npz'
                    # The prior preflight/current main evaluation input digest binds these exact caches.
                    expected=[r['sha256'] for r in receipt['inputs'] if r['path'].endswith('/'+str(path.relative_to(parent)))]
                    if len(set(expected))!=1:raise ValueError('Historical cache absent from main evaluation provenance')
                    loaded=_load_arrays(path,expected[0],evidence)
                    require_membership(loaded['reference_points'],loaded['reference_original_indices'],new['reference_points'],new['reference_original_indices'])
                    sets.append((label,loaded['prediction_surface_samples']))
                sets.append(('Local LC',new['prediction_surface_samples']))
                sections=section_figure(case/'raw_sections.png',new['reference_points'],sets,bounds,width,
                    f'{region} / {condition["id"]} / matched raw TSDF512')
                options=[]
                for index,view in enumerate(views):
                    box=quality.projected_prism_bbox(bounds,view['R'],view['t'],view['K'],view['width'],view['height'])
                    area=(box[2]-box[0])*(box[3]-box[1]) if box else 0
                    options.append(( -area,view['name'],index,box))
                _,name,index,box=min(options)
                if box is None:raise ValueError('No fixed evaluation camera projects the regional prism')
                view=views[index];photo_path=parent/'inputs'/region/'scene/images'/name;evidence.bind(photo_path,view['sha256'])
                images=[quality.read_rgb(photo_path)]
                for cname,variant in [('D005_Pnative','anchor_512'),(condition['parent_condition'],'final')]:
                    candidate=_sealed_candidate(seal,region,cname,variant)
                    render=[r for r in candidate['render_records'] if r['name']==name and r['evaluation_index']==index
                            and r['camera_id']==view['camera_id'] and r['image_id']==view['image_id']]
                    if len(render)!=1:raise ValueError('Historical matched render pose membership differs')
                    render=render[0];path=safe_child(parent,render['render_path']);evidence.bind(path,render['render_sha256']);images.append(quality.read_rgb(path))
                mapping_path=evaluation/base/'render_identity.json';evidence.bind(mapping_path,outputs[str(base/'render_identity.json')])
                mapping=read_json(mapping_path)
                render=[r for r in mapping['records'] if r['name']==name and r['evaluation_index']==index
                        and r['camera_id']==view['camera_id'] and r['image_id']==view['image_id']]
                if len(render)!=1:raise ValueError('Local matched render pose membership differs')
                render=render[0];run=run_from_evaluation(task,region,condition['id'],receipt,evidence.bind)
                path=run/render['render_path'];evidence.bind(path,render['render_sha256']);images.append(quality.read_rgb(path))
                labels=['Actual current photograph','Anchor8k','Matched Global G','Local LC']
                full=photo_figure(case/'matched_camera_full.png',images,labels,[0,0,view['width'],view['height']])
                crop=photo_figure(case/'matched_camera_roi.png',images,labels,box)
                records.append(dict(region=region,condition=condition['id'],sections=sections,
                    photograph=name,camera_id=view['camera_id'],image_id=view['image_id'],evaluation_index=index,
                    camera_selection='max fixed prism projected bbox area, ties by frozen photo name; output/reference independent',
                    full=full,crop=crop,figure_directory=str(base),scientific_verdict=None))
                print(json.dumps(dict(region=region,condition=condition['id'],status='MATCHED_FIGURES_WRITTEN')),flush=True)
        write_json(output/'receipt.json',dict(schema='jbgs.local_complementary_visuals.v2',
            status='PASS_MATCHED_FIGURES_WRITTEN_REQUIRES_VISUAL_REVIEW',scientific_verdict=None,
            task_id=cfg['task_id'],records=records,inputs=list(evidence.files.values()),
            implementation_snapshots=snapshots,report_revision='v2.2_explicit_evaluated_run_source',
            wall_seconds=time.time()-started,peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
            raw_photo_ox_or_temporal_truth_inferred=False,
            outputs=[dict(path=str(p.relative_to(output)),sha256=sha(p),bytes=p.stat().st_size)
                     for p in sorted(output.rglob('*.png'))]))
    except Exception as error:
        write_json(output/'failure.json',dict(status='FAIL_MATCHED_FIGURES',scientific_verdict=None,
            exception_type=type(error).__name__,error=str(error),completed=records,inputs=list(evidence.files.values())))
        raise


if __name__=='__main__':main()
