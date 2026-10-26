"""Reproducible opt-in training observations, owned r17 files only; Docker."""
import difflib
from pathlib import Path
from inputs import save,sha

def main():
    fork=Path('/fork17');src=Path('/repo/scripts/phd/main_losstrain_v1')
    j=fork/'jbgs_judgment.py';t=fork/'train.py';before={p.name:sha(p) for p in [j,t]}
    s=j.read_text();assert 'def lt_observe(' not in s
    marker='    g.add_argument("--jbgs_depth_lambda", type=float, default=0.0025)'
    assert s.count(marker)==1
    s=s.replace(marker,marker+'\n    g.add_argument("--jbgs_lt_monitor", type=int, choices=[0, 1], default=0)\n'
        '    g.add_argument("--jbgs_lt_gradient_from", type=int, default=0)\n'
        '    g.add_argument("--jbgs_lt_gradient_to", type=int, default=0)\n'
        '    g.add_argument("--jbgs_lt_opacity_reset_grace", type=int, choices=[0, 100], default=0)\n'
        '    g.add_argument("--jbgs_lt_nojudge_opacity", default="")')
    s+='\n\n'+(src/'r17_monitor.py').read_text();j.write_text(s)
    s=t.read_text();marker='        total_loss.backward()';assert s.count(marker)==1
    hook='''        if judgment is not None and args.jbgs_lt_monitor:
            jbgs_judgment.lt_observe(judgment, iteration, gaussians, total_loss, rgb_loss,
                judgment.lambda_mvs * mvs_term + judgment.lambda_prior * prior_term, render_pkg, cam_name)
'''
    s=s.replace(marker,hook+marker)
    marker='        iter_end.record()';assert s.count(marker)==1
    s=s.replace(marker,'''        if judgment is not None and args.jbgs_lt_monitor and args.jbgs_lt_opacity_reset_grace:
            jbgs_judgment.lt_opacity_health(judgment, iteration, gaussians, cam_name,
                'after optimizer and opacity floors, before density/reset')

'''+marker)
    marker='                    gaussians.reset_opacity(exempt_mask=judgment.exempt_mask(gaussians) if judgment is not None else None)  # [jbgs_judgment]'
    assert s.count(marker)==1
    s=s.replace(marker,marker+'''
                    if judgment is not None and args.jbgs_lt_monitor:
                        jbgs_judgment.lt_reset_observed(judgment, iteration, iteration % opt.opacity_reset_interval == 0)
''')
    t.write_text(s)
    base=Path('/repo/src/phd/forks/GeoGS-conf-guided-v1-r16');diff=''
    for p in [j,t]:
        diff+=''.join(difflib.unified_diff((base/p.name).read_text().splitlines(True),p.read_text().splitlines(True),
            'r16/'+p.name,'r17/'+p.name))
    Path('/docs/provenance/r16_to_r17_direct.diff').write_text(diff)
    save('/docs/provenance/r17_direct_amendment.json',dict(before=before,after={p.name:sha(p) for p in [j,t]},
        changed=['jbgs_judgment.py','train.py'],monitor_default=0,
        runtime_change='new loss uses direct-stage1 values; opt-in monitoring only reads health/gradients and stops on authorized failure conditions',scientific_verdict=None))
    for p in [j,t]:compile(p.read_text(),str(p),'exec')
    print('r17 direct values + optional monitoring source compile PASS')

if __name__=='__main__':main()
