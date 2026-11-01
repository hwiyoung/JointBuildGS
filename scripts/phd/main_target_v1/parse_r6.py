import ast
from common import *
files=list((REPO/'scripts/phd/main_target_v1').glob('*r6.py'))+list((REPO/'src/phd/forks/GeoGS-conf-guided-v1-r20').rglob('*.py'))
for p in files:ast.parse(p.read_text())
print('CONTAINER_PYTHON_PARSE_PASS',len(files),flush=True)
