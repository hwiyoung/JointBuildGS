"""Addendum 5: saved residual counts and read-only implementation provenance."""
from common import *
import struct, platform
from PIL import Image

def camera(path):
    with Path(path).open('rb') as f:
        count, = struct.unpack('<Q', f.read(8))
        ident, model, width, height = struct.unpack('<iiQQ', f.read(24))
    return dict(path=str(path), sha256=sha(path), count=count, first_camera_id=ident,
                model=model, width=width, height=height)

def main():
    begin=time.monotonic()
    config=C/'ch6_impl_check.json'
    spec=json.loads(config.read_text())
    doc=Path('/docs')
    out=Path('/out/ch6_impl_check')
    out.mkdir(exist_ok=True)
    lock=C/'ch6_impl_check.initial.lock.json'
    assert not lock.exists(), 'Read existing output instead of repeating the count'
    dump(lock,dict(at=now(),config_sha256=sha(config),script_sha256=sha(__file__),scientific_verdict=None))
    old=json.loads((doc/'tables/table1_tau.json').read_text())['rows']
    rows=[]; registration=[]; evidence={}
    for region in ['B0','R2','R1']:
        for prior in ['LoD2','ALS']:
            path=PH/spec['residual_source'].replace('<region>',region).replace('<prior>',prior)
            digest=sha(path)
            with np.load(path,allow_pickle=False) as z:
                for kind in (['roof','wall'] if prior=='LoD2' else ['roof']):
                    previous=next(r for r in old if (r['search_region'],r['prior'],r['kind'])==(region,prior,kind))
                    assert digest==previous['source_sha256']
                    raw=z[kind].astype(np.float64)
                    finite=np.isfinite(raw);x=np.abs(raw[finite]);n=len(x)
                    assert n==previous['n_pixels'] and n>0
                    tau=spec['tau_cm_from_user_table6_5'][region][prior+'_'+kind]/100
                    nt=int(np.count_nonzero(x>tau));n2=int(np.count_nonzero(x>2.0))
                    rows.append(dict(search_region=region,prior=prior,surface=kind,n_saved=int(raw.size),n_finite=n,
                                     n_nonfinite=int((~finite).sum()),tau_cm=100*tau,n_abs_gt_tau=nt,pct_abs_gt_tau=100*nt/n,
                                     n_abs_gt_2m=n2,pct_abs_gt_2m=100*n2/n,stored_unrounded_tau_m=previous['new_tau_m'],
                                     residual_definition='(image_depth-prior_depth)*surface_factor',source=str(path),
                                     source_sha256=digest,array_key=kind,scientific_verdict=None))
            summ=path.with_name('summary.json');reg=json.loads(summ.read_text())['registration']
            registration.append(dict(region=region,prior=prior,shift_xyz_m=reg['shift_applied'],
                                     horizontal_accepted=reg['accepted_horizontal'],vertical_accepted=reg['accepted_vertical'],
                                     source=str(summ),source_sha256=sha(summ)))
    csvpath=doc/'tables/ch6_tau_residual_ratios.csv'
    with csvpath.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    with csvpath.open() as f:
        loaded=list(csv.DictReader(f))
    assert len(loaded)==9
    for r in loaded:
        n=int(r['n_finite'])
        for count,pct in [('n_abs_gt_tau','pct_abs_gt_tau'),('n_abs_gt_2m','pct_abs_gt_2m')]:
            assert abs(float(r[pct])-100*int(r[count])/n)<1e-10
    metadata=[]
    p0=Path('/art/phase-payloads/p0-audit')
    cams=[camera(p0/'data/work/mvs/colmap_dense/sparse/cameras.bin')]
    for site,region in [('B0_b10','B0'),('B173nb_b10','R2'),('R1rep_b10','R1')]:
        for prior in ['ALS','LoD2']:
            p=S0/'s61/box'/site/prior/'summary.json';r=json.loads(p.read_text())['registration']
            expected=next(x for x in registration if x['region']==region and x['prior']==prior)['shift_xyz_m']
            assert r['shift_applied']==expected
            metadata.append(dict(site=site,prior=prior,shift_xyz_m=expected,source=str(p),source_sha256=sha(p),fixed_from=r.get('fixed_from')))
        cams.append(camera(S0/'fork_inputs/s61'/site/'scene_LoD2/sparse/0/cameras.bin'))
        p=PH/'main_baselines_v1/PHD-MAIN-BASELINES-v1/prep/geogs_als'/f'{site}_inputs.json'
        d=json.loads(p.read_text())
        evidence[str(p)]=dict(sha256=sha(p),surface=d['surface'],registration_check=d['registration_check'])
        for prior in ['ALS','LoD2']:
            p=PH/'main_fill_v1/PHD-MAIN-FILL-v1/prep/cdgs'/f'scene_{site}_{prior}.json'
            if p.exists():
                d=json.loads(p.read_text());evidence[str(p)]=dict(sha256=sha(p),prior_depth=d.get('prior_depth'),checks=d.get('checks'),all_checks_pass=d.get('all_checks_pass'))
    split=json.loads((S0/'fork_inputs/s61/B0_b10/split.json').read_text())
    name=split['train'][0]
    image_sizes=[]
    for p in [p0/'data/work/mvs/colmap_dense/images'/f'{name}.JPG',S0/'fork_inputs/s61/B0_b10/images'/f'{name}.jpg']:
        if p.exists():
            with Image.open(p) as im:image_sizes.append(dict(path=str(p),size=list(im.size)))
    result=dict(task_id=spec['task_id'],created_at=now(),residual_rows=rows,registration=registration,
                fixed_site_registration=metadata,cameras=cams,image_header_sizes=image_sizes,method_receipts=evidence,
                csv=str(csvpath),csv_sha256=sha(csvpath),script_sha256=sha(__file__),config_sha256=sha(config),
                commit=os.environ.get('RESCORE_COMMIT'),image=os.environ.get('RESCORE_IMAGE'),python=platform.python_version(),
                numpy=np.__version__,seconds=time.monotonic()-begin,training_steps=0,gpu_used=False,meshes_rebuilt=0,scores_rebuilt=0,
                validation='PASS_SOURCE_HASH_COUNTS_AND_CSV_ARITHMETIC',scientific_verdict=None)
    dump(doc/'provenance/ch6_impl_check.json',result)
    dump(out/'receipt.json',{k:v for k,v in result.items() if k not in ['residual_rows','method_receipts']})
    for r in rows:print(r['search_region'],r['prior'],r['surface'],r['n_finite'],f"{r['pct_abs_gt_tau']:.4f}%",f"{r['pct_abs_gt_2m']:.4f}%")
    print('PASS',result['seconds'],flush=True)

if __name__=='__main__':main()
