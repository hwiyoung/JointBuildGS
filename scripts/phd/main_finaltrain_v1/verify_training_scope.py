"""Verify the additive scope, queued report routing and unchanged training bytes."""
import ast
from unittest.mock import patch
from common import *
from scope_policy import training_only,require_postprocessing,POLICY
import report,run_queue

def main():
    cfg();lock=json.loads((C/'runtime.lock.json').read_text())
    for path,digest in lock['files'].items():assert sha(path)==digest,path
    checked=[]
    for site in ['B0_b10','R1rep_b10']:
        assert training_only(site)
        try:require_postprocessing(site)
        except RuntimeError:pass
        else:raise AssertionError('Postprocessing was not blocked')
        for prior in ['ALS','LoD2']:
            with patch('training_report.main',return_value='training_only') as routed:
                assert report.main(site,prior)=='training_only';routed.assert_called_once_with(site,prior)
            with patch.object(run_queue,'cpu') as cpu,patch.object(run_queue,'publish') as publish:
                run_queue.post(site,prior,0 if prior=='ALS' else 1)
                cpu.assert_called_once_with('training-report-'+site+'__'+prior,'training_report.py',site,prior)
                publish.assert_called_once_with(site,prior)
            checked.append(site+'__'+prior)
    assert not training_only('B173nb_b10');require_postprocessing('B173nb_b10')
    for name in ['render_final.py','mesh.py','rescore_bridge.py','figures_bridge.py']:
        tree=ast.parse(Path(__file__).with_name(name).read_text())
        function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
        assert any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='require_postprocessing' for n in ast.walk(function)),name
    dump(O/'verification/training_only_addendum.json',dict(at=now(),status='PASS',runtime_files_unchanged=len(lock['files']),
        report_routes=checked,postprocessing_entrypoints_blocked=True,policy_sha256=sha(POLICY),scientific_verdict=None))
    print('PASS_TRAINING_ONLY_SCOPE',len(checked),len(lock['files']))

if __name__=='__main__':main()
