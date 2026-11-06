"""Host stdlib orchestration only. Scientific commands run in bounded containers."""
import datetime, json, subprocess, sys, traceback
from pathlib import Path
R=Path(__file__).resolve().parents[3]
O=R.parent/'JointBuildGS-artifacts/phase-payloads/phd/main_gtjudge_v1/PHD-MAIN-GTJUDGE-v1'
D=R/'docs/experiments/phd/main_gtjudge_v1'
def run(tag,script,*args):
    cmd=['bash',str(R/'scripts/phd/main_gtjudge_v1/run_cpu.sh'),'add4-'+tag,script,*map(str,args)]
    subprocess.run(cmd,cwd=R,check=True)
def main(mode):
    if mode=='profile-final':
        for c,v in [('c1',2),('c2',2),('c3',1)]:
            run(c+'-profile-final','add4_virtual.py',c,v,'profile')
            run(c+'-profile-render','add4_render.py',c)
        run('c3-input-detail','add4_details.py')
        run('profile-aliases','add4_finalize_visual.py')
        run('profile-check','add4_validate.py')
        run('profile-preview','add4_preview.py')
    elif mode=='context-final':
        for c in ['c1','c2','c3']:
            for what in ['tops','sections']:run(c+'-'+what+'-context','add4_figures.py',what,c)
            run(c+'-render-context','add4_render.py',c)
        run('c4-render-pixels','add4_render.py','c4')
        run('validate-context','add4_validate.py')
        run('preview-context','add4_preview.py')
    elif mode=='repair-distance':
        for c in ['c1','c2','c3','c4']:
            run(c+'-pixel-render','add4_render.py',c)
        run('validate-cases-pixel','add4_validate.py')
        run('preview-cases-pixel','add4_preview.py')
    elif mode=='repair-cameras':
        for c in ['c1','c2','c3']:
            run(c+'-prep-fix','add4_prepare.py',c)
            for what in ['tops','photos','sections']:run(c+'-'+what+'-fix','add4_figures.py',what,c)
            run(c+'-render-fix','add4_render.py',c)
    elif mode in ['cases','cases-draft']:
        for c in ['c1','c2','c3','c4']:
            run(c+'-prep','add4_prepare.py',c)
            for what in ['tops','photos','sections']:run(c+'-'+what,'add4_figures.py',what,c)
            run(c+'-render','add4_render.py',c)
        run('validate-cases','add4_validate.py')
        if mode=='cases':run('pack-cases','add4_package.py','cases')
    elif mode=='sites':
        run('sites','add4_figures.py','sites');run('pack-sites','add4_package.py','sites')
    elif mode=='keep':
        failures=[]
        for site in ['B173nb_b10','B0_b10','R1rep_b10']:
            for prior in ['ALS','LoD2']:
                stem=site+'__'+prior
                for family in ['always_keep_mesh','always_keep_mesh_t010']:
                    root=O/'meshes'/(stem+'__'+family);wd=root/'final_work'
                    try:
                        if not (root/'final.json').exists():
                            for step,sentinel in [('render',O/'renders'/(stem+'__always_keep_mesh')/'receipt.json'),('prepare',wd/'inputs/meta.json'),('plan',wd/'plan/order.json')]:
                                if not sentinel.exists():run(stem+'-'+family+'-'+step,'add4_keep.py',site,prior,family,step)
                            layout=json.loads((wd/'plan/layout.json').read_text())
                            for tile in layout['tiles']:
                                k=tile['k']
                                if not (wd/'tiles'/f'tile{k}.json').exists():run(stem+'-'+family+'-tile'+str(k),'add4_keep.py',site,prior,family,'tile:'+str(k))
                            for step in ['merge','finish']:run(stem+'-'+family+'-'+step,'add4_keep.py',site,prior,family,step)
                        run(stem+'-'+family+'-score','add4_keep.py',site,prior,family,'score')
                    except subprocess.CalledProcessError as e:
                        failures.append(dict(site=site,prior=prior,family=family,command=e.cmd,exit_code=e.returncode))
                run(stem+'-features','add4_features.py',site,prior)
        if failures:
            (O/'addendum4/keep_failures.json').write_text(json.dumps(failures,indent=2));raise RuntimeError('Keep diagnostic has failed commands; see keep_failures.json')
        run('keep-report','add4_keep_report.py');run('pack-keep','add4_package.py','keep')
    else:raise ValueError(mode)
if __name__=='__main__':
    try:main(sys.argv[1])
    except Exception:
        p=O/'addendum4'/('failure_'+sys.argv[1]+'.txt');p.parent.mkdir(exist_ok=True);p.write_text(traceback.format_exc())
        with (D/'issues.md').open('a') as f:f.write('- '+datetime.datetime.now().astimezone().isoformat()+': addendum4 '+sys.argv[1]+' execution error; see '+str(p)+'\n')
        raise
