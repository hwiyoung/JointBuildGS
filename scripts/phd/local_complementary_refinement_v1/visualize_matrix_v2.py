"""Static, receipt-bound comparison of every observed matched G->LC condition.

Chart contract: horizontal signed lollipops in three aligned metric panels;
precision/recall use percentage points, F1 retains its native 0--1 units. Rows
follow the frozen region/condition order. Missing conditions are not zero rows.
A second two-panel chart retains correction and damage separately on the same
original-reference denominator. Blue/right and orange/left marks plus signed
labels distinguish direction; no confidence intervals for one run per condition.
Only sealed summary receipt, paired_summary.csv and frozen config are loaded.
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import time

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np

BLUE='#2E6FBB';ORANGE='#DF8F35';INK='#26303A';GRAY='#7A838C';GRID='#E5E8EB'
REVISION='v2.2_sealed_matrix_fixed_spacing'


def sha(path):
    value=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(8<<20),b''):value.update(chunk)
    return value.hexdigest()


def record(path):
    path=Path(path)
    return dict(path=str(path),bytes=path.stat().st_size,sha256=sha(path))


def read_json(path):return json.loads(Path(path).read_text())


def write_json(path,value):
    with Path(path).open('x') as stream:
        json.dump(value,stream,indent=2,allow_nan=False);stream.write('\n')


def number(row,key,optional=False):
    value=row.get(key)
    if value in (None,'','null'):
        if optional:return None
        raise ValueError('Missing numeric field: '+key)
    value=float(value)
    if not math.isfinite(value):raise ValueError('Nonfinite field: '+key)
    return value


def integer(row,key):
    value=number(row,key)
    if value<0 or int(value)!=value:raise ValueError('Nonnegative integer required: '+key)
    return int(value)


def expected_conditions(cfg):
    if cfg.get('schema')!='jbgs.local_complementary_refinement.v2' or cfg.get('scientific_verdict','absent') is not None:
        raise ValueError('Explicit technical v2 configuration required')
    if (cfg['training']['repetitions']!=1 or cfg['evaluation']['paired_primary_threshold_m']!=.5
        or cfg['evaluation']['mesh_resolutions']!=[512]
        or cfg['evaluation'].get('reference_for_training_or_parameter_selection') is not False):
        raise ValueError('One run, evaluation-only reference and raw512/.5m contract required')
    regions=cfg['regions'];conditions=cfg['conditions']
    if len(regions)!=len(set(regions)) or len({c['id'] for c in conditions})!=len(conditions):
        raise ValueError('Duplicate frozen region/condition')
    ordered=[(region,c['id']) for region in regions for c in conditions]
    if len(ordered)!=18:raise ValueError('Exact first18 configuration required')
    return ordered,{c['id']:c for c in conditions}


def validate_rows(rows,cfg,receipt):
    ordered,conditions=expected_conditions(cfg)
    if (receipt.get('schema')!='jbgs.local_complementary_summary.v2'
        or receipt.get('scientific_verdict','absent') is not None
        or receipt.get('raw_gt_or_model_loaded') is not False
        or receipt.get('parameter_selection_or_temporal_truth_inferred') is not False
        or receipt.get('task_id')!=cfg['task_id']):
        raise ValueError('A sealed technical summary with explicit null/evaluation-only scope is required')
    complete=receipt.get('status')=='COMPLETE_18_DEVELOPMENT_SUMMARY'
    if not complete and receipt.get('status')!='PARTIAL_INTERMEDIATE_NO_OUTCOME_CONCLUSION':
        raise ValueError('Only completed full or explicitly partial summary attempts may be plotted')
    if receipt.get('expected_condition_count')!=18 or receipt.get('observed_condition_count')!=len(rows) or not rows:
        raise ValueError('Summary receipt and observed/expected row counts differ')
    observed={};denominators={}
    for source in rows:
        identity=(source['region'],source['condition'])
        if identity not in ordered or identity in observed:raise ValueError('Unexpected or duplicate condition row')
        c=conditions[source['condition']]
        if (source['parent_condition']!=c['parent_condition'] or source['protection']!=c['protection']
            or number(source,'lambda_prior')!=c['lambda_p']):
            raise ValueError('Row does not use its frozen matched G condition')
        if source['mesh_kind']!='raw' or integer(source,'mesh_res')!=512 or number(source,'threshold_m')!=.5:
            raise ValueError('Only the matched primary raw512/.5m slice may be plotted')
        if source.get('scientific_verdict','absent') not in (None,'','null'):
            raise ValueError('Explicit null row scientific verdict required')
        n=integer(source,'reference_count');g=integer(source,'local_corrected_vs_global');d=integer(source,'local_damaged_vs_global')
        if g+d>n:raise ValueError('Correction/damage are disjoint subsets of the same reference points')
        region=source['region']
        if region in denominators and denominators[region]!=n:raise ValueError('Same-region original reference denominator changed')
        denominators[region]=n
        row=dict(region=region,condition=source['condition'],parent_condition=c['parent_condition'],lambda_prior=c['lambda_p'],
                 protection=c['protection'],reference_count=n,corrected_point_count=g,damaged_point_count=d,
                 correction_percent=100*g/n if n else None,damage_percent=100*d/n if n else None,
                 mesh_kind='raw',mesh_res=512,threshold_m=.5,scientific_verdict=None)
        for metric in ('precision','recall','f1'):
            old,new,delta=[number(source,key,True) for key in ('global_'+metric,'local_'+metric,'delta_'+metric)]
            if not n:
                if any(v is not None for v in (old,new,delta)):raise ValueError('Absent reference must remain unassessed, not zero')
            elif (old is None or new is None or delta is None or not 0<=old<=1 or not 0<=new<=1
                  or not math.isclose(new-old,delta,rel_tol=0,abs_tol=1e-12)):
                raise ValueError('Metric value/delta mismatch: '+metric)
            row.update({'global_'+metric:old,'local_'+metric:new,'delta_'+metric:delta})
            if metric!='f1':row['delta_'+metric+'_percentage_points']=100*delta if delta is not None else None
        if n:
            if not math.isclose(row['delta_recall'],(g-d)/n,rel_tol=0,abs_tol=1e-12):
                raise ValueError('Recall change differs from same-point correction/damage counts')
            for side in ('global','local'):
                p,r=row[side+'_precision'],row[side+'_recall'];f=2*p*r/(p+r) if p+r else 0.
                if not math.isclose(row[side+'_f1'],f,rel_tol=0,abs_tol=1e-12):
                    raise ValueError('F1 differs from its precision/recall')
        observed[identity]=row
    if complete and set(observed)!=set(ordered):raise ValueError('Complete summary requires exact all18 membership')
    missing=[dict(region=r,condition=c) for r,c in ordered if (r,c) not in observed]
    return [observed[key] for key in ordered if key in observed],missing,complete


def status_line(n,complete):
    return (f'COMPLETE DEVELOPMENT MATRIX | {n}/18 conditions plotted' if complete else
            f'PARTIAL OBSERVATION | {n}/18 conditions plotted | {18-n} remaining conditions not plotted (not zero)')


def signed_label(value,digits):
    """A nonzero measured difference must not acquire an exactly-zero label."""
    if value and abs(value)<.5*10**(-digits):return f'{value:+.2e}'
    return f'{value if value else 0.:+.{digits}f}'


def labels(rows,with_denominator=False):
    result=[]
    for r in rows:
        label=f"{r['region']} | λp={r['lambda_prior']:g} | {r['protection']}"
        if with_denominator:label+=f" | N={r['reference_count']:,}"
        result.append(label)
    return result


def base_figure(rows,columns,title,complete,denominator=False):
    n=len(rows);height=max(5.1,3.5+.33*n)
    fig,axes=plt.subplots(1,columns,figsize=(16,height),sharey=True,squeeze=False)
    axes=axes[0]
    fig.text(.025,1-.23/height,title,fontsize=17,color=INK,va='top')
    fig.text(.025,1-.63/height,status_line(n,complete),fontsize=11,color=INK,weight='bold')
    fig.text(.025,1-.98/height,'Raw TSDF512 | distance < 0.5 m | LC versus matching G | one run per condition',fontsize=10,color=GRAY)
    fig.subplots_adjust(left=.23 if denominator else .195,right=.97,top=1-1.6/height,bottom=1.7/height,wspace=.25)
    for ax in axes:
        ax.set_ylim(n-.35,-.65);ax.set_yticks(np.arange(n))
        ax.set_yticklabels(labels(rows,denominator),fontsize=10)
        ax.tick_params(axis='y',length=0,pad=12);ax.tick_params(axis='x',labelsize=9,colors=GRAY)
        ax.grid(axis='x',color=GRID,linewidth=.65);ax.set_axisbelow(True)
        for y in range(n):ax.axhline(y,color='#F1F3F5',linewidth=.7,zorder=0)
        for edge in ('top','right','left'):ax.spines[edge].set_visible(False)
        ax.spines['bottom'].set_color(GRAY)
    fig.text(.025,.36/height,'Reference proximity is not surface area or temporal truth. No confidence intervals: each condition has one run.',fontsize=10,color=GRAY)
    fig.text(.025,.14/height,'No mean-multiplier global control or controller replay; spatial-allocation causality and reproducibility remain unconfirmed.',fontsize=9.5,color=GRAY)
    return fig,axes


def draw_deltas(path,rows,complete,synthetic=False):
    if Path(path).exists():raise FileExistsError(path)
    title=('SYNTHETIC QA | ' if synthetic else '')+'Matched G to LC change by condition'
    fig,axes=base_figure(rows,3,title,complete)
    specs=[('delta_precision_percentage_points','Precision change','Percentage points',2),
           ('delta_recall_percentage_points','Recall change','Percentage points',2),
           ('delta_f1','F1 change','Native F1 units (0–1 scale)',4)]
    pp=[abs(r[key]) for r in rows for key in ('delta_precision_percentage_points','delta_recall_percentage_points') if r[key] is not None]
    shared_pp_limit=max([1.0,*pp])*1.45
    try:
        for ax,(key,title,unit,digits) in zip(axes,specs):
            limit=shared_pp_limit if key!='delta_f1' else max([.01,*[abs(r[key]) for r in rows if r[key] is not None]])*1.6
            ax.set_xlim(-limit,limit);ax.axvline(0,color=INK,linewidth=1.1,zorder=1)
            ax.set_title(title,fontsize=12,pad=15,color=INK);ax.set_xlabel(unit,fontsize=10,labelpad=10)
            for y,row in enumerate(rows):
                value=row[key]
                if value is None:
                    ax.text(0,y,'N/A: no reference',ha='center',va='center',fontsize=9,color=GRAY,
                            bbox=dict(facecolor='white',edgecolor='none',pad=2));continue
                color=BLUE if value>0 else ORANGE if value<0 else GRAY
                marker='>' if value>0 else '<' if value<0 else 'o'
                ax.plot([0,value],[y,y],color=color,linewidth=2,zorder=2)
                ax.scatter([value],[y],marker=marker,s=55,color=color,edgecolor=INK,linewidth=.45,zorder=3)
                shift=limit*.045 if value>=0 else -limit*.045
                ax.text(value+shift,y,signed_label(value,digits),ha='left' if value>=0 else 'right',va='center',fontsize=10,color=INK)
        fig.legend(handles=[Line2D([],[],marker='>',color=BLUE,linestyle='none',label='Metric increase'),
                            Line2D([],[],marker='<',color=ORANGE,linestyle='none',label='Metric decrease'),
                            Line2D([],[],marker='o',color=GRAY,linestyle='none',label='Exactly zero')],
                   loc='lower center',bbox_to_anchor=(.58,.68/fig.get_figheight()),ncol=3,frameon=False,fontsize=10)
        fig.savefig(path,dpi=160,facecolor='white')
    finally:plt.close(fig)


def draw_correction_damage(path,rows,complete,synthetic=False):
    if Path(path).exists():raise FileExistsError(path)
    title=('SYNTHETIC QA | ' if synthetic else '')+'Correction and damage on the same reference-point denominator'
    fig,axes=base_figure(rows,2,title,complete,True)
    maximum=max([1.,*[r[key] for r in rows for key in ('correction_percent','damage_percent') if r[key] is not None]])
    try:
        for ax,key,numerator,title,color,marker in zip(axes,('correction_percent','damage_percent'),
                ('corrected_point_count','damaged_point_count'),('Correction: G far → LC near','Damage: G near → LC far'),
                (BLUE,ORANGE),('o','x')):
            ax.set_xlim(0,maximum*1.7);ax.axvline(0,color=INK,linewidth=1)
            ax.set_title(title,fontsize=12,pad=15,color=INK)
            ax.set_xlabel('Percent of the same original reference points',fontsize=10,labelpad=10)
            for y,row in enumerate(rows):
                value=row[key]
                if value is None:
                    ax.text(maximum*.05,y,'N/A: no reference',va='center',color=GRAY);continue
                ax.plot([0,value],[y,y],linewidth=2,color=color)
                ax.scatter([value],[y],s=55,marker=marker,color=color,zorder=3)
                ax.text(value+maximum*.045,y,f'{value:.2f}% ({row[numerator]:,} points)',va='center',fontsize=10,color=INK)
        fig.text(.58,.83/fig.get_figheight(),'N = all original reference points for that row. Correction and damage remain separate; neither uses predicted samples.',
                 ha='center',fontsize=9.5,color=GRAY)
        fig.savefig(path,dpi=160,facecolor='white')
    finally:plt.close(fig)


def produce(summary,config,output):
    started=time.time();summary=Path(summary).resolve();config=Path(config).resolve();output=Path(output).resolve()
    receipt_path=summary/'receipt.json';receipt=read_json(receipt_path);cfg=read_json(config)
    expected_config={r['sha256'] for r in receipt['inputs'] if Path(r['path']).name=='experiment_v2.json'}
    if expected_config!={sha(config)}:raise ValueError('Summary and supplied frozen configuration digests differ')
    csv_path=summary/'paired_summary.csv'
    if not csv_path.resolve().is_relative_to(summary):raise ValueError('CSV escaped immutable summary')
    entries=[entry for entry in receipt['outputs'] if entry['path']=='paired_summary.csv']
    if len(entries)!=1 or entries[0]['sha256']!=sha(csv_path) or entries[0]['bytes']!=csv_path.stat().st_size:
        raise ValueError('Sealed paired summary CSV changed or is missing a unique digest')
    with csv_path.open(newline='') as stream:source_rows=list(csv.DictReader(stream))
    rows,missing,complete=validate_rows(source_rows,cfg,receipt)
    if output==summary or output.is_relative_to(summary) or summary.is_relative_to(output):
        raise ValueError('Figure outputs must be separate from immutable summary')
    attempt=output/('attempt_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'))
    attempt.mkdir(parents=True,exist_ok=False)
    inputs=[record(receipt_path),record(csv_path),record(config),record(__file__)]
    try:
        for source,name in [(config,'config_snapshot.json'),(receipt_path,'source_summary_receipt.json'),
                            (csv_path,'source_paired_summary.csv'),(Path(__file__),'source_snapshot.py')]:
            with (attempt/name).open('xb') as stream:stream.write(source.read_bytes())
        with (attempt/'chart_data.csv').open('x',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
        write_json(attempt/'not_plotted_conditions.json',missing)
        synthetic=cfg['task_id'].startswith('SYNTHETIC')
        draw_deltas(attempt/'delta_metrics.png',rows,complete,synthetic)
        draw_correction_damage(attempt/'correction_damage.png',rows,complete,synthetic)
        result=dict(schema='jbgs.local_complementary_matrix_figures.v2',revision=REVISION,
            status='PASS_COMPLETE_18_MATRIX_FIGURES' if complete else 'PASS_PARTIAL_MATRIX_FIGURES_NO_OUTCOME_CONCLUSION',
            scientific_verdict=None,task_id=cfg['task_id'],source_summary_status=receipt['status'],
            observed_condition_count=len(rows),expected_condition_count=18,not_plotted_condition_count=len(missing),
            missing_conditions_are_zero_rows=False,reference_or_model_loaded=False,parameter_selection_performed=False,
            uncertainty_intervals_present=False,repetitions_per_condition=1,inputs=inputs,
            chart_contract=dict(family='aligned horizontal lollipops',row_order='frozen config region/condition order; observed rows only',
                metric_direction='LC minus matched G',precision_recall_unit='percentage points',f1_unit='native 0–1 units',
                zero='same G and LC metric; all delta panels center at zero',
                correction_damage_denominator='all same original reference points for each condition; never netted',
                palette=dict(increase_or_correction=BLUE,decrease_or_damage=ORANGE,zero_or_unassessed=GRAY)),
            limitations=['One run per condition; no confidence intervals or small-difference reproducibility claim.',
                'No mean-multiplier global control or controller replay; spatial-allocation causality unconfirmed.',
                'Proximity correction/damage is not surface area, same 3D patch or temporal truth.'],
            versions=dict(python=platform.python_version(),numpy=np.__version__,matplotlib=matplotlib.__version__),
            wall_seconds=time.time()-started,
            outputs=[dict(record(p),path=p.name) for p in sorted(attempt.iterdir()) if p.is_file()])
        write_json(attempt/'receipt.json',result)
        return attempt,result
    except Exception as error:
        write_json(attempt/'failure.json',dict(status='FAIL_MATRIX_FIGURES',scientific_verdict=None,inputs=inputs,
            exception_type=type(error).__name__,exception=str(error)))
        raise


def main():
    if not Path('/.dockerenv').exists():raise RuntimeError('Docker required')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--summary',type=Path,required=True);parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    attempt,receipt=produce(args.summary,args.config,args.output)
    print(json.dumps(dict(status=receipt['status'],output=str(attempt),observed_conditions=receipt['observed_condition_count'],scientific_verdict=None)))


if __name__=='__main__':main()
