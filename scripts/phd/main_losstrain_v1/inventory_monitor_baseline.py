"""Read exact historical observation availability; never interpolate training states."""
import json
from pathlib import Path
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
from inputs import PH,OUT,SITES,PRIORS,save,sha

def main():
    rows=[]
    for site in SITES:
        for prior in PRIORS:
            model=PH/'main_stage3_v1/PHD-MAIN-STAGE3-v1/runs'/site/('nojudge_'+prior+'_s0')/'model'
            ev=EventAccumulator(str(model),size_guidance={'scalars':0,'images':1});ev.Reload()
            key='train/loss_viewpoint - psnr';values=[dict(iteration=x.step,psnr_db=x.value) for x in ev.Scalars(key)]
            tags=ev.Tags().get('images',[])
            names=sorted({x.split('/')[0][len('train_view_'):] for x in tags if x.startswith('train_view_')})
            row=dict(site=site,prior=prior,model=str(model),train_psnr_legacy5=values,legacy5_camera_names=names,
                legacy_psnr_definition='train.py training_report: five fixed training cameras; utils.image_utils.psnr(image_CHW,target_CHW).mean(), then mean of five',
                point_cloud_iterations=sorted(int(p.name.split('_')[1]) for p in (model/'point_cloud').glob('iteration_*')),
                dump_iterations=sorted(int(p.name.split('_')[1]) for p in (model/'dump').glob('iteration_*')),
                source_events=[dict(path=str(p),sha256=sha(p)) for p in model.glob('events.*')],
                unavailable=['whole opacity medians at reset+100 from original per-Gaussian states',
                    'density-born versus surviving initial disks: no independent birth tag stored',
                    'GT-cell split opacity at unsaved iterations','all-training-view PSNR at unsaved iterations'],scientific_verdict=None)
            assert {x['iteration'] for x in values}=={7000,15000,30000}
            rows.append(row)
    save(OUT/'checks/monitor_v2/baseline_inventory.json',dict(rows=rows,scientific_verdict=None))
    save('/docs/tables/monitor_v2_baseline_inventory.json',dict(rows=rows,scientific_verdict=None))
    print('baseline inventory',[(r['site'],r['prior'],len(r['legacy5_camera_names']),r['train_psnr_legacy5']) for r in rows],flush=True)

if __name__=='__main__':main()
