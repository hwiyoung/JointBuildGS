"""Bounded policy change verification; unchanged NaN and other halt functions."""
import ast
from types import SimpleNamespace
from common import *
source=Path('/repo/src/phd/forks/GeoGS-conf-guided-v1-r17/jbgs_judgment.py')
nodes=[n for n in ast.parse(source.read_text()).body if isinstance(n,ast.FunctionDef) and n.name in ['lt_whole_stop','lt_psnr_stop']]
import math
exec(compile(ast.Module(body=nodes,type_ignores=[]),str(source),'exec'))
original_whole=lt_whole_stop
events=[];J=SimpleNamespace(lt_write=lambda j,p,r:events.append(r));context={'j':object(),'iteration':3100}
wrapper=Path(__file__).with_name('replay_current_record_only.py')
node=next(n for n in ast.parse(wrapper.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='opacity_check')
exec(compile(ast.Module(body=[node],type_ignores=[]),str(wrapper),'exec'))
assert opacity_check(True,.03778748959302902,100) is None and events[-1]['opacity_stop_record_only']
assert opacity_check(False,None,100)=='nonfinite opacity'
assert opacity_check(True,.01,99) is None and not events[-1]['opacity_stop_record_only']
assert opacity_check(True,.1,100) is None
assert lt_psnr_stop(7000,float('nan'),{})=='nonfinite training PSNR'
assert lt_psnr_stop(7000,10.,{7000:14.})=='training PSNR more than 3 dB below same-iteration nojudge'
save(DOC/'provenance/current_retry_policy_check.json',dict(at=now(),status='PASS',events=events,wrapper_sha256=sha(wrapper),source_sha256=sha(source),scientific_verdict=None))
print('current retry: only finite opacity threshold suppressed; NaN and PSNR checks preserved PASS')
