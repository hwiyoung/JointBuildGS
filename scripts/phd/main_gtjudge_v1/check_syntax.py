"""Parse only new task scripts and the copied r25 Python files; no bytecode writes."""
import ast
from common import *

cfg()
paths=[p for root in [R/'scripts/phd/main_gtjudge_v1',R/'src/phd/forks/GeoGS-conf-guided-v1-r25']
       for p in root.rglob('*.py')]
for p in paths:ast.parse(p.read_text(),filename=str(p))
dump(D/'tables/syntax.json',dict(at=now(),status='PASS',files=len(paths),scientific_verdict=None))
print('SYNTAX_PASS',len(paths))
