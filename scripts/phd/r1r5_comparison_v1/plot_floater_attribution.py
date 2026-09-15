"""Publish a diagnostic figure from validated ray-compositing receipts."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

base=Path('/trace');out=Path('/out')
observed=json.loads((base/'r1_splat_trace_v2/receipt.json').read_text());assert observed['status']=='PASS_CPU_SAVED_DEPTH_PARITY'
counter=json.loads((base/'r1_splat_counterfactual/receipt.json').read_text());assert counter['status']=='PASS_CPU_SAVED_DEPTH_PARITY'
rows=counter['rows'];x=np.arange(len(rows));fig,ax=plt.subplots(figsize=(10,5))
values={label:[] for label in ['MVS control','Local prior 0','Local prior 0: one splat disabled']}
for row in rows:
    control=next(r for r in observed['rows'] if r['camera']==row['camera'] and r['branch']=='mvs')
    values['MVS control'].append(control['expected_depth']);values['Local prior 0'].append(row['expected_depth'])
    values['Local prior 0: one splat disabled'].append(row['counterfactuals'][0]['expected_depth'])
for j,(label,val) in enumerate(values.items()):
    bars=ax.bar(x+(j-1)*.25,val,.24,label=label,color=['#2383ba','#e88440','#48a275'][j])
    ax.bar_label(bars,fmt='%.2f',fontsize=9,padding=3)
ax.set_xticks(x,[r['camera'].split('_')[-2]+' / pixel '+str(tuple(r['pixel'])) for r in rows]);ax.set_ylabel('Rendered camera-Z depth (m)')
ax.set_ylim(0,68);ax.set_title('Z06 floater: one oversized splat pulls the rendered depth forward')
ax.legend(loc='upper right',fontsize=8);ax.spines[['top','right']].set_visible(False)
fig.text(.08,.015,'Final prior-0 Gaussian #1816099: scales 2.99 m / 168.43 m. Diagnostic replay only; original outputs unchanged.',fontsize=8)
fig.tight_layout(rect=[0,.04,1,1]);fig.savefig(out/'Z06_floater_cause_20260918_v1.png',dpi=160)
receipt=dict(status='PASS_VALIDATED_RAY_COUNTERFACTUAL_FIGURE',scientific_verdict=None,values=values,
             cameras=[r['camera'] for r in rows],model_mutated=False,full_mesh_reextracted=False)
(out/'Z06_floater_cause_receipt.json').write_text(json.dumps(receipt,indent=2))
