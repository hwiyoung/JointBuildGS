"""Parse new drivers before their first execution; do not replay passed science checks."""
from common import *
import ast
files=sorted((R/'scripts/phd/main_rescore_v1').glob('s2_*.py'))
for p in files:ast.parse(p.read_text(),filename=str(p))
dump(O/'validation/syntax.json',dict(status='PASS',files={p.name:sha(p) for p in files},scientific_verdict=None))
print('PARSE_PASS',len(files),flush=True)
