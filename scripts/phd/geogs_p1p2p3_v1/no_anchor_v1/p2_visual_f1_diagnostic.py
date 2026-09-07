"""Display saved P2 distances and a magnification of the existing fixed section."""
import csv
import hashlib
import json
from pathlib import Path
import platform
import sys
import traceback

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


out = Path('/out')
cfg = json.loads(Path('/config.json').read_text())
receipt = dict(status='FAIL', scientific_verdict=None, config_sha256=sha('/config.json'),
               script_sha256=sha(__file__), python=platform.python_version(), numpy=np.__version__,
               matplotlib=matplotlib.__version__, analysis_role=cfg['analysis_role'],
               new_distances_computed=False, reference_alignment_performed=False,
               evaluation_scope_changed=False, inputs=[], outputs=[], checks=[])
try:
    require(Path('/.dockerenv').exists(), 'Docker required')
    records=[]
    for item in cfg['inputs']:
        base=Path('/task')/item['base']
        paths={ext:Path(str(base)+'.'+ext) for ext in ['json','npz']}
        for ext,p in paths.items():
            require(sha(p)==item[ext+'_sha256'], 'Frozen input digest differs')
            receipt['inputs'].append(dict(path=str(p),sha256=sha(p),bytes=p.stat().st_size))
        metric=json.loads(paths['json'].read_text())
        require(metric['region']=='P2' and metric['iteration']==item['iteration'] and metric['mesh_res']==512,
                'Wrong region, update count or TSDF resolution')
        require(metric['surface_kind']=='triangle_surface' and metric['scientific_verdict'] is None,
                'Not a saved evaluated surface')
        with np.load(paths['npz']) as source:
            arrays={k:source[k] for k in ['prediction_surface_samples','reference_points',
                     'reference_original_indices','prediction_to_reference_distance','reference_to_triangle_distance']}
        for key in ['prediction_to_reference_distance','reference_to_triangle_distance']:
            require(np.isfinite(arrays[key]).all() and (arrays[key]>=0).all(), 'Invalid saved distance')
        for row in metric['thresholds']:
            p=float(np.mean(arrays['prediction_to_reference_distance']<row['threshold_m']))
            r=float(np.mean(arrays['reference_to_triangle_distance']<row['threshold_m']))
            f=2*p*r/(p+r) if p+r else 0.0
            require(all(abs(v-row[k])<1e-12 for k,v in [('precision',p),('recall',r),('f1',f)]),
                    'Saved arrays do not reproduce published threshold scores')
        records.append((item,metric,arrays))
    for key in ['reference_points','reference_original_indices']:
        require(np.array_equal(records[0][2][key],records[1][2][key]), 'Reference membership/coordinates differ')
    for key in ['bounds_half_open','reference_sha256','surface_sample_spacing_m','reference_voxel_size_m','seed','crs']:
        require(records[0][1][key]==records[1][1][key], 'Common evaluation control differs: '+key)
    receipt['checks']=['Both source SHA bindings verified','All published threshold values reproduced',
                       'Identical reference point membership and coordinates','Same ROI/CRS/sampling/seed']
    fig,axes=plt.subplots(2,2,figsize=(14,8.5),constrained_layout=True)
    cdf_rows=[]
    thresholds=np.linspace(0,cfg['cdf_display_max_m'],cfg['cdf_display_steps'])
    for column,(item,metric,a) in enumerate(records):
        ref=a['reference_points']; pred=a['prediction_surface_samples']
        rm=np.abs(ref[:,0]-cfg['section_x_m'])<cfg['section_width_m']/2
        pm=np.abs(pred[:,0]-cfg['section_x_m'])<cfg['section_width_m']/2
        ax=axes[0,column]
        ax.scatter(ref[rm,1],ref[rm,2],c='#323232',s=2,label='Observed UAS')
        ax.scatter(pred[pm,1],pred[pm,2],c=item['color'],s=3,label='Surface samples',alpha=.85)
        ax.set(xlim=cfg['display_zoom_y_m'],ylim=cfg['display_zoom_z_m'],xlabel='Y (m)',ylabel='Z (m)',
               title=item['label']+'\nSame X=134m section, width=0.5m; roof detail magnified')
        ax.set_aspect('equal',adjustable='box');ax.grid(alpha=.25);ax.legend(fontsize=9,markerscale=2)
        for col,(key,title) in enumerate([
            ('prediction_to_reference_distance','Surface samples -> observed UAS points (precision)'),
            ('reference_to_triangle_distance','Observed UAS points -> triangle surface (recall)')]):
            distances=np.sort(a[key]); fractions=np.searchsorted(distances,thresholds,side='left')/len(distances)
            hit=float(np.mean(distances<cfg['marked_threshold_m']))
            axes[1,col].plot(thresholds,100*fractions,c=item['color'],lw=2,
                             label=item['label']+f' | at 0.5m: {100*hit:.1f}%')
            axes[1,col].scatter([cfg['marked_threshold_m']],[100*hit],c=item['color'],s=35)
            axes[1,col].set(title=title,xlabel='Distance threshold t (m); strict d < t',
                           ylabel='Share below threshold (%)',xlim=(0,2),ylim=(0,100))
            cdf_rows.extend(dict(condition=item['id'],direction=key,threshold_m=float(t),fraction=float(f))
                            for t,f in zip(thresholds,fractions))
    for ax in axes[1]:
        ax.axvline(.5,color='#555555',ls='--',lw=1);ax.grid(alpha=.25);ax.legend(fontsize=8,loc='lower right')
    fig.suptitle('P2 | Similar overview, different surface proximity\nOfficial raw TSDF512; saved distances only; 30k vs 8k is an unequal-budget diagnostic',fontsize=14)
    fig.savefig(out/'P2_surface_and_distance_diagnostic.png',dpi=170)
    fig.savefig(out/'P2_surface_and_distance_diagnostic.pdf')
    plt.close(fig)
    with (out/'cdf_display_values.csv').open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(cdf_rows[0]));writer.writeheader();writer.writerows(cdf_rows)
    receipt['section_display_only']=dict(x_m=cfg['section_x_m'],width_m=cfg['section_width_m'],
                                        zoom_y=cfg['display_zoom_y_m'],zoom_z=cfg['display_zoom_z_m'],
                                        reason=cfg['display_zoom_reason'],samples_resampled=False)
    receipt['status']='PASS_SAVED_DISTANCE_DIAGNOSTIC'
except Exception as error:
    receipt['error']=str(error);(out/'failure.log').write_text(traceback.format_exc())
finally:
    receipt['outputs']=[dict(path=p.name,sha256=sha(p),bytes=p.stat().st_size) for p in sorted(out.iterdir())
                        if p.suffix in ['.png','.pdf','.csv']]
    with (out/'receipt.json').open('x') as stream:
        json.dump(receipt,stream,indent=2);stream.write('\n')
    print(json.dumps(dict(status=receipt['status'],error=receipt.get('error'))))
sys.exit(0 if receipt['status'].startswith('PASS') else 1)
