"""Read historical training receipts only; never launch training."""
import json
import numpy as np
from analysis_common import O,DOC,save_table
from preflight import PH,PREP,sha
S0=PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1';S1=PH/'main_stage1_v1/PHD-MAIN-STAGE1-v1'

def main():
    cov=np.load(O/'inputs/coverage.npz');area=float(cov['common'].sum())*float(cov['res'])**2
    tiles=json.loads((O/'inputs/tiles.json').read_text());images=len(json.loads((O/'image_split.json').read_text())['train'])
    boxes=json.loads((PREP/'step06/box_ranges.json').read_text());rows=[];attempts=[]
    for f in sorted((S1/'stage1').glob('*/*/receipt.json')):
        r=json.loads(f.read_text());site=r.get('site');p=f.parent/'post/post.json'
        if site not in boxes:continue
        post=json.loads(p.read_text()) if p.exists() else {};split=S0/'fork_inputs/s61'/site/'split.json'
        ni=len(json.loads(split.read_text())['train']) if split.exists() else None
        sa=boxes[site]['area_m2'];sec=r.get('wall_seconds');mem=r.get('gpu_memory_used_mib',{}).get('peak_minus_idle')
        entry=dict(site=site,result=f.parent.name,method=r.get('method'),status=r.get('status'),training_seconds=sec,
            gpu_peak_minus_idle_GiB=mem/1024 if mem is not None else None,final_gaussians=post.get('gaussians',{}).get('n'),
            post_seconds=post.get('seconds'),post_host_peak_GiB=post.get('peak_host_gb'),training_images=ni,input_area_m2=sa,
            receipt=str(f),receipt_sha256=sha(f),post_source=str(p) if p.exists() else None,post_sha256=sha(p) if p.exists() else None)
        attempts.append(entry)
        if r.get('status')!='PASS' or '_old_' in f.parent.name or sec is None:continue
        entry=dict(entry,seconds_per_input_m2=sec/sa,seconds_per_image=sec/ni if ni else None,
            full_area_hours_linear=sec/sa*area/3600,full_images_hours_linear=sec/ni*images/3600 if ni else None,
            one_100m_core_hours_linear=sec/sa*10000/3600,one_buffered_120m_tile_hours_linear=sec/sa*14400/3600,
            all_buffered_tiles_hours_linear=sec/sa*14400*len(tiles)/3600,
            full_area_gaussians_linear=post.get('gaussians',{}).get('n',0)/sa*area if post.get('gaussians',{}).get('n') else None,
            full_area_memory_GiB_linear=mem/1024/sa*area if mem is not None else None)
        rows.append(entry)
    save_table('앞학습_실행기록',attempts,training_launched=False)
    save_table('계산_어림',rows,full_area_m2=area,full_training_images=images,tiles=len(tiles),
        assumptions=['Historical 30000-iteration implementations only; proposed new validity-probability method not measured.',
            'Separate linear area and image models, not their product; neither is a measured full-area runtime.',
            '100 m cores use 10 m halo each side (120 m input); independent tiles duplicate observations and setup.',
            'Memory and Gaussian extrapolations are crude proportional scenarios, not guarantees of fitting one GPU.',
            'Training time includes historical evaluation and checkpoint writing; post timing dictionary preserves cumulative timings.'],training_launched=False)
    print('historical training receipt rows',len(rows),'attempts',len(attempts),flush=True)
if __name__=='__main__':main()
