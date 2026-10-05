"""Compact, denominator-aware integration tables and scientific B figure."""
import argparse
from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scripts.phd.p2_ab_v1.c_evaluate import read,write,csv_write,sha


def aggregate(result):
    rows=result['units'];present=[r for r in rows if r['prediction_count']]
    ref=sum(r['reference_count'] for r in rows)
    prediction=sum(r['prediction_count'] for r in rows)
    recovered=sum(next(s['reference_recovered_count'] for s in r['tolerance_sweep'] if s['tolerance_m']==.5) for r in rows)
    precision=sum(next(s['predicted_inlier_count'] for s in r['tolerance_sweep'] if s['tolerance_m']==.5) for r in rows)
    errors=[r['prediction_to_reference']['p90_m'] for r in present if r['prediction_to_reference']['p90_m'] is not None]
    delta=[r['final_minus_initial_p90_m'] for r in rows if r.get('final_minus_initial_p90_m') is not None]
    initial=[r['initial_metrics'] for r in rows if 'initial_metrics' in r]
    initial_rec=sum(next(s['reference_recovered_count'] for s in r['tolerance_sweep'] if s['tolerance_m']==.5) for r in initial)
    initial_ref=sum(r['reference_count'] for r in initial)
    return dict(run=result['run'],decision_method=result.get('decision_method'),arm=result.get('arm'),
        selected_units_denominator=len(rows),emitted_units=len(present),missing_units=len(rows)-len(present),
        emitted_surface_sample_points=prediction,reference_native_points=ref,
        reference_recovered_points_050m=recovered,reference_recall_050m=recovered/ref if ref else None,
        initial_reference_recall_050m=initial_rec/initial_ref if initial_ref else None,
        prediction_precision_050m=precision/prediction if prediction and ref else None,
        mean_emitted_unit_p90_m=float(np.mean(errors)) if errors else None,
        comparable_initial_final_units=len(delta),mean_unit_p90_change_m=float(np.mean(delta)) if delta else None,
        improved_unit_count_1mm=sum(d < -.001 for d in delta),degraded_unit_count_1mm=sum(d > .001 for d in delta),
        unchanged_within_1mm_unit_count=sum(abs(d)<=.001 for d in delta))


def main(args):
    args.output.mkdir(parents=True,exist_ok=False)
    rows=[aggregate(r) for r in read(args.integrated/'reconstruction_unit_metrics.json')]
    appearance=read(args.appearance/'common_appearance.json')
    for row in rows:
        matched=[r for r in appearance if r['run']==row['run'] and r['arm']==row['arm']]
        if matched:
            a=matched[0]
            row.update(common_ray_psnr_db=a['psnr_db'],common_ray_coverage=a['ray_coverage'],
                       common_ray_pixels=a['input_domain_pixels'],common_ray_mae=a['mae'])
    csv_write(args.output/'reconstruction_summary.csv',rows)
    write(args.output/'reconstruction_summary.json',rows)
    arms=['surface_texturing','fixed_gs','prior_loss_gs','constrained_gs']
    colors=['#a18121','#286c9d','#c16c36','#697b32'];markers=['s','o','^','D']
    methods=list(dict.fromkeys(r['decision_method'] for r in rows if r.get('arm') in arms))
    dn_arm=next((r['arm'] for r in rows if str(r.get('arm','')).startswith('dn_splatter_original')),None)
    if dn_arm:
        arms.append(dn_arm);colors.append('#a05378');markers.append('x')
    fig,axes=plt.subplots(1,3,figsize=(15,5),layout='constrained')
    specs=[('reference_recall_050m','UAS point recovery at 0.5 m','Fraction of fixed native UAS points'),
           ('common_ray_coverage','Common input-ray coverage','Fraction of fixed input-derived rays'),
           ('common_ray_psnr_db','RGB on common input rays','PSNR (dB), missing pixels retained')]
    for ax,(key,title,label) in zip(axes,specs):
        for j,arm in enumerate(arms):
            y=[]
            for method in methods:
                row=next((r for r in rows if r['arm']==arm and r['decision_method']==method),{})
                y.append(row.get(key,np.nan))
            ax.plot(np.arange(len(methods))+(j-1.5)*.08,y,linestyle='none',marker=markers[j],
                    label='DN-Splatter (96 steps, 3DGS)' if arm==dn_arm else arm,
                    color=colors[j],markersize=7,markerfacecolor='none' if j==3 else colors[j])
        ax.set_title(title,fontsize=12);ax.set_ylabel(label,fontsize=10)
        ax.set_xticks(np.arange(len(methods)),[m.replace('FIXED_','').replace('DISCRETE_RANGE','RANGE').replace('BAYES_GAUSS_UNIFORM','BAYES').replace('SCORE_GATE','SCORE') for m in methods],rotation=25)
        ax.grid(axis='y',color='#d9dee3',linewidth=.6);ax.spines[['top','right']].set_visible(False)
        if key!='common_ray_psnr_db':ax.set_ylim(0,1)
    axes[0].legend(fontsize=8,loc='upper left')
    extra=' + original DN-Splatter (prior input)' if len(arms)>4 else ''
    fig.suptitle('P2: five judgment methods × four reconstruction arms'+extra+'\n64 fixed development units; numeric-frame UAS diagnostic; historical development views',fontsize=12)
    for ext in ['png','pdf']:fig.savefig(args.output/f'reconstruction_comparison.{ext}',dpi=170)
    plt.close(fig)
    source_paths=[args.integrated/'reconstruction_unit_metrics.json',args.appearance/'common_appearance.json',Path(__file__)]
    write(args.output/'technical_receipt.json',dict(status='INTEGRATION_SUMMARY_COMPLETE',
        inputs_sha256={str(p):sha(p) for p in source_paths},scientific_verdict=None,
        labels={'1mm':'Display-only near-zero change bin; not an application tolerance or tuned threshold',
                'mean_emitted_unit_p90':'Descriptive mean on emitted units; do not compare without missing units and fixed reference recall',
                'common_ray_domain':'Unoptimized fixed IMAGE/PRIOR alpha union; not certified surface area'}))
    print(json.dumps(rows,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--integrated',type=Path,required=True);p.add_argument('--appearance',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    main(p.parse_args())
