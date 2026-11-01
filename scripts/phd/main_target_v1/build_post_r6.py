"""Derive additive r6 read-out without altering the r4n scorer or reference mesh."""
from pathlib import Path
P=Path(__file__).parent;s=(P/'post7000_r4n.py').read_text()
s=s.replace("OUT/'r4n/runs'", "OUT/'r6/runs'").replace("f'tg_{site}_{prior}_s0", "f'tg_{site}_{prior}_s0_r6")
s=s.replace('def score(site,prior,wd):','def score(site,prior,wd,reference=False):')
s=s.replace("e['cell']=task['cell'];mesh=o3d.io.read_triangle_mesh(str(wd/'merged.ply'));", "e['cell']=task['cell'];mesh_path=(OUT/'r4n/runs'/f'tg_{site}_{prior}_s0/post7000/merged.ply') if reference else wd/'merged.ply';mesh=o3d.io.read_triangle_mesh(str(mesh_path));")
s=s.replace("mesh_sha256=sha(wd/'merged.ply')", "mesh_sha256=sha(mesh_path)")
s=s.replace("mean_share_of_pixels_in_box=float(np.mean(kept)),depth_dir", "mean_share_of_pixels_in_box=float(np.mean(kept)),mean_share_of_pixels_with_depth=float(np.mean(kept_depth)),seconds=None,depth_dir")
s=s.replace('intr=[];extr=[];kept=[]', 'intr=[];extr=[];kept=[];kept_depth=[]')
s=s.replace("a=loadz(root/'renders'/f\"{v['camera']}.npz\");d=a['depth'];", "a=loadz(root/'renders'/f\"{v['camera']}.npz\");d=a['depth'];kept_depth.append(float((np.isfinite(d)&(d>0)).mean()));")
start=s.index("    record['alignment']=alignment")
end=s.index('    # Associate visible first-hit',start)
s=s[:start]+'''    record['alignment']=alignment
    record['no_surface_fraction_cells_0_3']=allcells['no_surface_pct']/100
    agreement=next(r for r in strata if r['replacement']=='all' and r['region']==1)['result_within_tau_fraction']
    record['agreement_within_tau_fraction']=agreement
    if reference:
        record['status']='REFERENCE_RECOUNT';dump(wd/'score.json',record);return
    ref=json.loads((OUT/'r6/reference'/prior/'score.json').read_text())
    threshold={'ALS':.693,'LoD2':.741}[prior]
    health=json.loads((wd.parent/'model/target_monitor/health_7000.json').read_text())
    gates=dict(health=health['status']=='PASS_HEALTH',floating=frac is not None and frac<=.05,
        agreement=agreement is not None and agreement>=threshold,
        no_surface=record['no_surface_fraction_cells_0_3']<=ref['no_surface_fraction_cells_0_3'])
    record.update(gates=gates,agreement_threshold=threshold,r4n_no_surface_fraction=ref['no_surface_fraction_cells_0_3'],
        r4n_agreement_fraction=ref['agreement_within_tau_fraction'],
        agreement_gain_percentage_points=100*(agreement-ref['agreement_within_tau_fraction']),
        status='PASS' if all(gates.values()) else 'FAIL')
    dump(wd/'score.json',record)
    if record['status']!='PASS':
        stop=OUT/'r6/STOP_BOTH.json'
        if not stop.exists():dump(stop,dict(at=stamp(),reason='r6_7000_geometry_gate',site=site,prior=prior,gates=gates,scientific_verdict=None))
''' + s[end:]
s=s.replace("large_background_dominant=(counts>0)&(mean[:,1]>=.5)","released_dominant=(counts>0)&(mean[:,1]>=.5)")
s=s.replace("floating_large_background_dominant=", "floating_released_dominant=")
s=s.replace("    if mode=='run':", "    if mode=='ref':\n        wd=OUT/'r6/reference'/prior;wd.mkdir(parents=True,exist_ok=False);score(site,prior,wd,reference=True)\n    elif mode=='run':")
(P/'post7000_r6.py').write_text(s)
