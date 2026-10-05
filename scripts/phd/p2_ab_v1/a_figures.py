"""Source-backed static decision QA charts; evaluation is read-only here."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from collections import Counter
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from scripts.phd.p2_ab_v1.a_run import sha, write_json
from src.phd.p2_ab_v1.decision import common_curve

METHODS = ['FIXED_IMAGE','FIXED_PRIOR','SCORE_GATE','BAYES_GAUSS_UNIFORM',
           'BAYES_GAUSS_UNIFORM_ALL_PAIRS','DISCRETE_RANGE','DISCRETE_RANGE_SHARED_SHIFT']
SHORT = ['Fixed image','Fixed prior','Score gate','Bayes disjoint','Bayes all pairs','Finite range','Range + shared shift']
COLORS = ['#7f8b9c','#a09280','#cc7c2e','#1f77b4','#81a5bd','#cf6388','#808526']
MARKERS = ['s','D','o','^','v','P','X']


def main(config):
    cfg = json.loads(config.read_text())
    run, eva, common, out = [Path(cfg[k]) for k in ('a_run','evaluation_run','common','output')]
    out.mkdir(parents=True,exist_ok=False)
    risk = json.loads((eva/'decision_risk_coverage.json').read_text())
    rows = json.loads((eva/'default_real_decisions.json').read_text())
    metrics = json.loads((eva/'candidate_metrics.json').read_text())
    candidates = json.loads((run/'candidates.json').read_text())
    units = json.loads((run/'selected_units.json').read_text())
    original = np.load(common/'units.npz',allow_pickle=False)
    m = np.load(run/'measurements.npz',allow_pickle=False)
    state_annotations=[]
    for u in units:
        states={}
        for source, action in [('mvs','IMAGE'),('als','PRIOR')]:
            count=int((original[source+'_unit_index']==u['unit_index']).sum())
            states[source]=dict(raw_count=count,state='ABSENT' if count==0 else
                'AVAILABLE_CONDITIONAL_DOMINANT_PLANAR_PATCH' if action in u['candidate_indices'] else 'PRESENT_NO_ELIGIBLE_PLANAR_PATCH')
        state_annotations.append(dict(unit_id=u['unit_id'],unit_index=u['unit_index'],sources=states))
    write_json(out/'source_availability_annotations.json',state_annotations)
    default=[r for r in risk if r['threshold']==.3 and r['tolerance_m']==.5]
    with PdfPages(out/'A_decision_validation.pdf') as pdf:
        fig,axes=plt.subplots(1,3,figsize=(15,6),sharey=True)
        null_legend=[]
        for ai,eps in enumerate([.25,.5,1.]):
            ax=axes[ai]
            null_counts=[]
            for name,label,color,marker in zip(METHODS,SHORT,COLORS,MARKERS):
                subset=[r for r in risk if r['condition']=='REAL' and r['tolerance_m']==eps and r['method']==name]
                defined=[r for r in subset if r['false_accept_rate_evaluated'] is not None]
                undefined=[r for r in subset if r['false_accept_rate_evaluated'] is None]
                ax.scatter([r['coverage'] for r in defined],[r['false_accept_rate_evaluated'] for r in defined],
                    s=70,facecolors='none',edgecolors=color,marker=marker,linewidths=1.5,label=label)
                if undefined:
                    null_legend.append(f'epsilon {eps:g}: {label}, {len(undefined)}/4 settings have zero acceptance')
                    null_counts.append(f'{label}: {len(undefined)}/4')
            ax.set(xlim=(-.02,1.02),ylim=(-.04,1.04),xlabel='Accepted / 64 frozen units',title=f'REAL | tolerance = {eps:g} m')
            ax.grid(alpha=.2)
            ax.text(.03,.97,'Zero acceptance; risk null\n'+'\n'.join(null_counts) if null_counts else 'No null risks',
                    transform=ax.transAxes,va='top',fontsize=7.5,bbox=dict(facecolor='white',alpha=.8,edgecolor='none'))
        axes[0].set_ylabel('Conditionally bad / reference-evaluable accepted units')
        axes[2].legend(loc='upper right',fontsize=8)
        fig.suptitle('Every preregistered setting; repeated settings reuse the same 64 development units',fontsize=12)
        fig.text(.04,.025,'Null risks are not plotted as 0. Identical coordinates overlap; no interpolation or best-setting selection.\n'
                 'Reference frame: uncalibrated legacy numeric bridge; point-set proximity diagnostic, not absolute current-use accuracy.',fontsize=9)
        fig.tight_layout(rect=[0,.10,1,.95]);pdf.savefig(fig);fig.savefig(out/'risk_coverage.png',dpi=180);plt.close(fig)
        write_json(out/'null_risk_settings.json',null_legend)

        conditions=list(dict.fromkeys(r['condition'] for r in default))
        fig,ax=plt.subplots(figsize=(16,8))
        color=np.full((len(conditions),len(METHODS)),np.nan)
        for yi,condition in enumerate(conditions):
            for xi,method in enumerate(METHODS):
                r=next(r for r in default if r['condition']==condition and r['method']==method)
                color[yi,xi]=r['false_accept_rate_evaluated'] if r['false_accept_rate_evaluated'] is not None else np.nan
                ax.text(xi,yi,f"A {r['accepted_units']}/{r['total_units']}  |  F {r['false_accept_units']}/{r['evaluated_accepted_units']}\n"
                    f"U {r['abstained_known_usable_units']}/{r['known_usable_units']}"+
                    ('  | risk null' if r['evaluated_accepted_units']==0 else ''),ha='center',va='center',fontsize=8)
        cmap=plt.get_cmap('Oranges').copy();cmap.set_bad('#ededed')
        ax.imshow(color,cmap=cmap,vmin=0,vmax=1,aspect='auto',alpha=.4)
        ax.set_xticks(range(len(METHODS)),SHORT,rotation=20,ha='right')
        ax.set_yticks(range(len(conditions)),conditions,fontsize=9)
        ax.set_xticks(np.arange(-.5,len(METHODS),1),minor=True)
        ax.set_yticks(np.arange(-.5,len(conditions),1),minor=True);ax.grid(which='minor',color='white',linewidth=2)
        ax.tick_params(which='minor',bottom=False,left=False)
        fig.suptitle('Fixed display setting: tau = .3, epsilon = .5 m | same 64 units in every condition',fontsize=12)
        fig.text(.05,.025,'A = accepted / all units; F = conditionally bad / evaluated accepted; U = abstained despite a known usable candidate / known-usable units.\n'
            'F 0/0 means null risk. Controls modify candidates or observations; they do not assign true error labels to original sources.',fontsize=9)
        fig.tight_layout(rect=[0,.09,1,.95]);pdf.savefig(fig);fig.savefig(out/'condition_denominators.png',dpi=180);plt.close(fig)

        chosen=[]
        criteria=[('DISCRETE_RANGE',False),('SCORE_GATE',True),('BAYES_GAUSS_UNIFORM',True)]
        for method,ok in criteria:
            for r in rows:
                if r['method']==method and r['action']!='ABSTAIN' and r['candidate_evaluation'][r['action']]['conditional_candidate_ok'] is ok:
                    if r['unit_id'] not in chosen:
                        chosen.append(r['unit_id'])
                    break
        fig,axes=plt.subplots(len(chosen),2,figsize=(13,3.7*len(chosen)),squeeze=False)
        selected_rows=[]
        byid={(r['unit_id'],r['method']):r for r in rows}
        for yi,uid in enumerate(chosen):
            members=[c for c in candidates if c['unit_id']==uid]
            for c in members:
                ci,s=c['candidate_index'],c['source']
                color={'IMAGE':'#2464ac','PRIOR':'#d27121','FUSION':'#27815b'}[s]
                curve,_=common_curve(m['rho'][:,:,ci],m['pair_view_ids'],3)
                axes[yi,0].plot(m['heights'],curve,color=color,label=s,marker='.',markersize=3)
                metric=next(c for c in metrics if c['candidate_index']==ci and c['offset_z_m']==0)
                error=metric['prediction_to_reference']['p90_m']
                axes[yi,1].scatter([s],[error],s=70,color=color)
                axes[yi,1].annotate(f'{error:.3f} m',(s,error),xytext=(0,8),textcoords='offset points',fontsize=9,ha='center')
            axes[yi,0].axhline(.3,color='black',linestyle=':',label='tau=.3')
            axes[yi,0].axvspan(-.5,.5,color='gray',alpha=.12)
            axes[yi,0].set_xlabel('Scene-Z offset from candidate (m)');axes[yi,0].set_ylabel('Common-pair median ZNCC')
            axes[yi,0].legend(fontsize=8);axes[yi,0].grid(alpha=.15)
            axes[yi,1].axhline(.5,color='gray',linestyle=':');axes[yi,1].set_ylabel('UAS nearest-3D p90 (m)')
            axes[yi,1].set_ylim(0,1.1);axes[yi,1].grid(alpha=.15)
            decisions=' | '.join(label+': '+byid[uid,k]['action'] for k,label in [('SCORE_GATE','Score'),('BAYES_GAUSS_UNIFORM','Bayes'),('DISCRETE_RANGE','Range')])
            axes[yi,0].set_title(uid,loc='left',fontsize=11)
            axes[yi,1].set_title(decisions,fontsize=8)
            selected_rows.extend(byid[uid,k] for k in ['SCORE_GATE','BAYES_GAUSS_UNIFORM','DISCRETE_RANGE'])
        fig.suptitle('Illustrative measured cases: first range failure, score success, Bayesian success in frozen unit order',fontsize=11)
        fig.text(.035,.015,'Case selection uses evaluation outcomes for illustration only. No selection/threshold changes follow.\n'
            'Height compatibility bound and nearest-3D metric differ; these panels do not calibrate the bound.',fontsize=9)
        fig.tight_layout(rect=[0,.06,1,.96]);pdf.savefig(fig);fig.savefig(out/'representative_failure_success.png',dpi=180);plt.close(fig)
    write_json(out/'representative_rows.json',selected_rows)
    write_json(out/'default_denominator_rows.json',default)
    write_json(out/'FIGURE_RECEIPT.json',dict(scientific_verdict=None,status='PASS',source_sha256=sha(__file__),
        config=cfg,config_sha256=sha(config),input_sha256={str(p):sha(p) for p in [eva/'decision_risk_coverage.json',eva/'candidate_metrics.json',eva/'default_real_decisions.json',run/'measurements.npz']},
        risk_setting_count=sum(r['condition']=='REAL' for r in risk),default_condition_rows=len(default),
        representative_units=chosen,zero_acceptance_risk_plotted_as_zero=False,
        outputs={str(p.relative_to(out)):sha(p) for p in out.iterdir() if p.is_file()}))
    print(json.dumps(dict(status='PASS',representatives=chosen,output=str(out))),flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--config',type=Path,required=True)
    main(ap.parse_args().config)
