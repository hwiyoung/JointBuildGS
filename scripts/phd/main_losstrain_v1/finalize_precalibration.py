"""Record the last measurement-definition amendment before any short training."""
import argparse
import json
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path
from inputs import OUT, save, sha

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--commit',required=True);a=ap.parse_args()
    assert not (OUT/'checks/calibration_start.json').exists()
    p=Path('/config/losstrain_v1.json');old=p.with_name('losstrain_v1.pre_calibration.json')
    assert not old.exists()
    assert sha(p)==json.loads(p.with_suffix('.lock.json').read_text())['sha256']
    shutil.copyfile(p,old);shutil.copyfile(p.with_suffix('.lock.json'),old.with_suffix('.lock.json'))
    cfg=json.loads(p.read_text());stamp=datetime.now(timezone(timedelta(hours=9))).isoformat()
    cfg['saved_at']=stamp;cfg['repo_commit']=a.commit
    cfg['lambda_selection']['psnr_definition']='per-image PSNR from RGB MSE with explicit batch axis, then arithmetic mean of every training camera; same as stage-1 postprocessing'
    cfg['lambda_selection']['compatible_depth_definition']='|Dp-Dm| <= 3*sqrt(sp_ray^2+sm_ray^2); target=(Dp/sp_ray^2+Dm/sm_ray^2)/(1/sp_ray^2+1/sm_ray^2); absolute deviation normalized by sqrt(1/(1/sp_ray^2+1/sm_ray^2)); pooled median of compatible pixels; diagnostic only'
    cfg['amendments'].append(dict(at=stamp,previous_config=old.name,previous_sha256=sha(old),
        reason='before first training: make all-view PSNR and record-only compatible-depth statistic explicit; no change to loss, thresholds or variants'))
    save(p,cfg);save(p.with_suffix('.lock.json'),dict(sha256=sha(p),saved_at=stamp,training_started=False,scientific_verdict=None))
    source=Path('/repo/scripts/phd/main_losstrain_v1')
    save(OUT/'checks/precalibration_sources.json',dict(at=stamp,config_sha256=sha(p),repo_commit=a.commit,
        scripts={x.name:sha(x) for x in source.glob('*.py')},scientific_verdict=None))
    print('precalibration definitions frozen',sha(p),flush=True)

if __name__=='__main__':main()
